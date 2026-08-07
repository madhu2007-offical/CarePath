import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Helper to get Gemini Client
def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        print("Failed to initialize Google GenAI Client:", e)
        return None

# ==========================================
# 1. EXTRACTION AGENT
# ==========================================
def run_extraction_agent(raw_record: str) -> dict:
    """Reads a patient's raw clinical record and extracts structured fields."""
    system_instruction = """
    You are the Extraction Agent in a healthcare prior-authorization system called CareGate.
    Your only job is to read a patient's raw clinical record and convert it into clean, structured data.
    You do not make judgments, recommendations, or medical necessity arguments — that is a different agent's job.

    Given a patient record (which may include unstructured notes), extract exactly these fields and return valid JSON only:
    {
      "patient_id": "",
      "diagnosis": "",
      "diagnosis_code_icd10": "",
      "medications": [],
      "treatment_requested": "",
      "referral_status": "present | missing | unclear",
      "lab_reports": "present | missing | unclear",
      "prior_therapies_tried": [],
      "insurance_plan": ""
    }

    Rules:
    - If a field is not present in the record, use "unclear" (for status fields) or an empty value — never guess or fabricate clinical information.
    - Never infer a diagnosis or medication that is not explicitly stated in the source text.
    - Output must be valid JSON with no markdown formatting, no explanation text before or after.
    """
    
    client = get_gemini_client()
    if client:
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"System Instructions:\n{system_instruction}\n\nPatient Record:\n{raw_record}",
                config=dict(response_mime_type="application/json")
            )
            text = response.text.strip()
            # Parse and return
            return json.loads(text)
        except Exception as e:
            print("Extraction Agent API error:", e)
            
    # Mock Fallback
    print("Running Extraction Agent Fallback...")
    return {
        "patient_id": "MOCK_EXTRACTED",
        "diagnosis": "Obsessive-Compulsive Disorder (OCD)",
        "diagnosis_code_icd10": "F42.2",
        "medications": ["SSRI (Escitalopram)"],
        "treatment_requested": "Fluvoxamine Step Therapy - Obsessive Compulsive Disorder",
        "referral_status": "missing",
        "lab_reports": "present",
        "prior_therapies_tried": ["SSRI"],
        "insurance_plan": "Aetna PPO Choice"
    }

