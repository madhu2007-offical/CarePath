import React, { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000/api';

export default function App() {
  // State variables
  const [patients, setPatients] = useState([]);
  const [previousRequests, setPreviousRequests] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [policyRules, setPolicyRules] = useState([]);
  
  // Workspace State
  const [selectedTreatment, setSelectedTreatment] = useState('');
  const [validationResults, setValidationResults] = useState(null);
  const [generatedLetter, setGeneratedLetter] = useState('');
  const [nextSteps, setNextSteps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  
  // Dashboard Search & Modals
  const [searchQuery, setSearchQuery] = useState('');
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  
  // Upload Modal State
  const [manualPatient, setManualPatient] = useState({
    patient_id: '',
    name: '',
    age: '',
    diagnosis: 'Obsessive-Compulsive Disorder (Obsessions: Harm-related, Compulsions: Checking)',
    medications: 'SSRI',
    referral_status: 'Missing',
    lab_reports: 'Missing',
    insurance_plan: 'Blue Cross Blue Shield PPO'
  });
  const [csvRowInput, setCsvRowInput] = useState('');
  const [uploadError, setUploadError] = useState('');

  // Fetch initial data
  useEffect(() => {
    fetchPatients();
    fetchRequests();
    fetchPolicyRules();
  }, []);

  const fetchPatients = async () => {
    try {
      const res = await fetch(`${API_BASE}/patients`);
      if (res.ok) {
        const data = await res.json();
        setPatients(data);
      }
    } catch (err) {
      console.error("Error fetching patients:", err);
    }
  };

  const fetchRequests = async () => {
    try {
      const res = await fetch(`${API_BASE}/requests`);
      if (res.ok) {
        const data = await res.json();
        setPreviousRequests(data);
      }
    } catch (err) {
      console.error("Error fetching requests:", err);
    }
  };

  const fetchPolicyRules = async () => {
    try {
      const res = await fetch(`${API_BASE}/policy-rules`);
      if (res.ok) {
        const data = await res.json();
        setPolicyRules(data);
        if (data.length > 0) {
          setSelectedTreatment(data[0].treatment);
        }
      }
    } catch (err) {
      console.error("Error fetching policy rules:", err);
    }
  };

  // Helper to determine status badge on dashboard
  const getInitialStatus = (p) => {
    const hasRef = p.referral_status === 'Present';
    const hasLab = p.lab_reports && p.lab_reports.toLowerCase() !== 'missing';
    if (hasRef && hasLab) {
      return { text: 'Ready', class: 'badge-ready' };
    } else if (!hasRef && !hasLab) {
      return { text: 'Not Started', class: 'badge-started' };
    } else {
      return { text: 'Missing Docs', class: 'badge-missing' };
    }
  };

  // Select patient and reset workspace
  const handleSelectPatient = (patient) => {
    setSelectedPatient(patient);
    setValidationResults(null);
    setGeneratedLetter('');
    setNextSteps([]);
  };

  // Run policy validation (deterministic backend logic)
  const handleValidate = async () => {
    if (!selectedPatient || !selectedTreatment) return;
    setValidating(true);
    setValidationResults(null);
    setGeneratedLetter('');
    setNextSteps([]);
    try {
      const res = await fetch(`${API_BASE}/patients/${selectedPatient.id}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ treatment: selectedTreatment })
      });
      if (res.ok) {
        const data = await res.json();
        setValidationResults(data);
      } else {
        alert("Failed to run policy validation.");
      }
    } catch (err) {
      console.error(err);
      alert("Error contacting validation API.");
    } finally {
      setValidating(false);
    }
  };

  // Generate Letter via Gemini API
  const handleGenerateLetter = async () => {
    if (!selectedPatient || !validationResults) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/patients/${selectedPatient.id}/generate-letter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          treatment: selectedTreatment,
          validation_results: validationResults
        })
      });
      if (res.ok) {
        const data = await res.json();
        setGeneratedLetter(data.letter);
        setNextSteps(data.next_steps);
        // Refresh previous requests log
        fetchRequests();
      } else {
        alert("Failed to generate letter.");
      }
    } catch (err) {
      console.error(err);
      alert("Error contacting Gemini API.");
    } finally {
      setLoading(false);
    }
  };

  // Handle DB reset / re-seed
  const handleResetDatabase = async () => {
    if (!confirm("Are you sure you want to reset the patient database to default seeds?")) return;
    try {
      const res = await fetch(`${API_BASE}/upload`, { method: 'POST' });
      if (res.ok) {
        alert("Database re-seeded successfully!");
        fetchPatients();
        setSelectedPatient(null);
      }
    } catch (err) {
      console.error(err);
      alert("Error re-seeding database.");
    }
  };

  // Manual Patient Upload
  const handleManualSubmit = async (e) => {
    e.preventDefault();
    setUploadError('');
    if (!manualPatient.patient_id || !manualPatient.name || !manualPatient.age) {
      setUploadError("Please fill out Patient ID, Name, and Age.");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/patients`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...manualPatient,
          age: parseInt(manualPatient.age)
        })
      });
      if (res.ok) {
        alert("Patient added successfully!");
        fetchPatients();
        setIsUploadModalOpen(false);
        // Reset manual form
        setManualPatient({
          patient_id: '',
          name: '',
          age: '',
          diagnosis: 'Obsessive-Compulsive Disorder (Obsessions: Harm-related, Compulsions: Checking)',
          medications: 'SSRI',
          referral_status: 'Missing',
          lab_reports: 'Missing',
          insurance_plan: 'Blue Cross Blue Shield PPO'
        });
      } else {
        const err = await res.json();
        setUploadError(err.detail || "Failed to add patient.");
      }
    } catch (err) {
      setUploadError("Error connecting to server.");
    }
  };

  // CSV Row paste parsing
  const handleCsvRowSubmit = async (e) => {
    e.preventDefault();
    setUploadError('');
    if (!csvRowInput.trim()) {
      setUploadError("Please paste a CSV row.");
      return;
    }
    
    // Simple CSV parser
    const parts = csvRowInput.split(',').map(s => s.trim());
    if (parts.length < 3) {
      setUploadError("Invalid CSV row format. Must contain at least: Patient ID, Age, Medications");
      return;
    }
    
    // Map pasted fields (e.g. from Kaggle format or basic columns)
    // Patient ID, Age, Medications are core.
    const pid = parts[0] || `CSV_${Math.floor(Math.random() * 10000)}`;
    const age = parseInt(parts[1]) || 35;
    const meds = parts[parts.length - 1] || 'None';
    
    const mockRecord = {
      patient_id: pid,
      name: `Imported Patient ${pid}`,
      age: age,
      diagnosis: `Obsessive-Compulsive Disorder. Medications: ${meds}`,
      medications: meds,
      referral_status: 'Missing',
      lab_reports: 'Missing',
      insurance_plan: 'Aetna HMO Choice'
    };

    try {
      const res = await fetch(`${API_BASE}/patients`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mockRecord)
      });
      if (res.ok) {
        alert("Patient parsed and imported successfully!");
        fetchPatients();
        setIsUploadModalOpen(false);
        setCsvRowInput('');
      } else {
        const err = await res.json();
        setUploadError(err.detail || "Failed to import CSV patient.");
      }
    } catch (err) {
      setUploadError("Error connecting to server.");
    }
  };

  // Copy to clipboard helper
  const handleCopyToClipboard = () => {
    navigator.clipboard.writeText(generatedLetter);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Download letter as .txt file helper
  const handleDownloadLetter = () => {
    const element = document.createElement("a");
    const file = new Blob([generatedLetter], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = `PriorAuth_${selectedPatient.name.replace(/\s+/g, '_')}.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  // View a previously saved request from history
  const handleViewHistoricalRequest = (req) => {
    // Find patient associated
    const associatedPatient = patients.find(p => p.patient_id === req.patient_id) || {
      patient_id: req.patient_id,
      name: req.patient_name,
      age: 'Unknown',
      diagnosis: 'History Log Import',
      medications: 'N/A',
      referral_status: 'N/A',
      lab_reports: 'N/A',
      insurance_plan: 'N/A'
    };
    
    setSelectedPatient(associatedPatient);
    setSelectedTreatment(req.treatment);
    setValidationResults(req.validation_results);
    setGeneratedLetter(req.letter_text);
    setNextSteps(req.next_steps);
  };

  // Search filter
  const filteredPatients = patients.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.patient_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.diagnosis.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div>
      <header>
        <div className="logo-container">
          <div className="logo-icon">CG</div>
          <div>
            <div className="logo-text">CareGate</div>
            <div className="logo-subtext">Prior Auth Readiness Platform</div>
          </div>
        </div>
        <div>
          <button className="btn btn-secondary" style={{ marginRight: '10px' }} onClick={handleResetDatabase}>
            Reset Database
          </button>
          <span className="badge badge-ready">System Online</span>
        </div>
      </header>

      <div className="app-container">
        {selectedPatient === null ? (
          /* DASHBOARD VIEW */
          <div>
            <div className="card" style={{ padding: '2rem' }}>
              <div className="card-title" style={{ fontSize: '1.4rem', borderBottom: '1px solid var(--border)', paddingBottom: '1rem' }}>
                <span>Provider Patient Database</span>
                <button className="btn btn-primary" onClick={() => setIsUploadModalOpen(true)}>
                  + Upload Patient Record
                </button>
              </div>

              {/* Search bar */}
              <div style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem' }}>
                <input 
                  type="text" 
                  placeholder="Search patients by name, ID, or diagnosis criteria..." 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{ flex: 1 }}
                />
              </div>

              {/* Patient Table */}
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Patient ID</th>
                      <th>Name</th>
                      <th>Age</th>
                      <th>Diagnosis Summary</th>
                      <th>Medications</th>
                      <th>Status Badge</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPatients.length > 0 ? (
                      filteredPatients.map(p => {
                        const status = getInitialStatus(p);
                        return (
                          <tr key={p.id} className="clickable-row" onClick={() => handleSelectPatient(p)}>
                            <td style={{ fontWeight: '600' }}>{p.patient_id}</td>
                            <td style={{ color: 'var(--primary-dark)', fontWeight: '500' }}>{p.name}</td>
                            <td>{p.age}</td>
                            <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {p.diagnosis}
                            </td>
                            <td>{p.medications}</td>
                            <td>
                              <span className={`badge ${status.class}`}>{status.text}</span>
                            </td>
                            <td>
                              <button className="btn btn-secondary btn-sm" onClick={(e) => {
                                e.stopPropagation();
                                handleSelectPatient(p);
                              }}>
                                Analyze &rarr;
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan="7" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                          No patient records found. Click "Upload Patient Record" or "Reset Database" to seed data.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Previous Requests List */}
            <div className="card">
              <h3 className="card-title">Previous Prior Authorization Requests</h3>
              {previousRequests.length > 0 ? (
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Patient ID</th>
                        <th>Name</th>
                        <th>Requested Treatment</th>
                        <th>Readiness Score</th>
                        <th>Date Processed</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previousRequests.map(r => {
                        let scoreClass = 'badge-started';
                        if (r.readiness_score === 100) scoreClass = 'badge-ready';
                        else if (r.readiness_score >= 50) scoreClass = 'badge-missing';
                        
                        return (
                          <tr key={r.id} className="clickable-row" onClick={() => handleViewHistoricalRequest(r)}>
                            <td>{r.patient_id}</td>
                            <td style={{ fontWeight: '500' }}>{r.patient_name}</td>
                            <td>{r.treatment}</td>
                            <td>
                              <span className={`badge ${scoreClass}`}>{r.readiness_score}%</span>
                            </td>
                            <td>{new Date(r.created_at).toLocaleString()}</td>
                            <td>
                              <button className="btn btn-secondary btn-sm" onClick={(e) => {
                                e.stopPropagation();
                                handleViewHistoricalRequest(r);
                              }}>
                                View Letter
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  No previous prior authorization documents generated. Select a patient above to start validation.
                </div>
              )}
            </div>
          </div>
        ) : (
          /* WORKSPACE VIEW (Patient selected) */
          <div>
            <div className="breadcrumb">
              <span className="breadcrumb-link" onClick={() => setSelectedPatient(null)}>Dashboard</span>
              <span>/</span>
              <span>Patient Workspace ({selectedPatient.name})</span>
            </div>

            <div className="grid-2">
              {/* Left Column: Patient Info & Policy Selection */}
              <div>
                <div className="card">
                  <h3 className="card-title">Patient Demographics & Records</h3>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Patient ID</div>
                    <div className="patient-info-value" style={{ fontWeight: '600' }}>{selectedPatient.patient_id}</div>
                  </div>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Full Name</div>
                    <div className="patient-info-value">{selectedPatient.name}</div>
                  </div>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Age</div>
                    <div className="patient-info-value">{selectedPatient.age}</div>
                  </div>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Insurance Plan</div>
                    <div className="patient-info-value" style={{ color: 'var(--primary-dark)', fontWeight: '600' }}>
                      {selectedPatient.insurance_plan}
                    </div>
                  </div>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Diagnosis</div>
                    <div className="patient-info-value">{selectedPatient.diagnosis}</div>
                  </div>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Current Medications</div>
                    <div className="patient-info-value" style={{ fontFamily: 'monospace' }}>
                      {selectedPatient.medications}
                    </div>
                  </div>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Referral Status</div>
                    <div className="patient-info-value">
                      <span className={`badge ${selectedPatient.referral_status === 'Present' ? 'badge-ready' : 'badge-missing'}`}>
                        {selectedPatient.referral_status}
                      </span>
                    </div>
                  </div>
                  <div className="patient-info-row">
                    <div className="patient-info-label">Lab Reports</div>
                    <div className="patient-info-value">
                      <span className={`badge ${selectedPatient.lab_reports !== 'Missing' ? 'badge-ready' : 'badge-missing'}`}>
                        {selectedPatient.lab_reports}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <h3 className="card-title">Insurer Policy Selector</h3>
                  <div style={{ marginBottom: '1.25rem' }}>
                    <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: '600', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                      SELECT PAYER CRITERIA TREATMENT TYPE
                    </label>
                    <select value={selectedTreatment} onChange={(e) => setSelectedTreatment(e.target.value)}>
                      {policyRules.map(r => (
                        <option key={r.id} value={r.treatment}>{r.treatment}</option>
                      ))}
                    </select>
                  </div>
                  <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleValidate} disabled={validating}>
                    {validating ? 'Running Validation...' : 'Run Policy Validation'}
                  </button>
                </div>
              </div>

              {/* Right Column: Validation Checklist & Outputs */}
              <div>
                {/* 1. Checklist Output */}
                {validationResults && (
                  <div className="card">
                    <h3 className="card-title">Deterministic Policy Checklist</h3>
                    <div style={{ marginBottom: '1rem', border: '1px solid var(--border)', borderRadius: '0.375rem' }}>
                      {validationResults.checklist.map((item, idx) => (
                        <div key={idx} className="checklist-item">
                          <span className={`checklist-icon ${item.status ? 'pass' : 'fail'}`}>
                            {item.status ? '✅' : '❌'}
                          </span>
                          <span style={{ fontWeight: '500' }}>{item.label}</span>
                        </div>
                      ))}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem' }}>
                      <div>
                        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: '600' }}>READINESS ESTIMATE</span>
                        <div style={{ fontSize: '1.8rem', fontWeight: '700', color: validationResults.readiness_score === 100 ? 'var(--success)' : 'var(--warning)' }}>
                          {validationResults.readiness_score}%
                        </div>
                      </div>
                      <button 
                        className="btn btn-primary" 
                        onClick={handleGenerateLetter} 
                        disabled={loading || validationResults.checklist.filter(c => c.field !== 'step_therapy' && c.status).length === 0}
                      >
                        {loading ? 'Consulting Gemini API...' : 'Generate Prior Authorization Letter'}
                      </button>
                    </div>
                  </div>
                )}

                {/* 2. Loading State */}
                {loading && (
                  <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
                    <div className="spinner" style={{ width: '2.5rem', height: '2.5rem', border: '4px solid var(--border)', borderTopColor: 'var(--primary)', borderRadius: '50%', margin: '0 auto 1.25rem auto' }}></div>
                    <h4 className="pulse" style={{ margin: 0, color: 'var(--secondary)', fontWeight: '600' }}>Generating Healthcare Letter Context</h4>
                    <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                      Gemini API is drafting the clinical necessity argument and documentation summary...
                    </p>
                  </div>
                )}

                {/* 3. Letter Output & Suggested Next Steps */}
                {!loading && generatedLetter && (
                  <div>
                    {/* Submission Readiness details */}
                    <div className="card">
                      <h3 className="card-title">Insurer Submission Readiness Summary</h3>
                      
                      {validationResults?.readiness_score === 100 ? (
                        <div className="banner banner-success">
                          <span>✅</span>
                          <div>
                            <div>Document Ready for Insurer Submission</div>
                            <div style={{ fontWeight: 'normal', fontSize: '0.8rem', marginTop: '0.15rem' }}>
                              All required fields and step therapy checks are fully documented.
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="banner banner-warning">
                          <span>⚠️</span>
                          <div>
                            <div>Needs Review Before Submission</div>
                            <div style={{ fontWeight: 'normal', fontSize: '0.8rem', marginTop: '0.15rem' }}>
                              Auto-submission is blocked. insubstantial documentation flagged by policy.
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Display circular indicator and missing docs */}
                      <div className="score-container">
                        <div className={`score-circle ${validationResults?.readiness_score === 100 ? 'high' : validationResults?.readiness_score >= 50 ? 'medium' : 'low'}`}>
                          {validationResults?.readiness_score}%
                        </div>
                        <div>
                          <div style={{ fontWeight: '600', fontSize: '0.9rem' }}>Required Payer Documentation Checklist</div>
                          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                            {validationResults?.checklist.filter(c => !c.status).length > 0 ? (
                              <span>Missing: {validationResults.checklist.filter(c => !c.status).map(c => c.label).join(", ")}</span>
                            ) : (
                              <span>All files are fully attached.</span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Suggested Next Steps */}
                      {nextSteps.length > 0 && (
                        <div style={{ marginTop: '1rem' }}>
                          <div style={{ fontSize: '0.85rem', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                            Gemini Suggested Next Steps
                          </div>
                          {nextSteps.map((step, idx) => (
                            <div key={idx} className="suggested-step-card">
                              {step}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Pre-formatted Letter Text */}
                    <div className="card">
                      <div className="card-title">
                        <span>Draft Prior Authorization Letter</span>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className="btn btn-secondary btn-sm" onClick={handleCopyToClipboard}>
                            {copied ? 'Copied!' : 'Copy Letter'}
                          </button>
                          <button className="btn btn-secondary btn-sm" onClick={handleDownloadLetter}>
                            Download .TXT
                          </button>
                        </div>
                      </div>
                      <div className="letter-box">
                        {generatedLetter}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* UPLOAD PATIENT RECORD MODAL */}
      {isUploadModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>Import Patient Record</h3>
              <button className="modal-close" onClick={() => setIsUploadModalOpen(false)}>&times;</button>
            </div>

            {uploadError && (
              <div className="banner banner-warning" style={{ padding: '0.5rem 1rem', marginBottom: '1rem' }}>
                {uploadError}
              </div>
            )}

            {/* TAB 1: CSV Row Import */}
            <div style={{ marginBottom: '1.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '1rem' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--primary-dark)' }}>Import CSV Patient Row</h4>
              <p style={{ margin: '0 0 1rem 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Paste a comma-separated row directly from the patient dataset:
              </p>
              <form onSubmit={handleCsvRowSubmit}>
                <div style={{ marginBottom: '0.75rem' }}>
                  <input 
                    type="text" 
                    placeholder="e.g. 1018, 32, Female, African, Single, Some College, 2016-07-15, 203, MDD, No, Harm-related, Checking, 17, 10, Yes, Yes, SNRI"
                    value={csvRowInput}
                    onChange={(e) => setCsvRowInput(e.target.value)}
                  />
                </div>
                <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                  Parse & Ingest CSV Row
                </button>
              </form>
            </div>

            {/* TAB 2: Manual Patient Form */}
            <div>
              <h4 style={{ margin: '0 0 1rem 0', color: 'var(--primary-dark)' }}>Manually Create Patient Record</h4>
              <form onSubmit={handleManualSubmit}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                  <div>
                    <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Patient ID</label>
                    <input 
                      type="text" 
                      placeholder="e.g. 5044" 
                      value={manualPatient.patient_id}
                      onChange={(e) => setManualPatient({...manualPatient, patient_id: e.target.value})}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Full Name</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Alice Smith" 
                      value={manualPatient.name}
                      onChange={(e) => setManualPatient({...manualPatient, name: e.target.value})}
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                  <div>
                    <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Age</label>
                    <input 
                      type="number" 
                      placeholder="e.g. 42" 
                      value={manualPatient.age}
                      onChange={(e) => setManualPatient({...manualPatient, age: e.target.value})}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Insurance Provider</label>
                    <input 
                      type="text" 
                      placeholder="e.g. Medicare Advantage" 
                      value={manualPatient.insurance_plan}
                      onChange={(e) => setManualPatient({...manualPatient, insurance_plan: e.target.value})}
                    />
                  </div>
                </div>

                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Diagnosis Description</label>
                  <textarea 
                    rows="2"
                    placeholder="e.g. Obsessive-Compulsive Disorder (Obsessions: Symmetry)" 
                    value={manualPatient.diagnosis}
                    onChange={(e) => setManualPatient({...manualPatient, diagnosis: e.target.value})}
                  />
                </div>

                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Active Medications</label>
                  <input 
                    type="text" 
                    placeholder="e.g. SSRI, SNRI" 
                    value={manualPatient.medications}
                    onChange={(e) => setManualPatient({...manualPatient, medications: e.target.value})}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem' }}>
                  <div>
                    <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Referral Status</label>
                    <select 
                      value={manualPatient.referral_status} 
                      onChange={(e) => setManualPatient({...manualPatient, referral_status: e.target.value})}
                    >
                      <option value="Present">Present</option>
                      <option value="Missing">Missing</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: '0.75rem', fontWeight: '600' }}>Lab Reports Status</label>
                    <select 
                      value={manualPatient.lab_reports} 
                      onChange={(e) => setManualPatient({...manualPatient, lab_reports: e.target.value})}
                    >
                      <option value="Present">Present</option>
                      <option value="Missing">Missing</option>
                    </select>
                  </div>
                </div>

                <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                  Create Patient Record
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
