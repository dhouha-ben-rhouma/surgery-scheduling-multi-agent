"""
failure_config.py — Fault-injection for scenario testing
=========================================================
Provides a shared FAILURE_MODE dict and two monkey-patch helpers:

  patch_tools()   — wraps every TOOL_FUNCTION so it can simulate
                    random errors, slow timeouts, and corrupt output.

  patch_chat()    — wraps agent.chat() so it can simulate HTTP-429
                    rate-limit responses without hitting the real API.

Usage
-----
    from failure_config import FAILURE_MODE, patch_tools, patch_chat
    patch_tools()   # call once, after importing tools
    patch_chat()    # call once, after importing agent

    FAILURE_MODE["random_error"] = True   # inject random errors
    FAILURE_MODE["timeout"]      = True   # inject slow calls
    FAILURE_MODE["rate_limit"]   = True   # inject HTTP-429 on chat
    FAILURE_MODE["corrupt_output"]= True  # inject malformed tool output

Resetting
---------
    FAILURE_MODE["random_error"] = False  # etc.

All flags default to False — production behaviour is unchanged unless
a flag is explicitly set.
"""

from __future__ import annotations
import time
import random
import types

# ── Shared fault-injection state ──────────────────────────────────────────────
FAILURE_MODE: dict[str, bool] = {
    "random_error":   False,   # 60 % chance each tool call raises an error
    "timeout":        False,   # sleep 8 s before every tool call
    "rate_limit":     False,   # chat() returns a fake HTTP-429 object
    "corrupt_output": False,   # tool returns structurally wrong data
}

# ── Tool-layer patch ──────────────────────────────────────────────────────────

def patch_tools() -> None:
    """
    Wrap every function in tools.TOOL_FUNCTIONS so fault flags are
    evaluated at call time.  Safe to call multiple times (idempotent).
    """
    import tools as _tools

    if getattr(_tools, "_FAILURE_PATCHED", False):
        return  # already patched
    _tools._FAILURE_PATCHED = True

    original: dict = dict(_tools.TOOL_FUNCTIONS)  # snapshot

    def _make_wrapper(name: str, fn):
        def wrapper(*args, **kwargs):
            # ── timeout ───────────────────────────────────────────────────────
            if FAILURE_MODE.get("timeout"):
                print(f"  [FAILURE_CONFIG] timeout injected — sleeping 8 s before '{name}'")
                time.sleep(8)

            # ── random error ──────────────────────────────────────────────────
            if FAILURE_MODE.get("random_error") and random.random() < 0.60:
                msg = f"Simulated random error in '{name}' (failure_config)"
                print(f"  [FAILURE_CONFIG] random_error triggered for '{name}'")
                return {"status": "error", "message": msg, "data": None}

            # ── corrupt output ────────────────────────────────────────────────
            if FAILURE_MODE.get("corrupt_output"):
                print(f"  [FAILURE_CONFIG] corrupt_output injected for '{name}'")
                return {"bad_key": True, "status": None, "data": "CORRUPTED"}

            # Normal execution
            return fn(*args, **kwargs)

        wrapper.__name__ = name
        return wrapper

    for name, fn in original.items():
        _tools.TOOL_FUNCTIONS[name] = _make_wrapper(name, fn)

    print("[failure_config] tool-layer fault injection ACTIVE")


# ── Chat-layer patch ──────────────────────────────────────────────────────────

class _Fake429:
    """Minimal stub that mimics an OpenAI completion response for a 429."""
    class _Choice:
        class _Message:
            content = '{"valid": false, "reason": "Rate limit (simulated 429)."}'
            tool_calls = None
        message = _Message()
    choices = [_Choice()]


def patch_chat() -> None:
    """
    Replace agent.chat() with a wrapper that returns a fake 429 object
    when FAILURE_MODE['rate_limit'] is True, and delegates to the real
    function otherwise.  Safe to call multiple times (idempotent).
    """
    import agent as _agent

    if getattr(_agent, "_CHAT_PATCHED", False):
        return
    _agent._CHAT_PATCHED = True

    _real_chat = _agent.chat

    def _patched_chat(*args, **kwargs):
        if FAILURE_MODE.get("rate_limit"):
            print("  [FAILURE_CONFIG] rate_limit injected — returning fake HTTP-429")
            return _Fake429()
        return _real_chat(*args, **kwargs)

    _agent.chat = _patched_chat
    print("[failure_config] chat-layer fault injection ACTIVE")