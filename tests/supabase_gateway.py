"""
A local stand-in for a hosted Supabase project, for end-to-end tests.

What's real and what isn't:

  real      Postgres, with the actual migration and RLS policies
            (tests/local_supabase.py), and PostgREST itself -- the same
            server Supabase runs behind /rest/v1 -- verifying JWTs and
            switching into the anon / authenticated / service_role roles.
  emulated  Auth (/auth/v1) and Storage (/storage/v1), implemented here to
            the documented request/response shapes. Storage writes its
            object rows into storage.objects *as the caller*, so the
            bucket's RLS policies decide uploads exactly as they would in
            Supabase; only the byte storage is a dict.
  gateway   the key handling Supabase's API gateway does: `apikey` must be
            one of the project's keys; with no user JWT, the key's own role
            is used.

Keys are the current sb_publishable_ / sb_secret_ kind by default, or the
legacy anon / service_role JWTs with legacy_keys=True, so the app's client
is exercised against both.

PostgREST is found via $POSTGREST_BIN, `postgrest` on PATH, or .tools/postgrest.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import httpx
import jwt
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from tests.local_supabase import ROOT, LocalPostgres, free_port, start_database

JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"
ACCESS_TTL = 3600


def find_postgrest() -> str | None:
    env = os.environ.get("POSTGREST_BIN")
    if env and Path(env).exists():
        return env
    on_path = shutil.which("postgrest")
    if on_path:
        return on_path
    local = ROOT / ".tools" / "postgrest"
    return str(local) if local.exists() else None


def _sign(claims: dict) -> str:
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


class FakeSupabase:
    def __init__(self, db: LocalPostgres, postgrest_bin: str, confirm_email: bool = True,
                 legacy_keys: bool = False):
        self.db = db
        self.postgrest_bin = postgrest_bin
        self.confirm_email = confirm_email
        self.rest_port = free_port()
        self.port = free_port()
        now = int(time.time())
        if legacy_keys:
            self.anon_key = _sign({"role": "anon", "iss": "supabase", "iat": now, "exp": now + 10**8})
            self.service_key = _sign({"role": "service_role", "iss": "supabase", "iat": now, "exp": now + 10**8})
        else:
            self.anon_key = "sb_publishable_" + secrets.token_urlsafe(24)
            self.service_key = "sb_secret_" + secrets.token_urlsafe(24)
        self._role_jwts = {
            self.anon_key: _sign({"role": "anon", "iat": now, "exp": now + 10**8}),
            self.service_key: _sign({"role": "service_role", "iat": now, "exp": now + 10**8}),
        }
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.refresh_tokens: dict[str, dict] = {}          # token -> {user_id, session_id, revoked}
        self.revoked_sessions: set[str] = set()
        self.requests: list[tuple[str, str, dict]] = []    # (method, path, headers) for assertions
        self._proc: subprocess.Popen | None = None
        self._server: uvicorn.Server | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # ------------------------------------------------------------ lifecycle --
    def start(self) -> "FakeSupabase":
        env = dict(os.environ,
                   PGRST_DB_URI=self.db.uri("authenticator"),
                   PGRST_DB_SCHEMAS="public",
                   PGRST_DB_ANON_ROLE="anon",
                   PGRST_JWT_SECRET=JWT_SECRET,
                   PGRST_DB_MAX_ROWS="1000",
                   PGRST_SERVER_HOST="127.0.0.1",
                   PGRST_SERVER_PORT=str(self.rest_port),
                   PGRST_LOG_LEVEL="crit")
        self._proc = subprocess.Popen([self.postgrest_bin], env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        self._wait(f"http://127.0.0.1:{self.rest_port}/")

        config = uvicorn.Config(self._app(), host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        threading.Thread(target=self._server.run, daemon=True).start()
        self._wait(f"{self.url}/health")
        return self

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    @staticmethod
    def _wait(url: str) -> None:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                httpx.get(url, timeout=1, trust_env=False)
                return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise RuntimeError(f"{url} did not come up")

    # -------------------------------------------------------------- helpers --
    def confirm(self, email: str) -> None:
        """What clicking the confirmation link does."""
        with self.db.connect() as conn:
            conn.execute("update auth.users set email_confirmed_at = now() where email = %s", (email,))

    @contextmanager
    def as_role(self, role: str, claims: dict | None = None):
        with self.db.connect(autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(f"set local role {role}")
                if claims:
                    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
                yield cur
            conn.commit()

    def _session_for(self, user: dict) -> dict:
        session_id = str(uuid.uuid4())
        now = int(time.time())
        access = _sign({"sub": user["id"], "email": user["email"], "role": "authenticated",
                        "aud": "authenticated", "session_id": session_id, "iat": now, "exp": now + ACCESS_TTL})
        refresh = secrets.token_urlsafe(18)
        self.refresh_tokens[refresh] = {"user_id": user["id"], "session_id": session_id, "revoked": False}
        return {"access_token": access, "token_type": "bearer", "expires_in": ACCESS_TTL,
                "expires_at": now + ACCESS_TTL, "refresh_token": refresh, "user": user}

    def _user(self, user_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("select id, email, email_confirmed_at, created_at from auth.users where id = %s",
                               (user_id,)).fetchone()
        if not row:
            return None
        return {"id": str(row[0]), "aud": "authenticated", "role": "authenticated", "email": row[1],
                "email_confirmed_at": row[2].isoformat() if row[2] else None,
                "created_at": row[3].isoformat(), "identities": [{"provider": "email"}]}

    def _verify(self, request: Request) -> dict | None:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return None
        token = header[7:]
        try:
            claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError:
            return None
        if claims.get("session_id") in self.revoked_sessions:
            return None
        return claims

    # ------------------------------------------------------------------ app --
    def _app(self) -> FastAPI:
        app = FastAPI()
        gw = self

        def gotrue_error(status: int, code: str, msg: str) -> JSONResponse:
            return JSONResponse({"code": status, "error_code": code, "msg": msg}, status_code=status)

        @app.middleware("http")
        async def gateway(request: Request, call_next):
            gw.requests.append((request.method, request.url.path, dict(request.headers)))
            if request.url.path != "/health" and request.headers.get("apikey") not in gw._role_jwts:
                return JSONResponse({"message": "Invalid API key"}, status_code=401)
            authz = request.headers.get("authorization")
            if authz and authz.startswith("Bearer sb_") and authz[7:] != request.headers.get("apikey"):
                return JSONResponse({"message": "Invalid API key"}, status_code=401)
            return await call_next(request)

        @app.get("/health")
        def health():
            return {"ok": True}

        # -- auth -----------------------------------------------------------
        @app.post("/auth/v1/signup")
        async def signup(request: Request):
            body = await request.json()
            email, password = body.get("email", "").lower(), body.get("password", "")
            if len(password) < 6:
                return JSONResponse({"code": 422, "error_code": "weak_password",
                                     "msg": "Password should be at least 6 characters.",
                                     "weak_password": {"reasons": ["length"]}}, status_code=422)
            with gw.db.connect() as conn:
                existing = conn.execute("select id from auth.users where email = %s", (email,)).fetchone()
                if existing:
                    if not gw.confirm_email:
                        return gotrue_error(422, "user_already_exists", "User already registered")
                    return {"id": str(uuid.uuid4()), "email": email, "identities": []}
                uid = conn.execute(
                    "insert into auth.users (email, encrypted_password, email_confirmed_at) "
                    "values (%s, %s, %s) returning id",
                    (email, hashlib.sha256(password.encode()).hexdigest(),
                     None if gw.confirm_email else time.strftime("%Y-%m-%d %H:%M:%S"))).fetchone()[0]
            user = gw._user(str(uid))
            return user if gw.confirm_email else gw._session_for(user)

        @app.post("/auth/v1/token")
        async def token(request: Request, grant_type: str):
            body = await request.json()
            if grant_type == "password":
                with gw.db.connect() as conn:
                    row = conn.execute("select id, encrypted_password, email_confirmed_at from auth.users "
                                       "where email = %s", (body.get("email", "").lower(),)).fetchone()
                if not row or row[1] != hashlib.sha256(body.get("password", "").encode()).hexdigest():
                    return gotrue_error(400, "invalid_credentials", "Invalid login credentials")
                if row[2] is None:
                    return gotrue_error(400, "email_not_confirmed", "Email not confirmed")
                return gw._session_for(gw._user(str(row[0])))
            if grant_type == "refresh_token":
                entry = gw.refresh_tokens.get(body.get("refresh_token", ""))
                if not entry or entry["revoked"] or entry["session_id"] in gw.revoked_sessions:
                    return gotrue_error(400, "refresh_token_not_found", "Invalid Refresh Token: Refresh Token Not Found")
                entry["revoked"] = True
                return gw._session_for(gw._user(entry["user_id"]))
            return gotrue_error(400, "unsupported_grant_type", "unsupported grant type")

        @app.get("/auth/v1/user")
        def user(request: Request):
            claims = gw._verify(request)
            if not claims:
                return gotrue_error(403, "bad_jwt", "invalid JWT: unable to parse or verify signature")
            found = gw._user(claims["sub"])
            return found or gotrue_error(403, "user_not_found", "User from sub claim in JWT does not exist")

        @app.post("/auth/v1/logout")
        def logout(request: Request):
            claims = gw._verify(request)
            if not claims:
                return gotrue_error(403, "bad_jwt", "invalid JWT")
            gw.revoked_sessions.add(claims["session_id"])
            return Response(status_code=204)

        # -- storage ----------------------------------------------------------
        def storage_error(status: str, error: str, message: str) -> JSONResponse:
            return JSONResponse({"statusCode": status, "error": error, "message": message}, status_code=400)

        def storage_role(request: Request):
            claims = gw._verify(request)
            if claims:
                return "authenticated", claims
            if request.headers.get("apikey") == gw.service_key:
                return "service_role", None
            return None, None

        @app.post("/storage/v1/object/{bucket}/{path:path}")
        async def upload(bucket: str, path: str, request: Request):
            role, claims = storage_role(request)
            if role is None:
                return storage_error("403", "Unauthorized", "invalid JWT")
            data = await request.body()
            content_type = request.headers.get("content-type", "").split(";")[0]
            with gw.db.connect() as conn:
                b = conn.execute("select file_size_limit, allowed_mime_types from storage.buckets where id = %s",
                                 (bucket,)).fetchone()
            if not b:
                return storage_error("404", "Bucket not found", "Bucket not found")
            if b[0] and len(data) > b[0]:
                return storage_error("413", "Payload too large", "The object exceeded the maximum allowed size")
            if b[1] and content_type not in b[1]:
                return storage_error("415", "invalid_mime_type", f"mime type {content_type} is not supported")
            import psycopg
            try:
                with gw.as_role(role, claims) as cur:
                    cur.execute("insert into storage.objects (bucket_id, name, owner, owner_id, metadata) "
                                "values (%s, %s, %s, %s, %s) returning id",
                                (bucket, path, claims["sub"] if claims else None,
                                 claims["sub"] if claims else None,
                                 json.dumps({"size": len(data), "mimetype": content_type})))
                    object_id = cur.fetchone()[0]
            except psycopg.errors.UniqueViolation:
                return storage_error("409", "Duplicate", "The resource already exists")
            except psycopg.errors.InsufficientPrivilege:
                return storage_error("403", "Unauthorized", "new row violates row-level security policy")
            gw.objects[(bucket, path)] = (data, content_type)
            return {"Key": f"{bucket}/{path}", "Id": str(object_id)}

        @app.get("/storage/v1/object/authenticated/{bucket}/{path:path}")
        def download(bucket: str, path: str, request: Request):
            role, claims = storage_role(request)
            if role is None:
                return storage_error("403", "Unauthorized", "invalid JWT")
            with gw.as_role(role, claims) as cur:
                cur.execute("select 1 from storage.objects where bucket_id = %s and name = %s", (bucket, path))
                visible = cur.fetchone() is not None
            if not visible or (bucket, path) not in gw.objects:
                return storage_error("404", "not_found", "Object not found")
            data, content_type = gw.objects[(bucket, path)]
            return Response(data, media_type=content_type)

        # -- data api ---------------------------------------------------------
        rest = httpx.AsyncClient(base_url=f"http://127.0.0.1:{gw.rest_port}", trust_env=False, timeout=30)

        @app.api_route("/rest/v1/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
        async def data_api(path: str, request: Request):
            apikey = request.headers["apikey"]
            authz = request.headers.get("authorization")
            if not authz or authz[7:] == apikey:
                authz = f"Bearer {gw._role_jwts[apikey]}"
            headers = {"Authorization": authz}
            for name in ("content-type", "prefer", "accept", "range"):
                if name in request.headers:
                    headers[name] = request.headers[name]
            upstream = await rest.request(request.method, f"/{path}", params=request.query_params,
                                          content=await request.body(), headers=headers)
            return Response(upstream.content, status_code=upstream.status_code,
                            media_type=upstream.headers.get("content-type"))

        return app


def start_fake_supabase(**kwargs) -> tuple[FakeSupabase | None, str]:
    """Returns (instance, "") or (None, reason-to-skip)."""
    postgrest = find_postgrest()
    if postgrest is None:
        return None, "PostgREST binary not found (set POSTGREST_BIN or put it at .tools/postgrest)"
    db = start_database()
    if db is None:
        return None, "no Postgres server binaries available"
    try:
        return FakeSupabase(db, postgrest, **kwargs).start(), ""
    except Exception:
        db.stop()
        raise
