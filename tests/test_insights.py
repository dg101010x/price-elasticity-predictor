"""
The insights engine's promise: every number in a recommendation is one of
the fitted numbers it was given.

Covers the validator (what it accepts, what it refuses), the retry-then-
template flow, the template itself against the same validator over many
random inputs, what the model is and isn't shown, and the Gemini HTTP
client against a mocked transport.
"""

from __future__ import annotations

import json
import random

import httpx
import pytest

from src.account import insights, llm

RUNS = [
    {"id": "run-overall", "category": None, "coefficient": -1.754, "ci_low": -1.843, "ci_high": -1.665,
     "r_squared": 0.368, "n_observations": 2600},
    {"id": "run-candles", "category": "Candles", "coefficient": -2.11, "ci_low": -2.246, "ci_high": -1.974,
     "r_squared": 0.451, "n_observations": 1144},
    {"id": "run-mugs", "category": "Mugs", "coefficient": -0.62, "ci_low": -0.9, "ci_high": -0.34,
     "r_squared": 0.12, "n_observations": 1040},
]
INPUTS = insights.model_input(RUNS)


def _ids():
    return [r["id"] for r in sorted(RUNS, key=lambda r: (r["category"] is not None, r["coefficient"]))]


def check(texts):
    return insights.validate(texts, INPUTS, _ids())


# ------------------------------------------------------------- the input --

def test_the_model_sees_only_the_six_field_objects():
    assert all(set(o) == {"category", "coefficient", "ci_low", "ci_high", "r_squared", "n_observations"}
               for o in INPUTS)
    assert INPUTS[0]["category"] is None, "whole catalogue first"


def test_the_prompt_keeps_the_specified_constraint_language():
    for phrase in ("Every number you state must appear in the JSON verbatim",
                   "Do not calculate new numbers, do not estimate",
                   "say that plainly instead of forcing a recommendation"):
        assert phrase in insights.SYSTEM_PROMPT


# -------------------------------------------------------------- validator --

def test_grounded_numbers_in_every_allowed_form_pass():
    result = check([
        "Across the catalogue, sensitivity is −1.754 (likely −1.843 to −1.665).",
        "Candles are the most sensitive: units have fallen 2.11% for each percent the price rose.",
        "Price explains 36.8% of the weekly swing, from 2,600 product-weeks.",
    ])
    assert result.ok, result.problem
    first = result.items[0]["numbers"][0]
    assert first["text"] == "−1.754"
    assert first["sources"][0] == {"run_id": "run-overall", "category": None, "field": "coefficient",
                                   "form": "exact"}
    pct = [n for n in result.items[2]["numbers"] if n["text"] == "36.8%"][0]
    assert pct["sources"][0]["field"] == "r_squared" and pct["sources"][0]["form"] == "percent"


@pytest.mark.parametrize("bad", [
    "Try a 10% price rise on candles.",                   # invented example change
    "Sensitivity is about −1.75.",                        # rounded
    "Sensitivity is +1.754.",                             # explicit wrong sign
    "Units would fall by roughly ten percent.",           # spelled out
    "Candles sell twice as well on promotion.",           # spelled multiplier
    "Cut the price by half.",                             # spelled fraction
    "Your 2025 sales show sensitivity of −1.754.",        # a year
    "Expect revenue to rise 3.2% if you cut prices.",     # computed forecast
])
def test_ungrounded_numbers_are_refused(bad):
    result = check([bad, "Sensitivity is −1.754.", "Mugs are at −0.62."])
    assert not result.ok
    assert result.ungrounded


def test_numbers_in_a_category_name_are_allowed():
    runs = [dict(RUNS[0]), {**RUNS[1], "category": "Size 10 Boots"}]
    inputs = insights.model_input(runs)
    ids = [r["id"] for r in sorted(runs, key=lambda r: (r["category"] is not None, r["coefficient"]))]
    result = insights.validate(["Size 10 Boots sit at −2.11.", "Overall −1.754.", "Range −1.843 to −1.665."],
                               inputs, ids)
    assert result.ok, result.problem


@pytest.mark.parametrize("reply,problem", [
    (["only one"], "3 to 5"),
    (["a", "b", "c", "d", "e", "f"], "3 to 5"),
    ("not a list", "JSON list"),
    (None, "JSON list"),
])
def test_shape_problems_are_refused(reply, problem):
    result = check(reply)
    assert not result.ok and problem in result.problem


def test_list_markers_are_not_mistaken_for_claims():
    result = check(["1. Sensitivity is −1.754.", "2) Candles at −2.11.", "- Mugs at −0.62."])
    assert result.ok, result.problem
    assert result.items[0]["text"] == "Sensitivity is −1.754."


def test_reply_parsing_accepts_fenced_json():
    assert insights.parse_reply('```json\n{"recommendations": ["a"]}\n```') == ["a"]
    assert insights.parse_reply("not json") is None


# --------------------------------------------------------------- template --

def _random_runs(rng: random.Random, n_categories: int) -> list[dict]:
    def one(cat):
        beta = round(rng.uniform(-4.0, 0.4), 3)
        half = round(rng.uniform(0.01, 1.2), 3)
        return {"id": f"run-{cat}", "category": cat, "coefficient": beta,
                "ci_low": round(beta - half, 3), "ci_high": round(beta + half, 3),
                "r_squared": round(rng.uniform(0.0, 0.8), 3), "n_observations": rng.randint(30, 250_000)}
    return [one(None)] + [one(f"Category {c}") for c in "ABCDEFG"[:n_categories]]


