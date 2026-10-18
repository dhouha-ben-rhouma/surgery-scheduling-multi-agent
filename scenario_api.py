from __future__ import annotations
import csv
import json
import os
import time
from datetime import datetime, timedelta
import random

import requests
from faker import Faker
from security import guard_url, redact

# ── Faker modifié : Uniquement Arabe et plus de diversité ─────────────────────
# Suppression de "fr_FR" pour garantir des noms 100% arabes
fake = Faker(["ar_AA"])          
Faker.seed(42)
random.seed(42)

# ── World Bank API ────────────────────────────────────────────────────────────
WB_BASE = "https://api.worldbank.org/v2"

INDICATORS = {
    "SP.POP.TOTL":    "Population, total",
    "SH.MED.BEDS.ZS": "Hospital beds (per 1,000 people)",
    "SH.XPD.CHEX.GD.ZS": "Current health expenditure (% of GDP)",
    "SP.DYN.LE00.IN": "Life expectancy at birth",
}

PATIENTS_FILE = "patients.csv"
ROOMS_FILE    = "rooms_schedule.csv"
P_COLS = ["patient_id", "patient_name", "urgency", "duration", "date", "status"]
R_COLS = ["room_id", "patient_id", "start_time", "end_time"]

def reset_csv() -> None:
    for path, cols in [(PATIENTS_FILE, P_COLS), (ROOMS_FILE, R_COLS)]:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=cols).writeheader()
    print("  [RESET] Fichiers CSV réinitialisés.")

def fetch_world_bank_indicator(indicator: str, country: str = "TN") -> float | None:
    url = f"{WB_BASE}/country/{country}/indicator/{indicator}?format=json&mrv=5"
    allowed, reason = guard_url(url)
    if not allowed:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list) and len(payload) > 1:
            for entry in payload[1]:
                if entry.get("value") is not None:
                    return float(entry["value"])
    except Exception:
        return None
    return None

def fetch_indicators() -> dict:
    print("\n  Récupération des indicateurs de santé (Tunisie)...")
    results = {}
    # Valeurs par défaut si l'API échoue
    mocks = {"SP.POP.TOTL": 12000000, "SH.MED.BEDS.ZS": 2.3, "SH.XPD.CHEX.GD.ZS": 7.2, "SP.DYN.LE00.IN": 76.1}
    for code, label in INDICATORS.items():
        val = fetch_world_bank_indicator(code) or mocks[code]
        results[code] = {"label": label, "value": val}
    return results

# ── Génération de la cohorte augmentée ────────────────────────────────────────

def generate_patient_cohort(indicators: dict) -> list[dict]:
    """
    Génère un plus grand nombre de patients avec des noms uniquement arabes.
    """
    beds_per_1k = indicators["SH.MED.BEDS.ZS"]["value"]
    
    # MODIFICATION : Augmentation de la limite à 30 patients au lieu de 15
    n_patients = max(10, min(30, int(beds_per_1k / 0.2))) 

    patients = []
    base_date = datetime.today()

    for i in range(1, n_patients + 1):
        # Utilise la locale ar_AA configurée plus haut
        name = fake.name() 
        
        urgency = random.choice(["high", "medium", "low"])
        duration = random.choice([1.0, 1.5, 2.0, 3.0, 4.0])
        
        patients.append({
            "patient_id":   i,
            "patient_name": name,
            "urgency":      urgency,
            "duration":     duration,
            "date":         (base_date + timedelta(days=random.randint(0, 30))).strftime("%d-%m-%Y"),
            "status":       "not_scheduled",
        })

    return patients

def scenario_external_api() -> None:
    reset_csv()
    indicators = fetch_indicators()
    patients = generate_patient_cohort(indicators)
    
    # Écriture dans le CSV
    with open(PATIENTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=P_COLS)
        writer.writeheader()
        writer.writerows(patients)
    
    print(f"\n  [OK] SUCCÈS : {len(patients)} patients (noms arabes) générés dans {PATIENTS_FILE}")
    for p in patients[:10]: # Affiche les 10 premiers pour vérifier
        print(f"    - {p['patient_name']}")
    print("    ...")

if __name__ == "__main__":
    scenario_external_api()