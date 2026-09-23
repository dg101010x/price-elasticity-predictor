"""
Row-level security, checked by what each role actually gets back.

A policy mistake rarely raises: an UPDATE with no matching SELECT policy
affects zero rows, a missing policy returns an empty list, and a too-broad
one returns someone else's data without complaint. So every test here
asserts on result sets and row counts, run as the `authenticated` role with
the same JWT claims PostgREST would set, against the real migration in
supabase/migrations/.

Two accounts, A and B, each with an owner; A also has a plain `member`.
Everything runs twice: under Supabase's current default (new tables granted
to nobody, since 2026-05-30) and its old one (granted to everyone), since a
project could have been created under either. Skips when no Postgres server
binaries are available.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager

import pytest

from tests.local_supabase import start_database

psycopg = pytest.importorskip("psycopg", reason="psycopg is not installed")


@pytest.fixture(scope="module", params=["current-default-grants", "legacy-default-grants"])
def db(request):
    database = start_database(legacy_grants=request.param == "legacy-default-grants")
    if database is None:
        pytest.skip("no Postgres server binaries available")
    yield database
    database.stop()


@pytest.fixture(scope="module")
def world(db):
    """Two tenants with data in every table, created the way the app does:
    onboarding through create_account(), uploads as the member, computed
    rows by the service role."""
    users = {name: uuid.uuid4() for name in ("owner_a", "member_a", "owner_b")}
    with db.connect() as conn:
        for name, uid in users.items():
            conn.execute("insert into auth.users (id, email, encrypted_password) values (%s, %s, 'x')",
                         (uid, f"{name}@example.com"))

    accounts = {}
    for owner, label in (("owner_a", "a"), ("owner_b", "b")):
        with as_user(db, users[owner]) as cur:
            cur.execute("select public.create_account(%s)", (f"Shop {label.upper()}",))
            accounts[label] = cur.fetchone()[0]

    with db.connect() as conn:
        conn.execute("insert into public.account_memberships (account_id, user_id, role) "
                     "values (%s, %s, 'member')", (accounts["a"], users["member_a"]))

    runs = {}
    for label, owner in (("a", "owner_a"), ("b", "owner_b")):
        with as_user(db, users[owner]) as cur:
            cur.execute(
                "insert into public.data_sources (account_id, filename, storage_path, uploaded_by) "
                "values (%s, 'sales.csv', %s, %s) returning id",
                (accounts[label], f"{accounts[label]}/x-sales.csv", users[owner]))
            source = cur.fetchone()[0]
        with as_service_role(db) as cur:
            cur.execute(
                "insert into public.sales_observations (account_id, data_source_id, product_key, "
                "week_start, price, units_sold) values (%s, %s, 'SKU1', '2025-01-06', 9.99, 12)",
                (accounts[label], source))
            cur.execute(
                "insert into public.elasticity_runs (account_id, data_source_id, category, coefficient, "
                "ci_low, ci_high, r_squared, n_observations) values (%s, %s, null, -1.2, -1.5, -0.9, 0.2, 800) "
                "returning id", (accounts[label], source))
            run = cur.fetchone()[0]
            cur.execute("insert into public.insights (account_id, elasticity_run_id, body, model) "
                        "values (%s, %s, 'body', 'template')", (accounts[label], run))
            cur.execute("update public.data_sources set status = 'ready' where id = %s", (source,))
        runs[label] = {"source": source, "run": run}

    return {"users": users, "accounts": accounts, "runs": runs}


@contextmanager
def as_user(db, user_id):
    """One transaction as `authenticated` with this user's JWT claims."""
    with db.connect(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role authenticated")
            cur.execute("select set_config('request.jwt.claims', %s, true)",
                        (json.dumps({"sub": str(user_id), "role": "authenticated"}),))
            yield cur
        conn.commit()


@contextmanager
def as_anon(db):
    with db.connect(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role anon")
            yield cur
        conn.rollback()


@contextmanager
def as_service_role(db):
    with db.connect(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("set local role service_role")
            yield cur
        conn.commit()


TENANT_TABLES = ("data_sources", "sales_observations", "elasticity_runs", "insights")


# ------------------------------------------------------------------ reads ---

@pytest.mark.parametrize("table", TENANT_TABLES)
def test_each_owner_sees_exactly_their_own_rows(db, world, table):
    for owner, label in (("owner_a", "a"), ("owner_b", "b")):
        with as_user(db, world["users"][owner]) as cur:
            cur.execute(f"select account_id from public.{table}")
            seen = {row[0] for row in cur.fetchall()}
        assert seen == {world["accounts"][label]}, f"{owner} read {table}: {seen}"


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_a_second_account_cannot_read_the_first_accounts_rows(db, world, table):
    """The acceptance criterion, stated directly: B asks for A's rows by id."""
    with as_user(db, world["users"]["owner_b"]) as cur:
        cur.execute(f"select count(*) from public.{table} where account_id = %s", (world["accounts"]["a"],))
        assert cur.fetchone()[0] == 0


def test_a_second_account_cannot_read_the_first_account_itself(db, world):
    with as_user(db, world["users"]["owner_b"]) as cur:
        cur.execute("select id from public.accounts")
        assert [r[0] for r in cur.fetchall()] == [world["accounts"]["b"]]
        cur.execute("select account_id, user_id from public.account_memberships")
        assert {r[0] for r in cur.fetchall()} == {world["accounts"]["b"]}


def test_a_plain_member_reads_their_account(db, world):
    with as_user(db, world["users"]["member_a"]) as cur:
        cur.execute("select count(*) from public.elasticity_runs")
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from public.account_memberships")
        assert cur.fetchone()[0] == 2, "a member sees who else is on their account"


@pytest.mark.parametrize("table", TENANT_TABLES + ("accounts", "account_memberships"))
def test_signed_out_visitors_get_nothing(db, world, table):
    with as_anon(db) as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(f"select * from public.{table}")


# ----------------------------------------------------------------- writes ---

@pytest.mark.parametrize("table,sql", [
    ("elasticity_runs",
     "insert into public.elasticity_runs (account_id, data_source_id, coefficient, ci_low, ci_high, "
     "r_squared, n_observations) values (%(account)s, %(source)s, -9, -9, -9, 0.99, 1)"),
    ("sales_observations",
     "insert into public.sales_observations (account_id, data_source_id, product_key, week_start, price, "
     "units_sold) values (%(account)s, %(source)s, 'x', '2025-01-06', 1, 1)"),
    ("insights",
     "insert into public.insights (account_id, elasticity_run_id, body, model) "
     "values (%(account)s, %(run)s, 'made up', 'me')"),
])
def test_members_cannot_forge_computed_results(db, world, table, sql):
    """Estimates, observations and insights are written by the server only."""
    params = {"account": world["accounts"]["a"], "source": world["runs"]["a"]["source"],
              "run": world["runs"]["a"]["run"]}
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with as_user(db, world["users"]["owner_a"]) as cur:
            cur.execute(sql, params)


def test_members_cannot_mark_their_own_upload_ready(db, world):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with as_user(db, world["users"]["owner_a"]) as cur:
            cur.execute(
                "insert into public.data_sources (account_id, filename, storage_path, uploaded_by, status) "
                "values (%s, 'f.csv', 'p', %s, 'ready')",
                (world["accounts"]["a"], world["users"]["owner_a"]))


def test_updates_are_refused_rather_than_silently_matching_nothing(db, world):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with as_user(db, world["users"]["owner_a"]) as cur:
            cur.execute("update public.elasticity_runs set coefficient = 5")
    with as_service_role(db) as cur:
        cur.execute("select count(*) from public.elasticity_runs where coefficient = 5")
        assert cur.fetchone()[0] == 0


def test_cannot_file_an_upload_under_someone_elses_account(db, world):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with as_user(db, world["users"]["owner_b"]) as cur:
            cur.execute(
                "insert into public.data_sources (account_id, filename, storage_path, uploaded_by) "
                "values (%s, 'f.csv', 'p', %s)", (world["accounts"]["a"], world["users"]["owner_b"]))


def test_cannot_file_an_upload_in_someone_elses_name(db, world):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with as_user(db, world["users"]["member_a"]) as cur:
            cur.execute(
                "insert into public.data_sources (account_id, filename, storage_path, uploaded_by) "
                "values (%s, 'f.csv', 'p', %s)", (world["accounts"]["a"], world["users"]["owner_a"]))


def test_members_cannot_add_themselves_to_another_account(db, world):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with as_user(db, world["users"]["owner_b"]) as cur:
            cur.execute("insert into public.account_memberships (account_id, user_id, role) "
                        "values (%s, %s, 'owner')", (world["accounts"]["a"], world["users"]["owner_b"]))


# ------------------------------------------------------------- onboarding ---

def test_create_account_is_idempotent_per_user(db, world):
    with as_user(db, world["users"]["owner_a"]) as cur:
        cur.execute("select public.create_account('A second shop')")
        assert cur.fetchone()[0] == world["accounts"]["a"]
    with as_service_role(db) as cur:
        cur.execute("select count(*) from public.accounts where primary_owner_user_id = %s",
                    (world["users"]["owner_a"],))
        assert cur.fetchone()[0] == 1


def test_create_account_makes_the_caller_owner(db, world):
    with as_user(db, world["users"]["owner_b"]) as cur:
        cur.execute("select role from public.account_memberships where user_id = %s",
                    (world["users"]["owner_b"],))
        assert [r[0] for r in cur.fetchall()] == ["owner"]


def test_create_account_rejects_a_blank_name(db):
    uid = uuid.uuid4()
    with db.connect() as conn:
        conn.execute("insert into auth.users (id, email, encrypted_password) values (%s, %s, 'x')",
                     (uid, f"{uid}@example.com"))
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        with as_user(db, uid) as cur:
            cur.execute("select public.create_account('   ')")


def test_signed_out_visitors_cannot_create_accounts(db):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with as_anon(db) as cur:
            cur.execute("select public.create_account('Sneaky')")


# ---------------------------------------------------------------- storage ---

def _upload(db, user_id, path):
    with as_user(db, user_id) as cur:
        cur.execute("insert into storage.objects (bucket_id, name, owner) values ('sales-uploads', %s, %s)",
                    (path, user_id))


def test_owners_can_upload_under_their_account_prefix(db, world):
    path = f"{world['accounts']['a']}/{uuid.uuid4()}-sales.csv"
    _upload(db, world["users"]["owner_a"], path)
    with as_user(db, world["users"]["member_a"]) as cur:
        cur.execute("select count(*) from storage.objects where name = %s", (path,))
        assert cur.fetchone()[0] == 1, "any member can read the account's uploads"
    with as_user(db, world["users"]["owner_b"]) as cur:
        cur.execute("select count(*) from storage.objects where name = %s", (path,))
        assert cur.fetchone()[0] == 0, "another account cannot"


def test_plain_members_cannot_upload(db, world):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _upload(db, world["users"]["member_a"], f"{world['accounts']['a']}/{uuid.uuid4()}-x.csv")


def test_managers_can_upload(db, world):
    uid = uuid.uuid4()
    with db.connect() as conn:
        conn.execute("insert into auth.users (id, email, encrypted_password) values (%s, %s, 'x')",
                     (uid, f"{uid}@example.com"))
        conn.execute("insert into public.account_memberships (account_id, user_id, role) "
                     "values (%s, %s, 'manage')", (world["accounts"]["a"], uid))
    _upload(db, uid, f"{world['accounts']['a']}/{uuid.uuid4()}-m.csv")


@pytest.mark.parametrize("path", [
    "{b}/sneaky.csv",              # someone else's prefix
    "sneaky.csv",                  # no prefix at all
    "not-a-uuid/sneaky.csv",       # malformed prefix: refused, not an error
])
def test_uploads_outside_your_own_prefix_are_refused(db, world, path):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _upload(db, world["users"]["owner_a"], path.format(b=world["accounts"]["b"]))


def test_bucket_is_private(db):
    with db.connect() as conn:
        public, limit, types = conn.execute(
            "select public, file_size_limit, allowed_mime_types from storage.buckets "
            "where id = 'sales-uploads'").fetchone()
    assert public is False
    assert limit and limit > 0
    assert types == ["text/csv"]
