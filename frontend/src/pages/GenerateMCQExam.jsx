import React, { useState, useEffect } from 'react';
import { ListChecks, ArrowLeft, Zap, CheckCircle, AlertCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { authFetch } from '../utils/api';
import './GenerateExamNL.css';

const API = 'http://localhost:8001';

const GenerateMCQExam = () => {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState([]);
  const [subjectId, setSubjectId] = useState('');
  const [nlRequest, setNlRequest] = useState('');
  const [preview, setPreview] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState('');
  const [generationInstruction, setGenerationInstruction] = useState('');

  const examplePrompts = [
    'Create 10 MCQs from Unit 1 and 2, 2 marks each',
    '20 MCQs from Unit 1 to 3, 1 mark each',
    '15 easy MCQs from Unit 1 and 2, 2 marks each',
    '5 questions from Unit 1, 10 from Unit 2 — 1 mark each',
    'Create 25 MCQs covering all units, 2 marks each'
  ];

  useEffect(() => {
    fetch(`${API}/subjects/`)
      .then(r => r.json())
      .then(data => setSubjects(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const handleProcessPrompt = async () => {
    setError('');
    if (!subjectId) {
      setError('Please select a subject.');
      return;
    }
    if (!nlRequest.trim()) {
      setError('Please describe your MCQ test requirements.');
      return;
    }

    setIsProcessing(true);
    setPreview(null);

    try {
      const response = await fetch(`${API}/generation/process-prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_id: parseInt(subjectId),
          request_text: nlRequest,
          paper_type: 'mcq'  // Force MCQ type
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to process prompt');
      }

      const data = await response.json();
      
      // Validate that it's actually MCQ
      if (data.exam_type !== 'MCQ' && !data.mcq_preview) {
        throw new Error('This prompt will generate a subjective exam. Please use the Subjective Exam page instead.');
      }
      
      setPreview(data);
    } catch (err) {
      setError(err.message || 'Failed to process prompt. Please try again.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleApprove = async () => {
    if (!preview) return;

    setIsGenerating(true);
    setError('');

    try {
      const response = await authFetch('/generation/approve-and-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_id: preview.subject_id,
          spec_type: preview.parsed_spec.type,
          spec: preview.parsed_spec,
          paper_type: 'mcq',
          ...(generationInstruction.trim() && { generation_instruction: generationInstruction.trim() })
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Generation failed');
      }

      const paper = await response.json();
      navigate(`/papers/${paper.paper_id}`);
    } catch (err) {
      setError(err.message || 'Generation failed. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExampleClick = (example) => {
    setNlRequest(example);
    setPreview(null);
  };

  const handleReset = () => {
    setPreview(null);
    setNlRequest('');
    setGenerationInstruction('');
    setError('');
  };

  const groupByUnit = (questions) => {
    const grouped = {};
    questions.forEach(q => {
      if (!grouped[q.unit_name]) {
        grouped[q.unit_name] = [];
      }
      grouped[q.unit_name].push(q);
    });
    return grouped;
  };

  return (
    <div className="genl-container">
      <div className="genl-card">
        <div className="genl-header">
          <button className="back-btn" onClick={() => navigate('/')}>
            <ArrowLeft size={20} />
          </button>
          <h1 className="genl-title">Generate MCQ Test</h1>
        </div>

        <div className="genl-body">
          {/* Left: Input Form */}
          <div className="genl-form-section">
            {error && (
              <div className="genl-error">
                <AlertCircle size={16} />
                {error}
              </div>
            )}

            {/* Subject Selection */}
            <div className="form-group">
              <label className="form-label">
                Subject <span className="required">*</span>
              </label>
              <select
                className="form-select"
                value={subjectId}
                onChange={(e) => setSubjectId(e.target.value)}
                disabled={isProcessing || preview}
              >
                <option value="">— Select subject —</option>
                {subjects.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>

            {/* NL Input */}
            <div className="form-group">
              <label className="form-label">
                Describe Your MCQ Test <span className="required">*</span>
              </label>
              <textarea
                className="form-textarea"
                rows={6}
                value={nlRequest}
                onChange={(e) => setNlRequest(e.target.value)}
                disabled={isProcessing || preview}
                placeholder="E.g., Create 20 MCQs from Unit 1 to 3, 2 marks each"
              />
            </div>

            {/* Example Prompts */}
            {!preview && (
              <div className="examples-section">
                <label className="form-label">Example Prompts:</label>
                <div className="examples-grid">
                  {examplePrompts.map((example, idx) => (
                    <button
                      key={idx}
                      className="example-btn"
                      onClick={() => handleExampleClick(example)}
                      disabled={isProcessing}
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="action-buttons">
              {!preview ? (
                <button
                  className="btn-primary"
                  onClick={handleProcessPrompt}
                  disabled={isProcessing || !subjectId || !nlRequest.trim()}
                >
                  {isProcessing ? (
                    <>
                      <div className="spinner" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Zap size={18} />
                      Process Prompt
                    </>
                  )}
                </button>
              ) : (
                <>
                  <div className="form-group" style={{ marginBottom: '12px' }}>
                    <label className="form-label">Extra instructions (optional)</label>
                    <input
                      type="text"
                      className="form-input"
                      value={generationInstruction}
                      onChange={(e) => setGenerationInstruction(e.target.value)}
                      placeholder="e.g. Use LaTeX for equations; prefer Truth Tables"
                      disabled={isGenerating}
                    />
                  </div>
                  <button
                    className="btn-primary"
                    onClick={handleApprove}
                    disabled={isGenerating}
                  >
                    {isGenerating ? (
                      <>
                        <div className="spinner" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <CheckCircle size={18} />
                        Approve & Generate
                      </>
                    )}
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={handleReset}
                    disabled={isGenerating}
                  >
                    Start Over
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Right: Preview */}
          <div className="genl-preview-section">
            {!preview ? (
              <div className="preview-empty">
                <ListChecks size={64} strokeWidth={1} />
                <p>Your MCQ test structure will appear here</p>
                <p className="preview-hint">
                  Enter your requirements and click "Process Prompt"
                </p>
              </div>
            ) : (
              <div className="preview-content">
                <div className="preview-header">
                  <h3>{preview.exam_type}</h3>
                  <div className="preview-stats">
                    <span className="stat-badge">
                      {preview.total_questions} MCQs
                    </span>
                    <span className="stat-badge">
                      {preview.total_marks} Marks
                    </span>
                  </div>
                </div>

                {/* MCQ Preview */}
                {preview.mcq_preview && (
                  <div className="mcq-breakdown">
                    <div className="breakdown-summary">
                      <div className="summary-row">
                        <strong>Marks per Question:</strong> {preview.marks_per_question}
                      </div>
                      <div className="summary-row bloom-info">
                        <strong>Bloom's Level:</strong> 
                        <span className="bloom-levels">
                          {preview.marks_per_question <= 2 ? 'Remember, Understand' : 'Understand, Apply'}
                        </span>
                      </div>
                    </div>
                    {Object.entries(groupByUnit(preview.mcq_preview)).map(([unitName, questions]) => (
                      <div key={unitName} className="unit-block">
                        <div className="unit-header">
                          <h4>{unitName}</h4>
                          <span className="unit-count">
                            {questions.length} questions × {preview.marks_per_question} marks = {questions.length * preview.marks_per_question} marks
                          </span>
                        </div>
                        <div className="question-list">
                          {questions.map(q => (
                            <div key={q.question_no} className="question-item">
                              <span className="q-no">Q{q.question_no}</span>
                              <span className="q-desc">{q.description}</span>
                              <span className="q-marks">{q.marks}M</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="preview-footer">
                  <div className="total-summary">
                    <strong>Total:</strong> {preview.total_questions} MCQs, {preview.total_marks} marks
                  </div>
                  <div className="difficulty-badge">
                    Difficulty: {preview.difficulty || 'auto'}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default GenerateMCQExam;
