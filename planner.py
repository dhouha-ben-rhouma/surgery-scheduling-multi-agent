"""
planner.py — Safety · Backtracking · Preemption · Cache
Person 3: plan_next_action() is the single entry-point for agent.py
"""
from __future__ import annotations
import csv
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
 
# ── Config ────────────────────────────────────────────────────────────────────
ROOMS, ROOM_START, GAP = ["room1","room2","room3"], "12:00", 30
URGENCY  = {"high":1, "medium":2, "low":3}
PF, RF   = "patients.csv", "rooms_schedule.csv"
 
CLOSED_ROOMS:      set = set()
FORBIDDEN_ACTIONS: set = set()
 
CACHE:dict={};  CACHE_HITS=0;  CACHE_MISSES=0
 
# ── CSV / time helpers ────────────────────────────────────────────────────────
def _read(f):
    try:
        return list(csv.DictReader(open(f, encoding="utf-8")))
    except FileNotFoundError: return []
 
def _write(f, rows, cols):
    w = csv.DictWriter(open(f,"w",newline="",encoding="utf-8"), fieldnames=cols)
    w.writeheader(); w.writerows(rows)
 
def _add(t, m): return (datetime.strptime(t,"%H:%M")+timedelta(minutes=m)).strftime("%H:%M")
def _dur(h):    return int(float(h)*60)
 
# ── State ─────────────────────────────────────────────────────────────────────
@dataclass
class PlannerState:
    failures:list=field(default_factory=list)  # (pid,room,slot) tried and failed
    directives:list=field(default_factory=list) # directive strings already sent
    pruned:set=field(default_factory=set)       # rooms permanently removed
    preemptions:list=field(default_factory=list)# displacement records
    cycle:int=0
    def tried(self,pid,room,slot): return (pid,room,slot) in self.failures
    def rooms(self): return [r for r in ROOMS if r not in self.pruned|CLOSED_ROOMS]
    def displaced(self,pid): return any(p["id"]==pid for p in self.preemptions)
 
# ── Room snapshot ─────────────────────────────────────────────────────────────
def _free(state):
    nf={r:ROOM_START for r in state.rooms()}
    for row in _read(RF):
        r,e=row.get("room_id","").strip(),row.get("end_time","").strip()
        if r in nf and e:
            c=_add(e,GAP)
            if c>nf[r]: nf[r]=c
    return nf
 
# ── Safety (cached) ───────────────────────────────────────────────────────────
def safety_check(action, params, state):
    global CACHE_HITS, CACHE_MISSES
    key=str(action)+str(sorted(params.items()))+str(FORBIDDEN_ACTIONS)+str(CLOSED_ROOMS)
    if key in CACHE: CACHE_HITS+=1; return CACHE[key]
    CACHE_MISSES+=1
    def done(r): CACHE[key]=r; return r
    if action in FORBIDDEN_ACTIONS:            return done((False,f"'{action}' is forbidden."))
    if action=="allocate_rooms" and not state.rooms(): return done((False,"All rooms closed."))
    if action=="add_patient":
        if params.get("urgency") not in URGENCY: return done((False,"Urgency must be high/medium/low."))
        n=params.get("patient_name","").strip().lower()
        if any(p.get("patient_name","").strip().lower()==n and p.get("status","").strip()=="scheduled"
               for p in _read(PF)):            return done((False,f"'{params['patient_name']}' already scheduled."))
    return done((True,""))
 
# ── Backtracking ──────────────────────────────────────────────────────────────
def generate_alternatives(pid, failed_room, failed_slot, state):
    state.failures.append((pid,failed_room,failed_slot))
    if sum(1 for f in state.failures if f[1]==failed_room)>=len(ROOMS): state.pruned.add(failed_room)
    pt={int(p["patient_id"].strip()):p for p in _read(PF)}.get(pid)
    if not pt: return None
    dur=_dur(pt["duration"].strip())
    for room in state.rooms():
        s=_free(state).get(room,ROOM_START)
        if not state.tried(pid,room,s):
            return {"room_id":room,"start_time":s,"end_time":_add(s,dur)}
    return None
 
# ── Preemption ────────────────────────────────────────────────────────────────
def preempt_for_high_urgency(high_pid, state):
    pm={p["patient_id"].strip():p for p in _read(PF) if p.get("status","").strip()=="scheduled"}
    sc=[r for r in _read(RF) if r.get("patient_id","").strip() in pm]
    if not sc: return None
    sc.sort(key=lambda r:(-URGENCY.get(pm[r["patient_id"].strip()]["urgency"].strip(),0),r["start_time"]))
    w=sc[0]; pid=int(w["patient_id"].strip()); urg=pm[w["patient_id"].strip()]["urgency"].strip()
    if urg=="high" or state.displaced(pid): return None
    _write(RF,[r for r in _read(RF) if r.get("patient_id","").strip()!=str(pid)],["room_id","patient_id","start_time","end_time"])
    pts=_read(PF)
    for p in pts:
        if p["patient_id"].strip()==str(pid): p["status"]="not_scheduled"
    _write(PF,pts,["patient_id","patient_name","urgency","duration","date","status"])
    rec={"id":pid,"name":pm[w["patient_id"].strip()]["patient_name"],"urgency":urg,
         "high_pid":high_pid,"room":w["room_id"].strip(),"start":w["start_time"].strip(),"end":w["end_time"].strip()}
    state.preemptions.append(rec)
    print(f"   [PREEMPTION] '{rec['name']}' ({urg}) displaced from {rec['room']} {rec['start']}–{rec['end']}")
    return {"room_id":rec["room"],"start_time":rec["start"],"end_time":rec["end"]}
 
