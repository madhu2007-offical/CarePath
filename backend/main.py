import os
import json
from fastapi import FastAPI, HTTPException, Body, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import sqlite3

# Load environment variables from project root .env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import database
import agents

app = FastAPI(title="CareGate API", version="1.0.0")

# Enable CORS for React frontend (default Vite dev server on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
def startup():
    database.init_db()

# Models
class ValidationRequest(BaseModel):
    treatment: str

class LetterRequest(BaseModel):
    treatment: str
    patient_data: Dict[str, Any]
    validation_results: Dict[str, Any]

class PatientCreate(BaseModel):
    patient_id: str
    name: str
    age: int
    diagnosis: str
    medications: str
    referral_status: str
    lab_reports: str
    insurance_plan: str

# Helper to get db connection
def get_db():
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.post("/api/upload")
def upload_dataset():
    """Reset and re-seed the patients database from the default CSV."""
    try:
        # Re-run init_db which seeds patients if empty.
        # To force reset, we can clear the patients table first.
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM patients")
        conn.commit()
        conn.close()
        
        database.init_db()
        return {"status": "success", "message": "Database re-seeded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/patients")
def create_patient(patient: PatientCreate):
    """Add a new patient record manually or from CSV import."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO patients (patient_id, name, age, diagnosis, medications, referral_status, lab_reports, insurance_plan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient.patient_id,
            patient.name,
            patient.age,
            patient.diagnosis,
            patient.medications,
            patient.referral_status,
            patient.lab_reports,
            patient.insurance_plan
        ))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return {"status": "success", "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/patients")
def list_patients():
    """Retrieve all patient records."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/patients/{id}")
def get_patient(id: int):
    """Retrieve a single patient record by ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE id = ?", (id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    return dict(row)

@app.get("/api/policy-rules")
def get_policy_rules():
    """Retrieve all policy rules."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM policy_rules")
    rows = cursor.fetchall()
    conn.close()
    
    rules = []
    for r in rows:
        d = dict(r)
        d["required_fields"] = json.loads(d["required_fields"])
        rules.append(d)
    return rules

