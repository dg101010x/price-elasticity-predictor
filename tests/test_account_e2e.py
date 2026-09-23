"""
End to end: sign up, confirm, create an account, upload a CSV, get an
estimate -- through the real app, over HTTP, against real PostgREST and
Postgres with the real migration (tests/supabase_gateway.py).

These are the acceptance criteria, as tests:

  * a new user can sign up, create an account, upload, and see their own
    elasticity with a CI and R^2
  * the number is computed from *their* data: two different synthetic
    businesses come back with different, correct answers, and each stored
    estimate is reproduced exactly from that account's stored observations
  * a second account cannot read the first account's data sources,
    observations, runs or insights -- checked with the second user's real
    token against the Data API, not just through this app's routes

Runs once with the current sb_publishable_/sb_secret_ keys and once with
legacy JWT keys. Skips without Postgres server binaries or PostgREST.
"""

from __future__ import annotations

import gzip
import json
import os
import time
from datetime import date

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from src import stats_engine
from src.account import config, ingest, session, supabase
from src.api import app
from tests.supabase_gateway import JWT_SECRET, start_fake_supabase
from tests.synthetic_sales import COFFEE_ROASTER, GIFT_SHOP, make_sales_csv

pytest.importorskip("psycopg", reason="psycopg is not installed")

PASSWORD = "correct horse battery staple"
GIFT_CSV = make_sales_csv(GIFT_SHOP, seed=1)
COFFEE_CSV = make_sales_csv(COFFEE_ROASTER, seed=2, daily=True,
                            headers=("Date", "Item Code", "Item Name", "Department", "Price", "Qty"))

ENV_KEYS = ("NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
            "PSL_INSECURE_COOKIES", "GEMINI_API_KEY")


@pytest.fixture(scope="module", params=["sb_ keys", "legacy JWT keys"])
def supa(request):
    fake, reason = start_fake_supabase(confirm_email=True, legacy_keys=request.param == "legacy JWT keys")
    if fake is None:
        pytest.skip(reason)
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    os.environ.update({
        "NEXT_PUBLIC_SUPABASE_URL": fake.url,
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": fake.anon_key,
        "SUPABASE_SERVICE_ROLE_KEY": fake.service_key,
        "PSL_INSECURE_COOKIES": "1",          # TestClient speaks plain http
    })
    os.environ.pop("GEMINI_API_KEY", None)
    _reset()
    yield fake
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _reset()
    fake.stop()
    fake.db.stop()


def _reset():
    config.reset()
    supabase.reset()
    session.clear_caches()


def _sign_up(client: TestClient, fake, email: str) -> None:
    r = client.post("/api/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["confirm_email"] is True
    fake.confirm(email)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text


def _upload(client: TestClient, csv_bytes: bytes, filename: str, mapping: dict | None = None,
            expect: int = 200) -> dict:
    body = gzip.compress(csv_bytes)
    if mapping is None:
        proposal = client.post("/api/uploads/inspect", content=body)
        assert proposal.status_code == 200, proposal.text
        mapping = proposal.json()["mapping"]
    r = client.post("/api/uploads", content=body,
                    params={"filename": filename, "mapping": json.dumps(mapping), "currency": "USD"})
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture(scope="module")
def shops(supa):
    """Two businesses, fully onboarded, one upload each."""
    out = {}
    for label, name, csv_bytes, filename in (("a", "Juniper Gifts", GIFT_CSV, "gift-shop.csv"),
                                             ("b", "Ridge Coffee", COFFEE_CSV, "roaster sales.csv")):
        client = TestClient(app)
        email = f"owner-{label}@example.com"
        _sign_up(client, supa, email)
        r = client.post("/api/account", json={"name": name})
        assert r.status_code == 200, r.text
        result = _upload(client, csv_bytes, filename)
        out[label] = {"client": client, "email": email, "name": name, "account": r.json()["account"],
                      "upload": result, "csv": csv_bytes}
    return out


def _token(client: TestClient) -> str:
    return client.cookies.get(session.ACCESS_COOKIE)


# ------------------------------------------------------------------ sign-up --

def test_login_is_refused_until_the_email_is_confirmed(supa):
    client = TestClient(app)
    r = client.post("/api/auth/signup", json={"email": "slow@example.com", "password": PASSWORD})
    assert r.json() == {"signed_in": False, "confirm_email": True,
                        "message": "Check slow@example.com for a confirmation link, then sign in."}
    r = client.post("/api/auth/login", json={"email": "slow@example.com", "password": PASSWORD})
    assert r.status_code == 400
    assert "Confirm your email" in r.json()["detail"]
    assert client.get("/api/me").json()["user"] is None


def test_wrong_password_is_refused_without_saying_which_part_was_wrong(supa, shops):
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"email": shops["a"]["email"], "password": "nope-nope"})
    assert r.status_code == 400
    assert r.json()["detail"] == "That email and password don't match an account."


