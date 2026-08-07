import os
import sqlite3
import csv
import json
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "caregate.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "patient_data.csv")

MOCK_NAMES = [
    "James Smith", "Michael Brown", "Robert Jones", "William Garcia", "David Miller",
    "Richard Davis", "Joseph Rodriguez", "Thomas Martinez", "Charles Hernandez", "Christopher Lopez",
    "Mary Williams", "Patricia Johnson", "Jennifer Brown", "Linda Jones", "Elizabeth Miller",
    "Barbara Davis", "Susan Rodriguez", "Jessica Martinez", "Sarah Hernandez", "Karen Lopez"
]

MOCK_INSURANCE = [
    "Aetna PPO Choice", "Blue Cross Blue Shield PPO", "Cigna HealthFlex", 
    "UnitedHealthcare Select Plus", "Humana ChoiceCare"
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create Patients Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT UNIQUE,
            name TEXT,
            age INTEGER,
            diagnosis TEXT,
            medications TEXT,
            referral_status TEXT,
            lab_reports TEXT,
            insurance_plan TEXT
        )
    """)

    # Create PolicyRules Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS policy_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treatment TEXT UNIQUE,
            required_fields TEXT,
            step_therapy_required INTEGER,
            min_failed_therapies INTEGER
        )
    """)

    # Create Requests Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            patient_name TEXT,
            treatment TEXT,
            readiness_score INTEGER,
            validation_results TEXT,
            letter_text TEXT,
            next_steps TEXT,
            audit_trail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Seed Policy Rules
    cursor.execute("SELECT COUNT(*) FROM policy_rules")
    if cursor.fetchone()[0] == 0:
        rules = [
            (
                "Biologic Therapy - Rheumatoid Arthritis",
                json.dumps(["diagnosis", "medication_history", "referral", "lab_report"]),
                1,
                2
            ),
            (
                "Fluvoxamine Step Therapy - Obsessive Compulsive Disorder",
                json.dumps(["diagnosis", "medication_history", "referral", "lab_report"]),
                1,
                2
            )
        ]
        cursor.executemany("""
            INSERT INTO policy_rules (treatment, required_fields, step_therapy_required, min_failed_therapies)
            VALUES (?, ?, ?, ?)
        """, rules)
        conn.commit()

    # Seed Patient Table from CSV
    cursor.execute("SELECT COUNT(*) FROM patients")
    if cursor.fetchone()[0] == 0 and os.path.exists(CSV_PATH):
        random.seed(42)  # For deterministic seeding
        with open(CSV_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            patients_to_insert = []
            for idx, row in enumerate(reader):
                pid = row.get("Patient ID", f"MOCK_{1000 + idx}")
                age = int(row.get("Age", 30))
                meds = row.get("Medications", "None")

                # Generate a mock name
                name = MOCK_NAMES[idx % len(MOCK_NAMES)]
                # Add variation to name to avoid identical duplicates
                if idx >= len(MOCK_NAMES):
                    name += f" {chr(65 + (idx // len(MOCK_NAMES)) % 26)}."

                # Construct realistic diagnosis based on CSV columns
                obs = row.get("Obsession Type", "General")
                comp = row.get("Compulsion Type", "General")
                prev = row.get("Previous Diagnoses", "None")
                y_bocs_obs = row.get("Y-BOCS Score (Obsessions)", "0")
                y_bocs_comp = row.get("Y-BOCS Score (Compulsions)", "0")
                
                diagnosis_desc = f"Obsessive-Compulsive Disorder (Obsession: {obs}, Compulsion: {comp}, Y-BOCS: {int(y_bocs_obs)+int(y_bocs_comp)})."
                if prev and prev != "None":
                    diagnosis_desc += f" Comorbid: {prev}."

                # Randomize clinical documentation status for realistic PA demo
                ref_status = "Present" if random.random() > 0.35 else "Missing"
                lab_status = "Present" if random.random() > 0.3 else "Missing"
                insurance = MOCK_INSURANCE[idx % len(MOCK_INSURANCE)]

                patients_to_insert.append((
                    pid, name, age, diagnosis_desc, meds, ref_status, lab_status, insurance
                ))

            cursor.executemany("""
                INSERT OR IGNORE INTO patients (patient_id, name, age, diagnosis, medications, referral_status, lab_reports, insurance_plan)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, patients_to_insert)
            conn.commit()

    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
