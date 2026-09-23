"""
The one place that knows which language model writes insights, and how.

    Gemini API (Google AI Studio key), REST generateContent, via httpx.

Free tier -> paid tier
----------------------
On the Gemini API the paid tier is the same endpoint, the same key and the
same request: it is switched on by linking Cloud Billing to the key's
Google Cloud project in AI Studio ("Set up billing"). What changes is the
data terms -- on the free tier Google may use prompts and responses to
improve its products and human reviewers may read them; on the paid tier
it does neither beyond abuse monitoring. Apps serving users in the EEA,
Switzerland or the UK must use the paid tier.

So the code change is this one line, which only changes what the page
*tells* people about where their numbers go:

    TIER = os.environ.get("GEMINI_TIER", "free")        # set GEMINI_TIER=paid

and GEMINI_MODEL pins a specific model instead of the rolling Flash alias.
Moving to Vertex AI instead would mean replacing `generate()` below and
nothing else: callers see only `generate(system, user) -> Completion`.

What is sent: the insights engine passes only the fitted runs -- category
names and six numbers per run. No sales rows ever reach this module.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-flash-latest"       # Google's rolling alias for the current Flash model
TIER = os.environ.get("GEMINI_TIER", "free")

TIMEOUT = httpx.Timeout(35.0, connect=5.0)
RETRYABLE = {429, 500, 503, 504}


class LLMError(Exception):
    """The model couldn't be reached or gave nothing usable. Callers fall
    back to the template; this is never shown raw to a user."""


@dataclass
class Completion:
    text: str
    model: str            # the model version that actually answered


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def tier() -> str:
    return os.environ.get("GEMINI_TIER", TIER).strip().lower() or "free"


def generate(system: str, user: str, api_key: str, transport: httpx.BaseTransport | None = None) -> Completion:
    model = model_name()
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        # maxOutputTokens includes any thinking tokens, so it is generous;
        # temperature is left at the model default (Google recommends 1.0
        # for Gemini 3), and thinking is left at the model's default level
        # because the 2.5 and 3.x families take incompatible settings.
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 4096},
    }
    with httpx.Client(timeout=TIMEOUT, transport=transport) as http:
        for attempt in range(2):
            try:
                response = http.post(f"{ENDPOINT}/models/{model}:generateContent", json=body,
                                     headers={"x-goog-api-key": api_key})
            except httpx.HTTPError as exc:
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                raise LLMError(f"network: {exc.__class__.__name__}") from exc
            if response.status_code in RETRYABLE and attempt == 0:
                time.sleep(2.0)
                continue
            break
    if response.status_code >= 400:
        raise LLMError(f"HTTP {response.status_code}: {response.text[:300]}")

    payload = response.json()
    feedback = payload.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise LLMError(f"blocked: {feedback['blockReason']}")
    candidates = payload.get("candidates") or []
    if not candidates:
        raise LLMError("no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise LLMError(f"empty response (finishReason={candidates[0].get('finishReason')})")
    return Completion(text=text, model=payload.get("modelVersion") or model)
