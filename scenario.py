"""
scenario.py — Démonstration complète du système multi-agent
===========================================================
7 scénarios couvrant les cas normaux et les cas d'échec.

Scénarios
---------
1. Normal          — ajout + allocation standard
2. Rooms closed    — toutes les salles fermées -> blocage gracieux
3. Tool blocked    — allocate_rooms interdit -> blocage gracieux
4. Preemption      — patient urgent arrive, déplace un patient faible
5. Random failure  — erreurs aléatoires dans les outils (60 % chance)
6. Timeout         — délai simulé de 8 s par appel outil
7. Rate limit      — HTTP-429 simulé sur chaque appel LLM

Chaque scénario :
  - remet les CSVs à un état propre avant de démarrer
  - affiche un en-tête lisible
  - active puis désactive les flags d'injection de fautes
"""

import csv
import os
import sys

# ── 1. Patch failure hooks AVANT tout autre import du projet ──────────────────
from failure_config import FAILURE_MODE, patch_tools, patch_chat

# ── 2. Imports du projet (après le patch) ─────────────────────────────────────
from agent import run_agent
from planner import close_room, open_room, forbid_action, allow_action

# Active les couches d'injection de fautes une seule fois
patch_tools()
patch_chat()

# ── Fichiers CSV ───────────────────────────────────────────────────────────────
PATIENTS_FILE = "patients.csv"
ROOMS_FILE    = "rooms_schedule.csv"

P_COLS = ["patient_id", "patient_name", "urgency", "duration", "date", "status"]
R_COLS = ["room_id", "patient_id", "start_time", "end_time"]


# ── Helper : remettre les CSVs à un état vide propre ──────────────────────────
def reset_csv() -> None:
    """Vide les deux fichiers CSV (garde uniquement l'en-tête)."""
    for path, cols in [(PATIENTS_FILE, P_COLS), (ROOMS_FILE, R_COLS)]:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=cols).writeheader()
    print("  [RESET] CSV files cleared.")


def _header(title: str) -> None:
    bar = "=" * 56
    print(f"\n{bar}")
    print(f"  {title}")
    print(f"{bar}")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 1 — NORMAL
# ─────────────────────────────────────────────────────────────────────────────
def scenario_normal() -> None:
    _header("SCENARIO 1 - NORMAL : ajout & allocation standard")
    reset_csv()

    run_agent("Add patient Ali Ben Salem, urgency high, 1 hour, 19-04-2026")
    run_agent("Add patient Sami Trabelsi, urgency medium, 2 hours, 19-04-2026")
    run_agent("Add patient Lina Chaabane, urgency low, 1 hour, 19-04-2026")
    run_agent("Allocate all patients")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 2 — FAILURE : ROOMS CLOSED
# ─────────────────────────────────────────────────────────────────────────────
def scenario_rooms_closed() -> None:
    _header("SCENARIO 2 - FAILURE : toutes les salles fermees")
    reset_csv()

    run_agent("Add patient Youssef Ayari, urgency high, 1 hour, 19-04-2026")

    print("\n  [ADMIN] Closing all rooms...")
    close_room("room1")
    close_room("room2")
    close_room("room3")

    run_agent("Allocate all patients")

    print("\n  [ADMIN] Re-opening all rooms.")
    open_room("room1")
    open_room("room2")
    open_room("room3")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 3 — FAILURE : TOOL BLOCKED
# ─────────────────────────────────────────────────────────────────────────────
def scenario_tool_blocked() -> None:
    _header("SCENARIO 3 - FAILURE : outil allocate_rooms interdit")
    reset_csv()

    run_agent("Add patient Nour Belhaj, urgency medium, 2 hours, 20-04-2026")

    print("\n  [ADMIN] Forbidding allocate_rooms (maintenance)...")
    forbid_action("allocate_rooms")

    run_agent("Allocate all patients")

    print("\n  [ADMIN] Allowing allocate_rooms again.")
    allow_action("allocate_rooms")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 4 — PREEMPTION
