# surgery-scheduling-multi-agent
A multi-agent LLM system (Planner, Worker, Critic) that schedules surgery patients into hospital rooms, with safety checks, backtracking, preemption, caching and thread-safe CSV operations.


## What is this project?

```
User message
    ↓
Planner Agent  →  decides what to do
    ↓
[YOUR CODE] plan_next_action()  →  safety check + history + backtracking
    ↓  (if safe and not already tried)
Worker Agent  →  actually calls the tool (add_patient, allocate_rooms, etc.)
    ↓
Critic Agent  →  checks if the result is correct
    ↓  (if wrong → loop back to YOUR code with new action/params)
Final response to user
```

**Your responsibility (Person 3)** is everything in the middle:
making the orchestrator *smart* instead of blindly retrying.

---

## Files you own

| File | What it does |
|---|---|
| `planner.py` | Safety · Backtracking · Preemption · Cache |
| `cache_stats.py` | Shows cache hit/miss statistics |
| `test_concurrency.py` | Parallel execution tests |
| `tools.py` | Modified — added a threading lock for concurrency safety |

---

## File 1: `planner.py`

### Why it exists

`agent.py` has a retry loop. Without `planner.py`, if something fails, the
orchestrator just sends the exact same instruction again — which will fail again.
`planner.py` makes it retry *smartly*.

---

### Global constants

```python
ROOMS       = ["room1", "room2", "room3"]  # all available rooms
ROOM_START  = "12:00"                      # earliest a room can be used
GAP         = 30                           # minutes between patients in same room
URGENCY     = {"high": 1, "medium": 2, "low": 3}  # lower = more urgent
PF          = "patients.csv"
RF          = "rooms_schedule.csv"
```

These mirror `tools.py` constants so both files stay in sync.

---

### Global constraint sets

```python
CLOSED_ROOMS      = set()   # rooms that are physically unavailable
FORBIDDEN_ACTIONS = set()   # tool names that are locked (e.g. during maintenance)
```

These are **sets** — meaning you can add/remove items at runtime.
The admin (or tests) can call `close_room("room2")` and from that moment,
`room2` will be skipped in every decision.

> **Note:** The `ABSENT_SURGEONS` set was removed. Surgeons are not part of
> the current data model — neither `patients.csv` nor `rooms_schedule.csv`
> has a surgeon column, so surgeon tracking would have no effect on any
> tool call.

---

### Cache variables

```python
CACHE        = {}   # stores safety_check results so they are not recomputed
CACHE_HITS   = 0    # how many times we returned a cached answer
CACHE_MISSES = 0    # how many times we had to compute fresh
```

`safety_check()` always gives the same answer for the same inputs,
so we cache it. If you check "is add_patient safe with these params?" twice,
the second time is instant.

---

### Helper functions

#### `_read(filepath)`
Reads a CSV file and returns a list of dictionaries.
Each row becomes one dict like `{"patient_id": "1", "patient_name": "Alice", ...}`.
Returns an empty list if the file doesn't exist (safe to call anytime).

#### `_write(filepath, rows, column_names)`
Saves a list of dictionaries back to a CSV file.
Overwrites the file completely each time.

#### `_add(time_string, minutes)`
Adds minutes to a time string.
Example: `_add("12:00", 90)` → `"13:30"`

#### `_dur(duration_in_hours)`
Converts hours to minutes.
Example: `_dur(1.5)` → `90`

---

### `PlannerState` class

```python
@dataclass
class PlannerState:
    failures:    list  # (patient_id, room, slot) tuples that already failed
    directives:  list  # instruction strings already sent to the worker
    pruned:      set   # rooms permanently removed from consideration
    preemptions: list  # records of every patient displacement
    cycle:       int   # which retry we are on
```

**Create one fresh instance per user request:**
```python
state = PlannerState()
```

Think of it as the **memory** for one conversation turn.
It remembers what was tried, what failed, and what was displaced,
so nothing is repeated.

#### Methods inside `PlannerState`

**`tried(patient_id, room, slot)`**
Returns `True` if we already tried putting this patient in this room at this time.
Prevents retrying the exact same failed combination.

**`rooms()`**
Returns the list of rooms that are currently usable — excluding rooms in
`state.pruned` and the global `CLOSED_ROOMS` set.

