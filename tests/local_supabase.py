"""
A throwaway Postgres with the Supabase migration applied, for tests.

Starts a private cluster on a free localhost port, loads
tests/fixtures/supabase_stub.sql (the roles and the auth/storage schemas a
hosted project provides) and then every file in supabase/migrations/ in
order -- the same files `supabase db push` would apply.

Needs the Postgres server binaries (initdb, pg_ctl); callers skip when
find_pg_bin() returns None. Postgres refuses to run as root, so when the
tests do, the cluster is run as the `postgres` system user instead.
"""

from __future__ import annotations

import glob
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB_SQL = ROOT / "tests" / "fixtures" / "supabase_stub.sql"
LEGACY_GRANTS_SQL = ROOT / "tests" / "fixtures" / "supabase_legacy_grants.sql"
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))


def find_pg_bin() -> str | None:
    env = os.environ.get("PG_BIN")
    if env and Path(env, "initdb").exists():
        return env
    on_path = shutil.which("initdb")
    if on_path:
        return str(Path(on_path).parent)
    candidates = sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True)
    for c in candidates:
        if Path(c, "initdb").exists() and Path(c, "pg_ctl").exists():
            return c
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalPostgres:
    def __init__(self, pg_bin: str):
        self.pg_bin = pg_bin
        self.port = free_port()
        self.tmp = tempfile.mkdtemp(prefix="psl-pg-")
        self.data_dir = os.path.join(self.tmp, "data")
        self.as_root = hasattr(os, "geteuid") and os.geteuid() == 0
        self.superuser = "postgres"

    # -- process control ----------------------------------------------------
    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        cmd = list(args)
        if self.as_root:
            cmd = ["runuser", "-u", "postgres", "--"] + cmd
        return subprocess.run(cmd, check=check, capture_output=True, text=True)

    def start(self) -> "LocalPostgres":
        if self.as_root:
            shutil.chown(self.tmp, user="postgres")
        self._run(os.path.join(self.pg_bin, "initdb"), "-D", self.data_dir,
                  "-U", self.superuser, "--auth=trust", "-E", "UTF8", "--no-sync")
        self._run(os.path.join(self.pg_bin, "pg_ctl"), "-D", self.data_dir, "-w",
                  "-l", os.path.join(self.tmp, "pg.log"),
                  "-o", f"-p {self.port} -k {self.tmp} -c listen_addresses=127.0.0.1 -c fsync=off",
                  "start")
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with self.connect():
                    break
            except Exception:
                time.sleep(0.2)
        return self

    def stop(self) -> None:
        self._run(os.path.join(self.pg_bin, "pg_ctl"), "-D", self.data_dir, "-m", "immediate",
                  "stop", check=False)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- access -------------------------------------------------------------
    @property
    def dsn(self) -> str:
        return f"host=127.0.0.1 port={self.port} user={self.superuser} dbname=postgres"

    def uri(self, user: str = "postgres") -> str:
        return f"postgresql://{user}@127.0.0.1:{self.port}/postgres"

    def connect(self, autocommit: bool = True):
        import psycopg
        return psycopg.connect(self.dsn, autocommit=autocommit)

    def apply_schema(self, legacy_grants: bool = False) -> None:
        with self.connect() as conn:
            conn.execute(STUB_SQL.read_text())
            if legacy_grants:
                conn.execute(LEGACY_GRANTS_SQL.read_text())
            for migration in MIGRATIONS:
                conn.execute(migration.read_text())


def start_database(legacy_grants: bool = False) -> LocalPostgres | None:
    """`legacy_grants` reproduces projects created before 2026-05-30, where
    every new public table was granted to anon and authenticated."""
    pg_bin = find_pg_bin()
    if pg_bin is None:
        return None
    db = LocalPostgres(pg_bin).start()
    db.apply_schema(legacy_grants=legacy_grants)
    return db