@pytest.mark.parametrize("seed", range(60))
def test_the_template_is_always_grounded(seed):
    rng = random.Random(seed)
    runs = _random_runs(rng, seed % 6)
    inputs = insights.model_input(runs)
    ids = [r["id"] for r in sorted(runs, key=lambda r: (r["category"] is not None, r["coefficient"]))]
    texts = insights.template(inputs)
    result = insights.validate(texts, inputs, ids)
    assert result.ok, (result.problem, texts)
    assert 3 <= len(texts) <= 5


def test_the_template_says_plainly_when_the_data_is_thin():
    runs = [{"id": "r", "category": None, "coefficient": -0.8, "ci_low": -2.1, "ci_high": 0.5,
             "r_squared": 0.01, "n_observations": 240}]
    texts = " ".join(insights.template(insights.model_input(runs)))
    assert "thin evidence" in texts
    assert "can't say" in texts


def test_the_template_never_states_the_break_even_value():
    texts = " ".join(insights.template(INPUTS))
    assert "break-even point" in texts
    assert "−1 " not in texts and "-1 " not in texts


# ------------------------------------------------------------ orchestrate --

def _reply(items):
    return llm.Completion(text=json.dumps({"recommendations": items}), model="gemini-test-001")


GROUNDED = ["Overall sensitivity is −1.754, likely −1.843 to −1.665.",
            "Candles are most sensitive at −2.11.",
            "Mugs are least sensitive at −0.62; price explains 12% of their swing."]
UNGROUNDED = ["Raise mug prices 5%.", "Candles at −2.11.", "Overall −1.754."]


def test_a_grounded_reply_is_accepted_first_time():
    calls = []
    result, grounding = insights.write(RUNS, "key", lambda s, u, k: calls.append((s, u)) or _reply(GROUNDED))
    assert result.source == "llm" and result.model == "gemini-test-001"
    assert len(calls) == 1
    assert grounding["input"] == INPUTS
    sent = json.loads(calls[0][1].strip("`").removeprefix("json\n"))
    assert sent == INPUTS, "the model is shown the six-field runs and nothing else"


def test_an_ungrounded_reply_is_retried_once_with_a_stricter_prompt():
    replies = iter([_reply(UNGROUNDED), _reply(GROUNDED)])
    systems = []
    result, grounding = insights.write(RUNS, "key", lambda s, u, k: systems.append(s) or next(replies))
    assert result.source == "llm"
    assert len(systems) == 2
    assert "5%" in systems[1] and "rejected" in systems[1]
    assert [a["ok"] for a in grounding["attempts"]] == [False, True]


def test_two_ungrounded_replies_fall_back_to_the_template():
    result, grounding = insights.write(RUNS, "key", lambda s, u, k: _reply(UNGROUNDED))
    assert result.source == "template" and result.model == insights.TEMPLATE_MODEL
    assert len(grounding["attempts"]) == 2
    assert "5%" not in result.body


def test_an_outage_falls_back_without_a_pointless_retry():
    calls = []

    def down(s, u, k):
        calls.append(1)
        raise llm.LLMError("HTTP 503")
    result, grounding = insights.write(RUNS, "key", down)
    assert result.source == "template" and len(calls) == 1


def test_no_api_key_means_template_and_no_call():
    result, grounding = insights.write(RUNS, None, lambda *a: pytest.fail("called the model"))
    assert result.source == "template"
    assert grounding["attempts"][0]["problem"] == "GEMINI_API_KEY is not set"


def test_every_number_in_a_stored_insight_traces_to_a_run():
    result, grounding = insights.write(RUNS, "key", lambda s, u, k: _reply(GROUNDED))
    run_ids = {r["id"] for r in RUNS}
    for item in grounding["items"]:
        for number in item["numbers"]:
            assert number["sources"] and all(s["run_id"] in run_ids for s in number["sources"])
            assert item["text"][number["start"]:number["end"]].strip() == number["text"]


# ------------------------------------------------------------ gemini http --

def _transport(handler):
    return httpx.MockTransport(handler)


def test_gemini_request_shape_and_thought_filtering(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-flash")
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True},
                                                  {"text": '{"recommendations": []}'}]},
                            "finishReason": "STOP"}],
            "modelVersion": "gemini-test-flash-002"})
    out = llm.generate("SYS", "USER", "k-123", transport=_transport(handler))
    assert seen["url"] == f"{llm.ENDPOINT}/models/gemini-test-flash:generateContent"
    assert seen["key"] == "k-123"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "USER"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert out.text == '{"recommendations": []}'
    assert out.model == "gemini-test-flash-002"


def test_gemini_retries_a_rate_limit_once(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    statuses = iter([429, 200])

    def handler(request):
        status = next(statuses)
        if status == 429:
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
    assert llm.generate("s", "u", "k", transport=_transport(handler)).text == "{}"


@pytest.mark.parametrize("response", [
    httpx.Response(404, json={"error": {"code": 404, "status": "NOT_FOUND"}}),
    httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
    httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}),
])
def test_gemini_failures_raise_for_the_template_to_take_over(response):
    with pytest.raises(llm.LLMError):
        llm.generate("s", "u", "k", transport=_transport(lambda r: response))


def test_the_default_model_is_the_rolling_flash_alias(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert llm.model_name() == "gemini-flash-latest"
