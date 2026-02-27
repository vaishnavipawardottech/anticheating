import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Users, BarChart3, Eye, EyeOff, Plus, Trash2, Clock, Shield, X, ChevronDown, ChevronRight } from 'lucide-react';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';
import dayjs from 'dayjs';
import './McqExamDetail.css';

const McqExamDetail = () => {
    const { examId } = useParams();
    const navigate = useNavigate();
    const [exam, setExam] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('groups');
    const [departments, setDepartments] = useState([]);
    const [divisions, setDivisions] = useState([]);
    const [years, setYears] = useState([]);
    const [assignForm, setAssignForm] = useState({ department_id: '', year_id: '', division_id: '' });
    const [assigning, setAssigning] = useState(false);
    const [results, setResults] = useState(null);

    // Proctoring
    const [proctoring, setProctoring] = useState(null);
    const [expandedStudent, setExpandedStudent] = useState(null);
    const [lightboxImg, setLightboxImg] = useState(null);

    // Time editing
    const [editStart, setEditStart] = useState('');
    const [editEnd, setEditEnd] = useState('');
    const [editingTime, setEditingTime] = useState(false);

    const toISOWithTimezone = (localVal) => {
        if (!localVal) return '';
        const d = new Date(localVal);
        const offset = -d.getTimezoneOffset();
        const sign = offset >= 0 ? '+' : '-';
        const hh = String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0');
        const mm = String(Math.abs(offset) % 60).padStart(2, '0');
        return `${localVal}:00${sign}${hh}:${mm}`;
    };

    const toLocalDatetimeValue = (isoStr) => {
        if (!isoStr) return '';
        const d = new Date(isoStr);
        const y = d.getFullYear();
        const mo = String(d.getMonth() + 1).padStart(2, '0');
        const da = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const mi = String(d.getMinutes()).padStart(2, '0');
        return `${y}-${mo}-${da}T${hh}:${mi}`;
    };

    const fetchExam = () => {
        authFetch(`/mcq-exams/${examId}`).then(r => r.json()).then(data => {
            setExam(data);
            setEditStart(toLocalDatetimeValue(data.start_time));
            setEditEnd(toLocalDatetimeValue(data.end_time));
            setLoading(false);
        }).catch(() => setLoading(false));
    };

    useEffect(() => {
        fetchExam();
        authFetch('/auth/departments').then(r => r.json()).then(setDepartments).catch(() => { });
        authFetch('/auth/divisions').then(r => r.json()).then(setDivisions).catch(() => { });
        authFetch('/auth/years').then(r => r.json()).then(setYears).catch(() => { });
    }, [examId]);

    const handleSaveTime = async () => {
        if (!editStart || !editEnd) { toast.error('Please set both times'); return; }
        setEditingTime(true);
        const res = await authFetch(`/mcq-exams/${examId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_time: toISOWithTimezone(editStart),
                end_time: toISOWithTimezone(editEnd),
            }),
        });
        if (res.ok) { toast.success('Time updated'); fetchExam(); }
        else toast.error('Failed to update');
        setEditingTime(false);
    };

    const handleAssign = async () => {
        if (!assignForm.department_id || !assignForm.year_id || !assignForm.division_id) {
            toast.error('Select department, year and division');
            return;
        }
        setAssigning(true);
        const res = await authFetch(`/mcq-exams/${examId}/assign`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                department_id: parseInt(assignForm.department_id),
                year_id: parseInt(assignForm.year_id),
                division_id: parseInt(assignForm.division_id),
            }),
        });
        if (res.ok) {
            toast.success('Assigned!');
            fetchExam();
            setAssignForm({ department_id: '', year_id: '', division_id: '' });
        } else {
            const err = await res.json().catch(() => ({}));
            toast.error(err.detail || 'Failed to assign');
        }
        setAssigning(false);
    };

    const handleRemoveAssignment = async (aId) => {
        const res = await authFetch(`/mcq-exams/${examId}/assign/${aId}`, { method: 'DELETE' });
        if (res.ok) { toast.success('Removed'); fetchExam(); }
        else toast.error('Failed');
    };

    const toggleResultVisibility = async () => {
        const res = await authFetch(`/mcq-exams/${examId}/toggle-results`, { method: 'PATCH' });
        if (res.ok) {
            const data = await res.json();
            setExam(prev => ({ ...prev, show_result_to_student: data.show_result_to_student }));
            toast.success(data.show_result_to_student ? 'Results visible to students' : 'Results hidden from students');
        }
    };

    const fetchResults = async () => {
        const res = await authFetch(`/mcq-exams/${examId}/results`);
        if (res.ok) setResults(await res.json());
    };

    useEffect(() => {
        if (activeTab === 'results' && !results) fetchResults();
        if (activeTab === 'proctoring' && !proctoring) fetchProctoring();
    }, [activeTab]);

    const fetchProctoring = async () => {
        const res = await authFetch(`/mcq-exams/${examId}/proctoring`);
        if (res.ok) setProctoring(await res.json());
    };

    const eventBadgeColor = (type) => {
        const colors = {
            'TAB_SWITCH': { bg: '#FEE2E2', color: '#991B1B' },
            'FULLSCREEN_EXIT': { bg: '#FEF3C7', color: '#92400E' },
            'MULTIPLE_FACES': { bg: '#FCE7F3', color: '#9D174D' },
            'EXAM_STARTED': { bg: '#D1FAE5', color: '#065F46' },
            'EXAM_SUBMITTED': { bg: '#DBEAFE', color: '#1E40AF' },
        };
        return colors[type] || { bg: '#F3F4F6', color: '#374151' };
    };

    if (loading) return <div className="mcq-empty-state">Loading…</div>;
    if (!exam) return <div className="mcq-empty-state">Exam not found</div>;

    return (
        <div className="mcq-detail-container">
            <div className="mcq-detail-card">
                {/* Header */}
                <div className="mcq-detail-header">
                    <button className="back-btn" onClick={() => navigate('/mcq-exams')}>
                        <ArrowLeft size={20} />
                    </button>
                    <div className="mcq-detail-header-info">
                        <h1 className="mcq-detail-title">{exam.title}</h1>
                        <p className="mcq-detail-subtitle">
                            {exam.subject_name} · {exam.exam_mode} · {exam.total_questions} questions · {exam.duration_minutes} min
                        </p>
                    </div>
                </div>

                {/* Info bar with editable times */}
                <div className="mcq-info-bar">
                    <div className="mcq-stat">
                        <span className="mcq-stat-label">Submissions</span>
                        <span className="mcq-stat-value">{exam.submissions?.completed || 0} / {exam.submissions?.total || 0}</span>
                    </div>
                    <div className="mcq-edit-time-row">
                        <div className="mcq-form-group">
                            <label className="mcq-form-label">Start Time</label>
                            <input type="datetime-local" className="mcq-form-input" value={editStart}
                                onChange={e => setEditStart(e.target.value)} />
                        </div>
                        <div className="mcq-form-group">
                            <label className="mcq-form-label">End Time</label>
                            <input type="datetime-local" className="mcq-form-input" value={editEnd}
                                onChange={e => setEditEnd(e.target.value)} />
                        </div>
                        <button className="save-time-btn" onClick={handleSaveTime} disabled={editingTime}>
                            {editingTime ? 'Saving…' : 'Save'}
                        </button>
                    </div>
                </div>

                {/* Tabs */}
                <div className="mcq-tabs">
                    <button className={`mcq-tab ${activeTab === 'groups' ? 'active' : ''}`}
                        onClick={() => setActiveTab('groups')}>
                        <Users size={15} /> Assigned Groups
                    </button>
                    <button className={`mcq-tab ${activeTab === 'results' ? 'active' : ''}`}
                        onClick={() => setActiveTab('results')}>
                        <BarChart3 size={15} /> Results
                    </button>
                    <button className={`mcq-tab ${activeTab === 'proctoring' ? 'active' : ''}`}
                        onClick={() => setActiveTab('proctoring')}>
                        <Shield size={15} /> Proctoring
                    </button>
                </div>

                {/* Tab Content */}
                <div className="mcq-tab-content">
                    {activeTab === 'groups' && (
                        <>
                            {/* Current Assignments */}
                            <div className="mcq-results-section">
                                <div className="mcq-results-header">
                                    <span className="mcq-results-title">Current Assignments</span>
                                </div>
                                {(!exam.assignments || exam.assignments.length === 0) ? (
                                    <div className="mcq-empty-state">Not assigned to any group yet</div>
                                ) : (
                                    <div className="mcq-assignment-list">
                                        {exam.assignments.map(a => (
                                            <div key={a.id} className="mcq-assignment-item">
                                                <span className="mcq-assignment-label">
                                                    <strong>{a.department?.name}</strong> · {a.year_of_study?.label} · Div {a.division?.name}
                                                </span>
                                                <button className="mcq-remove-btn" onClick={() => handleRemoveAssignment(a.id)}>
                                                    <Trash2 size={14} />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Assign Form */}
                            <div className="mcq-assign-card">
                                <div className="mcq-assign-card-header">
                                    <Plus size={16} style={{ color: '#0061a1' }} /> Assign to Group
                                </div>
                                <div className="mcq-assign-card-body">
                                    <select className="mcq-form-select" value={assignForm.department_id}
                                        onChange={e => setAssignForm(f => ({ ...f, department_id: e.target.value }))}>
                                        <option value="">Department…</option>
                                        {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                                    </select>
                                    <select className="mcq-form-select" value={assignForm.year_id}
                                        onChange={e => setAssignForm(f => ({ ...f, year_id: e.target.value }))}>
                                        <option value="">Year…</option>
                                        {years.map(y => <option key={y.id} value={y.id}>{y.label} (Year {y.year})</option>)}
                                    </select>
                                    <select className="mcq-form-select" value={assignForm.division_id}
                                        onChange={e => setAssignForm(f => ({ ...f, division_id: e.target.value }))}>
                                        <option value="">Division…</option>
                                        {divisions.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                                    </select>
                                    <button className="mcq-assign-btn" onClick={handleAssign} disabled={assigning}>
                                        {assigning ? 'Assigning…' : 'Assign'}
                                    </button>
                                </div>
                            </div>

                            {/* Questions */}
                            <div className="mcq-questions-section">
                                <div className="mcq-questions-section-header">
                                    Questions ({exam.questions?.length || 0})
                                </div>
                                {exam.questions?.map(q => (
                                    <div key={q.id} className="mcq-detail-question-item">
                                        <p className="mcq-detail-question-text">
                                            <span className="q-num">Q{q.question_order}.</span> {q.question_text}
                                        </p>
                                        <div className="mcq-detail-options">
                                            {q.options?.map(opt => (
                                                <span key={opt.label}
                                                    className={`mcq-detail-option ${opt.label === q.correct_answer ? 'correct' : 'wrong'}`}>
                                                    {opt.label}. {opt.text}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </>
                    )}

                    {activeTab === 'results' && (
                        <>
                            {/* Controls */}
                            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', alignItems: 'center' }}>
                                <button
                                    className={`mcq-toggle-result-btn ${exam.show_result_to_student ? 'visible' : 'hidden'}`}
                                    onClick={toggleResultVisibility}>
                                    {exam.show_result_to_student ? <><Eye size={14} /> Results Visible to Students</> : <><EyeOff size={14} /> Results Hidden from Students</>}
                                </button>
                            </div>

                            {/* Results table */}
                            <div className="mcq-results-section">
                                <div className="mcq-results-header">
                                    <span className="mcq-results-title">
                                        Student Results ({results?.total_students || 0})
                                    </span>
                                </div>
                                {!results ? (
                                    <div className="mcq-empty-state">Loading results…</div>
                                ) : results.results?.length === 0 ? (
                                    <div className="mcq-empty-state">No submissions yet</div>
                                ) : (
                                    <table className="mcq-results-table">
                                        <thead>
                                            <tr>
                                                {['Student', 'Score', 'Percentage', 'Submitted', 'Auto'].map(h => (
                                                    <th key={h}>{h}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {results.results.map((r, i) => (
                                                <tr key={i}>
                                                    <td>
                                                        <span style={{ fontWeight: 500 }}>{r.student_name}</span>
                                                        <br />
                                                        <span style={{ fontSize: '0.7rem', color: '#9CA3AF' }}>{r.student_email}</span>
                                                    </td>
                                                    <td>{r.score}/{r.total_questions}</td>
                                                    <td>
                                                        <span className={`mcq-percentage-badge ${(r.percentage || 0) >= 50 ? 'pass' : 'fail'}`}>
                                                            {r.percentage}%
                                                        </span>
                                                    </td>
                                                    <td>{r.submitted_at ? dayjs(r.submitted_at).format('HH:mm') : '—'}</td>
                                                    <td>{r.is_auto_submitted ? 'Yes' : 'No'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </div>
                        </>
                    )}

                    {activeTab === 'proctoring' && (
                        <div className="mcq-results-section">
                            <div className="mcq-results-header">
                                <span className="mcq-results-title">
                                    <Shield size={14} style={{ marginRight: 6 }} />
                                    Proctoring Events ({proctoring?.students_with_events || 0} students flagged)
                                </span>
                            </div>
                            {!proctoring ? (
                                <div className="mcq-empty-state">Loading proctoring data…</div>
                            ) : proctoring.students?.length === 0 ? (
                                <div className="mcq-empty-state">No proctoring events recorded</div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                    {proctoring.students.map((s) => {
                                        const isExpanded = expandedStudent === s.student_id;
                                        const violations = s.events.filter(e => !['EXAM_STARTED', 'EXAM_SUBMITTED'].includes(e.event_type));
                                        return (
                                            <div key={s.student_id} style={{
                                                background: '#fff', border: '1px solid #E5E7EB',
                                                borderRadius: '0.5rem', overflow: 'hidden',
                                            }}>
                                                {/* Student header */}
                                                <div
                                                    onClick={() => setExpandedStudent(isExpanded ? null : s.student_id)}
                                                    style={{
                                                        padding: '0.75rem 1rem', cursor: 'pointer',
                                                        display: 'flex', alignItems: 'center', gap: '0.75rem',
                                                        background: violations.length > 3 ? '#FEF2F2' : '#fff',
                                                        borderBottom: isExpanded ? '1px solid #E5E7EB' : 'none',
                                                    }}
                                                >
                                                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                                    <div style={{ flex: 1 }}>
                                                        <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{s.student_name}</span>
                                                        <span style={{ color: '#9CA3AF', fontSize: '0.75rem', marginLeft: 8 }}>{s.student_email}</span>
                                                    </div>
                                                    <span style={{
                                                        background: violations.length > 3 ? '#FEE2E2' : violations.length > 0 ? '#FEF3C7' : '#D1FAE5',
                                                        color: violations.length > 3 ? '#991B1B' : violations.length > 0 ? '#92400E' : '#065F46',
                                                        padding: '0.125rem 0.625rem', borderRadius: '1rem',
                                                        fontSize: '0.75rem', fontWeight: 600,
                                                    }}>
                                                        {violations.length} violation{violations.length !== 1 ? 's' : ''}
                                                    </span>
                                                </div>

                                                {/* Expanded event timeline */}
                                                {isExpanded && (
                                                    <div style={{ padding: '0.75rem 1rem' }}>
                                                        <table style={{ width: '100%', fontSize: '0.8125rem', borderCollapse: 'collapse' }}>
                                                            <thead>
                                                                <tr style={{ borderBottom: '1px solid #E5E7EB' }}>
                                                                    <th style={{ textAlign: 'left', padding: '0.375rem 0', color: '#6B7280', fontWeight: 600 }}>Time</th>
                                                                    <th style={{ textAlign: 'left', padding: '0.375rem 0', color: '#6B7280', fontWeight: 600 }}>Event</th>
                                                                    <th style={{ textAlign: 'left', padding: '0.375rem 0', color: '#6B7280', fontWeight: 600 }}>Details</th>
                                                                    <th style={{ textAlign: 'center', padding: '0.375rem 0', color: '#6B7280', fontWeight: 600 }}>Snapshot</th>
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {s.events.map((evt) => {
                                                                    const badge = eventBadgeColor(evt.event_type);
                                                                    return (
                                                                        <tr key={evt.id} style={{ borderBottom: '1px solid #F3F4F6' }}>
                                                                            <td style={{ padding: '0.5rem 0', color: '#6B7280', fontFamily: 'monospace', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                                                                                {evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : '—'}
                                                                            </td>
                                                                            <td style={{ padding: '0.5rem 0.5rem' }}>
                                                                                <span style={{
                                                                                    background: badge.bg, color: badge.color,
                                                                                    padding: '0.125rem 0.5rem', borderRadius: '0.25rem',
                                                                                    fontSize: '0.6875rem', fontWeight: 600,
                                                                                    textTransform: 'uppercase', letterSpacing: '0.04em',
                                                                                }}>
                                                                                    {evt.event_type.replace(/_/g, ' ')}
                                                                                </span>
                                                                            </td>
                                                                            <td style={{ padding: '0.5rem 0', color: '#374151', fontSize: '0.8rem' }}>
                                                                                {evt.details || '—'}
                                                                            </td>
                                                                            <td style={{ padding: '0.5rem 0', textAlign: 'center' }}>
                                                                                {evt.snapshot_url ? (
                                                                                    <img
                                                                                        src={`http://localhost:8001${evt.snapshot_url}`}
                                                                                        alt="Snapshot"
                                                                                        onClick={() => setLightboxImg(`http://localhost:8001${evt.snapshot_url}`)}
                                                                                        style={{
                                                                                            width: 48, height: 36, objectFit: 'cover',
                                                                                            borderRadius: '0.25rem', cursor: 'pointer',
                                                                                            border: '1px solid #D1D5DB',
                                                                                        }}
                                                                                    />
                                                                                ) : (
                                                                                    <span style={{ color: '#D1D5DB', fontSize: '0.75rem' }}>—</span>
                                                                                )}
                                                                            </td>
                                                                        </tr>
                                                                    );
                                                                })}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Lightbox Modal for Snapshots */}
                {lightboxImg && (
                    <div
                        onClick={() => setLightboxImg(null)}
                        style={{
                            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            zIndex: 9999, cursor: 'zoom-out',
                        }}
                    >
                        <button
                            onClick={(e) => { e.stopPropagation(); setLightboxImg(null); }}
                            style={{
                                position: 'absolute', top: 20, right: 20,
                                background: '#fff', border: 'none', borderRadius: '50%',
                                width: 36, height: 36, cursor: 'pointer',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}
                        >
                            <X size={18} />
                        </button>
                        <img
                            src={lightboxImg}
                            alt="Snapshot full"
                            onClick={(e) => e.stopPropagation()}
                            style={{
                                maxWidth: '90vw', maxHeight: '90vh',
                                borderRadius: '0.5rem', boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
                                cursor: 'default',
                            }}
                        />
                    </div>
                )}
            </div>
        </div>
    );
};

export default McqExamDetail;
