import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, FileText, CheckCircle2, ChevronDown, ChevronUp, Printer, Eye, EyeOff } from 'lucide-react';
import './ViewExam.css';

const API_BASE = 'http://localhost:8001';

const DIFFICULTY_COLORS = {
  easy: { bg: '#D1FAE5', color: '#047857' },
  medium: { bg: '#FEF3C7', color: '#B45309' },
  hard: { bg: '#FEE2E2', color: '#DC2626' },
};

const TYPE_LABELS = { mcq: 'MCQ', short: 'Short Answer', long: 'Long Answer' };

const ViewExam = () => {
  const { examId } = useParams();
  const navigate = useNavigate();
  const [exam, setExam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAnswers, setShowAnswers] = useState(false);
  const [expandedQ, setExpandedQ] = useState(new Set());

  useEffect(() => {
    const fetchExam = async () => {
      try {
        const res = await fetch(`${API_BASE}/exams/${examId}`);
        if (!res.ok) throw new Error(res.status === 404 ? 'Exam not found' : `Failed (${res.status})`);
        setExam(await res.json());
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchExam();
  }, [examId]);

  const toggleQ = (id) => {
    setExpandedQ(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const groupByType = (questions) => {
    const groups = { mcq: [], short: [], long: [] };
    questions.forEach(q => {
      if (groups[q.type]) groups[q.type].push(q);
      else groups[q.type] = [q];
    });
    return groups;
  };

  if (loading) {
    return (
      <div className="view-exam-container">
        <div className="exam-loading"><Loader2 size={28} className="spin" /> Loading exam...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="view-exam-container">
        <div className="exam-header-bar">
          <button className="back-btn" onClick={() => navigate('/exams')}><ArrowLeft size={18} /></button>
          <h1>Exam</h1>
        </div>
        <div className="exam-error-msg">{error}</div>
      </div>
    );
  }

  const grouped = groupByType(exam.questions);
  let globalIdx = 0;

  return (
    <div className="view-exam-container">
      <div className="exam-header-bar">
        <button className="back-btn" onClick={() => navigate('/exams')}><ArrowLeft size={18} /></button>
        <div className="exam-header-info">
          <h1>Exam #{exam.id}</h1>
          <span className="exam-subject-badge">{exam.subject_name}</span>
        </div>
        <div className="exam-header-actions">
          <button className={`toggle-answers-btn ${showAnswers ? 'active' : ''}`} onClick={() => setShowAnswers(v => !v)}>
            {showAnswers ? <EyeOff size={16} /> : <Eye size={16} />}
            {showAnswers ? 'Hide Answers' : 'Show Answers'}
          </button>
          <button className="print-btn" onClick={() => window.print()}>
            <Printer size={16} /> Print
          </button>
        </div>
      </div>

      <div className="exam-meta-bar">
        <span>{exam.questions.length} questions</span>
        <span className="meta-sep">|</span>
        <span>{grouped.mcq.length} MCQ, {grouped.short.length} Short, {grouped.long.length} Long</span>
        <span className="meta-sep">|</span>
        <span>Seed: {exam.seed}</span>
        <span className="meta-sep">|</span>
        <span>{new Date(exam.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
      </div>

      <div className="exam-body">
        {['mcq', 'short', 'long'].map(type => {
          const qs = grouped[type];
          if (!qs || qs.length === 0) return null;
          return (
            <section key={type} className="question-section">
              <h2 className="section-title">
                <FileText size={18} />
                {TYPE_LABELS[type]} ({qs.length})
              </h2>
              {qs.map((q) => {
                globalIdx++;
                const num = globalIdx;
                const isExpanded = expandedQ.has(q.id);
                const diffStyle = DIFFICULTY_COLORS[q.difficulty] || DIFFICULTY_COLORS.medium;
                return (
                  <div key={q.id} className="question-card">
                    <div className="question-top" onClick={() => toggleQ(q.id)}>
                      <span className="q-number">Q{num}</span>
                      <p className="q-text">{q.text}</p>
                      <div className="q-badges">
                        <span className="q-diff" style={{ background: diffStyle.bg, color: diffStyle.color }}>{q.difficulty}</span>
                        {q.bloom_level && <span className="q-bloom">{q.bloom_level}</span>}
                        <button className="expand-btn">
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                      </div>
                    </div>

                    {type === 'mcq' && q.options && (
                      <div className="mcq-options">
                        {q.options.map((opt, i) => {
                          const letter = String.fromCharCode(65 + i);
                          const isCorrect = showAnswers && q.answer_key?.correct_option === letter;
                          return (
                            <div key={i} className={`mcq-option ${isCorrect ? 'correct' : ''}`}>
                              <span className="opt-letter">{letter}</span>
                              <span className="opt-text">{opt.replace(/^[A-D][.)]\s*/, '')}</span>
                              {isCorrect && <CheckCircle2 size={16} className="correct-icon" />}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {(isExpanded || showAnswers) && q.answer_key && (
                      <div className="answer-panel">
                        {q.answer_key.correct_option && (
                          <div className="answer-row"><strong>Correct:</strong> {q.answer_key.correct_option}</div>
                        )}
                        {q.answer_key.why_correct && (
                          <div className="answer-row"><strong>Explanation:</strong> {q.answer_key.why_correct}</div>
                        )}
                        {q.answer_key.why_others_wrong && (
                          <div className="answer-row">
                            <strong>Why others wrong:</strong>
                            <ul>{(Array.isArray(q.answer_key.why_others_wrong) ? q.answer_key.why_others_wrong : [q.answer_key.why_others_wrong]).map((r, i) => <li key={i}>{r}</li>)}</ul>
                          </div>
                        )}
                        {q.answer_key.expected_answer && (
                          <div className="answer-row"><strong>Expected Answer:</strong> {q.answer_key.expected_answer}</div>
                        )}
                        {q.answer_key.key_points && (
                          <div className="answer-row">
                            <strong>Key Points:</strong>
                            <ul>{q.answer_key.key_points.map((p, i) => <li key={i}>{p}</li>)}</ul>
                          </div>
                        )}
                        {q.answer_key.answer_outline && (
                          <div className="answer-row"><strong>Answer Outline:</strong> {q.answer_key.answer_outline}</div>
                        )}
                        {q.answer_key.rubric && (
                          <div className="answer-row"><strong>Rubric:</strong> {typeof q.answer_key.rubric === 'string' ? q.answer_key.rubric : JSON.stringify(q.answer_key.rubric, null, 2)}</div>
                        )}
                        {q.answer_key.marking_scheme && (
                          <div className="answer-row"><strong>Marking Scheme:</strong> {q.answer_key.marking_scheme}</div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </section>
          );
        })}
      </div>
    </div>
  );
};

export default ViewExam;