def test_signed_in_user_has_an_owner_account(supa, shops):
    me = shops["a"]["client"].get("/api/me").json()
    assert me["user"]["email"] == shops["a"]["email"]
    assert me["account"] == {"id": shops["a"]["account"]["id"], "name": "Juniper Gifts", "role": "owner"}


def test_onboarding_twice_does_not_make_a_second_account(supa, shops):
    r = shops["a"]["client"].post("/api/account", json={"name": "Another name"})
    assert r.json()["account"]["id"] == shops["a"]["account"]["id"]


def test_session_cookies_are_httponly_and_carry_no_server_key(supa, shops):
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"email": shops["b"]["email"], "password": PASSWORD})
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for c in cookies:
        assert "HttpOnly" in c and "SameSite=lax" in c
        assert supa.service_key not in c
    for path in ("/api/me", "/api/account/estimates", "/api/account/benchmarks"):
        assert supa.service_key not in client.get(path).text


# ----------------------------------------------------------- the estimates --

def test_upload_produces_an_estimate_with_a_real_interval_and_r_squared(supa, shops):
    upload = shops["a"]["upload"]
    assert upload["data_source"]["status"] == "ready"
    est = shops["a"]["client"].get("/api/account/estimates").json()
    overall = est["overall"]
    assert overall["ci_low"] < overall["elasticity"] < overall["ci_high"]
    assert 0 < overall["r_squared"] < 1
    assert overall["n_observations"] > 1000
    assert overall["advice"]["headline"] and overall["evidence"]["fit"]
    assert est["data_source"]["filename"] == "gift-shop.csv"


def test_the_numbers_are_exactly_what_the_shared_engine_fits(supa, shops):
    """Same file through ingest.prepare directly -> identical six-field runs."""
    for label in ("a", "b"):
        csv_bytes = shops[label]["csv"]
        proposal = ingest.inspect(csv_bytes)
        expected = ingest.prepare(csv_bytes, proposal["mapping"], proposal["date_order"]).runs
        stored = [{k: r[k] for k in ("category", "coefficient", "ci_low", "ci_high", "r_squared",
                                     "n_observations")} for r in shops[label]["upload"]["runs"]]
        assert sorted(stored, key=str) == sorted(expected, key=str)


def test_two_businesses_get_their_own_different_answers(supa, shops):
    """The gift shop was simulated around -1.6 to -2.2, the roaster around -0.5."""
    a = shops["a"]["client"].get("/api/account/estimates").json()["overall"]
    b = shops["b"]["client"].get("/api/account/estimates").json()["overall"]
    assert a["elasticity"] < -1.3 and b["elasticity"] > -0.8
    assert a["ci_high"] < b["ci_low"], "the intervals shouldn't even overlap"
    assert a["advice"]["raising_price"] == "loses revenue"
    assert b["advice"]["raising_price"] == "gains revenue"


def test_each_category_recovers_its_simulated_elasticity(supa, shops):
    est = shops["a"]["client"].get("/api/account/estimates").json()
    by_cat = {row["category"]: row for row in est["by_category"]}
    for name, (_, truth) in GIFT_SHOP.items():
        if name in by_cat:
            assert by_cat[name]["ci_low"] - 0.15 < truth < by_cat[name]["ci_high"] + 0.15, (name, by_cat[name])


def test_a_small_category_is_excluded_and_says_why(supa, shops):
    est = shops["a"]["client"].get("/api/account/estimates").json()
    excluded = {e["category"]: e["reason"] for e in est["excluded_categories"]}
    assert "Greeting Cards" in excluded
    assert "insufficient data" in excluded["Greeting Cards"]
    assert "Greeting Cards" not in {r["category"] for r in est["by_category"]}


