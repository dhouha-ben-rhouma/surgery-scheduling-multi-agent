"""project by Touka Tammar 2BIS1
Dhouha ben rhouma 2BIS1
Sarra mejri 2BIS1
Fedi neffousi 2BIS1
Roua Charfeddine 2BIS1
"""
"""
agent.py — Hospital Surgery Scheduling Multi-Agent System
"""

import os
import json
import textwrap
import uuid
import time
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS

from planner import (
    PlannerState,
    plan_next_action,
    format_preemption_summary,
    close_room, open_room,
    forbid_action, allow_action,
)

from security import redact, validate_tool_input, scrub_log

load_dotenv()

client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

MODEL     = "nvidia/nemotron-3-super-120b-a12b:free"
MAX_STEPS = 5

# ── Logging helpers ───────────────────────────────────────────────────────────

CURRENT_RUN_ID = "run-init"

def _redact_dict(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _redact_dict(v)
        elif isinstance(v, str):
            out[k] = redact(v)
        else:
            out[k] = v
    return out

def save_log(entry_dict):
    safe = scrub_log(_redact_dict(entry_dict))
    with open("logs.txt", "a") as f:
        f.write(json.dumps(safe) + "\n")

RESET  = "\033[0m";  BOLD   = "\033[1m"
PURPLE = "\033[95m"; GREEN  = "\033[92m"
YELLOW = "\033[93m"; RED    = "\033[91m"
CYAN   = "\033[96m"; GRAY   = "\033[90m"

import re

def strip_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def log(agent: str, msg: str, color: str = RESET, detail: dict = None,
        latency_ms: float | None = None):
    tag = f"{BOLD}{color}[{agent.upper()}]{RESET}"
    lat = f"  {GRAY}({latency_ms:.0f} ms){RESET}" if latency_ms is not None else ""
    print(f"\n{tag} {msg}{lat}")

    log_entry = {
        "time":       datetime.now().isoformat(),
        "run_id":     CURRENT_RUN_ID,
        "agent":      agent.lower(),
        "message":    strip_ansi_codes(msg),
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        "detail":     detail,
    }
    save_log(log_entry)

    if detail:
        try:
            dumped = json.dumps(detail, indent=2, ensure_ascii=False)
            for line in dumped.splitlines():
                print(f"  {GRAY}{line}{RESET}")
        except TypeError:
            print(f"  {GRAY}{detail}{RESET}")

def separator():
    print(f"\n{GRAY}{'-' * 60}{RESET}")

# ── OpenRouter chat helper ────────────────────────────────────────────────────

def chat(system: str, user: str, json_mode: bool = False, tools: list = None):
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        import sys
        err_msg = redact(str(e))
        if "429" in err_msg or "Rate limit" in err_msg:
            print(f"\nAPI ERROR: Rate limit exceeded for the AI model. Please wait or change the model in agent.py.")
        else:
            print(f"\nAPI ERROR: {err_msg}")
        sys.exit(1)

# ── Agent roles ───────────────────────────────────────────────────────────────

def _load_patient_roster() -> str:
    import csv
    try:
        with open("patients.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return "No patients registered yet."
        lines = [
            f"  #{r['patient_id'].strip()} {r['patient_name'].strip()} "
            f"({r['urgency'].strip()}, {r['status'].strip()})"
            for r in rows
        ]
        return "\n".join(lines)
    except FileNotFoundError:
        return "No patients registered yet."


def planner_agent(user_message: str) -> tuple[str, str, dict]:
    log("planner", "Generating task directive...", PURPLE)
    t0 = time.perf_counter()

    patient_roster = _load_patient_roster()

    system = textwrap.dedent(f"""
        You are a Hospital Surgery Scheduling Planner.

        CURRENT PATIENT LIST (use this to resolve names to numeric IDs):
{patient_roster}

        Analyze the user request and output ONLY a JSON object (no extra text) with:
        {{
          "directive": "<instruction string for the worker>",
          "action": "<tool name>",
          "params": {{ <tool parameters> }}
        }}

        Available tools:
        1. add_patient(patient_name, urgency, duration, date)
        2. allocate_rooms()   — no params
        3. update_patient(patient_id, patient_name?, urgency?, duration?, date?)
        4. delete_patient(patient_id)
        5. unschedule_patient(patient_id)

        RULES:
        - For add_patient: NEVER include patient_id (auto-incremented).
        - For allocate_rooms: params must be {{}}.
        - urgency: "high" | "medium" | "low"
        - duration: float (hours)
        - date format: DD-MM-YYYY
        - For delete_patient / update_patient / unschedule_patient: patient_id MUST be
          a numeric integer. Look up the name in the CURRENT PATIENT LIST above to find
          the correct numeric ID. NEVER pass a name as patient_id.

        EXAMPLES:
        User: "Add patient John Doe, urgency high, 2 hours, 19-04-2026"
        -> {{"directive":"use add_patient with patient_name=\\"John Doe\\", urgency=\\"high\\", duration=2, date=\\"19-04-2026\\"",
           "action":"add_patient",
           "params":{{"patient_name":"John Doe","urgency":"high","duration":2,"date":"19-04-2026"}}}}

        User: "Allocate all patients"
        -> {{"directive":"use allocate_rooms with no arguments","action":"allocate_rooms","params":{{}}}}

        User: "Update patient 3, urgency to medium"
        -> {{"directive":"use update_patient with patient_id=3, urgency=\\"medium\\"",
           "action":"update_patient","params":{{"patient_id":3,"urgency":"medium"}}}}

        User: "Delete Bob"   (Bob is #2 in the list above)
        -> {{"directive":"use delete_patient with patient_id=2",
           "action":"delete_patient","params":{{"patient_id":2}}}}
    """)

    response = chat(system=system, user=user_message, json_mode=True)
    latency_ms = (time.perf_counter() - t0) * 1000
    raw = response.choices[0].message.content.strip()

    try:
        parsed    = json.loads(raw)
        directive = parsed.get("directive", "")
        action    = parsed.get("action", "")
        params    = parsed.get("params", {})
    except Exception:
        directive = raw
        action    = ""
        params    = {}

    log("planner", f"Directive: {BOLD}{directive}{RESET}", PURPLE,
        latency_ms=latency_ms)
    return directive, action, params


def worker_agent(task_directive: str) -> tuple[dict, object]:
    log("worker", f"Fulfilling directive: {BOLD}{task_directive}{RESET}", GREEN)
    t0 = time.perf_counter()

    system = textwrap.dedent(f"""
        You are a Hospital Surgery Scheduling Specialist.
        Your goal is to fulfil this specific instruction: "{task_directive}"

        You have access to tools. Always call the appropriate tool — do not guess.

        IMPORTANT RULES:
        - For add_patient: NEVER pass a patient_id.
        - For allocate_rooms: call it with NO arguments.
        - For update_patient: only pass the fields that need to change plus patient_id.
        - For delete_patient: only pass the patient_id.
        - For unschedule_patient: only pass the patient_id.

        Once you have the tool result, return it as-is.
    """)

    response = chat(
        system=system,
        user=f"Please execute: {task_directive}",
        tools=TOOL_DECLARATIONS,
    )

    message = response.choices[0].message

    if message.tool_calls:
        tc        = message.tool_calls[0]
        tool_name = tc.function.name
        try:
            tool_args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            tool_args = {}

        latency_ms = (time.perf_counter() - t0) * 1000
        log("worker", f"Calling tool: {BOLD}{tool_name}{RESET}", GREEN,
            tool_args, latency_ms=latency_ms)

        # ── SECURITY: Schema + Pydantic validation before tool execution ──────
        valid, validation_err = validate_tool_input(tool_name, tool_args)
        if not valid:
            err_result = {
                "status":  "error",
                "message": f"[SECURITY] Schema validation failed: {validation_err}",
                "data":    None,
            }
            log("worker", f"Schema validation BLOCKED: {validation_err}", RED)
            return err_result, response

        if tool_name in TOOL_FUNCTIONS:
            t1 = time.perf_counter()
            try:
                result = TOOL_FUNCTIONS[tool_name](**tool_args)
            except Exception as e:
                result = {"status": "error", "message": str(e), "data": None}
            tool_ms = (time.perf_counter() - t1) * 1000
        else:
            result   = {"status": "error", "message": f"Tool '{tool_name}' not found.", "data": None}
            tool_ms  = 0

        log("worker", "Tool output received.", GREEN, result, latency_ms=tool_ms)
        return result, response
    else:
        latency_ms = (time.perf_counter() - t0) * 1000
        log("worker", "No tool called.", RED, latency_ms=latency_ms)
        return {"status": "error", "message": "Worker did not call any tool.", "data": None}, response


def critic_agent(user_message: str, worker_result: dict) -> dict:
    log("critic", "Analysing worker result...", YELLOW)
    t0 = time.perf_counter()

    system = textwrap.dedent("""
        You are a QA Critic for a Hospital Surgery Scheduling System.

        Evaluate whether the Worker's tool result correctly fulfils the user's request.

        Check:
        1. Did the tool return "success" status? "error" -> invalid.
        2. Is the returned data complete and relevant?
        3. add_patient  -> patient in result with auto-incremented ID?
        4. allocate_rooms -> room assignments with start + end times?
        5. update_patient -> only allowed fields updated?
        6. delete_patient -> patient deleted successfully?
        7. unschedule_patient -> patient unscheduled successfully?

        Output ONLY JSON:
        {"valid": true|false, "reason": "...", "action": "<tool_name>", "params": {}}

        Include "action" and "params" only when you can infer what retry should be attempted.
    """)

    user = textwrap.dedent(f"""
        User request: "{user_message}"
        Tool Result: {json.dumps(worker_result)}
    """)

    response = chat(system=system, user=user, json_mode=True)
    latency_ms = (time.perf_counter() - t0) * 1000

    try:
        verdict = json.loads(response.choices[0].message.content)
    except Exception:
        verdict = {"valid": False, "reason": "Critic failed to output valid JSON."}

    if verdict.get("valid"):
        log("critic", "VALIDATED [OK]  " + verdict.get("reason", ""),
            YELLOW, verdict, latency_ms=latency_ms)
    else:
        log("critic", "REJECTED [FAIL]  " + verdict.get("reason", ""),
            RED, verdict, latency_ms=latency_ms)

    return verdict


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_agent(user_message: str):
    global CURRENT_RUN_ID
    CURRENT_RUN_ID = f"run-{uuid.uuid4().hex[:6]}"

    separator()
    print(f"\n{BOLD}{CYAN}USER:{RESET} {user_message}")
    separator()

    save_log({
        "time":    datetime.now().isoformat(),
        "run_id":  CURRENT_RUN_ID,
        "agent":   "user",
        "message": "USER REQUEST",
        "detail":  {"user_message": user_message},
    })

    planner_state = PlannerState()
    directive, action, params = planner_agent(user_message)
    last_result: dict | None  = None

    steps = 0
    while steps < MAX_STEPS:
        steps += 1
        log("orchestrator", f"Cycle {steps}/{MAX_STEPS}", CYAN)

        decision = plan_next_action(
            user_message = user_message,
            action       = action,
            params       = params,
            last_result  = last_result,
            state        = planner_state,
        )

        if not decision["proceed"]:
            log("orchestrator", f"PLANNER BLOCKED: {decision['reason']}", RED)

            system = ("You are a friendly Hospital Scheduling Assistant. "
                      "Explain the following issue kindly. Don't expose internal details.")
            final_explanation = chat(
                system=system,
                user=f"User asked: '{user_message}'. Issue: {decision['reason']}",
            ).choices[0].message.content.strip()

            separator()
            print(f"\n{BOLD}{CYAN}AGENT:{RESET} {final_explanation}")
            separator()
            return final_explanation

        result, _ = worker_agent(decision["directive"])
        last_result = result

        verdict = critic_agent(user_message, result)

        if verdict.get("valid"):
            log("orchestrator", "Task complete. Generating final response.", CYAN)

            system = textwrap.dedent("""
                You are a friendly Hospital Scheduling Assistant.
                Based on the data provided, answer the user's request in plain English.
                Be concise and clear.
                - Rooms allocated -> list each patient: room, start time, end time.
                - Patient added   -> confirm name, urgency, duration, ID.
                - Patient updated -> confirm what changed.
                - Patient deleted -> confirm deletion.
                - Patient unscheduled -> confirm unscheduling.
            """)
            user_ctx = f"Original request: {user_message}\nResult: {json.dumps(result)}"
            final_text = chat(system=system, user=user_ctx).choices[0].message.content.strip()

            preemption_note = format_preemption_summary(planner_state)
            if preemption_note:
                final_text += preemption_note

            separator()
            print(f"\n{BOLD}{CYAN}AGENT:{RESET} {final_text}")
            separator()
            return final_text

        log("orchestrator", "Critic rejected result. Backtracking...", RED)

        retry_action = verdict.get("action", action) or action
        retry_params = verdict.get("params", params) or params
        action   = retry_action
        params   = retry_params
        directive = decision["directive"]

    log("orchestrator", "MAX_STEPS reached without validation.", RED)
    separator()
    msg = f"Sorry, I was unable to complete the request after {MAX_STEPS} attempts."
    print(f"\n{BOLD}{CYAN}AGENT:{RESET} {msg}")
    separator()
    return msg


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{BOLD}Hospital Surgery Scheduling Multi-Agent System{RESET}")
    print(f"{GRAY}Model: {MODEL} | Max steps: {MAX_STEPS}{RESET}")
    print(f"{GRAY}Type 'quit' to exit.{RESET}")
    print(f"{GRAY}Admin commands: close_room:<id>  open_room:<id>  "
          f"forbid:<tool>  allow:<tool>{RESET}")

    while True:
        try:
            user_input = input(f"\n{BOLD}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Bye!")
            break

        if user_input.startswith("close_room:"):
            print(close_room(user_input.split(":", 1)[1].strip()))
            continue
        if user_input.startswith("open_room:"):
            print(open_room(user_input.split(":", 1)[1].strip()))
            continue

        run_agent(user_input)