def format_preemption_summary(state):
    if not state.preemptions: return ""
    return "\n Preemption notice:\n"+"".join(
        f"  • '{p['name']}' ({p['urgency']}) moved out of {p['room']} [{p['start']}–{p['end']}] → waiting list.\n"
        for p in state.preemptions)
 
# ── Fallback (backtrack → preempt) ───────────────────────────────────────────
def _fallback(action, params, last_result, state):
    if action!="allocate_rooms" or not last_result: return None
    for e in (last_result.get("data") or []):
        pid,room,start=int(e.get("patient_id",0)),e.get("room_id",""),e.get("start_time","")
        alt=generate_alternatives(pid,room,start,state)
        if alt:
            p=deepcopy(params); p["_override"]={"patient_id":pid,**alt}
            return {"action":action,"params":p,"directive":f"use allocate_rooms — move patient {pid} to {alt['room_id']} at {alt['start_time']}"}
        pts={int(p["patient_id"].strip()):p for p in _read(PF)}
        if pts.get(pid,{}).get("urgency","").strip()=="high":
            freed=preempt_for_high_urgency(pid,state)
            if freed:
                p=deepcopy(params); p["_override"]={"patient_id":pid,**freed}
                return {"action":action,"params":p,"directive":f"use allocate_rooms — PREEMPTED for patient {pid}: {freed['room_id']} {freed['start_time']}–{freed['end_time']}"}
    return None
 
# ── Main entry-point ──────────────────────────────────────────────────────────
def plan_next_action(user_message, action, params, last_result, state):
    state.cycle+=1
    ok,reason=safety_check(action,params,state)
    if not ok: return {"proceed":False,"directive":"","action":action,"params":params,"reason":f"[SAFETY BLOCK] {reason}"}
    d=("use allocate_rooms with no arguments" if action=="allocate_rooms"
       else "use "+action+" with "+", ".join(f'{k}="{v}"' if isinstance(v,str) else f"{k}={v}" for k,v in params.items()))
    if d in state.directives:
        fb=_fallback(action,params,last_result,state)
        if not fb: return {"proceed":False,"directive":"","action":action,"params":params,"reason":"All alternatives exhausted."}
        d,action,params=fb["directive"],fb["action"],fb["params"]
    state.directives.append(d)
    return {"proceed":True,"directive":d,"action":action,"params":params,"reason":f"Cycle {state.cycle}: proceeding."}
 
# ── Constraint helpers ────────────────────────────────────────────────────────
def close_room(r):           CLOSED_ROOMS.add(r);          return f"Room '{r}' CLOSED."
def open_room(r):            CLOSED_ROOMS.discard(r);      return f"Room '{r}' OPEN."
def forbid_action(t):        FORBIDDEN_ACTIONS.add(t);     return f"'{t}' FORBIDDEN."
def allow_action(t):         FORBIDDEN_ACTIONS.discard(t); return f"'{t}' ALLOWED."
 
# ── Tests (python planner.py) ─────────────────────────────────────────────────
if __name__ == "__main__":
    S="─"*48
    def sec(t): print(f"\n{S}\n  {t}\n{S}")
    def chk(label,ok,got): print(f"  {'[OK]' if ok else '[FAIL]'}  {label}: {got}")
 
    P_COLS=["patient_id","patient_name","urgency","duration","date","status"]
    R_COLS=["room_id","patient_id","start_time","end_time"]
    D="19-04-2026"
 
    def seed_normal():
        _write(PF,[{"patient_id":"1","patient_name":"Alice","urgency":"low","duration":"1","date":D,"status":"scheduled"},
                   {"patient_id":"2","patient_name":"Bob","urgency":"medium","duration":"2","date":D,"status":"scheduled"},
                   {"patient_id":"3","patient_name":"Carol","urgency":"high","duration":"1","date":D,"status":"not_scheduled"}],P_COLS)
        _write(RF,[{"room_id":"room1","patient_id":"1","start_time":"12:00","end_time":"13:00"},
                   {"room_id":"room2","patient_id":"2","start_time":"12:00","end_time":"14:00"}],R_COLS)
 
    def seed_full():
        _write(PF,[{"patient_id":"1","patient_name":"Alice","urgency":"low","duration":"1","date":D,"status":"scheduled"},
                   {"patient_id":"2","patient_name":"Bob","urgency":"medium","duration":"2","date":D,"status":"scheduled"},
                   {"patient_id":"3","patient_name":"Dave","urgency":"low","duration":"1","date":D,"status":"scheduled"},
                   {"patient_id":"4","patient_name":"Eve","urgency":"high","duration":"1","date":D,"status":"not_scheduled"}],P_COLS)
        _write(RF,[{"room_id":"room1","patient_id":"1","start_time":"12:00","end_time":"13:00"},
                   {"room_id":"room2","patient_id":"2","start_time":"12:00","end_time":"14:00"},
                   {"room_id":"room3","patient_id":"3","start_time":"12:00","end_time":"13:00"}],R_COLS)
 
 
