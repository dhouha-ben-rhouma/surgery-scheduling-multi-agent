"""
security.py — Lightweight Threat Model & Defensive Controls
============================================================
Covers all five threat vectors from the spec:

  1. SECRET LEAKAGE      – redact API keys from logs / GUI output
  2. SCHEMA VALIDATION   – jsonschema + pydantic enforce input contracts
  3. PATH TRAVERSAL      – file-access restricted to project root allow-list
  4. UNBOUNDED HTTP       – outbound requests limited to an allow-listed domain set
  5. CROSS-RUN LEAKAGE   – per-run PII scrub before any log is written

Usage
-----
    from security import redact, validate_tool_input, guard_file, guard_url, scrub_log

Threat model documentation is printed by running this file directly:
    python security.py
"""

from __future__ import annotations
import re, os, json
from typing import Any

import jsonschema
from pydantic import BaseModel, Field, validator

# ══════════════════════════════════════════════════════════════════════════════
# 1. SECRET REDACTION
# ══════════════════════════════════════════════════════════════════════════════

# Patterns that look like secret tokens (API keys, bearer tokens, etc.)
_SECRET_PATTERNS = [
    re.compile(r'sk-or-v1-[A-Za-z0-9]{60,}'),          # OpenRouter
    re.compile(r'sk-[A-Za-z0-9]{40,}'),                  # OpenAI-style
    re.compile(r'Bearer\s+[A-Za-z0-9\-_\.]{20,}'),       # Bearer tokens
    re.compile(r'api[_-]?key["\s:=]+[A-Za-z0-9\-_]{16,}', re.IGNORECASE),
    re.compile(r'OPENROUTER_API_KEY\s*=\s*\S+'),
]

def redact(text: str) -> str:
    """Replace any secret-looking strings with [REDACTED]."""
    if not isinstance(text, str):
        text = str(text)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text