def test_every_stored_estimate_is_reproducible_from_stored_observations(supa, shops):
    """'Provably computed from their data': refit from the table, compare."""
    import pandas as pd
    for label in ("a", "b"):
        account_id = shops[label]["account"]["id"]
        with supa.as_role("service_role") as cur:
            cur.execute("select product_key, category, week_start, units_sold, price "
                        "from public.sales_observations where account_id = %s", (account_id,))
            rows = cur.fetchall()
            cur.execute("select category, coefficient, ci_low, ci_high, r_squared, n_observations "
                        "from public.elasticity_runs where account_id = %s", (account_id,))
            stored = {r[0]: [float(x) for x in r[1:5]] + [int(r[5])] for r in cur.fetchall()}
        panel = pd.DataFrame(rows, columns=["product", "category", "week", "qty", "price"])
        panel["qty"] = panel["qty"].astype(float)
        panel["price"] = panel["price"].astype(float)
        panel["week"] = pd.to_datetime(panel["week"])
        panel = panel.sort_values(["product", "category", "week"]).reset_index(drop=True)
        refit = stats_engine.fit_catalogue(panel, catch_all={ingest.UNCATEGORIZED: "x"})
        rebuilt = {None: refit["overall"], **{r["category"]: r for r in refit["by_category"]}}
        assert set(rebuilt) == set(stored)
        for cat, fit in rebuilt.items():
            assert stored[cat] == [fit["elasticity"], fit["ci_low"], fit["ci_high"], fit["r_squared"],
                                   fit["n_observations"]], cat


def test_catalog_and_benchmarks_use_the_accounts_own_data(supa, shops):
    client = shops["a"]["client"]
    catalog = client.get("/api/account/catalog").json()
    assert len(catalog["products"]) == sum(n for n, _ in GIFT_SHOP.values())
    assert catalog["currency"] == "USD"
    assert "Greeting Cards" in catalog["excluded"]
    bench = client.get("/api/account/benchmarks").json()
    overall = client.get("/api/account/estimates").json()["overall"]
    assert bench["available"] is True
    assert bench["this_catalogue"]["market"] == "Juniper Gifts"
    assert bench["this_catalogue"]["elasticity"] == overall["elasticity"]
    assert len(bench["benchmarks"]) >= 10, "the 13 public markets stay alongside"


# ---------------------------------------------------------------- isolation --

@pytest.mark.parametrize("table", ["data_sources", "sales_observations", "elasticity_runs", "insights",
                                   "accounts", "account_memberships"])
def test_second_account_cannot_read_the_first_over_the_data_api(supa, shops, table):
    """B's real access token, straight at /rest/v1 -- no app code in the way."""
    column = "id" if table == "accounts" else "account_id"

    def rows_seen_by(label: str) -> list:
        r = httpx.get(f"{supa.url}/rest/v1/{table}", trust_env=False,
                      params={column: f"eq.{shops['a']['account']['id']}"},
                      headers={"apikey": supa.anon_key,
                               "Authorization": f"Bearer {_token(shops[label]['client'])}"})
        assert r.status_code == 200, r.text
        return r.json()

    if table != "insights":        # A has no insights yet in this module
        assert rows_seen_by("a"), "control: the owner's own token does see these rows"
    assert rows_seen_by("b") == []


def test_second_account_cannot_download_the_first_accounts_file(supa, shops):
    path = shops["a"]["upload"]["data_source"]["storage_path"]
    sb = supabase.client(config.settings())
    assert sb.download("sales-uploads", path, _token(shops["a"]["client"])) == GIFT_CSV
    with pytest.raises(supabase.SupabaseError):
        sb.download("sales-uploads", path, _token(shops["b"]["client"]))


def test_uploads_are_written_to_storage_as_the_user_not_the_server(supa, shops):
    """Storage RLS only protects anything if the upload carries the user's JWT."""
    uploads = [h for m, p, h in supa.requests if m == "POST" and p.startswith("/storage/v1/object/")]
    assert uploads
    for headers in uploads:
        claims = jwt.decode(headers["authorization"][7:], JWT_SECRET, algorithms=["HS256"],
                            audience="authenticated")
        assert claims["role"] == "authenticated"


def test_signed_out_callers_get_nothing(supa, shops):
    client = TestClient(app)
    for path in ("/api/account/estimates", "/api/account/catalog", "/api/uploads"):
        assert client.get(path).status_code == 401


