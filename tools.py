import csv
import os
import threading
from datetime import datetime, timedelta
 
PATIENTS_FILE = "patients.csv"
ROOMS_FILE    = "rooms_schedule.csv"
URGENCY_ORDER = {"high": 1, "medium": 2, "low": 3}
ROOM_START_TIME = "12:00"
ROOMS       = ["room1", "room2", "room3"]
GAP_MINUTES = 30
 
# ── ONE lock shared by all threads ────────────────────────────────────────────
# Any function that reads OR writes a CSV must hold this lock first.
# This prevents two tasks from corrupting the files at the same time.
_CSV_LOCK = threading.Lock()
 
def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    # include thread name so concurrent logs are traceable
    thread = threading.current_thread().name
    print(f"[{timestamp}][{thread}] [TOOL]  {message}")
 
def success(message, data=None): return {"status": "success", "message": message, "data": data}
def error(message):              return {"status": "error",   "message": message, "data": None}
 
# ── Helpers ───────────────────────────────────────────────────────────────────
 
def read_csv(file_path):
    with open(file_path, mode="r", encoding="utf-8") as f:
        return list(csv.DictReader(f))
 
def write_csv(file_path, rows, fieldnames):
    with open(file_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
 
def add_minutes(time_str, minutes):
    return (datetime.strptime(time_str, "%H:%M") + timedelta(minutes=minutes)).strftime("%H:%M")
 
def duration_to_minutes(duration_hours):
    return int(float(duration_hours) * 60)
 
# ── Tool 1: Add Patient ───────────────────────────────────────────────────────
 
def add_patient(patient_name: str, urgency: str, duration: float, date: str) -> dict:
    log(f"Adding patient: {patient_name}")
    if urgency not in URGENCY_ORDER:
        return error(f"Invalid urgency '{urgency}'. Must be: high, medium, low")
 
    with _CSV_LOCK:                          # ← lock: read-modify-write is atomic
        patients = read_csv(PATIENTS_FILE)
        max_id   = max((int(p["patient_id"].strip()) for p in patients), default=0)
        new_id   = max_id + 1
        new_patient = {
            "patient_id": new_id, "patient_name": patient_name,
            "urgency": urgency, "duration": duration,
            "date": date, "status": "not_scheduled"
        }
        patients.append(new_patient)
        write_csv(PATIENTS_FILE, patients,
                  ["patient_id","patient_name","urgency","duration","date","status"])
 
    return success(f"Patient '{patient_name}' added with ID {new_id}", new_patient)
 
# ── Tool 2: Allocate Rooms ────────────────────────────────────────────────────
 
def allocate_rooms() -> dict:
    log("Allocating rooms...")
 
    with _CSV_LOCK:                          # ← lock: entire allocate is one atomic op
        patients     = read_csv(PATIENTS_FILE)
        unscheduled  = [p for p in patients if p["status"].strip() == "not_scheduled"]
        if not unscheduled:
            return error("No unscheduled patients found")
 
        unscheduled.sort(key=lambda p: URGENCY_ORDER.get(p["urgency"].strip(), 99))
 
        room_next_time = {room: ROOM_START_TIME for room in ROOMS}
        try:
            existing = [r for r in read_csv(ROOMS_FILE) if r.get("patient_id","").strip()]
            for alloc in existing:
                rid, end = alloc["room_id"].strip(), alloc["end_time"].strip()
                if rid in room_next_time and end:
                    candidate = add_minutes(end, GAP_MINUTES)
                    if candidate > room_next_time[rid]:
                        room_next_time[rid] = candidate
        except Exception:
            existing = []
 
        new_allocations = []
        return_data = []
        for i, patient in enumerate(unscheduled):
            room_id = min(ROOMS, key=lambda r: datetime.strptime(room_next_time[r], "%H:%M"))
            start_time = room_next_time[room_id]
            dur_mins   = duration_to_minutes(patient["duration"].strip())
            end_time   = add_minutes(start_time, dur_mins)
            room_next_time[room_id] = add_minutes(end_time, GAP_MINUTES)
            
            alloc = {
                "room_id": room_id, "patient_id": patient["patient_id"].strip(),
                "start_time": start_time, "end_time": end_time
            }
            new_allocations.append(alloc)
            
            ret_alloc = alloc.copy()
            ret_alloc["patient_name"] = patient["patient_name"].strip()
            return_data.append(ret_alloc)
            
            for p in patients:
                if p["patient_id"].strip() == patient["patient_id"].strip():
                    p["status"] = "scheduled"
 
        write_csv(PATIENTS_FILE, patients,
                  ["patient_id","patient_name","urgency","duration","date","status"])
        write_csv(ROOMS_FILE, existing + new_allocations,
                  ["room_id","patient_id","start_time","end_time"])
 
    return success(f"Allocated {len(new_allocations)} patients to rooms", return_data)
 
# ── Tool 3: Update Patient ────────────────────────────────────────────────────
 
def update_patient(patient_id: int, patient_name: str = None,
                   urgency: str = None, duration: float = None,
                   date: str = None) -> dict:
    log(f"Updating patient ID: {patient_id}")
 
    with _CSV_LOCK:                          # ← lock: read-modify-write is atomic
        patients = read_csv(PATIENTS_FILE)
        target   = next((p for p in patients if p["patient_id"].strip() == str(patient_id)), None)
        if not target:
            return error(f"Patient with ID {patient_id} not found")
 
        if target["status"].strip() == "scheduled":
            if urgency is not None or duration is not None or date is not None:
                return error("Patient is already scheduled. You can only update the name.")
            if patient_name is not None:
                target["patient_name"] = patient_name
        else:
            if patient_name is not None: target["patient_name"] = patient_name
            if urgency is not None:
                if urgency not in URGENCY_ORDER:
                    return error(f"Invalid urgency '{urgency}'. Must be: high, medium, low")
                target["urgency"] = urgency
            if duration is not None: target["duration"] = duration
            if date is not None: target["date"] = date
 
        write_csv(PATIENTS_FILE, patients,
                  ["patient_id","patient_name","urgency","duration","date","status"])
 
    return success(f"Patient {patient_id} updated successfully", target)
 
# ── Tool 4: Delete Patient ────────────────────────────────────────────────────
 
def delete_patient(patient_id: int) -> dict:
    log(f"Deleting patient ID: {patient_id}")
    with _CSV_LOCK:
        patients = read_csv(PATIENTS_FILE)
        new_patients = [p for p in patients if p["patient_id"].strip() != str(patient_id)]
        if len(new_patients) == len(patients):
            return error(f"Patient with ID {patient_id} not found")
        
        write_csv(PATIENTS_FILE, new_patients,
                  ["patient_id","patient_name","urgency","duration","date","status"])
                  
        # Also remove from rooms if scheduled
        try:
            rooms = read_csv(ROOMS_FILE)
            new_rooms = [r for r in rooms if r.get("patient_id", "").strip() != str(patient_id)]
            write_csv(ROOMS_FILE, new_rooms, ["room_id","patient_id","start_time","end_time"])
        except Exception:
            pass

    return success(f"Patient {patient_id} deleted successfully")

# ── Tool 5: Unschedule Patient ────────────────────────────────────────────────

def unschedule_patient(patient_id: int) -> dict:
    log(f"Unscheduling patient ID: {patient_id}")
    with _CSV_LOCK:
        patients = read_csv(PATIENTS_FILE)
        target = next((p for p in patients if p["patient_id"].strip() == str(patient_id)), None)
        if not target:
            return error(f"Patient with ID {patient_id} not found")
        
        if target["status"].strip() != "scheduled":
            return error(f"Patient {patient_id} is not currently scheduled")
            
        target["status"] = "not_scheduled"
        write_csv(PATIENTS_FILE, patients,
                  ["patient_id","patient_name","urgency","duration","date","status"])
                  
        # Remove from rooms
        try:
            rooms = read_csv(ROOMS_FILE)
            new_rooms = [r for r in rooms if r.get("patient_id", "").strip() != str(patient_id)]
            write_csv(ROOMS_FILE, new_rooms, ["room_id","patient_id","start_time","end_time"])
        except Exception:
            pass
        
    return success(f"Patient {patient_id} unscheduled successfully")

# ── Tool mapping & declarations (unchanged) ───────────────────────────────────
 
TOOL_FUNCTIONS = {
    "add_patient":    add_patient,
    "allocate_rooms": allocate_rooms,
    "update_patient": update_patient,
    "delete_patient": delete_patient,
    "unschedule_patient": unschedule_patient,
}
 
TOOL_DECLARATIONS = [
    {"type":"function","function":{
        "name":"add_patient",
        "description":"Add a new patient. ID is auto-incremented, never provided manually.",
        "parameters":{"type":"object","properties":{
            "patient_name":{"type":"string"},
            "urgency":{"type":"string","enum":["high","medium","low"]},
            "duration":{"type":"number","description":"Duration in hours"},
            "date":{"type":"string","description":"Date of surgery e.g. 18-04-2026"}
        },"required":["patient_name","urgency","duration","date"]}}},
    {"type":"function","function":{
        "name":"allocate_rooms",
        "description":"Sort all not_scheduled patients by urgency and assign them to rooms.",
        "parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{
        "name":"update_patient",
        "description":"Update a patient by ID. Scheduled: name only. Not scheduled: name/urgency/duration/date.",
        "parameters":{"type":"object","properties":{
            "patient_id":{"type":"integer"},
            "patient_name":{"type":"string"},
            "urgency":{"type":"string","enum":["high","medium","low"]},
            "duration":{"type":"number"},
            "date":{"type":"string","description":"Date of surgery e.g. 18-04-2026"}
        },"required":["patient_id"]}}},
    {"type":"function","function":{
        "name":"delete_patient",
        "description":"Delete a patient by ID.",
        "parameters":{"type":"object","properties":{
            "patient_id":{"type":"integer"}
        },"required":["patient_id"]}}},
    {"type":"function","function":{
        "name":"unschedule_patient",
        "description":"Unschedule a patient by ID, removing them from their room assignment but keeping them in the system.",
        "parameters":{"type":"object","properties":{
            "patient_id":{"type":"integer"}
        },"required":["patient_id"]}}},
]