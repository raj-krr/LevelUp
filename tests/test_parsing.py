"""Unit tests for JSON parsing and response normalization in LevelUp."""

import pytest
from ai import parse_json, normalize_response, RESPONSE_DEFAULTS


class TestParseJson:
    def test_clean_json(self):
        sample = '{"subject": "math", "confidence": "high"}'
        result = parse_json(sample)
        assert result == {"subject": "math", "confidence": "high"}

    def test_json_in_markdown_fence(self):
        sample = """```json
{
  "subject": "science",
  "confidence": "medium"
}
```"""
        result = parse_json(sample)
        assert result is not None
        assert result["subject"] == "science"
        assert result["confidence"] == "medium"

    def test_json_with_preamble_and_postamble(self):
        sample = """Here is your homework analysis:
{
  "subject": "math",
  "image_quality": "good",
  "confidence": "high"
}
Hope this helps!"""
        result = parse_json(sample)
        assert result is not None
        assert result["subject"] == "math"
        assert result["confidence"] == "high"

    def test_nested_json(self):
        sample = """{
  "hints": {
    "nudge": "Look at the units",
    "bigger_hint": "Divide by 10",
    "full_solution": "42"
  }
}"""
        result = parse_json(sample)
        assert result is not None
        assert result["hints"]["nudge"] == "Look at the units"
        assert result["hints"]["full_solution"] == "42"

    def test_invalid_json(self):
        assert parse_json("Not valid json at all") is None
        assert parse_json("") is None
        assert parse_json(None) is None


class TestNormalizeResponse:
    def test_fills_missing_keys(self):
        partial = {"subject": "math"}
        normalized = normalize_response(partial)
        for key in RESPONSE_DEFAULTS:
            assert key in normalized
        assert normalized["subject"] == "math"
        assert normalized["image_quality"] == "good"
        assert normalized["confidence"] == "medium"
        assert isinstance(normalized["hints"], dict)
        assert "nudge" in normalized["hints"]
        assert "bigger_hint" in normalized["hints"]
        assert "full_solution" in normalized["hints"]

    def test_clamps_confidence(self):
        assert normalize_response({"confidence": "super_high"})["confidence"] == "medium"
        assert normalize_response({"confidence": "low"})["confidence"] == "low"
        assert normalize_response({"confidence": "high"})["confidence"] == "high"

    def test_clamps_image_quality(self):
        assert normalize_response({"image_quality": "poor"})["image_quality"] == "poor"
        assert normalize_response({"image_quality": "blurry"})["image_quality"] == "good"

    def test_clamps_subject(self):
        assert normalize_response({"subject": "Math"})["subject"] == "math"
        assert normalize_response({"subject": "SCIENCE"})["subject"] == "science"
        assert normalize_response({"subject": "astronomy"})["subject"] == "other"

    def test_forces_lists_and_strings(self):
        res = normalize_response({
            "teach_script": "Just count apples",
            "key_terms": [
                {"term": "Numerator", "meaning": "Top number"},
                {"term": "Denominator", "meaning": "Bottom number"},
                {"term": "Fraction", "meaning": "Part of a whole"},
                {"term": "Ratio", "meaning": "Comparison"},
                {"term": "Extra", "meaning": "Exceeds 4 items"}
            ]
        })
        assert isinstance(res["teach_script"], list)
        assert len(res["teach_script"]) == 1
        assert len(res["key_terms"]) == 4  # max 4
        assert res["key_terms"][0]["term"] == "Numerator"


if __name__ == "__main__":
    pytest.main([__file__])
