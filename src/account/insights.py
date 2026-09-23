"""
Business recommendations written from the fitted numbers, and only those.

The model sees one thing: the list of six-field run objects that
src/stats_engine.run_record produces and elasticity_runs stores --
category, coefficient, ci_low, ci_high, r_squared, n_observations. No sales
rows, no product names, nothing it could compute a new number from.

Every response is then checked, number by number:

  * each numeric token must equal a value in that JSON -- as written, with
    its sign dropped ("units fall 1.754%"), or as a simple percentage of it
    (an r_squared of 0.368 written as 36.8%); a token written with an
    explicit sign must match the sign too
  * spelled-out quantities ("ten percent", "twice", "half") are refused
    outright, since they would slip past a digit check
  * there must be 3 to 5 recommendations

A response that fails is retried once with a stricter prompt naming what
was wrong. If that fails too, the recommendations come from template()
below -- deterministic sentences over the same JSON, held to the same
validator by tests/test_insights.py -- rather than showing anything
ungrounded. Whatever is accepted is stored with a trace of which run and
field every number came from, which is what the Insights page uses to let
someone check a claim against the estimate behind it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable

from . import llm

FIELDS = ("coefficient", "ci_low", "ci_high", "r_squared", "n_observations")
TEMPLATE_MODEL = "template-v1"

SYSTEM_PROMPT = """You are a pricing analyst. Given only the numbers in the JSON below, write 3 to 5 specific, numbered business recommendations for a small business owner. Every number you state must appear in the JSON verbatim. Do not calculate new numbers, do not estimate, do not mention any number not present in the input. If the data is too thin to say something meaningful (low n_observations, very low r_squared), say that plainly instead of forcing a recommendation.

How to read the JSON. Each object is one price-elasticity estimate fitted from this business's own weekly sales history. "category": null is the whole catalogue; other objects are one product category each. "coefficient" is the price elasticity: the percentage change in units sold that has gone with a one percent price rise. "ci_low" and "ci_high" bound its 95% confidence interval. "r_squared" is the share of the week-to-week swing in units sold that price explains. "n_observations" is how many product-weeks the estimate rests on.

The break-even point is the elasticity at which a price change leaves revenue unchanged. When an estimate's whole interval sits below it (more negative), price cuts have tended to grow revenue; when the whole interval sits above it (closer to zero), price rises have; when the interval spans it, the data cannot say which way revenue would move. Refer to it only as "the break-even point" and never write its value.

Rules for numbers:
- Copy numbers exactly as the JSON writes them. You may drop the minus sign when you say units "fall", and you may write r_squared as a percentage (0.253 as 25.3%). Nothing else.
- Write no other number: no example price changes, no percentages of your own, no years, no counts of anything, no rounding, and no spelled-out quantities such as "ten percent", "twice" or "half".
- No costs are given, so never claim a change raises profit; say what it does to revenue and tell the owner to check margins.
- These are associations in past sales, not guarantees. Do not promise outcomes.

Reply with JSON only, in exactly this shape: {"recommendations": ["...", "..."]} -- 3 to 5 strings, one recommendation per string, without list numbers."""

STRICT_SUFFIX = """