# ==========================================
# 2. CRITERIA-MATCHING AGENT
# ==========================================
def run_criteria_matching_agent(patient_data: dict, policy_rules: dict) -> dict:
    """Matches structured patient data against insurer policies."""
    system_instruction = """
    You are the Criteria-Matching Agent in CareGate, a prior-authorization readiness system.
    You receive structured patient data and a payer's policy rules (as JSON).
    Your job is to determine which required fields are present, missing, or insufficient — and nothing else.
    You do not draft letters and you do not decide whether to approve or deny anything; only a licensed reviewer or payer makes that call.

    Input Format:
    patient_data (JSON), policy_rules (JSON)

    Return valid JSON only:
    {
      "checklist": [
        {"field": "diagnosis", "status": "present | missing | insufficient", "note": ""},
        {"field": "medication", "status": "present | missing | insufficient", "note": ""},
        {"field": "referral", "status": "present | missing | insufficient", "note": ""},
        {"field": "lab_report", "status": "present | missing | insufficient", "note": ""}
      ],
      "step_therapy_met": true | false,
      "overall_confidence": 0-100,
      "escalate_to_human": true | false,
      "escalation_reason": ""
    }

    Rules:
    - Set escalate_to_human to true if: policy_rules does not clearly cover this treatment type, if evidence is ambiguous, or if overall_confidence is below 70.
    - Never mark a field "present" unless it is explicitly present in patient_data — do not assume or infer.
    - Be conservative: when uncertain, flag for human review rather than guessing.
    """
    
    client = get_gemini_client()
    if client:
        try:
            prompt = f"Patient Data:\n{json.dumps(patient_data)}\n\nPolicy Rules:\n{json.dumps(policy_rules)}"
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"System Instructions:\n{system_instruction}\n\nInput Data:\n{prompt}",
                config=dict(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except Exception as e:
            print("Criteria Matching Agent API error:", e)

    # Mock Fallback
    print("Running Criteria Matching Agent Fallback...")
    has_ref = patient_data.get("referral_status") == "present"
    has_lab = patient_data.get("lab_reports") == "present"
    has_med = len(patient_data.get("medications", [])) > 0 or patient_data.get("medications") != "None"
    
    checklist = [
        {"field": "diagnosis", "status": "present", "note": "Diagnosis matches guidelines"},
        {"field": "medication", "status": "present" if has_med else "missing", "note": ""},
        {"field": "referral", "status": "present" if has_ref else "missing", "note": "Referral letter not attached"},
        {"field": "lab_report", "status": "present" if has_lab else "missing", "note": "CBC panel present"}
    ]
    
    # Check step therapy
    meds_tried = len(patient_data.get("prior_therapies_tried", []))
    min_failed = policy_rules.get("min_failed_therapies", 2)
    step_therapy_met = meds_tried >= min_failed
    
    escalate = not has_ref or not step_therapy_met
    
    return {
        "checklist": checklist,
        "step_therapy_met": step_therapy_met,
        "overall_confidence": 95 if not escalate else 65,
        "escalate_to_human": escalate,
        "escalation_reason": "Missing required referral letter or failed step therapy criteria" if escalate else ""
    }

# ==========================================
# 3. LETTER-GENERATION AGENT
# ==========================================
def run_letter_generation_agent(patient_data: dict, checklist_data: dict) -> str:
    """Drafts a formal prior authorization letter based on patient data and checklist results."""
    system_instruction = """
    You are the Letter-Generation Agent in CareGate. You write formal prior authorization letters on behalf of a physician, based on structured patient data and validation results you are given. You write persuasive, clinically accurate medical necessity arguments — you do not fabricate clinical facts not present in the input data.

    Input: patient_data (JSON), checklist (JSON from Criteria-Matching Agent)

    Write a formal prior authorization letter including:
    1. Patient and provider identification (use placeholders like [Provider Name] if not supplied)
    2. Diagnosis and relevant clinical history, using only the facts provided
    3. Treatment being requested and medical necessity rationale
    4. Prior therapies tried, if provided, framed as step-therapy documentation
    5. A "Supporting Documentation" section that explicitly lists any fields marked "missing" or "insufficient" in the checklist, rather than omitting them silently

    Rules:
    - Do not invent lab values, dates, or clinical details not present in the input.
    - If a required field is missing, state that clearly in the letter rather than glossing over it — a physician will review this before it is ever submitted.
    - Tone: formal, clinical, concise. No filler language.
    - Output plain text formatted as a real letter, not JSON.
    """
    
    client = get_gemini_client()
    if client:
        try:
            prompt = f"Patient Data:\n{json.dumps(patient_data)}\n\nChecklist Data:\n{json.dumps(checklist_data)}"
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"System Instructions:\n{system_instruction}\n\nInput Data:\n{prompt}"
            )
            return response.text.strip()
        except Exception as e:
            print("Letter Generation Agent API error:", e)

    # Mock Fallback
    print("Running Letter Generation Agent Fallback...")
    missing_items = [c["field"] for c in checklist_data.get("checklist", []) if c["status"] != "present"]
    present_items = [c["field"] for c in checklist_data.get("checklist", []) if c["status"] == "present"]
    
    return f"""### PRIOR AUTHORIZATION REQUEST
DATE: August 7, 2026

PATIENT ID: {patient_data.get('patient_id')}
INSURANCE PLAN: {patient_data.get('insurance_plan')}
REQUESTED TREATMENT: {patient_data.get('treatment_requested')}

Dear Medical Director,

I am writing to request a prior authorization for {patient_data.get('treatment_requested')} for patient ID {patient_data.get('patient_id')}.

CLINICAL HISTORY & DIAGNOSIS:
The patient is diagnosed with: {patient_data.get('diagnosis')} (ICD-10: {patient_data.get('diagnosis_code_icd10')}).
Documented medications: {', '.join(patient_data.get('medications', []))}.

STEP THERAPY DOCUMENTATION:
Prior therapies tried: {', '.join(patient_data.get('prior_therapies_tried', []))}.
Step therapy criteria met: {checklist_data.get('step_therapy_met')}.

SUPPORTING DOCUMENTATION STATUS:
- Enclosed: {', '.join(present_items) if present_items else 'None'}
- Missing / Pending Request: {', '.join(missing_items) if missing_items else 'None'}

Please expedite review of this request.

Sincerely,
[Attending Physician]
CareGate Clinical Team
"""

