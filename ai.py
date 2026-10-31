"""AI integration for LevelUp — Gemma calls, JSON parsing, verification.

This module handles all communication with the Gemini API (Gemma models).
It never logs image data or model output content — only operational metrics.
"""

import json
import logging
import os
import re
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from google import genai
from google.genai import types

from prompts import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    VERIFIER_PROMPT,
    CHECK_WORK_SYSTEM_PROMPT,
    CHECK_WORK_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY")
MAIN_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it")
VERIFY_MODEL = os.environ.get("GEMMA_VERIFY_MODEL", "gemma-4-31b-it")

MAIN_TIMEOUT = 60      # seconds for the explainer call
VERIFY_TIMEOUT = 20    # seconds for the verifier call
RETRY_DELAY = 1        # seconds between retries

# ---------------------------------------------------------------------------
# Client singleton (lazy-initialised)
# ---------------------------------------------------------------------------
_client = None


def get_client():
    """Return the genai client, creating it on first call."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        main_model = os.environ.get("GEMMA_MODEL", MAIN_MODEL)
        verify_model = os.environ.get("GEMMA_VERIFY_MODEL", VERIFY_MODEL)
        _client = genai.Client(api_key=api_key)
        logger.info(
            "Initialised genai client — main=%s  verify=%s",
            main_model, verify_model,
        )
    return _client


# ---------------------------------------------------------------------------
# Robust JSON parsing
# ---------------------------------------------------------------------------
def parse_json(text: str) -> dict | None:
    """Extract a JSON object from model output.

    Handles:
      - Clean JSON
      - JSON wrapped in ```json ... ``` code fences
      - JSON preceded/followed by natural-language preamble
    Returns None if no valid JSON is found.
    """
    if not text:
        return None

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    # Attempt 1: direct parse
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # Attempt 2: extract the outermost { ... }
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, TypeError):
            pass

    return None


# ---------------------------------------------------------------------------
# Response normalisation
# ---------------------------------------------------------------------------
VALID_CONFIDENCES = {"low", "medium", "high"}
VALID_QUALITIES = {"good", "poor"}
VALID_SUBJECTS = {
    "math", "science", "english", "social", "other", "not_homework",
}

RESPONSE_DEFAULTS: dict = {
    "subject": "other",
    "image_quality": "good",
    "retake_hint": "",
    "problem_summary": "",
    "parent_explanation": "",
    "teach_script": [],
    "everyday_example": "",
    "hints": {"nudge": "", "bigger_hint": "", "full_solution": ""},
    "key_terms": [],
    "practice_questions": [],
    "needs_verification": True,
    "confidence": "medium",
}


def normalize_response(data: dict) -> dict:
    """Fill missing keys with safe defaults and clamp values."""
    result = {}

    for key, default in RESPONSE_DEFAULTS.items():
        val = data.get(key, default)

        # Force correct types
        if isinstance(default, str) and not isinstance(val, str):
            val = str(val) if val is not None else default
        elif isinstance(default, list) and not isinstance(val, list):
            val = [val] if val else default
        elif isinstance(default, dict) and not isinstance(val, dict):
            val = default
        elif isinstance(default, bool) and not isinstance(val, bool):
            val = bool(val) if val is not None else default

        result[key] = val

    # Clamp enums
    if result["confidence"] not in VALID_CONFIDENCES:
        result["confidence"] = "medium"
    if result["image_quality"] not in VALID_QUALITIES:
        result["image_quality"] = "good"
    subj = result["subject"].lower().strip()
    result["subject"] = subj if subj in VALID_SUBJECTS else "other"

    # Ensure hints has all three keys
    hints_default = RESPONSE_DEFAULTS["hints"]
    if isinstance(result["hints"], dict):
        for hk in hints_default:
            if hk not in result["hints"]:
                result["hints"][hk] = ""
            elif not isinstance(result["hints"][hk], str):
                result["hints"][hk] = str(result["hints"][hk])
    else:
        result["hints"] = dict(hints_default)

    # Limit key_terms to 4 items and ensure each has term + meaning
    terms = result["key_terms"][:4]
    clean_terms = []
    for t in terms:
        if isinstance(t, dict) and "term" in t and "meaning" in t:
            clean_terms.append({
                "term": str(t["term"]),
                "meaning": str(t["meaning"]),
            })
    result["key_terms"] = clean_terms

    # Ensure teach_script items are strings
    result["teach_script"] = [
        str(s) for s in result["teach_script"][:5]
    ]

    # Limit practice_questions to 3 items and ensure question + answer
    practice = result["practice_questions"][:3]
    clean_practice = []
    for p in practice:
        if isinstance(p, dict) and "question" in p:
            clean_practice.append({
                "question": str(p["question"]),
                "answer": str(p.get("answer", "")),
            })
    result["practice_questions"] = clean_practice

    return result


# ---------------------------------------------------------------------------
# Main explainer call
# ---------------------------------------------------------------------------
def explain_homework(
    image_bytes: bytes,
    mime_type: str,
    language: str,
    grade: int,
    subject: str,
) -> dict:
    """Send a homework image to Gemma and return a normalised response dict.

    Raises RuntimeError on unrecoverable failures.
    """
    client = get_client()
    user_text = USER_TEMPLATE.format(
        language=language, grade=grade, subject=subject,
    )

    # We'll try up to 2 attempts (initial + 1 retry)
    last_error = None
    for attempt in range(2):
        if attempt > 0:
            time.sleep(RETRY_DELAY)

        start = time.time()
        try:
            data = _call_explainer(client, image_bytes, mime_type, user_text)
            latency = time.time() - start
            logger.info(
                "explain attempt=%d status=ok latency=%.1fs model=%s",
                attempt, latency, MAIN_MODEL,
            )
            return data
        except json.JSONDecodeError as e:
            last_error = e
            logger.info(
                "explain attempt=%d status=bad_json model=%s",
                attempt, MAIN_MODEL,
            )
        except Exception as e:
            last_error = e
            latency = time.time() - start
            logger.info(
                "explain attempt=%d status=error error=%s latency=%.1fs model=%s",
                attempt, type(e).__name__, latency, MAIN_MODEL,
            )
            # If it's a 429, don't retry — surface it immediately
            err_str = str(e).lower()
            if "429" in err_str or "resource exhausted" in err_str.lower():
                raise RuntimeError("rate_limited") from e

    raise RuntimeError(f"explain_failed: {type(last_error).__name__}") from last_error


def _call_explainer(
    client, image_bytes: bytes, mime_type: str, user_text: str,
) -> dict:
    """Single attempt at calling the explainer model. Returns normalised dict."""
    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        user_text,
    ]

    # Build config — try with system_instruction first
    config_kwargs: dict = {
        "system_instruction": SYSTEM_PROMPT,
        "temperature": 0.3,
    }

    # Try requesting JSON mime type
    try:
        config_kwargs["response_mime_type"] = "application/json"
    except Exception:
        pass

    try:
        response = client.models.generate_content(
            model=MAIN_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as first_err:
        # Fallback: put system prompt in user text instead
        logger.info("system_instruction fallback: %s", type(first_err).__name__)
        config_kwargs.pop("system_instruction", None)
        config_kwargs.pop("response_mime_type", None)
        fallback_text = SYSTEM_PROMPT + "\n\n" + user_text
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            fallback_text,
        ]
        response = client.models.generate_content(
            model=MAIN_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

    parsed = parse_json(response.text)
    if parsed is None:
        raise json.JSONDecodeError("No JSON found in model output", "", 0)

    return normalize_response(parsed)


# ---------------------------------------------------------------------------
# Verification pass
# ---------------------------------------------------------------------------
def verify_solution(problem_summary: str, full_solution: str) -> dict | None:
    """Independently verify a solution using the larger Gemma model.

    Returns {"agrees": bool, "my_answer": str, "note": str} or None on failure.
    """
    try:
        client = get_client()
    except RuntimeError:
        return None

    user_text = (
        f"Problem: {problem_summary}\n\n"
        f"Proposed solution: {full_solution}\n\n"
        "Solve this problem yourself first, then compare."
    )

    config_kwargs: dict = {
        "system_instruction": VERIFIER_PROMPT,
        "temperature": 0.1,
    }

    # Try enabling thinking for deeper reasoning
    try:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level="HIGH",
        )
    except Exception:
        logger.info("thinking_config not supported, continuing without it")

    start = time.time()
    try:
        response = client.models.generate_content(
            model=VERIFY_MODEL,
            contents=[user_text],
            config=types.GenerateContentConfig(**config_kwargs),
        )
        latency = time.time() - start
        logger.info(
            "verify status=ok latency=%.1fs model=%s", latency, VERIFY_MODEL,
        )

        result = parse_json(response.text)
        if result and "agrees" in result:
            return {
                "agrees": bool(result["agrees"]),
                "my_answer": str(result.get("my_answer", "")),
                "note": str(result.get("note", "")),
            }
        return None

    except Exception as e:
        latency = time.time() - start
        logger.info(
            "verify status=error error=%s latency=%.1fs model=%s",
            type(e).__name__, latency, VERIFY_MODEL,
        )
        return None


# ---------------------------------------------------------------------------
# Check Child's Work (Should-Have #11)
# ---------------------------------------------------------------------------
VALID_VERDICTS = {"correct", "partly", "incorrect", "unclear"}

CHECK_DEFAULTS = {
    "verdict": "unclear",
    "what_is_right": "",
    "mistake_explained": "",
    "next_step_hint": "",
}


def normalize_check_response(data: dict) -> dict:
    """Normalize response for check_child_work."""
    result = {}
    for key, default in CHECK_DEFAULTS.items():
        val = data.get(key, default)
        result[key] = str(val) if val is not None else default

    v = result["verdict"].lower().strip()
    result["verdict"] = v if v in VALID_VERDICTS else "unclear"
    return result


def check_child_work(
    image_bytes: bytes,
    mime_type: str,
    language: str,
    grade: int,
    subject: str,
    problem_text: str = "",
) -> dict:
    """Analyze a photo of child's written work and return kind feedback."""
    client = get_client()
    user_text = CHECK_WORK_USER_TEMPLATE.format(
        language=language,
        grade=grade,
        subject=subject,
        problem_text=problem_text or "Not provided",
    )

    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        user_text,
    ]

    config_kwargs: dict = {
        "system_instruction": CHECK_WORK_SYSTEM_PROMPT,
        "temperature": 0.2,
    }

    try:
        config_kwargs["response_mime_type"] = "application/json"
    except Exception:
        pass

    start = time.time()
    try:
        response = client.models.generate_content(
            model=MAIN_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        latency = time.time() - start
        logger.info(
            "check_work status=ok latency=%.1fs model=%s", latency, MAIN_MODEL,
        )
    except Exception as e:
        latency = time.time() - start
        logger.info(
            "check_work status=error error=%s latency=%.1fs model=%s",
            type(e).__name__, latency, MAIN_MODEL,
        )
        # Fallback without system_instruction if needed
        fallback_text = CHECK_WORK_SYSTEM_PROMPT + "\n\n" + user_text
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            fallback_text,
        ]
        config_kwargs.pop("system_instruction", None)
        config_kwargs.pop("response_mime_type", None)
        response = client.models.generate_content(
            model=MAIN_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

    parsed = parse_json(response.text)
    if not parsed:
        raise json.JSONDecodeError("No JSON found in model output", "", 0)

    return normalize_check_response(parsed)