def redact_dict(d: dict) -> dict:
    """Recursively redact secrets from a dict (for log entries)."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = redact_dict(v)
        elif isinstance(v, str):
            out[k] = redact(v)
        else:
            out[k] = v
    return out

# ══════════════════════════════════════════════════════════════════════════════
# 2. SCHEMA VALIDATION (jsonschema + pydantic)
# ══════════════════════════════════════════════════════════════════════════════

# JSON Schema definitions for every tool call
_TOOL_SCHEMAS: dict[str, dict] = {
    "add_patient": {
        "type": "object",
        "properties": {
            "patient_name": {"type": "string",  "minLength": 1, "maxLength": 120},
            "urgency":      {"type": "string",  "enum": ["high", "medium", "low"]},
            "duration":     {"type": "number",  "minimum": 0.5, "maximum": 24},
            "date":         {"type": "string",  "pattern": r"^\d{2}-\d{2}-\d{4}$"},
        },
        "required": ["patient_name", "urgency", "duration", "date"],
        "additionalProperties": False,
    },
    "allocate_rooms": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "update_patient": {
        "type": "object",
        "properties": {
            "patient_id":   {"type": "integer", "minimum": 1},
            "patient_name": {"type": "string",  "minLength": 1, "maxLength": 120},
            "urgency":      {"type": "string",  "enum": ["high", "medium", "low"]},
            "duration":     {"type": "number",  "minimum": 0.5, "maximum": 24},
            "date":         {"type": "string",  "pattern": r"^\d{2}-\d{2}-\d{4}$"},
        },
        "required": ["patient_id"],
        "additionalProperties": False,
    },
    "delete_patient": {
        "type": "object",
        "properties": {
            "patient_id": {"type": "integer", "minimum": 1},
        },
        "required": ["patient_id"],
        "additionalProperties": False,
    },
    "unschedule_patient": {
        "type": "object",
        "properties": {
            "patient_id": {"type": "integer", "minimum": 1},
        },
        "required": ["patient_id"],
        "additionalProperties": False,
    },
}

# Pydantic models for stronger runtime guarantees
class AddPatientModel(BaseModel):
    patient_name: str = Field(..., min_length=1, max_length=120)
    urgency:      str = Field(..., pattern=r'^(high|medium|low)$')
    duration:     float = Field(..., ge=0.5, le=24)
    date:         str = Field(..., pattern=r'^\d{2}-\d{2}-\d{4}$')

class UpdatePatientModel(BaseModel):
    patient_id:   int  = Field(..., ge=1)
    patient_name: str  = Field(None, min_length=1, max_length=120)
    urgency:      str  = Field(None, pattern=r'^(high|medium|low)$')
    duration:     float = Field(None, ge=0.5, le=24)
    date:         str  = Field(None, pattern=r'^\d{2}-\d{2}-\d{4}$')

class PatientIdModel(BaseModel):
    patient_id: int = Field(..., ge=1)


def validate_tool_input(tool_name: str, params: dict) -> tuple[bool, str]:
    """
    Validate tool call params against JSON Schema then Pydantic.
    Returns (True, "") on success, (False, error_message) on failure.
    """
    schema = _TOOL_SCHEMAS.get(tool_name)
    if schema is None:
        return False, f"Unknown tool '{tool_name}'"

    # --- JSON Schema pass ---
    try:
        jsonschema.validate(instance=params, schema=schema)
    except jsonschema.ValidationError as e:
        return False, f"Schema violation: {e.message}"

    # --- Pydantic pass (for tools that need it) ---
    try:
        if tool_name == "add_patient":
            AddPatientModel(**params)
        elif tool_name == "update_patient":
            UpdatePatientModel(**params)
        elif tool_name in ("delete_patient", "unschedule_patient"):
            PatientIdModel(**params)
    except Exception as e:
        return False, f"Type validation failed: {e}"

    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# 3. PATH TRAVERSAL GUARD
# ══════════════════════════════════════════════════════════════════════════════

_ALLOWED_FILES = {"patients.csv", "rooms_schedule.csv", "logs.txt"}

def guard_file(path: str) -> tuple[bool, str]:
    """
    Allow only the pre-approved CSV/log files in the project root.
    Blocks any path that escapes the working directory.
    """
    name = os.path.basename(os.path.normpath(path))
    abs_path = os.path.realpath(path)
    cwd = os.path.realpath(os.getcwd())
    if not abs_path.startswith(cwd):
        return False, f"Path traversal blocked: '{path}'"
    if name not in _ALLOWED_FILES:
        return False, f"File '{name}' not in allow-list"
    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# 4. OUTBOUND HTTP ALLOW-LIST
# ══════════════════════════════════════════════════════════════════════════════

_ALLOWED_DOMAINS = {
    "openrouter.ai",
    "api.worldbank.org",          # World Bank open data
    "api.imf.org",                # IMF data
    "comtradeapi.un.org",         # UN Comtrade
    "databank.worldbank.org",
}

def guard_url(url: str) -> tuple[bool, str]:
    """Block any HTTP call whose host is not in the allow-list."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().split(":")[0]
        # strip www.
        if host.startswith("www."):
            host = host[4:]
        for allowed in _ALLOWED_DOMAINS:
            if host == allowed or host.endswith("." + allowed):
                return True, ""
        return False, f"Domain '{host}' not in HTTP allow-list"
    except Exception as e:
        return False, f"URL parse error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# 5. CROSS-RUN PII SCRUB
# ══════════════════════════════════════════════════════════════════════════════

# Fields that might carry PII and should be scrubbed in exported/shared logs
_PII_KEYS = {"patient_name", "name"}

def scrub_log(entry: dict) -> dict:
    """
    Return a copy of a log entry with patient names anonymised.
    Keeps structure intact; replaces name values with 'Patient-<id>'.
    """
    import copy
    entry = copy.deepcopy(entry)
    detail = entry.get("detail") or {}
    if isinstance(detail, dict):
        for key in _PII_KEYS:
            if key in detail:
                detail[key] = "[ANONYMISED]"
        entry["detail"] = detail
    # Also scrub secrets from free-text message
    entry["message"] = redact(entry.get("message", ""))
    return entry


# ══════════════════════════════════════════════════════════════════════════════
# THREAT MODEL DOCUMENTATION
# ══════════════════════════════════════════════════════════════════════════════

