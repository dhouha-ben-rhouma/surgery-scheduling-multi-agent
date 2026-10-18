"""
test_concurrency.py — Parallel execution + data integrity tests
===============================================================
Runs multiple run_agent() calls at the same time using threads.
Verifies:
  1. No data mixing  — each patient appears exactly once in the CSV
  2. No duplicate IDs — auto-increment stays unique under parallel writes
  3. No corrupt rows  — every row has all required fields
  4. Schedule integrity — every room slot has a valid patient_id
"""

import csv
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── We test tools directly (no API key needed) ────────────────────────────────
from tools import (
    add_patient, allocate_rooms, update_patient,
    read_csv, write_csv,
    PATIENTS_FILE, ROOMS_FILE,
    _CSV_LOCK,
)

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"; RED  = "\033[91m"
CYAN   = "\033[96m"; BOLD = "\033[1m"; RESET = "\033[0m"

def ok(msg):   print(f"  {GREEN}[OK]  {msg}{RESET}")
def fail(msg): print(f"  {RED}[FAIL]  {msg}{RESET}")
def sec(msg):  print(f"\n{BOLD}{CYAN}{'─'*50}\n  {msg}\n{'─'*50}{RESET}")

# ── CSV seed helper ───────────────────────────────────────────────────────────
P_COLS = ["patient_id","patient_name","urgency","duration","date","status"]
R_COLS = ["room_id","patient_id","start_time","end_time"]

def reset_csvs():
    """Wipe both CSVs to a clean state before each test."""
    with _CSV_LOCK:
        write_csv(PATIENTS_FILE, [], P_COLS)
        write_csv(ROOMS_FILE,    [], R_COLS)

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Parallel add_patient: no duplicate IDs, no lost rows
# ═══════════════════════════════════════════════════════════════════════════════
def test_parallel_add():
    sec("TEST 1 — Parallel add_patient (5 threads)")
    reset_csvs()

    tasks = [
        ("Alice",   "high",   1, "19-04-2026"),
        ("Bob",     "medium", 2, "19-04-2026"),
        ("Carol",   "low",    1, "19-04-2026"),
        ("Dave",    "high",   3, "19-04-2026"),
        ("Eve",     "medium", 2, "19-04-2026"),
    ]

    results = []
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="AddWorker") as ex:
        futures = [ex.submit(add_patient, *t) for t in tasks]
        for f in as_completed(futures):
            results.append(f.result())

    # All succeeded
    statuses = [r["status"] for r in results]
    if all(s == "success" for s in statuses):
        ok("All 5 add_patient calls succeeded")
    else:
        fail(f"Some calls failed: {statuses}")

    # Read back and check
    patients = read_csv(PATIENTS_FILE)
    ids      = [p["patient_id"].strip() for p in patients]
    names    = [p["patient_name"].strip() for p in patients]

    # No duplicate IDs
    if len(ids) == len(set(ids)):
        ok(f"No duplicate patient IDs  (got: {sorted(ids, key=int)})")
    else:
        fail(f"Duplicate IDs found: {ids}")

    # All 5 patients present
    if len(patients) == 5:
        ok("All 5 patients written to CSV")
    else:
        fail(f"Expected 5 patients, got {len(patients)}")

    # No corrupt rows (all fields present)
    corrupt = [p for p in patients if not all(p.get(c,"").strip() for c in P_COLS)]
    if not corrupt:
        ok("No corrupt rows")
    else:
        fail(f"Corrupt rows: {corrupt}")

    return len(patients) == 5 and len(ids) == len(set(ids))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Parallel allocate_rooms: schedule stays consistent