def test_cross_site_posts_are_refused(supa, shops):
    r = shops["a"]["client"].post("/api/account", json={"name": "x"},
                                  headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


# ------------------------------------------------------------- permissions --

def test_a_plain_member_can_read_but_not_upload(supa, shops):
    client = TestClient(app)
    email = "member-a@example.com"
    _sign_up(client, supa, email)
    with supa.db.connect() as conn:
        uid = conn.execute("select id from auth.users where email = %s", (email,)).fetchone()[0]
        conn.execute("insert into public.account_memberships (account_id, user_id, role) values (%s, %s, 'member')",
                     (shops["a"]["account"]["id"], uid))
    assert client.get("/api/me").json()["account"]["role"] == "member"
    assert client.get("/api/account/estimates").status_code == 200
    r = client.post("/api/uploads", content=gzip.compress(GIFT_CSV),
                    params={"filename": "x.csv", "mapping": json.dumps(ingest.inspect(GIFT_CSV)["mapping"])})
    assert r.status_code == 403
    assert client.get("/api/uploads").json()["can_upload"] is False


# ------------------------------------------------------------ failure paths --

def test_an_unusable_file_is_recorded_as_failed_with_a_reason(supa, shops):
    client = shops["b"]["client"]
    flat = make_sales_csv({"Beans": (20, -1.0)}, seed=9).decode().splitlines()
    header, rows = flat[0], flat[1:]
    # Same price every week for every product: nothing to learn from.
    fixed = [",".join(r.split(",")[:4] + ["10.00"] + r.split(",")[5:]) for r in rows]
    result = _upload(client, ("\n".join([header] + fixed) + "\n").encode(), "flat.csv")
    assert result["data_source"]["status"] == "failed"
    assert "Not enough price movement" in result["data_source"]["status_reason"]
    history = client.get("/api/uploads").json()["uploads"]
    assert history[0]["status"] == "failed" and history[0]["status_reason"]
    # The dashboard keeps showing the last good upload.
    assert client.get("/api/account/estimates").json()["data_source"]["filename"] == "roaster-sales.csv"


def test_a_wrong_mapping_is_refused_before_anything_is_stored(supa, shops):
    client = shops["b"]["client"]
    before = len(client.get("/api/uploads").json()["uploads"])
    r = client.post("/api/uploads", content=gzip.compress(COFFEE_CSV),
                    params={"filename": "x.csv", "mapping": json.dumps({"product_key": "Item Code"})})
    assert r.status_code == 422
    assert "Choose a column for" in r.json()["detail"]
    assert len(client.get("/api/uploads").json()["uploads"]) == before


def test_ambiguous_dates_are_flagged_for_the_user_to_settle(supa, shops):
    csv_bytes = make_sales_csv({"Beans": (16, -1.0)}, seed=4, weeks=10, date_format="%m/%d/%Y",
                               start=date(2024, 1, 1))
    lines = csv_bytes.decode().splitlines()
    # Keep only weeks where both numbers are 12 or under, so nothing in the
    # file says which one is the day.
    early = [l for l in lines[1:] if l.split(",")[0].split("/")[1] in {f"{d:02d}" for d in range(1, 13)}]
    proposal = shops["b"]["client"].post(
        "/api/uploads/inspect", content=gzip.compress(("\n".join([lines[0]] + early) + "\n").encode())).json()
    assert proposal["date_order_certain"] is False
    assert proposal["needs_confirmation"] is True


def test_headers_with_no_known_alias_ask_for_confirmation(supa, shops):
    odd = b"When,Thing,Cost,How many\n2024-01-01,A,1.00,3\n2024-01-08,A,1.10,2\n"
    proposal = shops["b"]["client"].post("/api/uploads/inspect", content=odd).json()
    assert proposal["needs_confirmation"] is True
    fields = {f["field"]: f for f in proposal["fields"]}
    assert fields["units"]["confident"] is False


# ------------------------------------------------------------------ session --

def test_an_expired_access_token_is_refreshed_transparently(supa, shops):
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"email": shops["a"]["email"], "password": PASSWORD})
    assert r.status_code == 200
    stale = jwt.decode(client.cookies.get(session.ACCESS_COOKIE), JWT_SECRET, algorithms=["HS256"],
                       audience="authenticated")
    stale["exp"] = int(time.time()) - 60
    client.cookies.set(session.ACCESS_COOKIE, jwt.encode(stale, JWT_SECRET, algorithm="HS256"))
    r = client.get("/api/me")
    assert r.json()["user"]["email"] == shops["a"]["email"]
    assert any(c.startswith(f"{session.ACCESS_COOKIE}=") for c in r.headers.get_list("set-cookie"))


def test_logout_ends_the_session_at_supabase_too(supa, shops):
    client = TestClient(app)
    client.post("/api/auth/login", json={"email": shops["b"]["email"], "password": PASSWORD})
    token = client.cookies.get(session.ACCESS_COOKIE)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/me").json()["user"] is None
    with pytest.raises(supabase.SupabaseError):
        supabase.client(config.settings()).get_user(token)
