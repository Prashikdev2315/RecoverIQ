import os
import json
from datetime import datetime, timedelta
from anthropic import Anthropic, APIError, APITimeoutError
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TIMEOUT_SECONDS = 30
MAX_TOKENS = 1024
MODEL = "claude-3-5-sonnet-20241022"

# Circuit breaker configuration
CIRCUIT_BREAKER_THRESHOLD = 3  # Open circuit after N consecutive failures
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 300  # 5 minutes cooldown

# Circuit breaker state (in-memory, not thread-safe but sufficient for demo)
_consecutive_failures = 0
_circuit_open_until = None

def call_claude(prompt: str, system_prompt: str = None, temperature: float = 0.7) -> dict:
    """
    Call Claude API with timeout, fallback logic, and circuit breaker.

    Circuit breaker: After N consecutive failures, stops calling LLM for cooldown period.
    This prevents 30s timeouts stacking up during API outages.

    Returns dict with success status, response, and metadata.
    """
    global _consecutive_failures, _circuit_open_until

    start_time = datetime.now()

    # Circuit breaker check
    if _circuit_open_until and datetime.now() < _circuit_open_until:
        remaining = (_circuit_open_until - datetime.now()).total_seconds()
        print(f"⚠ Circuit breaker OPEN: Skipping LLM call, cooldown for {remaining:.0f}s more")

        return {
            "success": False,
            "response": None,
            "error": "circuit_breaker_open",
            "log": {
                "timestamp": start_time.isoformat(),
                "model": MODEL,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "response": None,
                "duration_seconds": 0,
                "success": False,
                "error": f"Circuit breaker open, cooldown until {_circuit_open_until.isoformat()}",
                "circuit_breaker": {
                    "state": "open",
                    "consecutive_failures": _consecutive_failures,
                    "cooldown_remaining_seconds": remaining
                }
            }
        }

    try:
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": messages,
            "temperature": temperature,
            "timeout": TIMEOUT_SECONDS
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = client.messages.create(**kwargs)

        content = response.content[0].text if response.content else ""

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Success - reset circuit breaker
        _consecutive_failures = 0
        if _circuit_open_until:
            print(f"✓ Circuit breaker CLOSED: LLM call succeeded, reset failure count")
            _circuit_open_until = None

        log_entry = {
            "timestamp": start_time.isoformat(),
            "model": MODEL,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "response": content,
            "duration_seconds": duration,
            "success": True,
            "error": None,
            "circuit_breaker": {"state": "closed", "consecutive_failures": 0}
        }

        return {
            "success": True,
            "response": content,
            "log": log_entry
        }

    except (APITimeoutError, APIError, Exception) as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Increment failure counter
        _consecutive_failures += 1

        # Determine error type
        if isinstance(e, APITimeoutError):
            error_msg = f"Timeout after {TIMEOUT_SECONDS}s"
            error_type = "timeout"
        elif isinstance(e, APIError):
            error_msg = str(e)
            error_type = "api_error"
        else:
            error_msg = f"Unexpected error: {str(e)}"
            error_type = "unexpected_error"

        # Open circuit if threshold reached
        if _consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            _circuit_open_until = datetime.now() + timedelta(seconds=CIRCUIT_BREAKER_COOLDOWN_SECONDS)
            print(f"✗ Circuit breaker OPEN: {_consecutive_failures} consecutive failures, cooling down for {CIRCUIT_BREAKER_COOLDOWN_SECONDS}s")

        print(f"⚠ Claude API {error_type}: {e} (failure {_consecutive_failures}/{CIRCUIT_BREAKER_THRESHOLD})")

        log_entry = {
            "timestamp": start_time.isoformat(),
            "model": MODEL,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "response": None,
            "duration_seconds": duration,
            "success": False,
            "error": error_msg,
            "circuit_breaker": {
                "state": "open" if _circuit_open_until else "closed",
                "consecutive_failures": _consecutive_failures,
                "threshold": CIRCUIT_BREAKER_THRESHOLD,
                "cooldown_until": _circuit_open_until.isoformat() if _circuit_open_until else None
            }
        }

        return {
            "success": False,
            "response": None,
            "error": error_type,
            "log": log_entry
        }

def parse_json_response(response: str) -> dict:
    """
    Extract and parse JSON from Claude response.
    Returns parsed dict or None if parsing fails.
    """
    try:
        # Try direct parse first
        return json.loads(response)
    except json.JSONDecodeError:
        # Try to find JSON in response
        start = response.find('{')
        end = response.rfind('}') + 1

        if start != -1 and end > start:
            try:
                return json.loads(response[start:end])
            except json.JSONDecodeError:
                pass

        print(f"⚠ Failed to parse JSON from response: {response[:200]}")
        return None
