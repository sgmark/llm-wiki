"""Tests for LLM-related functions in wiki_core.llm."""
import pytest
from wiki_core.llm import extract_json


class TestExtractJson:
    """Test cases for extract_json function."""

    def test_valid_json_object(self):
        """Test extraction of a simple valid JSON object."""
        text = '{"key": "value", "number": 42}'
        result = extract_json(text)
        assert result == {"key": "value", "number": 42}

    def test_valid_json_in_code_block(self):
        """Test extraction of JSON inside markdown code block."""
        text = """Here's the result:
```json
{"key": "value", "nested": {"a": 1}}
```
Some more text."""
        result = extract_json(text)
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_valid_json_in_code_block_without_json_tag(self):
        """Test extraction of JSON inside code block without 'json' language tag."""
        text = """```
{"items": [1, 2, 3]}
```"""
        result = extract_json(text)
        assert result == {"items": [1, 2, 3]}

    def test_qwen3_thinking_block_stripped(self):
        """Test that Qwen3 <think>...</think> thinking blocks are removed."""
        text = """<think>
This is my internal thinking process.
I need to analyze the request carefully.
</think>
{"result": "success", "data": [1, 2, 3]}"""
        result = extract_json(text)
        assert result == {"result": "success", "data": [1, 2, 3]}

    def test_qwen3_thinking_block_with_code_block(self):
        """Test Qwen3 thinking block combined with code block."""
        text = """<think>
Let me think about this...
</think>
```json
{"answer": "found", "confidence": 0.95}
```"""
        result = extract_json(text)
        assert result == {"answer": "found", "confidence": 0.95}

    def test_multiple_thinking_blocks(self):
        """Test multiple thinking blocks are all stripped."""
        text = """<think>
First thought
</think>
Some text
<think>
Second thought
</think>
{"final": "result"}"""
        result = extract_json(text)
        assert result == {"final": "result"}

    def test_json_with_nested_objects(self):
        """Test extraction of JSON with deeply nested objects."""
        text = """{"outer": {"middle": {"inner": "value", "list": [1, 2, {"key": "val"}]}}}"""
        result = extract_json(text)
        assert result["outer"]["middle"]["inner"] == "value"
        assert result["outer"]["middle"]["list"] == [1, 2, {"key": "val"}]

    def test_json_with_special_characters(self):
        """Test JSON with escaped special characters."""
        text = '{"message": "Hello \\nWorld", "quote": "He said \\"Hi\\""}'
        result = extract_json(text)
        assert result["message"] == "Hello \nWorld"
        assert result["quote"] == 'He said "Hi"'

    def test_json_with_unicode(self):
        """Test JSON with unicode characters."""
        text = '{"emoji": "🎉", "chinese": "你好", "arabic": "مرحبا"}'
        result = extract_json(text)
        assert result["emoji"] == "🎉"
        assert result["chinese"] == "你好"

    def test_malformed_json_in_code_block_falls_back(self):
        """Test that malformed JSON in code block falls back to finding any JSON."""
        text = """```json
{"invalid": json}
```
{"valid": "json"}"""
        # The fallback regex will try to parse the malformed JSON first
        # So this will raise ValueError
        with pytest.raises(ValueError):
            extract_json(text)

    def test_no_json_found_raises_value_error(self):
        """Test that ValueError is raised when no JSON is found."""
        text = "This is just plain text with no JSON at all."
        with pytest.raises(ValueError, match="No JSON found"):
            extract_json(text)

    def test_only_thinking_block_raises_value_error(self):
        """Test that only thinking blocks (no JSON) raises ValueError."""
        text = """<think>
I'm thinking but not producing JSON
</think>"""
        with pytest.raises(ValueError, match="No JSON found"):
            extract_json(text)

    def test_empty_string_raises_value_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="No JSON found"):
            extract_json("")

    def test_empty_code_block_raises_value_error(self):
        """Test that empty code block raises ValueError."""
        text = "```\n```"
        with pytest.raises(ValueError, match="No JSON found"):
            extract_json(text)

    def test_json_with_only_code_block_content(self):
        """Test extraction when JSON is only in code block."""
        text = """Some intro text
```json
{"extracted": true}
```
Some outro text"""
        result = extract_json(text)
        assert result == {"extracted": True}

    def test_malformed_json_raises_value_error(self):
        """Test that malformed JSON raises ValueError."""
        text = '{"key": "value"'  # Missing closing brace
        with pytest.raises(ValueError):
            extract_json(text)

    def test_json_array_at_top_level(self):
        """Test that top-level JSON array is handled."""
        text = '[1, 2, 3, {"key": "value"}]'
        # extract_json looks for objects with {, so this will fail
        # The regex will match the inner object {"key": "value"}
        result = extract_json(text)
        assert result == {"key": "value"}

    def test_whitespace_only_raises_value_error(self):
        """Test that whitespace-only string raises ValueError."""
        text = "   \n\t  "
        with pytest.raises(ValueError, match="No JSON found"):
            extract_json(text)

    def test_json_with_comments_fails(self):
        """Test that JSON with comments (invalid JSON) fails."""
        text = '{"key": "value" // comment}'
        with pytest.raises(ValueError):
            extract_json(text)

    def test_very_large_json_object(self):
        """Test extraction of a large JSON object."""
        large_data = {f"key_{i}": f"value_{i}" for i in range(1000)}
        text = str(large_data).replace("'", '"')
        result = extract_json(text)
        assert len(result) == 1000
        assert result["key_0"] == "value_0"
        assert result["key_999"] == "value_999"

    def test_json_with_null_values(self):
        """Test JSON with null values."""
        text = '{"a": null, "b": "value", "c": null}'
        result = extract_json(text)
        assert result["a"] is None
        assert result["b"] == "value"
        assert result["c"] is None

    def test_json_with_boolean_values(self):
        """Test JSON with boolean values."""
        text = '{"true_val": true, "false_val": false, "mixed": true}'
        result = extract_json(text)
        assert result["true_val"] is True
        assert result["false_val"] is False
        assert result["mixed"] is True

    def test_json_with_float_values(self):
        """Test JSON with float values."""
        text = '{"pi": 3.14159, "negative": -2.5, "scientific": 1.5e10}'
        result = extract_json(text)
        assert abs(result["pi"] - 3.14159) < 0.0001
        assert result["negative"] == -2.5
        assert result["scientific"] == 1.5e10

    def test_multiline_json_string(self):
        """Test JSON with multiline string values."""
        text = '{"paragraph": "Line 1\\nLine 2\\nLine 3"}'
        result = extract_json(text)
        assert result["paragraph"] == "Line 1\nLine 2\nLine 3"

    def test_json_with_empty_objects_and_arrays(self):
        """Test JSON with empty objects and arrays."""
        text = '{"empty_obj": {}, "empty_arr": [], "nested_empty": {"a": {}}}'
        result = extract_json(text)
        assert result["empty_obj"] == {}
        assert result["empty_arr"] == []
        assert result["nested_empty"] == {"a": {}}
