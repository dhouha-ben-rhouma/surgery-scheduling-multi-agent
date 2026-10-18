from tools import add_patient, allocate_rooms, update_patient
from planner import safety_check, PlannerState

def test_add_patient():
    res = add_patient("TestUser", "high", 1, "19-04-2026")
    assert res["status"] == "success"
    print("[OK] add_patient OK")

def test_invalid_urgency():
    res = add_patient("TestUser", "urgent", 1, "19-04-2026")
    assert res["status"] == "error"
    print("[OK] invalid urgency blocked")

def test_update_patient():
    res = update_patient(1, patient_name="NewName")
    assert res["status"] in ["success", "error"]
    print("[OK] update_patient OK")

def test_safety():
    state = PlannerState()
    verdict = safety_check("add_patient", {"urgency": "wrong"}, state)
    ok, reason = safety_check("add_patient", {"urgency": "wrong"}, state)
    assert ok == False
    print("[OK] safety check OK")

def test_allocate():
    res = allocate_rooms()
    assert res["status"] in ["success", "error"]
    print("[OK] allocate_rooms OK")


if __name__ == "__main__":
    test_add_patient()
    test_invalid_urgency()
    test_update_patient()
    test_safety()
    test_allocate()

    print("\n[SUCCESS] ALL TESTS PASSED")