import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, XCircle, Info, Lock, BookOpen, FileText, User, LogOut } from 'lucide-react';
import { toast } from 'react-toastify';
import dayjs from 'dayjs';
import './StudentExamList.css';
import './Dashboard.css';
import './StudentExamResult.css';

const API = 'http://localhost:8001';

const getStudentToken = () => {
    try {
        const s = JSON.parse(localStorage.getItem('pareeksha_student_session') || 'null');
        return s?.token || null;
    } catch { return null; }
};

const getSession = () => {
    try { return JSON.parse(localStorage.getItem('pareeksha_student_session') || 'null'); } catch { return null; }
};

const studentFetch = (path, opts = {}) => {
    const token = getStudentToken();
    return fetch(`${API}${path}`, {
        ...opts,
        headers: { ...(opts.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    });
};

const StudentExamResult = () => {
    const { examId } = useParams();
    const navigate = useNavigate();
    const session = getSession();
    const student = session?.student;
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(true);

    const handleLogout = () => {
        localStorage.removeItem('pareeksha_student_session');
        window.location.href = '/student/login';
    };

    useEffect(() => {
        if (!getStudentToken()) {
            navigate('/student/login');
            return;
        }

        studentFetch(`/student/exams/${examId}/result`)
            .then(res => {
                if (!res.ok) throw res;
                return res.json();
            })
            .then(data => {
                setResult(data);
                setLoading(false);
            })
            .catch(async err => {
                const errorData = await err.json?.().catch(() => ({}));
                toast.error(errorData.detail || 'Failed to open result');
                navigate('/student/exams');
            });
    }, [examId, navigate]);

    if (loading) return <div className="student-result-page">Loading result...</div>;
    if (!result) return null;

    const getScoreHue = (pct) => {
        if (pct >= 80) return 'excellent';
        if (pct >= 60) return 'good';
        if (pct >= 40) return 'average';
        return 'poor';
    };

    const statusStyle = getScoreHue(result.percentage);

    return (
        <div className="student-portal">
            <nav className="student-nav">
                <div className="student-nav-left">
                    <div className="student-nav-brand"><BookOpen size={18} /> Pareeksha</div>
                    <div className="student-nav-links">
                        <a href="/student/exams" className="student-nav-link"><FileText size={14} /> My Exams</a>
                        <a href="/student/profile" className="student-nav-link"><User size={14} /> Profile</a>
                    </div>
                </div>
                <div className="student-nav-right">
                    <a href="/student/profile" className="student-nav-user">
                        <div className="student-nav-avatar">{student?.full_name?.charAt(0) || 'S'}</div>
                        <span className="student-nav-name">{student?.full_name || 'Student'}</span>
                    </a>
                    <button className="student-logout-btn" onClick={handleLogout}><LogOut size={12} /> Logout</button>
                </div>
            </nav>

            <div className="student-result-page">
                <div className="student-result-container">
                    <button className="ser-back-btn" onClick={() => navigate('/student/exams')}>
                        <ArrowLeft size={14} /> Back to Exams
                    </button>

                    {/* Header card — same as dash-card */}
                    <div className="dash-card" style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
                        <h1 className="student-result-title">{result.exam_title}</h1>
                        <div className="student-result-meta">
                            Submitted on {dayjs(result.submitted_at).format('MMM D, YYYY [at] hh:mm A')}
                            {result.is_auto_submitted && " (Auto-submitted)"}
                        </div>

                        {/* Score display */}
                        <div className="student-score-circle-container">
                            <div className={`student-score-circle ${statusStyle}`}>
                                <div className="student-score-value">{result.score}</div>
                                <div className="student-score-total">/ {result.total_questions}</div>
                                <div className="student-score-percentage">{result.percentage}%</div>
                            </div>
                        </div>

                        {/* Summary Stats */}
                        <div className="student-result-stats">
                            <div className="student-result-stat">
                                <span className="student-result-stat-label">Correct</span>
                                <span className="student-result-stat-value correct">
                                    <CheckCircle2 size={16} /> {result.score}
                                </span>
                            </div>
                            <div className="ser-divider" />
                            <div className="student-result-stat">
                                <span className="student-result-stat-label">Incorrect / Missed</span>
                                <span className="student-result-stat-value incorrect">
                                    <XCircle size={16} /> {result.total_questions - result.score}
                                </span>
                            </div>
                        </div>

                        {/* Visual progress bar */}
                        <div className="ser-progress-wrap">
                            <div className="ser-progress-bar">
                                <div
                                    className="ser-progress-correct"
                                    style={{ width: `${result.percentage}%` }}
                                />
                            </div>
                            <div className="ser-progress-labels">
                                <span className="ser-progress-label correct">
                                    <span className="ser-dot correct" />{result.percentage}% correct
                                </span>
                                <span className="ser-progress-label incorrect">
                                    <span className="ser-dot incorrect" />{100 - result.percentage}% missed
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Breakdown Section */}
                    {result.show_result_to_student ? (
                        <div className="student-breakdown-section">
                            <div className="dash-card-header" style={{ fontSize: '1rem', fontWeight: 700, color: '#111827', marginBottom: '1rem' }}>
                                <Info size={18} style={{ color: '#0061a1' }} /> Question Breakdown
                            </div>

                            {result.breakdown?.map((q) => {
                                const stateClass = !q.your_answer ? 'unanswered' : (q.is_correct ? 'correct' : 'incorrect');

                                return (
                                    <div key={q.question_number} className={`student-question-card ${stateClass}`}>
                                        <div className="student-question-header">
                                            <div className="student-question-number">Question {q.question_number}</div>
                                            <div className={`student-question-badge ${stateClass}`}>
                                                {stateClass === 'correct' && <><CheckCircle2 size={12} /> Correct</>}
                                                {stateClass === 'incorrect' && <><XCircle size={12} /> Incorrect</>}
                                                {stateClass === 'unanswered' && <><Info size={12} /> Unanswered</>}
                                            </div>
                                        </div>

                                        <p className="student-question-text">{q.question_text}</p>

                                        <div className="student-question-options">
                                            {q.options?.map(opt => {
                                                const isCorrectAns = opt.label === q.correct_answer;
                                                const isSelectedAns = opt.label === q.your_answer;

                                                let optClass = "student-question-option";
                                                let Icon = null;

                                                if (isCorrectAns) {
                                                    optClass += " is-correct-answer";
                                                    Icon = () => <CheckCircle2 size={16} className="student-opt-icon correct" />;
                                                } else if (isSelectedAns && !q.is_correct) {
                                                    optClass += " is-wrong-answer";
                                                    Icon = () => <XCircle size={16} className="student-opt-icon wrong" />;
                                                }

                                                return (
                                                    <div key={opt.label} className={optClass}>
                                                        <div className="student-opt-label">{opt.label}</div>
                                                        <div className="student-opt-text">{opt.text}</div>
                                                        {Icon && <Icon />}
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        {/* Explanation */}
                                        {q.explanation && (
                                            <div className="student-question-explanation">
                                                <div className="student-explanation-title">
                                                    <Info size={12} /> Explanation
                                                </div>
                                                <p className="student-explanation-text">{q.explanation}</p>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div className="student-result-hidden-msg">
                            <div className="student-result-hidden-icon"><Lock size={32} /></div>
                            <h3>Detailed Results Hidden</h3>
                            <p>Detailed question breakdown is currently not available for this exam.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default StudentExamResult;
