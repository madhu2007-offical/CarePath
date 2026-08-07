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
    """Run deterministic policy validation against patient record."""
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
    required_fields = json.loads(rule["required_fields"])
    
    # Run deterministic checks
    checklist = []
    present_count = 0
    
    # 1. Diagnosis Check
    diag_present = bool(patient["diagnosis"] and patient["diagnosis"].strip())
    checklist.append({
        "field": "diagnosis",
        "label": "Diagnosis Present",
        "status": diag_present
    })
    if diag_present and "diagnosis" in required_fields:
        present_count += 1
        
    # 2. Medication History Check
    med_present = bool(patient["medications"] and patient["medications"].lower() != "none")
    checklist.append({
        "field": "medication_history",
        "label": "Medication History Present",
        "status": med_present
    })
    if med_present and "medication_history" in required_fields:
        present_count += 1
        
    # 3. Referral Check
    ref_present = patient["referral_status"] == "Present"
    checklist.append({
        "field": "referral",
        "label": "Referral Letter Present",
        "status": ref_present
    })
    if ref_present and "referral" in required_fields:
        present_count += 1
        
    # 4. Lab Report Check
    lab_present = patient["lab_reports"] and patient["lab_reports"].lower() != "missing"
    checklist.append({
        "field": "lab_report",
        "label": "Lab Report Present",
        "status": lab_present
    })
    if lab_present and "lab_report" in required_fields:
        present_count += 1

    # Step Therapy Check
    step_met = True
    failed_count = 0
    med_str = patient["medications"].upper()
    if "SNRI" in med_str:
        # SNRI implies they failed SSRI first
        failed_count = 2
    elif "SSRI" in med_str or "BENZODIAZEPINE" in med_str:
        failed_count = 1
    else:
        failed_count = 0
        
    if rule["step_therapy_required"]:
        step_met = failed_count >= rule["min_failed_therapies"]
        checklist.append({
            "field": "step_therapy",
            "label": f"Step Therapy Met ({failed_count}/{rule['min_failed_therapies']} failed therapies)",
            "status": step_met
        })

    # Computed Readiness Score based only on required fields
    total_required = len(required_fields)
    readiness_score = int((present_count / total_required) * 100) if total_required > 0 else 100
    
    return {
        "treatment": req.treatment,
        "checklist": checklist,
        "readiness_score": readiness_score,
        "failed_therapies_count": failed_count,
        "step_therapy_met": step_met
    }

@app.post("/api/patients/{id}/generate-letter")
def generate_letter(id: int, req: LetterRequest):
    """Call Gemini to generate the PA letter and suggested next steps."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE id = ?", (id,))
    patient = cursor.fetchone()
    conn.close()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    patient = dict(patient)
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # Formulate context variables for Gemini
    checklist = req.validation_results.get("checklist", [])
    missing_docs = [item["label"] for item in checklist if not item["status"]]
    present_docs = [item["label"] for item in checklist if item["status"]]
    
    prompt_letter = f"""
    You are a clinical administrative assistant drafting a formal Prior Authorization (PA) letter for a healthcare provider.
    Write a formal prior authorization request letter to the payer requesting approval for the treatment: "{req.treatment}".
    
    Patient Details:
    - Name: {patient['name']}
    - Age: {patient['age']}
    - Insurance Plan: {patient['insurance_plan']}
    - Diagnosis Details: {patient['diagnosis']}
    - Current/Past Medications: {patient['medications']}
    - Referral Document: {patient['referral_status']}
    - Lab Report: {patient['lab_reports']}
    
    Validation Results Context:
    - Present Documents: {', '.join(present_docs) if present_docs else 'None'}
    - Missing Documents: {', '.join(missing_docs) if missing_docs else 'None'}
    - Readiness Score: {req.validation_results.get('readiness_score')}%
    - Step Therapy requirement met: {req.validation_results.get('step_therapy_met')} ({req.validation_results.get('failed_therapies_count')} failed therapies documented)
    
    Your letter MUST include:
    1. Header with today's date, patient name, patient ID, and insurance plan.
    2. Executive Summary requesting authorization for "{req.treatment}".
    3. Clinical Summary detailing the diagnosis, severity (Y-BOCS scores if applicable), and symptom history.
    4. Medical Necessity Argument: Justify why this therapy is needed. Mention the medication history (Step Therapy context). If the step therapy requirement is not fully met, explain the clinical rationale or urge expedited review.
    5. An explicit "Supporting Documentation" section. In this section, list the documents that are enclosed (Present Documents) and explicitly note any documents that are currently missing but are being expedited/requested (Missing Documents).
    6. Formal closing from the healthcare provider.
    
    Write the letter in clear, formal, clinical prose. Use professional markdown formatting.
    """

    prompt_next_steps = f"""
    Based on the following missing items for patient {patient['name']}'s prior authorization check for "{req.treatment}",
    generate exactly 2 to 3 concrete, actionable next steps for the clinical coordinator to gather the missing documents.
    
    Missing items list:
    {', '.join(missing_docs) if missing_docs else 'None (All required documentation present)'}
    
    Format the output as a simple JSON array of strings, for example:
    [
      "Request referral letter from primary care physician",
      "Attach most recent lab panel dated within 90 days"
    ]
    Do not return any markdown code blocks or wrapper text, just the raw JSON array.
    """

    letter_text = ""
    next_steps_list = []

    if api_key:
        try:
            # We can use either the new google-genai client or import google.generativeai
            # Let's import the client inside to handle any import issues dynamically
            from google import genai
            client = genai.Client(api_key=api_key)
            
            # Generate Letter
            response_letter = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_letter,
            )
            letter_text = response_letter.text
            
            # Generate Next Steps
            response_steps = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_next_steps,
            )
            steps_content = response_steps.text.strip()
            
            # Clean JSON if wrapped in markdown blocks
            if steps_content.startswith("```"):
                lines = steps_content.split("\n")
                if lines[0].startswith("```json") or lines[0].startswith("```"):
                    lines = lines[1:-1]
                steps_content = "\n".join(lines).strip()
                
            next_steps_list = json.loads(steps_content)
        except Exception as e:
            # Fallback to mock generator if API call fails
            letter_text = f"""### PRIOR AUTHORIZATION REQUEST (DEMO FALLBACK - API Error)
