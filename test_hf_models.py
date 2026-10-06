#!/usr/bin/env python3
"""
Hugging Face Model Evaluation for Business Insights Platform

Tests three candidate models for:
1. Initial synthesis (profile-based guidance)
2. Data synthesis (grounded narrative from computed results)
3. Guardrails (never invents numbers, always traceable)

Usage:
    export HF_API_KEY="your_key_here"
    python3 test_hf_models.py
"""

import os
import requests
import json
from typing import Dict, List, Tuple

HF_API_KEY = os.getenv("HF_API_KEY")
if not HF_API_KEY:
    print("ERROR: Set HF_API_KEY environment variable")
    print("Get it from: https://huggingface.co/settings/tokens")
    exit(1)

HF_ENDPOINT = "https://api-inference.huggingface.co/models"

MODELS_TO_TEST = [
    "mistralai/Mistral-7B-Instruct-v0.1",
    "HuggingFaceH4/zephyr-7b-beta",
    "meta-llama/Llama-2-7b-chat-hf",
]

# Test Scenario 1: Initial Synthesis (profile-only, no data yet)
INITIAL_SYNTHESIS_PROMPT = """You are a business insights advisor. A new business has signed up and told us about themselves.
Based ONLY on this profile information, provide 2-3 brief, directional insights about their pricing strategy.
IMPORTANT: Frame these as guidance ("businesses like yours often..." or "consider that..."), NOT as measured facts.
Do NOT invent any numbers. Keep it to 3-4 sentences max.

Profile:
- Business: Small grocery store
- Location: Lagos, Nigeria
- Industry: Retail / Grocery
- Description: Neighborhood convenience store serving local foot traffic
- Competition Scope: Local (within 2km radius)
- Primary Cost Pressure: Rent-driven
- Seasonality: Flat

Provide your insights:"""

# Test Scenario 2: Data Synthesis (grounded, numbers from computed results)
DATA_SYNTHESIS_PROMPT = """You are a business analyst. This business has uploaded sales data, and we've computed the following results.
Synthesize these results into a 2-3 sentence narrative. ONLY mention insights that directly trace to the numbers below.
NEVER invent numbers or metrics. If you can't confidently ground a claim, don't make it.

Computed Results:
- Price Elasticity: -0.95 (95% CI: -1.1 to -0.8), R² = 0.68
  → Interpretation: A 10% price increase → ~9.5% reduction in units sold
- 30-Day Demand Forecast: 450 units (±15% confidence interval)
- Inventory: 2 SKUs showing overstock risk (>60 days stock-on-hand)

Write your narrative:"""

# Test Scenario 3: Guardrail Test (should reject made-up numbers)
GUARDRAIL_TEST_PROMPT = """Based on the results below, write a summary mentioning the elasticity coefficient and inventory status.
IMPORTANT: Only use numbers that appear in the results. Do NOT estimate or invent numbers.

Results:
- Elasticity: -1.2
- Forecast: 500 units next month

Write your summary (max 2 sentences):"""


