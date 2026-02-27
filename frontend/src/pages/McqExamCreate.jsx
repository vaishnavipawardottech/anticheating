import React, { useState, useEffect } from 'react';
import { ArrowLeft, Settings, Users, BookOpen, X, CheckSquare } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';
import './McqExamCreate.css';

const McqExamCreate = () => {
    const navigate = useNavigate();
    const [activeTab, setActiveTab] = useState('settings');

    const [subjects, setSubjects] = useState([]);
    const [units, setUnits] = useState([]);
    const [poolQuestions, setPoolQuestions] = useState([]);
    const [departments, setDepartments] = useState([]);
    const [divisions, setDivisions] = useState([]);
    const [years, setYears] = useState([]);

    const [form, setForm] = useState({
        title: '', subject_id: '', exam_mode: 'static',
        start_time: '', end_time: '', duration_minutes: 60,
        total_questions: 0, show_result_to_student: false,
    });
    const [selectedQuestions, setSelectedQuestions] = useState([]);
    const [filterUnit, setFilterUnit] = useState('');
    const [creating, setCreating] = useState(false);

    // Group assignment state
    const [assignments, setAssignments] = useState([]);
    const [assignForm, setAssignForm] = useState({ department_id: '', year_id: '', division_id: '' });

    useEffect(() => {
        authFetch('/subjects').then(r => r.json()).then(setSubjects).catch(() => { });
        authFetch('/auth/departments').then(r => r.json()).then(setDepartments).catch(() => { });
        authFetch('/auth/divisions').then(r => r.json()).then(setDivisions).catch(() => { });
        authFetch('/auth/years').then(r => r.json()).then(setYears).catch(() => { });
    }, []);

    useEffect(() => {
        if (form.subject_id) {
            authFetch(`/units/subject/${form.subject_id}`).then(r => r.json()).then(setUnits).catch(() => setUnits([]));
            authFetch(`/mcq-pool/?subject_id=${form.subject_id}&limit=500`).then(r => r.json()).then(data => setPoolQuestions(data.questions || [])).catch(() => setPoolQuestions([]));
        }
    }, [form.subject_id]);

    const filteredQuestions = filterUnit ? poolQuestions.filter(q => q.unit_id === parseInt(filterUnit)) : poolQuestions;

    const toggleQuestion = (qid) => {
        setSelectedQuestions(prev => prev.includes(qid) ? prev.filter(id => id !== qid) : [...prev, qid]);
    };

    const selectAll = () => setSelectedQuestions(filteredQuestions.map(q => q.id));
    const deselectAll = () => setSelectedQuestions([]);

    const addGroup = () => {
        if (!assignForm.department_id || !assignForm.year_id || !assignForm.division_id) {
            toast.error('Select department, year and division');
            return;
        }
        const dup = assignments.find(a =>
            a.department_id === assignForm.department_id &&
            a.year_id === assignForm.year_id &&
            a.division_id === assignForm.division_id
        );
        if (dup) { toast.error('Group already added'); return; }

        const dept = departments.find(d => d.id === parseInt(assignForm.department_id));
        const yr = years.find(y => y.id === parseInt(assignForm.year_id));
        const div = divisions.find(d => d.id === parseInt(assignForm.division_id));

        setAssignments(prev => [...prev, {
            department_id: parseInt(assignForm.department_id),
            year_id: parseInt(assignForm.year_id),
            division_id: parseInt(assignForm.division_id),
            label: `${dept?.name || ''} · ${yr?.label || ''} · Div ${div?.name || ''}`,
        }]);
        setAssignForm({ department_id: '', year_id: '', division_id: '' });
    };

    const removeGroup = (idx) => setAssignments(prev => prev.filter((_, i) => i !== idx));

    const toISOWithTimezone = (localVal) => {
        if (!localVal) return '';
        const d = new Date(localVal);
        const offset = -d.getTimezoneOffset();
        const sign = offset >= 0 ? '+' : '-';
        const hh = String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0');
        const mm = String(Math.abs(offset) % 60).padStart(2, '0');
        return `${localVal}:00${sign}${hh}:${mm}`;
    };

    const handleCreate = async () => {
        if (!form.title || !form.subject_id || !form.start_time || !form.end_time || selectedQuestions.length === 0) {
            toast.error('Fill all fields and select questions');
            return;
        }
        setCreating(true);
        try {
            const total = form.exam_mode === 'dynamic' ? form.total_questions || selectedQuestions.length : selectedQuestions.length;
            const res = await authFetch('/mcq-exams/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...form,
                    subject_id: parseInt(form.subject_id),
                    duration_minutes: parseInt(form.duration_minutes),
                    total_questions: total,
                    question_ids: selectedQuestions,
                    start_time: toISOWithTimezone(form.start_time),
                    end_time: toISOWithTimezone(form.end_time),
                    assignments: assignments.length > 0 ? assignments.map(a => ({
                        department_id: a.department_id,
                        year_id: a.year_id,
                        division_id: a.division_id,
                    })) : null,
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || 'Failed to create exam');
            } else {
                toast.success('Exam created!');
                navigate('/mcq-exams');
            }
        } catch { toast.error('Network error'); }
        finally { setCreating(false); }
    };

    return (
        <div className="mcq-create-container">
            <div className="mcq-create-card">
                {/* Header */}
                <div className="mcq-create-header">
                    <button className="back-btn" onClick={() => navigate('/mcq-exams')}>
                        <ArrowLeft size={20} />
                    </button>
                    <h1 className="mcq-create-title">Create MCQ Exam</h1>
                </div>

                {/* Summary bar */}
                <div className="mcq-create-summary">
                    <span>Title: <strong>{form.title || '—'}</strong></span>
                    <span>Questions: <strong>{selectedQuestions.length}</strong></span>
                    <span>Groups: <strong>{assignments.length}</strong></span>
                    <span>Duration: <strong>{form.duration_minutes} min</strong></span>
                </div>

                {/* Tabs */}
                <div className="mcq-create-tabs">
                    <button className={`mcq-create-tab ${activeTab === 'settings' ? 'active' : ''}`}
                        onClick={() => setActiveTab('settings')}>
                        <Settings size={14} /> Exam Settings
                    </button>
                    <button className={`mcq-create-tab ${activeTab === 'groups' ? 'active' : ''}`}
                        onClick={() => setActiveTab('groups')}>
                        <Users size={14} /> Assign Groups
                        {assignments.length > 0 && <span className="tab-count">{assignments.length}</span>}
                    </button>
                    <button className={`mcq-create-tab ${activeTab === 'questions' ? 'active' : ''}`}
                        onClick={() => setActiveTab('questions')}>
                        <BookOpen size={14} /> Select Questions
                        {selectedQuestions.length > 0 && <span className="tab-count">{selectedQuestions.length}</span>}
                    </button>
                </div>

                {/* Tab Content */}
                <div className="mcq-create-content">
                    {/* ── Settings Tab ── */}
                    {activeTab === 'settings' && (
                        <>
                            <div className="mcq-form-group">
                                <label className="mcq-form-label">Exam Title *</label>
                                <input type="text" className="mcq-form-input" value={form.title}
                                    onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                                    placeholder="e.g. Unit 1-3 Mid Semester MCQ" />
                            </div>
                            <div className="mcq-form-row cols-2">
                                <div className="mcq-form-group">
                                    <label className="mcq-form-label">Subject *</label>
                                    <select className="mcq-form-select" value={form.subject_id}
                                        onChange={e => { setForm(f => ({ ...f, subject_id: e.target.value })); setSelectedQuestions([]); }}>
                                        <option value="">Select subject…</option>
                                        {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                                    </select>
                                </div>
                                <div className="mcq-form-group">
                                    <label className="mcq-form-label">Exam Mode</label>
                                    <select className="mcq-form-select" value={form.exam_mode}
                                        onChange={e => setForm(f => ({ ...f, exam_mode: e.target.value }))}>
                                        <option value="static">Static (same paper for all)</option>
                                        <option value="dynamic">Dynamic (random per student)</option>
                                    </select>
                                </div>
                            </div>
                            <div className="mcq-form-row cols-3">
                                <div className="mcq-form-group">
                                    <label className="mcq-form-label">Start Time *</label>
                                    <input type="datetime-local" className="mcq-form-input" value={form.start_time}
                                        onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} />
                                </div>
                                <div className="mcq-form-group">
                                    <label className="mcq-form-label">End Time *</label>
                                    <input type="datetime-local" className="mcq-form-input" value={form.end_time}
                                        onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} />
                                </div>
                                <div className="mcq-form-group">
                                    <label className="mcq-form-label">Duration (min)</label>
                                    <input type="number" min={1} className="mcq-form-input" value={form.duration_minutes}
                                        onChange={e => setForm(f => ({ ...f, duration_minutes: e.target.value }))} />
                                </div>
                            </div>
                            {form.exam_mode === 'dynamic' && (
                                <div className="mcq-form-group">
                                    <label className="mcq-form-label">Questions per student</label>
                                    <input type="number" min={1} max={selectedQuestions.length || 100}
                                        className="mcq-form-input" value={form.total_questions}
                                        onChange={e => setForm(f => ({ ...f, total_questions: parseInt(e.target.value) || 0 }))} />
                                    <span className="mcq-form-hint">Each student will get this many random questions from the selected pool ({selectedQuestions.length} selected)</span>
                                </div>
                            )}
                            <div className="mcq-checkbox-row">
                                <input type="checkbox" id="show-result" checked={form.show_result_to_student}
                                    onChange={e => setForm(f => ({ ...f, show_result_to_student: e.target.checked }))} />
                                <label htmlFor="show-result">Show result to students after submission</label>
                            </div>
                        </>
                    )}

                    {/* ── Assign Groups Tab ── */}
                    {activeTab === 'groups' && (
                        <>
                            {assignments.length > 0 && (
                                <div className="mcq-assigned-groups">
                                    {assignments.map((a, i) => (
                                        <div key={i} className="mcq-group-tag">
                                            <span>{a.label}</span>
                                            <button onClick={() => removeGroup(i)}><X size={14} /></button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <div className="mcq-group-add-row">
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
                                <button className="add-group-btn" onClick={addGroup}>Add</button>
                            </div>
                            {assignments.length === 0 && (
                                <div className="mcq-empty" style={{ marginTop: '2rem' }}>
                                    No groups assigned yet. Select department, year & division above.
                                </div>
                            )}
                        </>
                    )}

                    {/* ── Select Questions Tab ── */}
                    {activeTab === 'questions' && (
                        <>
                            <div className="mcq-question-list-header">
                                <div className="left">
                                    <CheckSquare size={16} className="section-icon" />
                                    <span className="section-title">{selectedQuestions.length} of {filteredQuestions.length} selected</span>
                                </div>
                                <div className="right">
                                    <select className="mcq-form-select" value={filterUnit}
                                        onChange={e => setFilterUnit(e.target.value)}
                                        style={{ width: 'auto', padding: '0.3rem 0.5rem', fontSize: '0.8rem' }}>
                                        <option value="">All Units</option>
                                        {units.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                                    </select>
                                    <button className="mcq-link-btn" onClick={selectAll}>Select All</button>
                                    <button className="mcq-link-btn danger" onClick={deselectAll}>Clear</button>
                                </div>
                            </div>
                            <div className="mcq-question-list">
                                {!form.subject_id ? (
                                    <div className="mcq-empty">Select a subject in the Settings tab first</div>
                                ) : filteredQuestions.length === 0 ? (
                                    <div className="mcq-empty">No pool questions. <a href="/mcq-pool/generate">Generate some first.</a></div>
                                ) : (
                                    filteredQuestions.map(q => (
                                        <div key={q.id}
                                            className={`mcq-question-item ${selectedQuestions.includes(q.id) ? 'selected' : ''}`}
                                            onClick={() => toggleQuestion(q.id)}>
                                            <input type="checkbox" checked={selectedQuestions.includes(q.id)} readOnly />
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <p className="mcq-question-text">{q.question_text}</p>
                                                <div className="mcq-question-options">
                                                    {q.options?.map(opt => (
                                                        <div key={opt.label}
                                                            className={`mcq-question-opt ${opt.label === q.correct_answer ? 'correct' : 'wrong'}`}>
                                                            <span className="opt-label">{opt.label}.</span>
                                                            <span>{opt.text}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                                <div className="mcq-question-tags">
                                                    {q.unit_name && <span className="mcq-tag unit">{q.unit_name}</span>}
                                                    {q.blooms_level && <span className="mcq-tag bloom">{q.blooms_level}</span>}
                                                    {q.difficulty && <span className="mcq-tag diff">{q.difficulty}</span>}
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="mcq-create-footer">
                    <button className="mcq-create-btn" onClick={handleCreate} disabled={creating}>
                        {creating ? 'Creating…' : `Create MCQ Exam (${selectedQuestions.length} questions)`}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default McqExamCreate;
