import React, { useState, useEffect } from 'react';
import { FileText, ArrowLeft, Zap, CheckCircle, AlertCircle, FileQuestion } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { authFetch } from '../utils/api';
import './GenerateExamNL.css';

const API = 'http://localhost:8001';

const GenerateSubjectiveExam = () => {
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
    '40 marks: 4 sections (one per unit), 3 sub-questions each, attempt any 2, 5 marks each. Include at least 2 diagram questions',
    '40 marks: 4 sections (one per unit), 3 sub-questions each, attempt any 2, 5 marks per sub-question',
    'Create a 30-mark paper: 3 long questions from Unit 1 to 3, 10 marks each. Guarantee 2 diagram-based questions',
    'Q1 from Unit 1, Q2 from Unit 2, Q3 from Unit 3 — 4 sub-questions each, attempt any 2, 5 marks each',
    '5 short questions from Unit 1 and 2, 4 marks each',
    '6 questions from all units, 5 marks each — attempt any 4',
    'Create 8 questions of 5 marks each, covering Unit 1 to 4'
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
      setError('Please describe your exam requirements.');
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
          paper_type: 'subjective'  // Force subjective type
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to process prompt');
      }

      const data = await response.json();
      
      // Validate that it's actually subjective
      if (data.exam_type === 'MCQ' || data.mcq_preview) {
        throw new Error('This prompt will generate MCQ questions. Please use the MCQ Test page instead.');
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
          paper_type: 'subjective',
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

  return (
    <div className="genl-container">
      <div className="genl-card">
        <div className="genl-header">
          <button className="back-btn" onClick={() => navigate('/')}>
            <ArrowLeft size={20} />
          </button>
          <h1 className="genl-title">Generate Subjective Exam</h1>
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
                Describe Your Exam <span className="required">*</span>
              </label>
              <textarea
                className="form-textarea"
                rows={6}
                value={nlRequest}
                onChange={(e) => setNlRequest(e.target.value)}
                disabled={isProcessing || preview}
                placeholder="E.g., Create a 30-mark paper: 3 long questions from Unit 1 to 3, 10 marks each"
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
                <FileText size={64} strokeWidth={1} />
                <p>Your exam structure will appear here</p>
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
                      {preview.total_questions} Questions
                    </span>
                    <span className="stat-badge">
                      {preview.total_marks} Marks
                    </span>
                  </div>
                </div>

                {/* Subjective Preview */}
                {preview.sections && (
                  <div className="subjective-breakdown">
                    {preview.sections.map(section => {
                      // Determine bloom level based on question type and marks
                      const isLongQuestion = section.question_type === 'long' || section.marks_per_question >= 8;
                      const bloomLevel = isLongQuestion 
                        ? 'Apply, Analyze, Evaluate' 
                        : 'Remember, Understand, Apply';
                      const questionTypeLabel = isLongQuestion ? 'Long Answer' : 'Short Answer';
                      
                      return (
                        <div key={section.section_no} className="section-block">
                          <div className="section-header">
                            <div className="section-title-group">
                              <h4>{section.title}</h4>
                              <span className={`question-type-badge ${section.question_type}`}>
                                {questionTypeLabel}
                              </span>
                            </div>
                            <span className="section-marks">{section.section_marks} marks</span>
                          </div>
                          <div className="section-details">
                            <div className="detail-row">
                              <span className="detail-label">Questions:</span>
                              <span>{section.total_questions} questions</span>
                            </div>
                            <div className="detail-row">
                              <span className="detail-label">Attempt:</span>
                              <span>{section.note}</span>
                            </div>
                            <div className="detail-row">
                              <span className="detail-label">Marks:</span>
                              <span>{section.marks_per_question} per question</span>
                            </div>
                            <div className="detail-row bloom-row">
                              <span className="detail-label">Bloom's Level:</span>
                              <span className="bloom-levels">{bloomLevel}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="preview-footer">
                  <div className="total-summary">
                    <strong>Total:</strong> {preview.total_questions} questions, {preview.total_marks} marks
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

export default GenerateSubjectiveExam;
