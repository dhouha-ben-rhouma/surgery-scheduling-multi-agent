import time

# ==============================
# GLOBAL METRICS
# ==============================

states_bt = 0
states_dp = 0
cache_hits = 0


# ==============================
# BACKTRACKING
# ==============================

def schedule_bt(patients, rooms, index=0, assignment=None):
    """
    Pure backtracking scheduler.
    Tries to assign each patient to a room respecting a one-patient-per-room
    constraint (simple capacity model for complexity demonstration).
    Counts every node visited so the caller can measure worst-case exploration.
    Returns True when all patients are successfully assigned.
    """
    global states_bt
    states_bt += 1

    if assignment is None:
        assignment = {}

    # Base case: every patient has been assigned a room
    if index == len(patients):
        return True

    patient = patients[index]

    for room in rooms:
        # Constraint: no two patients share the same room simultaneously
        if room not in assignment.values():
            assignment[patient] = room
            if schedule_bt(patients, rooms, index + 1, assignment):
                return True
            # Backtrack: remove this assignment and try the next room
            del assignment[patient]

    # No valid room found for this patient; signal failure up the call stack
    return False


# ==============================
# DYNAMIC PROGRAMMING
# ==============================

def schedule_dp(patients, rooms, index=0, used_rooms=None, memo=None):
    """
    DP scheduler with memoisation on (patient_index, frozenset_of_used_rooms).
    Sub-problems that share the same (index, used_rooms) state are only solved once,
    which is what gives DP its advantage over plain backtracking on larger inputs.
    """
    global states_dp, cache_hits

    if memo       is None: memo       = {}
    if used_rooms is None: used_rooms = frozenset()

    key = (index, used_rooms)

    if key in memo:
        cache_hits += 1
        return memo[key]

    states_dp += 1

    # Base case: all patients assigned
    if index == len(patients):
        memo[key] = True
        return True

    result = False
    for room in rooms:
        if room not in used_rooms:
            if schedule_dp(patients, rooms, index + 1, used_rooms | {room}, memo):
                result = True
                break          # found a valid assignment; no need to try others

    memo[key] = result
    return result


# ==============================
# COMPARISON FUNCTION
# ==============================

def compare_algorithms(patients, rooms):
    global states_bt, states_dp, cache_hits

    # Reset all counters
    states_bt  = 0
    states_dp  = 0
    cache_hits = 0

    patient_list = list(patients)
    room_list    = list(rooms)

    # ---- BACKTRACKING ----
    start_bt = time.perf_counter()
    schedule_bt(patient_list, room_list)
    end_bt   = time.perf_counter()

    bt_snapshot = states_bt          # save before resetting DP counters

    # Reset DP-specific counters (bt counter keeps its value for the report)
    states_dp  = 0
    cache_hits = 0

    # ---- DYNAMIC PROGRAMMING ----
    start_dp = time.perf_counter()
    schedule_dp(patient_list, room_list)
    end_dp   = time.perf_counter()

    bt_time = end_bt - start_bt
    dp_time = end_dp - start_dp

    states_bt = bt_snapshot          # restore for the return dict

    # ---- PRINT RESULTS ----
    print("\n COMPARISON RESULTS")
    print("----------------------")
    print(f"BT time:             {bt_time:.6f} s")
    print(f"DP time:             {dp_time:.6f} s")
    print(f"BT states explored:  {states_bt}")
    print(f"DP states explored:  {states_dp}")
    print(f"Cache hits (DP):     {cache_hits}")
    print("DP is faster" if dp_time < bt_time else "BT is faster")

    return {
        "bt_time":   bt_time,
        "dp_time":   dp_time,
        "bt_states": states_bt,
        "dp_states": states_dp,
        "cache_hits": cache_hits,
        "dp_faster": dp_time < bt_time,
    }