**`displaced(patient_id)`**
Returns `True` if this patient was already bumped out once.
Prevents bumping the same person twice (infinite loop prevention).

---

### `_free(state)` — room availability snapshot

```
Input:  a PlannerState
Output: {"room1": "12:00", "room2": "14:30", "room3": "12:00"}
```

Reads `rooms_schedule.csv` and figures out the earliest available start time
for each room. It takes the last `end_time` in each room and adds the 30-minute
gap. If a room has nothing scheduled yet, it defaults to `"12:00"`.

---

### `safety_check(action, params, state)`

**The gatekeeper.** Called before every worker call.

```
Input:  action name (string), params (dict), current state
Output: (True, "")            → safe, proceed
        (False, "reason...")  → blocked, stop
```

**What it checks, in order:**

1. Is this tool name in `FORBIDDEN_ACTIONS`? → block
2. Is `allocate_rooms` being called but all rooms are closed? → block
3. Is the urgency value invalid (not high/medium/low)? → block
4. Is this patient already scheduled? → block (no duplicates)

**Caching:** before doing any of these checks, it builds a cache key from
`action + params + FORBIDDEN_ACTIONS + CLOSED_ROOMS`. If that exact combination
was already evaluated, it returns the cached result instantly and increments
`CACHE_HITS`. Otherwise it computes fresh and stores the result, incrementing
`CACHE_MISSES`.

**Why cache it?** Because `safety_check` is called every cycle of the retry loop.
If the user sends the same request twice, the second check is free.

---

### `generate_alternatives(patient_id, failed_room, failed_slot, state)`

**The backtracking function.**

```
Input:  which patient, which room failed, which time slot failed, state
Output: {"room_id": "room2", "start_time": "12:00", "end_time": "13:00"}
        or None if all options exhausted
```

**What it does step by step:**

1. Records the failure in `state.failures` as a tuple `(pid, room, slot)`
2. Checks if this room has failed too many times → if yes, adds it to `state.pruned` (auto-pruning)
3. Looks up the patient's duration from the CSV
4. Loops through every available room in order
5. For each room, gets the earliest free slot using `_free(state)`
6. If that `(patient, room, slot)` combination was not tried before → returns it
7. If everything has been tried → returns `None` (caller will try preemption next)

**Simple analogy:** it's like trying to book a hotel room. Room A is full?
Try room B. Room B is full? Try room C. All full? Tell the caller there's nothing left.

---

### `preempt_for_high_urgency(high_urgency_patient_id, state)`

**The preemption function — the most important and complex one.**

Called only when a HIGH urgency patient has absolutely no free slot anywhere.

```
Input:  ID of the high urgency patient who needs a room, state
Output: {"room_id": "room1", "start_time": "12:00", "end_time": "13:00"}
        or None if preemption is impossible
```

**What it does step by step:**

1. Reads all currently scheduled patients from both CSVs
2. Sorts them to find the **least urgent** scheduled patient
   (sorting trick: multiply urgency rank by -1 so `low` comes first)