@app.post("/api/patients/{id}/validate")
def validate_policy(id: int, req: ValidationRequest):
    """Run agentic extraction and criteria matching validation."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE id = ?", (id,))
    patient = cursor.fetchone()
    
    cursor.execute("SELECT * FROM policy_rules WHERE treatment = ?", (req.treatment,))
    rule = cursor.fetchone()
    conn.close()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not rule:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    
    patient = dict(patient)
    rule = dict(rule)
    rule["required_fields"] = json.loads(rule["required_fields"])
    
    # 1. Construct raw text record for Extraction Agent
    raw_notes = f"""
    Patient ID: {patient['patient_id']}
    Demographics: {patient['name']}, Age {patient['age']}
    Diagnosis Notes: {patient['diagnosis']}
    Active Medications: {patient['medications']}
    Referral Letter Status: {patient['referral_status']}
    Lab Reports Available: {patient['lab_reports']}
    Insurance Plan: {patient['insurance_plan']}
    Requested Treatment: {req.treatment}
    """
    
    # 2. Run Extraction Agent
    extracted_data = agents.run_extraction_agent(raw_notes)
    # Ensure ID and treatment match DB state
    extracted_data["patient_id"] = patient["patient_id"]
    extracted_data["treatment_requested"] = req.treatment
    extracted_data["insurance_plan"] = patient["insurance_plan"]
    
    # Adapt prior therapies based on DB medication history if empty
    if not extracted_data.get("prior_therapies_tried"):
        meds = patient["medications"].upper()
        if "SNRI" in meds:
            extracted_data["prior_therapies_tried"] = ["SSRI", "SNRI"]
        elif "SSRI" in meds or "BENZODIAZEPINE" in meds:
            extracted_data["prior_therapies_tried"] = [patient["medications"]]
        else:
            extracted_data["prior_therapies_tried"] = []

    # 3. Run Criteria-Matching Agent
    validation_output = agents.run_criteria_matching_agent(extracted_data, rule)
    
    # 4. Map checklist items to UI format
    checklist_mapped = []
    present_count = 0
    required_fields = ["diagnosis", "medication", "referral", "lab_report"]
    
    for item in validation_output.get("checklist", []):
        field = item.get("field")
        status_str = item.get("status", "missing")
        note = item.get("note", "")
        
        labels = {
            "diagnosis": "Diagnosis Present",
            "medication": "Medication History Present",
            "referral": "Referral Letter Present",
            "lab_report": "Lab Report Present"
        }
        label = labels.get(field, f"{field.capitalize()} Present")
        if note:
            label += f" ({note})"
            
        is_present = status_str == "present"
        checklist_mapped.append({
            "field": field,
            "label": label,
            "status": is_present
        })
        
        if is_present and field in required_fields:
            present_count += 1
            
    # Add step therapy to checklist if rule demands it
    step_met = validation_output.get("step_therapy_met", False)
    if rule["step_therapy_required"]:
        checklist_mapped.append({
            "field": "step_therapy",
            "label": f"Step Therapy Met (Prior therapies: {', '.join(extracted_data.get('prior_therapies_tried', []))})",
            "status": step_met
        })

    # Computed Readiness Score based only on the 4 required fields
    readiness_score = int((present_count / len(required_fields)) * 100)
    
    return {
        "treatment": req.treatment,
        "patient_data": extracted_data,
        "validation_results": {
            "checklist": checklist_mapped,
            "readiness_score": readiness_score,
            "step_therapy_met": step_met,
            "overall_confidence": validation_output.get("overall_confidence", 100),
            "escalate_to_human": validation_output.get("escalate_to_human", False),
            "escalation_reason": validation_output.get("escalation_reason", "")
        }
    }

@app.post("/api/patients/{id}/generate-letter")
def generate_letter(id: int, req: LetterRequest):
    """Call specialized agents to generate PA letter, next steps, and run case audit."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE id = ?", (id,))
    patient = cursor.fetchone()
    conn.close()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    patient = dict(patient)
    
    # 1. Run Letter-Generation Agent
    letter_text = agents.run_letter_generation_agent(req.patient_data, req.validation_results)
    
    # 2. Extract missing fields from checklist for Suggested-Next-Steps Agent
    checklist = req.validation_results.get("checklist", [])
    missing_fields = [item["label"] for item in checklist if not item["status"]]
    
    # 3. Run Suggested-Next-Steps Agent
    next_steps_output = agents.run_next_steps_agent(missing_fields, req.treatment)
    next_steps_list = next_steps_output.get("next_steps", [])
    
    # 4. Run Escalation / Audit Agent
    audit_trail_data = agents.run_audit_agent(req.patient_data, req.validation_results, letter_text)
    
    # Save request history to SQLite database (including audit_trail)
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO requests (patient_id, patient_name, treatment, readiness_score, validation_results, letter_text, next_steps, audit_trail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient['patient_id'],
            patient['name'],
            req.treatment,
            req.validation_results.get("readiness_score", 0),
            json.dumps(req.validation_results),
            letter_text,
            json.dumps(next_steps_list),
            json.dumps(audit_trail_data)
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Failed to save request history:", e)
        
    return {
        "letter": letter_text,
        "next_steps": next_steps_list,
        "audit_trail": audit_trail_data
    }

@app.get("/api/requests")
def list_requests():
    """Retrieve previously generated requests with audit trails."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM requests ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    requests = []
    for r in rows:
        d = dict(r)
        d["validation_results"] = json.loads(d["validation_results"])
        d["next_steps"] = json.loads(d["next_steps"])
        if d.get("audit_trail"):
            d["audit_trail"] = json.loads(d["audit_trail"])
        else:
            d["audit_trail"] = None
        requests.append(d)
    return requests
