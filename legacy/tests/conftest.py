"""
Shared fixtures. The browser tests need a real server (the page fetches
/estimates and /catalog on load), so one uvicorn process is started per
session on a free port.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Playwright's Python package expects its own browser build. This environment
# ships a Node-installed Chromium instead, so point at that when it exists
# rather than downloading another copy.
_BUNDLED_CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PYTHONPATH=ROOT)
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("uvicorn exited before serving")
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=1):
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.25)
        else:
            raise RuntimeError("uvicorn did not come up in time")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def browser():
    playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright is not installed"
    )
    launch_kwargs = {"args": ["--no-sandbox"]}
    if os.path.exists(_BUNDLED_CHROMIUM):
        launch_kwargs["executable_path"] = _BUNDLED_CHROMIUM

    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(**launch_kwargs)
        except Exception as exc:                     # pragma: no cover
            pytest.skip(f"no usable chromium: {exc}")
        yield b
        b.close()


def _make_page(browser, base_url, width, height, **context_kwargs):
    context = browser.new_context(viewport={"width": width, "height": height}, **context_kwargs)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector("#layout:not([hidden])", timeout=20000)
    page.wait_for_selector("#compare-chart svg", timeout=20000)
    return context, page


@pytest.fixture
def page(browser, base_url):
    context, page = _make_page(browser, base_url, 1440, 900)
    yield page
    context.close()


@pytest.fixture
def mobile_page(browser, base_url):
    context, page = _make_page(browser, base_url, 390, 844, has_touch=True, is_mobile=True)
    yield page
    context.close()


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: needs a real browser")


@pytest.fixture(scope="session", autouse=True)
def _check_playwright():
    if shutil.which("node") is None and not os.path.exists(_BUNDLED_CHROMIUM):
        pytest.skip("no browser available for frontend tests", allow_module_level=True)