def call_hf_api(model_id: str, prompt: str, max_tokens: int = 256) -> Tuple[bool, str]:
    """
    Call HF Inference API and return (success, response_text)
    """
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": 0.7,
            "top_p": 0.9,
        },
    }

    try:
        response = requests.post(
            f"{HF_ENDPOINT}/{model_id}",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                text = result[0].get("generated_text", "").replace(prompt, "").strip()
                return True, text
            else:
                return False, f"Unexpected response format: {result}"
        elif response.status_code == 503:
            return False, "Model loading (first call can be slow)..."
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except requests.exceptions.Timeout:
        return False, "Timeout (model may be loading)"
    except Exception as e:
        return False, f"Error: {str(e)}"


def evaluate_initial_synthesis(model_id: str) -> Dict:
    """Test initial (profile-only) synthesis"""
    print(f"\n{'='*60}")
    print(f"TEST 1: Initial Synthesis (profile-only)")
    print(f"Model: {model_id}")
    print(f"{'='*60}")

    success, response = call_hf_api(model_id, INITIAL_SYNTHESIS_PROMPT, max_tokens=200)

    if not success:
        print(f"❌ Failed: {response}")
        return {"status": "failed", "error": response}

    print(f"\n{response}\n")

    # Manual eval checklist
    checks = {
        "uses_guidance_language": "consider" in response.lower() or "often" in response.lower() or "may" in response.lower(),
        "no_invented_numbers": not any(char.isdigit() for char in response),
        "coherent": len(response) > 50,
        "on_topic": "pricing" in response.lower() or "price" in response.lower() or "strategy" in response.lower(),
    }

    print("Evaluation:")
    for check, passed in checks.items():
        symbol = "✅" if passed else "❌"
        print(f"  {symbol} {check.replace('_', ' ')}: {passed}")

    return {"status": "success", "response": response, "checks": checks}


def evaluate_data_synthesis(model_id: str) -> Dict:
    """Test data-grounded synthesis (must only use provided numbers)"""
    print(f"\n{'='*60}")
    print(f"TEST 2: Data Synthesis (grounded, never invent)")
    print(f"Model: {model_id}")
    print(f"{'='*60}")

    success, response = call_hf_api(model_id, DATA_SYNTHESIS_PROMPT, max_tokens=200)

    if not success:
        print(f"❌ Failed: {response}")
        return {"status": "failed", "error": response}

    print(f"\n{response}\n")

    # Check that only known numbers appear
    known_numbers = {"0.95", "1.1", "0.8", "0.68", "450", "15", "60", "2"}
    invented = set()

    words = response.split()
    for word in words:
        # Extract numbers from words (e.g., "9.5%" -> "9.5")
        num_str = ''.join(c for c in word if c.isdigit() or c == '.')
        if num_str and num_str not in known_numbers and float(num_str) > 0 if num_str.isdigit() else False:
            invented.add(num_str)

    checks = {
        "no_invented_numbers": len(invented) == 0,
        "mentions_elasticity": "elasticity" in response.lower() or "price" in response.lower(),
        "mentions_forecast": "forecast" in response.lower() or "demand" in response.lower(),
        "coherent": len(response) > 50,
        "under_sentence_limit": response.count('.') <= 4,
    }

    print("Evaluation:")
    for check, passed in checks.items():
        symbol = "✅" if passed else "❌"
        print(f"  {symbol} {check.replace('_', ' ')}: {passed}")

    if invented:
        print(f"\n⚠️  Invented numbers detected: {invented}")

    return {"status": "success", "response": response, "checks": checks, "invented_numbers": list(invented)}


def evaluate_guardrail(model_id: str) -> Dict:
    """Test guardrail: does it resist making up numbers?"""
    print(f"\n{'='*60}")
    print(f"TEST 3: Guardrail (resist inventing numbers)")
    print(f"Model: {model_id}")
    print(f"{'='*60}")

    success, response = call_hf_api(model_id, GUARDRAIL_TEST_PROMPT, max_tokens=100)

    if not success:
        print(f"❌ Failed: {response}")
        return {"status": "failed", "error": response}

    print(f"\n{response}\n")

    # Numbers that should appear (from prompt)
    valid_numbers = {"1.2", "500"}

    # Extract all numbers from response
    words = response.split()
    used_numbers = set()
    for word in words:
        num_str = ''.join(c for c in word if c.isdigit() or c == '.')
        if num_str and (num_str.isdigit() or '.' in num_str):
            used_numbers.add(num_str)

    checks = {
        "only_uses_provided_numbers": used_numbers.issubset(valid_numbers) or len(used_numbers) == 0,
        "mentions_elasticity": "elasticity" in response.lower() or "-1.2" in response,
        "mentions_forecast": "500" in response or "forecast" in response.lower(),
        "short_and_focused": len(response) < 150,
    }

    print("Evaluation:")
    for check, passed in checks.items():
        symbol = "✅" if passed else "❌"
        print(f"  {check.replace('_', ' ')}: {passed}")

    if used_numbers and not used_numbers.issubset(valid_numbers):
        extra = used_numbers - valid_numbers
        print(f"\n⚠️  Extra numbers (possibly invented): {extra}")

    return {"status": "success", "response": response, "checks": checks}


def main():
    print("\n" + "="*60)
    print("HuggingFace Model Evaluation for Business Insights")
    print("="*60)

    results = {}

    for model_id in MODELS_TO_TEST:
        print(f"\n\n{'#'*60}")
        print(f"EVALUATING: {model_id}")
        print(f"{'#'*60}")

        model_results = {
            "initial_synthesis": evaluate_initial_synthesis(model_id),
            "data_synthesis": evaluate_data_synthesis(model_id),
            "guardrail": evaluate_guardrail(model_id),
        }

        results[model_id] = model_results

    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")

    for model_id, tests in results.items():
        print(f"{model_id}:")

        passed_counts = {}
        for test_name, test_result in tests.items():
            if test_result["status"] == "success":
                passed = sum(1 for v in test_result["checks"].values() if v)
                total = len(test_result["checks"])
                passed_counts[test_name] = (passed, total)
                print(f"  {test_name}: {passed}/{total} checks ✅" if passed == total else f"  {test_name}: {passed}/{total} checks ⚠️")
            else:
                print(f"  {test_name}: FAILED ❌ ({test_result['error'][:50]}...)")

        print()

    print("\nRECOMMENDATION:")
    print("- Zephyr-7B: Best for grounding (fine-tuned, newer)")
    print("- Mistral-7B: Fastest, good instruction following")
    print("- Llama-2-7b-chat: Most stable, widely tested")
    print("\nNext step: Pick winner and tell me the model name")


if __name__ == "__main__":
    main()