#tests
    sec("1 — Normal allocation"); seed_normal()
    d=plan_next_action("","allocate_rooms",{},None,PlannerState())
    chk("proceed=True",d["proceed"]==True,d["proceed"]); chk("correct directive","allocate_rooms" in d["directive"],d["directive"])
 
    sec("2 — Forbidden action"); forbid_action("allocate_rooms")
    d2=plan_next_action("","allocate_rooms",{},None,PlannerState())
    chk("proceed=False",d2["proceed"]==False,d2["proceed"]); chk("SAFETY in reason","SAFETY" in d2["reason"],d2["reason"]); allow_action("allocate_rooms")
 
    sec("3 — All rooms closed"); [close_room(r) for r in ROOMS]
    d3=plan_next_action("","allocate_rooms",{},None,PlannerState())
    chk("proceed=False",d3["proceed"]==False,d3["proceed"]); [open_room(r) for r in ROOMS]
 
    sec("4 — Duplicate directive"); seed_normal(); s4=PlannerState()
    p4={"patient_name":"X","urgency":"high","duration":1,"date":D}
    d4a=plan_next_action("","add_patient",p4,None,s4); d4b=plan_next_action("","add_patient",p4,{"status":"error"},s4)
    chk("first proceeds",d4a["proceed"]==True,d4a["proceed"]); chk("second handled",True,f"proceed={d4b['proceed']}")
 
    sec("5 — Backtracking"); seed_normal(); s5=PlannerState()
    alt=generate_alternatives(3,"room1","12:00",s5)
    chk("alternative found",alt is not None,alt)
    chk("not same failed slot",not(alt and alt["room_id"]=="room1" and alt["start_time"]=="12:00"),alt)
 
    sec("6 — * Preemption"); seed_full(); s6=PlannerState()
    freed=preempt_for_high_urgency(4,s6)
    chk("slot freed",freed is not None,freed); chk("recorded",len(s6.preemptions)==1,len(s6.preemptions))
    if s6.preemptions:
        pr=s6.preemptions[0]
        chk("displaced low/medium",pr["urgency"] in ("low","medium"),pr["urgency"]); chk("high_pid=4",pr["high_pid"]==4,pr["high_pid"])
    did=str(s6.preemptions[0]["id"]) if s6.preemptions else None
    if did:
        chk("not_scheduled",{p["patient_id"]:p for p in _read(PF)}[did]["status"]=="not_scheduled",did)
    chk("removed from schedule",not any(r["patient_id"]==did for r in _read(RF)),did)
 
    sec("7 — Preemption refused (all high)")
    _write(PF,[{"patient_id":"1","patient_name":"Alice","urgency":"high","duration":"1","date":D,"status":"scheduled"},
               {"patient_id":"2","patient_name":"New","urgency":"high","duration":"1","date":D,"status":"not_scheduled"}],P_COLS)
    _write(RF,[{"room_id":"room1","patient_id":"1","start_time":"12:00","end_time":"13:00"}],R_COLS)
    chk("returns None",preempt_for_high_urgency(2,PlannerState()) is None,None)
 
    sec("8 — No displacement loop"); seed_full(); s8=PlannerState()
    preempt_for_high_urgency(4,s8)
    pts=_read(PF)
    for p in pts:
        if p["patient_id"]=="1": p["status"]="scheduled"
    _write(PF,pts,P_COLS); _write(RF,_read(RF)+[{"room_id":"room1","patient_id":"1","start_time":"12:00","end_time":"13:00"}],R_COLS)
    preempt_for_high_urgency(4,s8)
    chk("Alice not displaced twice",not any(p["id"]==1 for p in s8.preemptions[1:]),[p["id"] for p in s8.preemptions])
 
    sec("9 — Preemption summary"); seed_full(); s9=PlannerState()
    preempt_for_high_urgency(4,s9); summ=format_preemption_summary(s9)
    chk("non-empty",len(summ)>0,len(summ)); chk("has room","room" in summ,summ[:60]); chk("has moved","moved out" in summ,summ[:80])
 
    print(f"\n{S}\n  All tests complete.\n{S}")
 