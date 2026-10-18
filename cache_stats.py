"""
cache_stats.py — Cache performance reporter for planner.py
Shows how many safety checks were served from cache vs computed fresh.
"""

import planner

def show_stats():
    """Print cache hit/miss counts and the hit ratio."""
    total = planner.CACHE_HITS + planner.CACHE_MISSES
    ratio = planner.CACHE_HITS / total if total else 0

    print("Cache hits:  ", planner.CACHE_HITS)
    print("Cache misses:", planner.CACHE_MISSES)
    print("Hit ratio:   ", f"{ratio:.0%}  ({planner.CACHE_HITS}/{total})")

def clear_cache():
    """Wipe the cache and reset counters — call this if constraints change at runtime."""
    planner.CACHE.clear()
    planner.CACHE_HITS   = 0
    planner.CACHE_MISSES = 0
    print("Cache cleared.")

# ── Quick demo ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from planner import safety_check, PlannerState, forbid_action, allow_action

    state  = PlannerState()
    params = {"patient_name": "Alice", "urgency": "high", "duration": 1, "date": "19-04-2026"}

    print("=== Cache stats demo ===\n")

    # First call → MISS (computed fresh)
    safety_check("add_patient", params, state)
    print("After 1st call:"); show_stats()

    # Same call again → HIT (returned from cache)
    safety_check("add_patient", params, state)
    print("\nAfter 2nd call (same params):"); show_stats()

    # Different params → MISS
    safety_check("add_patient", {"patient_name":"Bob","urgency":"low","duration":2,"date":"19-04-2026"}, state)
    print("\nAfter 3rd call (different params):"); show_stats()

    # Constraint changes → different key → MISS even for same params
    forbid_action("add_patient")
    safety_check("add_patient", params, state)
    print("\nAfter 4th call (constraints changed):"); show_stats()
    allow_action("add_patient")

    print("\n--- Clear cache ---")
    clear_cache()
    show_stats()