# ═══════════════════════════════════════════════════════════════════════════════
def test_parallel_allocate():
    sec("TEST 2 — Parallel allocate_rooms (3 threads)")
    reset_csvs()

    # Seed 3 patients first (sequentially — we're testing allocate here)
    add_patient("P1", "high",   1, "19-04-2026")
    add_patient("P2", "medium", 2, "19-04-2026")
    add_patient("P3", "low",    1, "19-04-2026")

    # Run 3 allocate_rooms in parallel — only one should actually allocate
    # (the others will find no unscheduled patients and return error)
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="AllocWorker") as ex:
        futures = [ex.submit(allocate_rooms) for _ in range(3)]
        results = [f.result() for f in as_completed(futures)]

    successes = [r for r in results if r["status"] == "success"]
    errors    = [r for r in results if r["status"] == "error"]

    if len(successes) == 1:
        ok("Exactly 1 allocate succeeded (others correctly got 'no unscheduled patients')")
    else:
        fail(f"Expected 1 success, got {len(successes)}: {[r['message'] for r in successes]}")

    # Schedule integrity: every entry must reference a real patient_id
    patients    = {p["patient_id"].strip() for p in read_csv(PATIENTS_FILE)}
    schedule    = read_csv(ROOMS_FILE)
    sched_pids  = [r["patient_id"].strip() for r in schedule]
    orphans     = [pid for pid in sched_pids if pid not in patients]

    if not orphans:
        ok(f"Schedule integrity OK — {len(schedule)} slots, all valid patient IDs")
    else:
        fail(f"Orphan patient_ids in schedule: {orphans}")

    # No duplicate patient in schedule
    if len(sched_pids) == len(set(sched_pids)):
        ok("No patient scheduled twice")
    else:
        fail(f"Duplicate schedule entries: {sched_pids}")

    return len(successes) == 1 and not orphans

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Mixed parallel ops: add + allocate + update simultaneously
# ═══════════════════════════════════════════════════════════════════════════════
def test_mixed_parallel():
    sec("TEST 3 — Mixed parallel ops (add + update + allocate)")
    reset_csvs()

    # Pre-seed one patient to update
    add_patient("Existing", "low", 1, "19-04-2026")

    def task_add():
        return add_patient("NewPatient", "high", 2, "19-04-2026")

    def task_update():
        time.sleep(0.05)  # slight delay so patient 1 exists
        return update_patient(1, patient_name="UpdatedExisting")

    def task_allocate():
        time.sleep(0.1)   # slight delay so patients exist
        return allocate_rooms()

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="MixWorker") as ex:
        f1 = ex.submit(task_add)
        f2 = ex.submit(task_update)
        f3 = ex.submit(task_allocate)
        r_add    = f1.result()
        r_update = f2.result()
        r_alloc  = f3.result()

    if r_add["status"] == "success":
        ok("Concurrent add_patient succeeded")
    else:
        fail(f"add_patient failed: {r_add['message']}")

    if r_update["status"] == "success":
        ok("Concurrent update_patient succeeded")
    else:
        fail(f"update_patient failed: {r_update['message']}")

    if r_alloc["status"] in ("success", "error"):
        ok(f"allocate_rooms finished cleanly: {r_alloc['message']}")
    else:
        fail("allocate_rooms crashed")

    # Final CSV must have no corrupt rows
    patients = read_csv(PATIENTS_FILE)
    corrupt  = [p for p in patients if not all(p.get(c,"").strip() for c in P_COLS)]
    if not corrupt:
        ok(f"No corrupt rows after mixed ops ({len(patients)} patients)")
    else:
        fail(f"Corrupt rows found: {corrupt}")

    return not corrupt

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4 — High load: 10 parallel adds, check IDs are all unique
# ═══════════════════════════════════════════════════════════════════════════════
def test_high_load():
    sec("TEST 4 — High load: 10 parallel add_patient calls")
    reset_csvs()

    names = [f"Patient_{i}" for i in range(10)]
    with ThreadPoolExecutor(max_workers=10, thread_name_prefix="LoadWorker") as ex:
        futures = [ex.submit(add_patient, n, "medium", 1, "19-04-2026") for n in names]
        results = [f.result() for f in as_completed(futures)]

    patients = read_csv(PATIENTS_FILE)
    ids      = [p["patient_id"].strip() for p in patients]

    if len(patients) == 10:
        ok("All 10 patients written")
    else:
        fail(f"Expected 10, got {len(patients)}")

    if len(ids) == len(set(ids)):
        ok(f"All IDs unique: {sorted(ids, key=int)}")
    else:
        dupes = [i for i in ids if ids.count(i) > 1]
        fail(f"Duplicate IDs: {dupes}")

    return len(patients) == 10 and len(ids) == len(set(ids))

# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5 — No data mixing between independent task groups
# ═══════════════════════════════════════════════════════════════════════════════
def test_no_data_mixing():
    """
    Simulates the exact pattern from the assignment:
        run_agent(task1)   ← thread 1: add Alice + allocate
        run_agent(task2)   ← thread 2: add Bob   + allocate
        run_agent(task3)   ← thread 3: add Carol + allocate

    We verify that no patient ends up with someone else's name or ID.
    """
    sec("TEST 5 — No data mixing between 3 parallel task groups")
    reset_csvs()

    def task(name, urgency):
        add_patient(name, urgency, 1, "19-04-2026")
        allocate_rooms()

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="TaskGroup") as ex:
        f1 = ex.submit(task, "Alice", "high")
        f2 = ex.submit(task, "Bob",   "medium")
        f3 = ex.submit(task, "Carol", "low")
        f1.result(); f2.result(); f3.result()

    patients = read_csv(PATIENTS_FILE)
    names    = [p["patient_name"].strip() for p in patients]
    ids      = [p["patient_id"].strip() for p in patients]

    expected = {"Alice", "Bob", "Carol"}
    if set(names) == expected:
        ok(f"All 3 patients present, no mixing: {names}")
    else:
        fail(f"Expected {expected}, got {set(names)}")

    if len(ids) == len(set(ids)):
        ok(f"No duplicate IDs: {sorted(ids, key=int)}")
    else:
        fail(f"Duplicate IDs: {ids}")

    # Check every scheduled patient_id exists
    schedule = read_csv(ROOMS_FILE)
    pid_set  = set(ids)
    orphans  = [r["patient_id"].strip() for r in schedule if r["patient_id"].strip() not in pid_set]
    if not orphans:
        ok(f"Schedule clean — {len(schedule)} slots, no orphan IDs")
    else:
        fail(f"Orphan IDs in schedule: {orphans}")

    return set(names) == expected and len(ids) == len(set(ids)) and not orphans

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\n{BOLD}Concurrency & Stability Test Suite{RESET}")
    print("No API key needed — tests tool layer directly.\n")

    results = {
        "Parallel add_patient":         test_parallel_add(),
        "Parallel allocate_rooms":      test_parallel_allocate(),
        "Mixed parallel ops":           test_mixed_parallel(),
        "High load (10 threads)":       test_high_load(),
        "No data mixing (3 tasks)":     test_no_data_mixing(),
    }

    print(f"\n{BOLD}{'─'*50}\n  SUMMARY\n{'─'*50}{RESET}")
    all_passed = True
    for name, passed in results.items():
        if passed:
            print(f"  {GREEN}[OK]  {name}{RESET}")
        else:
            print(f"  {RED}[FAIL]  {name}{RESET}")
            all_passed = False

    print()
    if all_passed:
        print(f"  {BOLD}{GREEN}[SUCCESS] ALL CONCURRENCY TESTS PASSED{RESET}")
    else:
        print(f"  {BOLD}{RED}[WARN]  SOME TESTS FAILED — check output above{RESET}")
