import React, { useState, useEffect } from 'react';
import { Upload, FileText, Zap, ArrowLeft, ChevronDown, AlertCircle, CheckCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import './GeneratePaper.css';

const API = 'http://localhost:8001';

const STEP_LABELS = [
  'Interpreting pattern…',
  'Building blueprint…',
  'Retrieving content…',
  'Generating questions…',
  'Mapping COs…',
  'Assembling paper…',
  'Validating…',
  'Saving paper…',
];

const GeneratePaper = () => {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState([]);
  const [subjectId, setSubjectId] = useState('');
  const [inputMode, setInputMode] = useState('text'); // 'text' | 'pdf'
  const [patternText, setPatternText] = useState('');
  const [patternFile, setPatternFile] = useState(null);
  const [totalMarks, setTotalMarks] = useState(60);
  const [difficulty, setDifficulty] = useState('auto');
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStep, setCurrentStep] = useState(-1);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${API}/subjects/`)
      .then(r => r.json())
      .then(data => setSubjects(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) setPatternFile(file);
    e.target.value = '';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file && file.type === 'application/pdf') setPatternFile(file);
  };

  const simulateSteps = async () => {
    for (let i = 0; i < STEP_LABELS.length; i++) {
      await new Promise(r => setTimeout(r, 600));
      setCurrentStep(i);
    }
  };

  const handleGenerate = async () => {
    setError('');
    if (!subjectId) { setError('Please select a subject.'); return; }
    if (inputMode === 'text' && !patternText.trim()) { setError('Please enter a pattern.'); return; }
    if (inputMode === 'pdf' && !patternFile) { setError('Please upload a pattern PDF.'); return; }
    if (!totalMarks || totalMarks < 1) { setError('Please set total marks.'); return; }

    setIsGenerating(true);
    setCurrentStep(0);
    simulateSteps();

    try {
      const formData = new FormData();
      formData.append('subject_id', subjectId);
      formData.append('total_marks', totalMarks);
      if (difficulty !== 'auto') formData.append('difficulty_preference', difficulty);
      if (inputMode === 'text') {
        formData.append('pattern_text', patternText);
      } else {
        formData.append('pattern_file', patternFile);
      }

      const res = await fetch(`${API}/generation/generate-paper`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Generation failed');
      }

      const data = await res.json();
      setCurrentStep(STEP_LABELS.length - 1);
      await new Promise(r => setTimeout(r, 400));
      navigate(`/papers/${data.paper_id}`);
    } catch (e) {
      setError(e.message || 'Generation failed. Please try again.');
    } finally {
      setIsGenerating(false);
      setCurrentStep(-1);
    }
  };

  return (
    <div className="gp-container">
      <div className="gp-card">

        {/* Header */}
        <div className="gp-header">
          <button className="back-btn" onClick={() => navigate('/')}>
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="gp-title">Generate Question Paper</h1>
            <p className="gp-subtitle">AI-powered paper generation from your exam pattern</p>
          </div>
        </div>

        <div className="gp-body">
          {/* Left: Form */}
          <div className="gp-form-section">

            {/* Error */}
            {error && (
              <div className="gp-error">
                <AlertCircle size={16} />
                {error}
              </div>
            )}

            {/* Subject */}
            <div className="form-group">
              <label className="form-label">Subject <span className="required">*</span></label>
              <div className="select-wrapper">
                <select
                  className="form-select"
                  value={subjectId}
                  onChange={e => setSubjectId(e.target.value)}
                  disabled={isGenerating}
                >
                  <option value="">— Select subject —</option>
                  {subjects.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
                <ChevronDown size={16} className="select-icon" />
              </div>
            </div>

            {/* Total Marks */}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Total Marks <span className="required">*</span></label>
                <input
                  type="number"
                  className="form-input"
                  value={totalMarks}
                  onChange={e => setTotalMarks(parseInt(e.target.value) || '')}
                  min={1}
                  max={200}
                  disabled={isGenerating}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Difficulty</label>
                <div className="select-wrapper">
                  <select
                    className="form-select"
                    value={difficulty}
                    onChange={e => setDifficulty(e.target.value)}
                    disabled={isGenerating}
                  >
                    <option value="auto">Auto (from pattern)</option>
                    <option value="easy">Easy</option>
                    <option value="medium">Medium</option>
                    <option value="hard">Hard</option>
                  </select>
                  <ChevronDown size={16} className="select-icon" />
                </div>
              </div>
            </div>

            {/* Pattern Input Mode */}
            <div className="form-group">
              <label className="form-label">Exam Pattern <span className="required">*</span></label>
              <div className="tab-row">
                <button
                  className={`tab-btn ${inputMode === 'text' ? 'active' : ''}`}
                  type="button"
                  onClick={() => setInputMode('text')}
                  disabled={isGenerating}
                >
                  <FileText size={14} /> Text
                </button>
                <button
                  className={`tab-btn ${inputMode === 'pdf' ? 'active' : ''}`}
                  type="button"
                  onClick={() => setInputMode('pdf')}
                  disabled={isGenerating}
                >
                  <Upload size={14} /> PDF Upload
                </button>
              </div>

              {inputMode === 'text' && (
                <textarea
                  className="form-textarea"
                  rows={10}
                  placeholder={`Example pattern:\nUnit 1 & 2 – Q1 or Q2 – 14 Marks – Basic concepts\nUnit 3 – Q3 or Q4 – 12 Marks – Application-based\nUnit 4 – Q5 or Q6 – 12 Marks – Case study\nUnit 5 – Q7 or Q8 – 12 Marks – Advanced topics\nUnit 5 – Q9 or Q10 – 10 Marks – Emerging trends`}
                  value={patternText}
                  onChange={e => setPatternText(e.target.value)}
                  disabled={isGenerating}
                />
              )}

              {inputMode === 'pdf' && (
                <div
                  className={`drop-zone ${patternFile ? 'has-file' : ''}`}
                  onDrop={handleDrop}
                  onDragOver={e => e.preventDefault()}
                >
                  <input
                    type="file"
                    id="pattern-file"
                    accept=".pdf"
                    onChange={handleFileChange}
                    className="hidden-input"
                    disabled={isGenerating}
                  />
                  <label htmlFor="pattern-file" className="drop-label">
                    {patternFile ? (
                      <div className="file-selected-info">
                        <FileText size={24} className="file-icon-ok" />
                        <span className="file-name">{patternFile.name}</span>
                        <span className="file-size">{(patternFile.size / 1024).toFixed(1)} KB</span>
                        <span className="change-hint">Click to change</span>
                      </div>
                    ) : (
                      <div className="drop-placeholder">
                        <Upload size={28} className="drop-icon" />
                        <span>Drop PDF here or click to upload</span>
                        <span className="drop-hint">Pattern document (PDF only)</span>
                      </div>
                    )}
                  </label>
                </div>
              )}
            </div>

            {/* Generate Button */}
            <button
              className="generate-btn"
              onClick={handleGenerate}
              disabled={isGenerating}
            >
              {isGenerating ? (
                <>
                  <div className="btn-spinner" />
                  Generating…
                </>
              ) : (
                <>
                  <Zap size={18} />
                  Generate Paper
                </>
              )}
            </button>
          </div>

          {/* Right: Progress / Info */}
          <div className="gp-info-section">
            {isGenerating ? (
              <div className="progress-card">
                <h3 className="progress-title">
                  <Zap size={16} className="progress-icon" />
                  Generating your paper
                </h3>
                <div className="steps-list">
                  {STEP_LABELS.map((label, i) => (
                    <div key={i} className={`step-item ${i < currentStep ? 'done' : i === currentStep ? 'active' : 'pending'}`}>
                      <div className="step-dot">
                        {i < currentStep ? <CheckCircle size={14} /> : <span>{i + 1}</span>}
                      </div>
                      <span>{label}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="info-card">
                <h3 className="info-title">How it works</h3>
                <div className="info-steps">
                  <div className="info-step">
                    <div className="info-num">1</div>
                    <div>
                      <strong>Pattern Parsing</strong>
                      <p>Your pattern is converted into a structured blueprint with unit-wise question specs.</p>
                    </div>
                  </div>
                  <div className="info-step">
                    <div className="info-num">2</div>
                    <div>
                      <strong>Content Retrieval</strong>
                      <p>Relevant content chunks are retrieved for each question using hybrid BM25+vector search.</p>
                    </div>
                  </div>
                  <div className="info-step">
                    <div className="info-num">3</div>
                    <div>
                      <strong>AI Generation</strong>
                      <p>Questions are generated with answer keys and marking schemes aligned to Bloom's taxonomy.</p>
                    </div>
                  </div>
                  <div className="info-step">
                    <div className="info-num">4</div>
                    <div>
                      <strong>Paper Assembly</strong>
                      <p>Questions are assembled with OR-pair variants, CO mapping, and validated.</p>
                    </div>
                  </div>
                </div>

                <div className="pattern-example">
                  <h4>Pattern example (text input):</h4>
                  <pre className="pattern-pre">{`Unit 1 & 2 – Q1 or Q2 – 14 Marks – Basic concepts
Unit 3 – Q3 or Q4 – 12 Marks – Application-based
Unit 4 – Q5 or Q6 – 12 Marks – Case study
Unit 5 – Q7 or Q8 – 12 Marks – Evaluation`}</pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default GeneratePaper;