**Date:** August 7, 2026  
**Patient Name:** {patient['name']}  
**Patient ID:** {patient['patient_id']}  
**Insurance Plan:** {patient['insurance_plan']}  
**Requested Treatment:** {req.treatment}  

Dear Medical Director,

We are writing to request a Prior Authorization for **{req.treatment}** for our patient, **{patient['name']}**, age {patient['age']}, who presents with:
* **Diagnosis:** {patient['diagnosis']}
* **Medication History:** {patient['medications']}

**Medical Necessity:**
The patient has tried and failed relevant therapies. The requested treatment is medically necessary to manage OCD symptoms and prevent further clinical deterioration.

**Supporting Documentation:**
* Enclosed: {', '.join(present_docs) if present_docs else 'None'}
* Missing/Pending: {', '.join(missing_docs) if missing_docs else 'None'}

Please contact our clinic for any further information.

Sincerely,  
CareGate Clinical Team
*(Note: This letter was generated via demo fallback due to an API exception: {str(e)})*"""
            
            # Generate static next steps
            next_steps_list = []
            for item in missing_docs:
                next_steps_list.append(f"Obtain and verify clinical records for: {item}")
            if not next_steps_list:
                next_steps_list.append("Verify all clinical records are signed and dated by the provider.")
    else:
        # Fallback if API key is not configured
        letter_text = f"""### PRIOR AUTHORIZATION REQUEST (DEMO FALLBACK - No API Key)
**Date:** August 7, 2026  
**Patient Name:** {patient['name']}  
**Patient ID:** {patient['patient_id']}  
**Insurance Plan:** {patient['insurance_plan']}  
**Requested Treatment:** {req.treatment}  

Dear Medical Director,

We are writing to request a Prior Authorization for **{req.treatment}** for our patient, **{patient['name']}**, who presents with **{patient['diagnosis']}**.

**Clinical History & Step Therapy:**
* Current medications: {patient['medications']}
* Documented failed therapies: {req.validation_results.get('failed_therapies_count')}

**Supporting Documentation:**
* Present: {', '.join(present_docs) if present_docs else 'None'}
* Missing/Pending: {', '.join(missing_docs) if missing_docs else 'None'}

Please approve this authorization or contact our clinic with any questions.

Sincerely,  
CareGate Clinical Team
*(Note: Please configure a valid GEMINI_API_KEY in the .env file to enable real AI generation.)*"""
        
        next_steps_list = []
        for item in missing_docs:
            next_steps_list.append(f"Acquire missing documentation for: {item}")
        if not next_steps_list:
            next_steps_list.append("Review complete file and submit to insurer portal.")

    # Save request history
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO requests (patient_id, patient_name, treatment, readiness_score, validation_results, letter_text, next_steps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            patient['patient_id'],
            patient['name'],
            req.treatment,
            req.validation_results.get("readiness_score"),
            json.dumps(req.validation_results),
            letter_text,
            json.dumps(next_steps_list)
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Failed to save request history:", e)
        
    return {
        "letter": letter_text,
        "next_steps": next_steps_list
    }

@app.get("/api/requests")
def list_requests():
    """Retrieve previously generated requests."""
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
        requests.append(d)
    return requests