3. **Safety checks before bumping:**
   - If the least urgent patient is also `high` urgency → refuse (can't bump an equal)
   - If this patient was already displaced once → refuse (prevents infinite loops)
4. **Physically removes them** from `rooms_schedule.csv`
5. **Resets their status** to `not_scheduled` in `patients.csv`
   (they go back to the waiting list to be rescheduled later)
6. Records the event in `state.preemptions`
7. Returns the freed slot so the high urgency patient can take it

**Simple analogy:** Emergency patient arrives, no room available.
We find whoever is lowest priority (e.g. a routine check-up), move them to
the waiting room, and give their room to the emergency patient.

---

### `format_preemption_summary(state)`

```
Input:  state (after preemption happened)
Output: a human-readable string like:
        " Preemption notice:
         • 'Alice' (low) moved out of room1 [12:00–13:00] → waiting list."
```

Returns an empty string if no preemption happened.
This string is appended to the final agent response so the user knows
someone was bumped.

---

### `_fallback(action, params, last_result, state)`

**Private helper called when a directive has already been tried.**

Tries alternatives in this order:
1. **Backtracking** — calls `generate_alternatives()` for the failed patient
2. **Preemption** — if backtracking returns `None` AND patient is `high` urgency,
   calls `preempt_for_high_urgency()`

Returns a new directive dict, or `None` if truly exhausted.

---

### `plan_next_action(user_message, action, params, last_result, state)` ← **MAIN FUNCTION**

**The single entry-point called by `agent.py`'s orchestrator every retry cycle.**

```
Input:  user_message (for context), action (tool name), params (tool arguments),
        last_result (what the worker returned last time, or None),
        state (the PlannerState for this request)

Output: {
    "proceed":   True or False,
    "directive": "use add_patient with ...",
    "action":    "add_patient",
    "params":    {...},
    "reason":    "Cycle 1: proceeding." or "[SAFETY BLOCK] reason..."
}
```

**Flow:**
```
1. Increment state.cycle
2. Call safety_check() → if blocked, return proceed=False immediately
3. Build the directive string from action + params
4. Check if this directive is already in state.directives
   → if yes: call _fallback() to get an alternative
   → if _fallback returns None: return proceed=False ("all alternatives exhausted")
   → if _fallback returns something: use the new directive
5. Record the directive in state.directives
6. Return proceed=True with the directive
```

**How `agent.py` uses it:**
```python
decision = plan_next_action(user_message, action, params, last_result, state)
if not decision["proceed"]:
    # tell user there's a problem
    return
result = worker_agent(decision["directive"])
```

---

### Constraint helper functions

These are called by the admin CLI shortcuts in `agent.py`:

| Function | What it does |
|---|---|
| `close_room("room2")` | Adds room2 to `CLOSED_ROOMS` — skipped in all decisions |
| `open_room("room2")` | Removes room2 from `CLOSED_ROOMS` |
| `forbid_action("allocate_rooms")` | Locks a tool completely |
| `allow_action("allocate_rooms")` | Unlocks it |

> **Note:** `mark_surgeon_absent()` and `mark_surgeon_present()` were removed.
> They had no effect because no tool or CSV field references a surgeon.

---

### How to run the built-in tests

```bash
python planner.py
```

No API key needed. Runs 9 tests covering every function.

| Test | What it checks |
|---|---|
| 1 | Normal allocation goes through |
| 2 | Forbidden tool is blocked |
| 3 | All rooms closed → blocked |
| 4 | Duplicate directive not repeated |
| 5 | Backtracking finds a different slot |
| 6 * | Preemption: high urgency bumps low urgency |
| 7 * | Preemption refused when all scheduled are high urgency |
| 8 * | Same patient never displaced twice |
| 9 * | Summary message generated correctly |

---

## File 2: `cache_stats.py`

A small utility to inspect the cache counters from `planner.py`.

### Functions

#### `show_stats()`
Prints how many safety checks were served from cache vs computed fresh.
```
Cache hits:   5
Cache misses: 3
Hit ratio:    63%  (5/8)
```

#### `clear_cache()`
Wipes the cache dictionary and resets both counters to 0.
Call this if you change constraints at runtime and want the cache to reflect
the new state (though the cache key already includes constraints, so this is
mainly for resetting between test runs).

### How to run

```bash
python cache_stats.py   # runs a built-in demo showing hits/misses
```

Or import it anywhere:
```python
from cache_stats import show_stats, clear_cache
show_stats()
```

---

## File 3: `tools.py` (modified)

### What was changed and why

The original `tools.py` had no protection against two threads writing to the
same CSV file at the same time. If two requests come in simultaneously, both
could read the file, both compute `max_id = 5`, both write `new_id = 6`,
and you'd end up with duplicate IDs and one patient lost.

**The fix — one lock for all CSV operations:**

```python
import threading
_CSV_LOCK = threading.Lock()
```

Every function that reads AND writes a CSV now wraps that block with:
```python
with _CSV_LOCK:
    patients = read_csv(...)    # read
    # ... modify in memory ...
    write_csv(...)              # write
```

The `with _CSV_LOCK` block means: "only one thread can be here at a time."
All other threads wait until it's their turn. This makes every read-modify-write
**atomic** — it either happens completely or not at all.

**Also added:** the `log()` function now includes the thread name so you can
see which thread is doing what:
```
[12:00:01][AddWorker_0] [TOOL]  Adding patient: Alice
[12:00:01][AddWorker_1] [TOOL]  Adding patient: Bob
```

---

## File 4: `test_concurrency.py`

Tests that the system works correctly when multiple tasks run at the same time.
**No API key needed** — tests the tool layer directly.

### How to run

```bash
python test_concurrency.py
```

### The 5 tests

#### Test 1 — Parallel add_patient (5 threads)
Launches 5 threads simultaneously, each adding a different patient.
Checks:
- All 5 calls succeeded
- All 5 patients were written to the CSV
- No two patients have the same ID
- No rows are missing required fields (corrupt)

#### Test 2 — Parallel allocate_rooms (3 threads)
Launches 3 threads all calling `allocate_rooms()` at the same time.
Checks:
- Exactly 1 thread succeeded (the others found no unscheduled patients)
- Every entry in the room schedule references a real patient_id
- No patient appears twice in the schedule

#### Test 3 — Mixed parallel ops
Runs `add_patient`, `update_patient`, and `allocate_rooms` all at once.
Checks:
- All 3 finished without crashing
- No rows are corrupt in the final CSV

#### Test 4 — High load (10 threads)
10 threads each add a patient simultaneously.
Checks:
- All 10 patients written
- IDs are 1 through 10 with no gaps or duplicates

#### Test 5 — No data mixing between 3 task groups
Simulates the assignment pattern:
```python
run_agent(task1)   # thread 1: add Alice + allocate
run_agent(task2)   # thread 2: add Bob   + allocate
run_agent(task3)   # thread 3: add Carol + allocate
```
Checks:
- Alice, Bob, and Carol are all present — no one got overwritten
- No duplicate IDs
- Schedule has no orphan patient_ids

---

## How everything connects

```
agent.py
│
├── calls planner_agent()     → gets (directive, action, params) from AI
│
└── retry loop:
    │
    ├── calls plan_next_action()   ← YOUR CODE (planner.py)
    │       ├── safety_check()     ← checks constraints + cache
    │       ├── generate_alternatives()  ← backtracking
    │       └── preempt_for_high_urgency()  ← preemption
    │
    ├── calls worker_agent()   → AI calls the actual tool
    │       └── tools.py       ← add_patient / allocate_rooms / update_patient
    │               └── _CSV_LOCK  ← YOUR CODE (concurrency safety)
    │
    └── calls critic_agent()   → AI checks if result is correct
            └── if wrong → back to plan_next_action() with new action/params
```

---

## Quick reference — what to run

```bash
# Test planner logic (no API key needed)
python planner.py

# Test cache stats
python cache_stats.py

# Test concurrency safety (no API key needed)
python test_concurrency.py

# Run full system (needs OPENROUTER_API_KEY in .env)
python agent.py

# Run all scenarios
python scenario.py

# Run unit tests
python tests.py
```

---

## If the professor deletes a block and asks you to rewrite it

### If `safety_check` is deleted:
It takes `(action, params, state)` and returns `(True, "")` or `(False, "reason")`.
Check in this order: forbidden actions → closed rooms → bad urgency → already scheduled.
Add cache: build a key from `action + params + FORBIDDEN_ACTIONS + CLOSED_ROOMS`, check `CACHE` first.

### If `generate_alternatives` is deleted:
It takes `(patient_id, failed_room, failed_slot, state)`.
Append the failure to `state.failures`. Check if that room failed ≥ 3 times → prune it.
Loop through available rooms, get free start time for each, return first untried slot.

### If `preempt_for_high_urgency` is deleted:
It takes `(high_pid, state)`.
Read scheduled patients, sort by urgency (least urgent first).
Refuse if worst is `high` or already displaced. Remove them from CSVs.
Reset their status to `not_scheduled`. Record in `state.preemptions`. Return freed slot.

### If `plan_next_action` is deleted:
It takes `(user_message, action, params, last_result, state)`.
1. Call `safety_check` → return `proceed=False` if blocked.
2. Build directive string.
3. If directive already in `state.directives` → call `_fallback` → if None, return `proceed=False`.
4. Append directive to `state.directives`.
5. Return `proceed=True` with the directive.

### If the lock in `tools.py` is deleted:
Add `import threading` at the top.
Add `_CSV_LOCK = threading.Lock()` as a module-level variable.
Wrap every `read_csv + write_csv` block in `with _CSV_LOCK:`.



project by Dhouha ben rhouma
Touka Tammar
Sarra mejri
Fedi neffousi 
Roua Charfeddine