Your previous answer was rejected: {problem}
Write the recommendations again. Every digit you write must be copied from the JSON exactly as shown there (a minus sign may be dropped; r_squared may be written as a percentage). If you are unsure whether a number is allowed, leave it out and describe the point in words."""

# A digit run, optionally signed, with optional thousands separators,
# decimals and a percent sign. Not preceded by another digit or separator.
NUMBER_RE = re.compile(r"(?<![\d.,])([-+−–]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?%)?")
SPELLED_RE = re.compile(
    r"\b(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|a hundred|hundred)\s*(?:-\s*)?"
    r"(?:percent|per cent|percentage points?|points?|times|x\b|%))"
    r"|\b(?:twice|thrice|double[ds]?|doubling|triple[ds]?|tripling|halve[ds]?|halving|half)\b",
    re.IGNORECASE,
)
LIST_MARKER_RE = re.compile(r"^\s*(?:\(?\d{1,2}[.)]|[-*•])\s+")


# ---------------------------------------------------------------- the input --

def model_input(runs: list[dict]) -> list[dict]:
    """elasticity_runs rows -> the six-field objects, whole catalogue first."""
    ordered = sorted(runs, key=lambda r: (r["category"] is not None, float(r["coefficient"])))
    return [{
        "category": r["category"],
        "coefficient": float(r["coefficient"]),
        "ci_low": float(r["ci_low"]),
        "ci_high": float(r["ci_high"]),
        "r_squared": float(r["r_squared"]),
        "n_observations": int(r["n_observations"]),
    } for r in ordered]


# ------------------------------------------------------------- validation --

@dataclass
class Check:
    ok: bool
    items: list[dict] = field(default_factory=list)       # [{"text", "numbers": [...]}]
    ungrounded: list[str] = field(default_factory=list)
    problem: str = ""


def _dec(value) -> Decimal:
    return Decimal(str(value))


def _allowed(inputs: list[dict], run_ids: list[str | None]):
    """(value, run_id, category, field) for every number in the input."""
    for obj, run_id in zip(inputs, run_ids):
        for f in FIELDS:
            yield _dec(obj[f]), run_id, obj["category"], f


def ground_token(token: re.Match, inputs: list[dict], run_ids: list[str | None]) -> list[dict]:
    sign, whole, frac, pct = token.group(1), token.group(2), token.group(3) or "", token.group(4)
    try:
        magnitude = Decimal(whole.replace(",", "") + frac)
    except InvalidOperation:
        return []
    matches = []
    for value, run_id, category, f in _allowed(inputs, run_ids):
        forms = []
        if sign in ("-", "−", "–"):
            forms.append(("exact", -magnitude == value))
        elif sign == "+":
            forms.append(("exact", magnitude == value))
        else:
            forms.append(("exact", magnitude == value))
            forms.append(("absolute", magnitude == abs(value)))
        if pct:
            forms.append(("percent", magnitude == abs(value) * 100))
        for form, hit in forms:
            if hit:
                matches.append({"run_id": run_id, "category": category, "field": f, "form": form})
                break
    # A number that is part of a category's own name ("Size 10") is also in the JSON verbatim.
    if not matches and not pct:
        for obj, run_id in zip(inputs, run_ids):
            name = obj["category"] or ""
            if re.search(rf"(?<![\d.]){re.escape(whole + frac)}(?![\d.])", name):
                matches.append({"run_id": run_id, "category": obj["category"], "field": "category",
                                "form": "name"})
    return matches


def validate(recommendations, inputs: list[dict], run_ids: list[str | None]) -> Check:
    if not isinstance(recommendations, list) or not all(isinstance(r, str) for r in recommendations):
        return Check(False, problem="the reply was not a JSON list of recommendation strings")
    items = [LIST_MARKER_RE.sub("", r).strip() for r in recommendations if r and r.strip()]
    if not 3 <= len(items) <= 5:
        return Check(False, problem=f"it had {len(items)} recommendations; 3 to 5 are required")
    checked, bad = [], []
    for text in items:
        if len(text) > 700:
            return Check(False, problem="a recommendation was far too long")
        numbers = []
        for m in NUMBER_RE.finditer(text):
            found = ground_token(m, inputs, run_ids)
            if found:
                numbers.append({"text": m.group(0).strip(), "start": m.start(), "end": m.end(),
                                "sources": found})
            else:
                bad.append(m.group(0).strip())
        for m in SPELLED_RE.finditer(text):
            bad.append(m.group(0))
        checked.append({"text": text, "numbers": numbers})
    if bad:
        return Check(False, items=checked, ungrounded=bad,
                     problem="it contained numbers that are not in the JSON: " + ", ".join(sorted(set(bad))))
    return Check(True, items=checked)


def parse_reply(text: str):
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data = data.get("recommendations")
    return data


# ----------------------------------------------------------------- template --

MINUS = "−"


def _num(value) -> str:
    d = _dec(value)
    if d == d.to_integral_value() and abs(d) >= 1000:
        text = f"{int(abs(d)):,}"
    else:
        text = format(abs(d).normalize(), "f")
    return (MINUS if d < 0 else "") + text


def _pct(fraction) -> str:
    return format((_dec(fraction) * 100).normalize(), "f") + "%"


def _side(obj: dict) -> str:
    if obj["ci_high"] < -1:
        return "discount"
    if obj["ci_low"] > -1:
        return "raise"
    return "unclear"


def _range(obj: dict) -> str:
    return f"{_num(obj['ci_low'])} to {_num(obj['ci_high'])}"


def _thin(obj: dict) -> bool:
    return obj["n_observations"] < 1000 or obj["r_squared"] < 0.05


def template(inputs: list[dict]) -> list[str]:
    """3 to 5 recommendations using only numbers copied from `inputs`.

    Never mentions the break-even point's value: it isn't in the data, so
    it isn't allowed in an insight either -- the glossary explains it.
    """
    overall = next(o for o in inputs if o["category"] is None)
    cats = [o for o in inputs if o["category"] is not None]
    out: list[str] = []

    side = _side(overall)
    head = (f"Across your whole catalogue, price sensitivity is {_num(overall['coefficient'])} "
            f"(likely range {_range(overall)}). ")
    if side == "discount":
        out.append(head + "That whole range sits on the discount side of the break-even point: price cuts "
                          "have tended to grow revenue here. Before running a promotion, check it still "
                          "clears your margin, because revenue is not profit.")
    elif side == "raise":
        out.append(head + "That whole range sits on the price-rise side of the break-even point: modest "
                          "price increases have tended to grow revenue, and discounts have mostly given "
                          "away margin. Try a small increase on a few products before a catalogue-wide one.")
    else:
        out.append(head + "That range spans the break-even point, so your history can't say whether a "
                          "price change would grow or shrink revenue. Don't reprice the whole catalogue "
                          "on the strength of this number.")

    if len(cats) >= 2:
        most, least = cats[0], cats[-1]
        line = (f"{most['category']} is your most price-sensitive category at {_num(most['coefficient'])} "
                f"(likely {_range(most)}); {least['category']} is the least at {_num(least['coefficient'])} "
                f"(likely {_range(least)}). ")
        if _side(least) == "raise" and _side(most) == "discount":
            line += (f"Test price rises in {least['category']} first, and keep promotions for "
                     f"{most['category']}, where they have paid for themselves in revenue.")
        else:
            line += (f"If you test a price rise anywhere, start with {least['category']}; "
                     f"customers of {most['category']} have reacted most to price.")
        out.append(line)

    unclear = [c for c in cats if _side(c) == "unclear"]
    if unclear:
        names = ", ".join(f"{c['category']} ({_range(c)})" for c in unclear[:3])
        out.append(f"Too close to call: {names}. Those ranges span the break-even point, so hold prices "
                   "there until more history narrows them.")

    evidence = (f"This rests on {_num(overall['n_observations'])} product-weeks, and price explains "
                f"{_pct(overall['r_squared'])} of the week-to-week swing in units sold. ")
    if _thin(overall):
        evidence += ("That is thin evidence: treat the direction as a hint, not a plan, and upload a "
                     "longer history before acting on it.")
    else:
        evidence += ("A low share is normal for retail, where season, promotions and stock move sales "
                     "too; the range above already accounts for that noise.")
    out.append(evidence)

    if len(out) < 5:
        out.append(f"Treat any price change as a test: make it on a few products, keep the rest as they "
                   f"are, and upload again after several weeks. If the new catalogue estimate lands "
                   f"inside {_range(overall)}, the pattern is holding.")
    if not cats and len(out) < 5:
        out.append("Add a category column to your next upload to see which product groups drive this "
                   "estimate; categories are only reported once they have enough history of their own.")
    return out[:5]


# -------------------------------------------------------------- orchestrate --

@dataclass
class Result:
    items: list[dict]            # [{"text", "numbers": [...]}]
    model: str
    source: str                  # "llm" | "template"
    attempts: list[dict]

    @property
    def body(self) -> str:
        return "\n".join(f"{i}. {item['text']}" for i, item in enumerate(self.items, 1))


def write(runs: list[dict], api_key: str | None,
          generate: Callable[[str, str, str], "llm.Completion"] | None = None) -> tuple[Result, dict]:
    """Recommendations for one upload's runs, plus the grounding record to
    store alongside them."""
    inputs = model_input(runs)
    ordered_ids = [r["id"] for r in sorted(runs, key=lambda r: (r["category"] is not None,
                                                                 float(r["coefficient"])))]
    user = "```json\n" + json.dumps(inputs, indent=2) + "\n```"
    attempts: list[dict] = []
    result: Result | None = None

    if api_key:
        generate = generate or llm.generate
        system = SYSTEM_PROMPT
        for _ in range(2):
            try:
                completion = generate(system, user, api_key)
            except llm.LLMError as exc:
                attempts.append({"ok": False, "problem": f"model unavailable ({exc})"})
                break                                   # a stricter prompt won't fix an outage
            check = validate(parse_reply(completion.text), inputs, ordered_ids)
            attempts.append({"ok": check.ok, "model": completion.model, "problem": check.problem,
                             "ungrounded": check.ungrounded})
            if check.ok:
                result = Result(check.items, completion.model, "llm", attempts)
                break
            system = SYSTEM_PROMPT + STRICT_SUFFIX.format(problem=check.problem)
    else:
        attempts.append({"ok": False, "problem": "GEMINI_API_KEY is not set"})

    if result is None:
        check = validate(template(inputs), inputs, ordered_ids)
        if not check.ok:                                # a bug in template(); never show it
            raise AssertionError(f"template produced ungrounded text: {check.problem}")
        result = Result(check.items, TEMPLATE_MODEL, "template", attempts)

    grounding = {
        "source": result.source,
        "tier": llm.tier() if result.source == "llm" else None,
        "input": inputs,
        "run_ids": ordered_ids,
        "items": result.items,
        "attempts": attempts,
    }
    return result, grounding