# ─────────────────────────────────────────────────────────────────────────────
def scenario_preemption() -> None:
    _header("SCENARIO 4 - PREEMPTION : patient urgent deplace un patient faible")
    reset_csv()

    run_agent("Add patient Amina Sassi, urgency low, 1 hour, 19-04-2026")
    run_agent("Add patient Bilel Mansour, urgency medium, 2 hours, 19-04-2026")
    run_agent("Add patient Cyrine Rejeb, urgency low, 1 hour, 19-04-2026")
    run_agent("Allocate all patients")

    print("\n  >>> Nouveau patient URGENT admis aux urgences !")
    run_agent("Add patient Dorra URGENT Hamdi, urgency high, 1 hour, 19-04-2026")
    run_agent("Allocate all patients")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 5 — RANDOM FAILURE
# ─────────────────────────────────────────────────────────────────────────────
def scenario_random_failure() -> None:
    _header("SCENARIO 5 - RANDOM FAILURE : erreurs aleatoires (60 % par appel)")
    reset_csv()

    run_agent("Add patient Fethi Zagrouba, urgency high, 1 hour, 21-04-2026")

    print("\n  [FAILURE_CONFIG] Activating random_error...")
    FAILURE_MODE["random_error"] = True

    run_agent("Allocate all patients")

    FAILURE_MODE["random_error"] = False
    print("\n  [FAILURE_CONFIG] random_error disabled.")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 6 — TIMEOUT
# ─────────────────────────────────────────────────────────────────────────────
def scenario_timeout() -> None:
    _header("SCENARIO 6 - TIMEOUT : delai artificiel de 8 s par appel outil")
    reset_csv()

    run_agent("Add patient Ghofrane Slim, urgency medium, 2 hours, 22-04-2026")

    print("\n  [FAILURE_CONFIG] Activating timeout (8 s sleep)...")
    FAILURE_MODE["timeout"] = True

    run_agent("Allocate all patients")

    FAILURE_MODE["timeout"] = False
    print("\n  [FAILURE_CONFIG] timeout disabled.")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO 7 — RATE LIMIT
# ─────────────────────────────────────────────────────────────────────────────
def scenario_rate_limit() -> None:
    _header("SCENARIO 7 - RATE LIMIT : faux HTTP-429 sur chaque appel LLM")
    reset_csv()

    run_agent("Add patient Hajer Khalfallah, urgency low, 1 hour, 23-04-2026")

    print("\n  [FAILURE_CONFIG] Activating rate_limit (fake HTTP-429)...")
    FAILURE_MODE["rate_limit"] = True

    run_agent("Allocate all patients")

    FAILURE_MODE["rate_limit"] = False
    print("\n  [FAILURE_CONFIG] rate_limit disabled.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "#" * 56)
    print("  Hospital Surgery Scheduling - Scenario Suite")
    print("  Contexte : organisation des blocs operatoires en Tunisie")
    print("#" * 56)

    scenarios = [
        ("1 - Normal",          scenario_normal),
        ("2 - Rooms closed",    scenario_rooms_closed),
        ("3 - Tool blocked",    scenario_tool_blocked),
        ("4 - Preemption",      scenario_preemption),
        ("5 - Random failure",  scenario_random_failure),
        ("6 - Timeout",         scenario_timeout),
        ("7 - Rate limit",      scenario_rate_limit),
    ]

    # Lancer un seul scenario via argument : python scenario.py 5
    if len(sys.argv) == 2:
        idx = int(sys.argv[1]) - 1
        if 0 <= idx < len(scenarios):
            name, fn = scenarios[idx]
            print(f"\nRunning only: {name}")
            fn()
            sys.exit(0)
        else:
            print(f"Invalid scenario number. Choose 1-{len(scenarios)}.")
            sys.exit(1)

    # Sinon lancer tous les scenarios dans l'ordre
    for name, fn in scenarios:
        try:
            fn()
        except KeyboardInterrupt:
            print("\n\nInterrupted by user.")
            sys.exit(0)
        except Exception as exc:
            print(f"\n[ERROR] Scenario '{name}' crashed: {exc}")
            for key in FAILURE_MODE:
                FAILURE_MODE[key] = False
            for room in ["room1", "room2", "room3"]:
                open_room(room)
            allow_action("allocate_rooms")
            continue

    print("\n" + "#" * 56)
    print("  Tous les scenarios termines.")
    print("#" * 56)