import json
import os
import re
import time
import warnings
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError
from dotenv import load_dotenv

load_dotenv()

# Read LLM configuration from environment variables with defaults
BASE_URL = os.environ.get("WIKI_LLM_URL", "http://10.6.12.18:9001/v1")
API_KEY = os.environ.get("WIKI_API_KEY", "EMPTY")
MODEL = os.environ.get("WIKI_LLM_MODEL", "cyankiwi/Qwen3.5-27B-AWQ-4bit")

# Warn if using default values
if BASE_URL == "http://localhost:8000/v1":
    warnings.warn(
        "WIKI_LLM_URL not set, using default: http://localhost:8000/v1. "
        "Set WIKI_LLM_URL environment variable to point to your LLM server."
    )
if API_KEY == "EMPTY":
    warnings.warn(
        "WIKI_API_KEY not set, using default: EMPTY. "
        "Set WIKI_API_KEY environment variable with your API key."
    )
if MODEL == "gpt-4":
    warnings.warn(
        "WIKI_LLM_MODEL not set, using default: gpt-4. "
        "Set WIKI_LLM_MODEL environment variable with your model name."
    )


class LLMError(Exception):
    """Custom exception for LLM-related errors."""
    def __init__(self, message: str, error_type: str = "unknown", retryable: bool = False):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


def get_client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY)


def chat(
    client: OpenAI,
    messages: list[dict],
    temperature: float = 0.3,
    timeout: float = 60.0,
    max_retries: int = 3,
    initial_delay: float = 1.0,
) -> str:
    """Chat with the LLM with error handling and retry logic.

    Args:
        client: OpenAI client instance
        messages: List of message dicts
        temperature: Temperature for generation
        timeout: Request timeout in seconds (default 60)
        max_retries: Maximum number of retry attempts (default 3)
        initial_delay: Initial delay before first retry in seconds (default 1)

    Returns:
        The response content as a string

    Raises:
        LLMError: If all retries are exhausted or a non-retryable error occurs
    """
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
                timeout=timeout,
            )
            return response.choices[0].message.content or ""

        except RateLimitError as e:
            # Rate limit - retry with exponential backoff
            last_error = e
            error_msg = f"Rate limit exceeded (attempt {attempt + 1}/{max_retries + 1})"
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                continue
            raise LLMError(error_msg, "rate_limit", retryable=True)

        except APIConnectionError as e:
            # Connection error - retry with exponential backoff
            last_error = e
            error_msg = f"Connection error (attempt {attempt + 1}/{max_retries + 1})"
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise LLMError(error_msg, "connection", retryable=True)

        except APITimeoutError as e:
            # Timeout - retry with exponential backoff
            last_error = e
            error_msg = f"Request timeout (attempt {attempt + 1}/{max_retries + 1})"
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise LLMError(error_msg, "timeout", retryable=True)

        except APIError as e:
            # Other API errors - may or may not be retryable
            last_error = e
            # Check if it's a server error (5xx) which is retryable
            retryable = hasattr(e, 'status_code') and e.status_code is not None and e.status_code >= 500
            error_msg = f"API error: {e.message if hasattr(e, 'message') else str(e)}"
            if retryable and attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise LLMError(error_msg, "api_error", retryable=retryable)

        except Exception as e:
            # Unknown errors - don't retry
            raise LLMError(f"Unexpected error: {str(e)}", "unknown", retryable=False)

    # Should not reach here, but just in case
    raise LLMError(
        f"All {max_retries + 1} attempts failed. Last error: {str(last_error)}",
        "max_retries",
        retryable=False
    )


def extract_json(text: str) -> dict:
    # Strip <think>...</think> blocks (Qwen3 thinking mode)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    # Try ```json ... ``` block
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match and match.group(1).strip():
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try first top-level JSON object
    match = re.search(r"(\{[\s\S]+\})", text)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"No JSON found in response:\n{text[:300]}")