THREAT_MODEL = """
╔══════════════════════════════════════════════════════════════════╗
║           LIGHTWEIGHT THREAT MODEL — Hospital Scheduler          ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  THREAT 1: Secret / API-key leakage                              ║
║  ─────────────────────────────────                               ║
║  Risk:    LLM output or log file exposes OPENROUTER_API_KEY.     ║
║  Control: redact() strips all secret-pattern strings before any  ║
║           text is written to logs.txt or displayed in the GUI.   ║
║  Where:   security.redact() called in agent.save_log()           ║
║                                                                  ║
║  THREAT 2: Prompt injection via tool arguments                   ║
║  ─────────────────────────────────────────────                   ║
║  Risk:    LLM passes malformed/oversized params to a tool,       ║
║           crashing the system or corrupting data.                ║
║  Control: validate_tool_input() (JSON Schema + Pydantic) rejects ║
║           unknown fields, wrong types, and out-of-range values   ║
║           before any tool function is invoked.                   ║
║  Where:   called in agent.worker_agent() after tool_calls parse. ║
║                                                                  ║
║  THREAT 3: Path traversal                                        ║
║  ────────────────────────                                        ║
║  Risk:    An adversarial directive causes a tool to open         ║
║           /etc/passwd or ../secrets via relative paths.          ║
║  Control: guard_file() checks realpath() stays inside CWD and    ║
║           that the filename is in the hard-coded allow-list.     ║
║  Where:   called at the top of read_csv() / write_csv().         ║
║                                                                  ║
║  THREAT 4: Unbounded outbound HTTP                               ║
║  ─────────────────────────────────                               ║
║  Risk:    A rogue tool or LLM call exfiltrates data to an        ║
║           attacker-controlled server.                            ║
║  Control: guard_url() checks every outbound URL against a        ║
║           hard-coded allow-list of domains.                      ║
║  Where:   called in scenario.py before external API fetches.     ║
║                                                                  ║
║  THREAT 5: Cross-run PII leakage                                 ║
║  ───────────────────────────────                                 ║
║  Risk:    Patient names from run N appear in the trace panel     ║
║           of run N+1.                                            ║
║  Control: scrub_log() anonymises patient_name in log entries     ║
║           before they are stored; the GUI read-only trace panel  ║
║           shows anonymised entries by default.                   ║
║  Where:   called in agent.save_log().                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

if __name__ == "__main__":
    print(THREAT_MODEL)

    # Quick self-test
    print("── Self-tests ──────────────────────────────────────")

    # Secret redaction
    key = "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"
    assert "[REDACTED]" in redact(key), "redact() failed"
    print("[OK]  Secret redaction")

    # Schema validation — valid
    ok, msg = validate_tool_input("add_patient", {
        "patient_name": "Alice", "urgency": "high", "duration": 1, "date": "19-04-2026"
    })
    assert ok, f"Valid input rejected: {msg}"
    print("[OK]  Schema valid input accepted")

    # Schema validation — invalid urgency
    ok, msg = validate_tool_input("add_patient", {
        "patient_name": "Bob", "urgency": "critical", "duration": 1, "date": "19-04-2026"
    })
    assert not ok, "Invalid urgency should be rejected"
    print("[OK]  Schema invalid input rejected")

    # Schema validation — unknown field
    ok, msg = validate_tool_input("add_patient", {
        "patient_name": "Carol", "urgency": "low", "duration": 1,
        "date": "19-04-2026", "extra_field": "hacked"
    })
    assert not ok, "Additional properties should be rejected"
    print("[OK]  Unknown field rejected")

    # Path traversal
    ok, _ = guard_file("../etc/passwd")
    assert not ok
    ok, _ = guard_file("patients.csv")
    assert ok
    print("[OK]  Path traversal guard")

    # URL allow-list
    ok, _ = guard_url("https://api.worldbank.org/v2/country")
    assert ok
    ok, _ = guard_url("https://evil.com/exfil")
    assert not ok
    print("[OK]  HTTP allow-list")

    print("\n[OK]  All security self-tests passed.")