# ==========================================
# 4. SUGGESTED-NEXT-STEPS AGENT
# ==========================================
def run_next_steps_agent(missing_fields: list, treatment_requested: str) -> dict:
    """Generates concrete next steps for missing fields."""
    system_instruction = """
    You are the Next-Steps Agent in CareGate. Given a list of missing or insufficient documentation fields for a prior authorization request, generate 2-4 concrete, actionable next steps a clinic staff member could take today.

    Input: missing_fields (list), treatment_requested (string)

    Return valid JSON only:
    {
      "next_steps": [
        "Request referral letter from primary care physician",
        "Attach most recent lab panel dated within 90 days"
      ]
    }

    Rules:
    - Each step must be concrete and actionable, not generic advice like "gather more documentation."
    - Do not suggest steps unrelated to the specific missing fields provided.
    - Keep each step to one sentence.
    """
    
    client = get_gemini_client()
    if client:
        try:
            prompt = f"Missing Fields:\n{json.dumps(missing_fields)}\n\nTreatment Requested: {treatment_requested}"
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"System Instructions:\n{system_instruction}\n\nInput Data:\n{prompt}",
                config=dict(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except Exception as e:
            print("Next Steps Agent API error:", e)

    # Mock Fallback
    print("Running Next Steps Agent Fallback...")
    steps = []
    for field in missing_fields:
        if "referral" in field.lower():
            steps.append("Request a formal psychiatric referral letter from the patient's primary care physician.")
        elif "lab" in field.lower():
            steps.append("Schedule the patient for a complete blood count (CBC) or relevant metabolic lab draw.")
        elif "medication" in field.lower() or "therapy" in field.lower():
            steps.append("Update the patient's chart with full pharmacy dispense records showing SSRI/SNRI usage history.")
            
    if not steps:
        steps.append(f"Submit the prior authorization request for {treatment_requested} to the insurer portal.")
        
    return {"next_steps": steps[:4]}

# ==========================================
# 5. ESCALATION / AUDIT AGENT
# ==========================================
def run_audit_agent(extraction_output: dict, validation_output: dict, letter_output: str = None) -> dict:
    """Produces a transparent, human-readable audit trail entry for the case."""
    system_instruction = """
    You are the Audit Agent in CareGate. You do not generate new content — you review the outputs of the other agents and produce a transparent, human-readable audit trail entry for this case.

    Input: extraction_output, validation_output, letter_output (or null if not yet generated)

    Return valid JSON only:
    {
      "case_summary": "one sentence describing what happened",
      "agents_involved": ["Extraction", "Criteria-Matching", "Letter-Generation"],
      "escalated": true | false,
      "escalation_reason": "",
      "confidence_score": 0-100,
      "timestamp": ""
    }

    Rules:
    - If validation_output.escalate_to_human is true, this record must also be marked escalated: true and carry forward the same reason — never override a human-escalation flag from an upstream agent.
    - This output is for internal logging and the demo trace UI — keep it factual and short, not persuasive.
    """
    
    client = get_gemini_client()
    if client:
        try:
            import datetime
            prompt = f"Extraction:\n{json.dumps(extraction_output)}\n\nValidation:\n{json.dumps(validation_output)}\n\nLetter:\n{letter_output or 'Not yet generated'}"
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"System Instructions:\n{system_instruction}\n\nInput Data:\n{prompt}",
                config=dict(response_mime_type="application/json")
            )
            return json.loads(response.text.strip())
        except Exception as e:
            print("Audit Agent API error:", e)

    # Mock Fallback
    print("Running Audit Agent Fallback...")
    import datetime
    escalate = validation_output.get("escalate_to_human", False)
    reason = validation_output.get("escalation_reason", "")
    
    agents = ["Extraction", "Criteria-Matching"]
    if letter_output:
        agents.append("Letter-Generation")
        
    summary = f"Patient file processed for {extraction_output.get('treatment_requested', 'requested treatment')} with {validation_output.get('overall_confidence', 80)}% confidence."
    
    return {
        "case_summary": summary,
        "agents_involved": agents,
        "escalated": escalate,
        "escalation_reason": reason,
        "confidence_score": validation_output.get("overall_confidence", 80),
        "timestamp": datetime.datetime.now().isoformat()
    }
