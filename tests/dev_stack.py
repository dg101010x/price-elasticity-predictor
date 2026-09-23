"""
Run the whole product locally, with no Supabase project and no keys.

    python -m tests.dev_stack            # http://127.0.0.1:8000
    python -m tests.dev_stack --port 8010 --no-seed

Starts the throwaway Postgres + real PostgREST + emulated Auth/Storage from
tests/supabase_gateway.py, points the app at it, and serves the app. Email
confirmation is off, so signing up signs you straight in. With --seed (the
default) a demo business is created and its sample upload fitted:

    demo@example.com / demo-password     "Juniper Gifts"

Insights use the template unless GEMINI_API_KEY is set in your shell, in
which case they call Gemini for real. Everything is thrown away on exit.
Needs the Postgres server binaries and PostgREST (see tests/supabase_gateway.py).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import threading
import time

import httpx
import uvicorn

from tests.supabase_gateway import start_fake_supabase
from tests.synthetic_sales import GIFT_SHOP, make_sales_csv

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password"


def seed(base: str) -> None:
    with httpx.Client(base_url=base, trust_env=False, timeout=120) as c:
        c.post("/api/auth/signup", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}).raise_for_status()
        c.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}).raise_for_status()
        c.post("/api/account", json={"name": "Juniper Gifts"}).raise_for_status()
        body = gzip.compress(make_sales_csv(GIFT_SHOP, seed=1))
        mapping = c.post("/api/uploads/inspect", content=body).json()["mapping"]
        c.post("/api/uploads", content=body, params={"filename": "juniper-2024-weekly.csv",
                                                     "mapping": json.dumps(mapping)}).raise_for_status()
        c.post("/api/account/insights").raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()

    fake, reason = start_fake_supabase(confirm_email=False)
    if fake is None:
        raise SystemExit(reason)
    os.environ.update({
        "NEXT_PUBLIC_SUPABASE_URL": fake.url,
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": fake.anon_key,
        "SUPABASE_SERVICE_ROLE_KEY": fake.service_key,
        "PSL_INSECURE_COOKIES": "1",
    })
    from src.api import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{args.port}"
    for _ in range(100):
        try:
            httpx.get(f"{base}/health", trust_env=False, timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    if not args.no_seed:
        seed(base)
        print(f"Seeded {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"Serving {base}  (Ctrl-C to stop)", flush=True)
    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        fake.stop()
        fake.db.stop()


if __name__ == "__main__":
    main()
