import React, { useState, useEffect } from 'react';
import { GraduationCap, Users, UserPlus, Eye, EyeOff, Building2, Filter, ChevronDown, ChevronUp, ClipboardList } from 'lucide-react';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';
import { useSelector } from 'react-redux';
import dayjs from 'dayjs';
import './StudentsList.css';

const StudentsList = () => {
    const isAdmin = useSelector(s => s.auth.teacher?.is_admin);
    const [students, setStudents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [departments, setDepartments] = useState([]);
    const [divisions, setDivisions] = useState([]);
    const [years, setYears] = useState([]);
    const [filterDept, setFilterDept] = useState('');
    const [filterYear, setFilterYear] = useState('');
    const [filterDiv, setFilterDiv] = useState('');

    // Detail panel state
    const [selectedStudent, setSelectedStudent] = useState(null);
    const [examHistory, setExamHistory] = useState(null);
    const [loadingHistory, setLoadingHistory] = useState(false);

    // Add student form
    const [showAddForm, setShowAddForm] = useState(false);
    const [form, setForm] = useState({ email: '', full_name: '', password: '', department_id: '', year_id: '', division_id: '' });
    const [showPw, setShowPw] = useState(false);
    const [creating, setCreating] = useState(false);

    // Quick add
    const [newDept, setNewDept] = useState('');
    const [newDiv, setNewDiv] = useState('');

    useEffect(() => {
        authFetch('/auth/departments').then(r => r.json()).then(setDepartments).catch(() => { });
        authFetch('/auth/divisions').then(r => r.json()).then(setDivisions).catch(() => { });
        authFetch('/auth/years').then(r => r.json()).then(setYears).catch(() => { });
    }, []);

    const fetchStudents = () => {
        setLoading(true);
        const params = new URLSearchParams();
        if (filterDept) params.append('department_id', filterDept);
        if (filterYear) params.append('year_id', filterYear);
        if (filterDiv) params.append('division_id', filterDiv);
        authFetch(`/auth/students?${params}`).then(r => r.json()).then(data => {
            setStudents(Array.isArray(data) ? data : []);
            setLoading(false);
        }).catch(() => setLoading(false));
    };

    useEffect(() => { fetchStudents(); }, [filterDept, filterYear, filterDiv]);

    const selectStudent = async (student) => {
        setSelectedStudent(student);
        setExamHistory(null);
        setLoadingHistory(true);
        try {
            const res = await authFetch(`/mcq-exams/student/${student.id}/history`);
            if (res.ok) setExamHistory(await res.json());
            else setExamHistory({ exams: [] });
        } catch {
            setExamHistory({ exams: [] });
        }
        setLoadingHistory(false);
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        setCreating(true);
        try {
            const res = await authFetch('/auth/students', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...form,
                    department_id: form.department_id ? parseInt(form.department_id) : null,
                    year_id: form.year_id ? parseInt(form.year_id) : null,
                    division_id: form.division_id ? parseInt(form.division_id) : null,
                }),
            });
            if (res.ok) {
                toast.success(`Student ${form.full_name} created`);
                setForm({ email: '', full_name: '', password: '', department_id: '', year_id: '', division_id: '' });
                fetchStudents();
            } else {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || 'Failed');
            }
        } catch { toast.error('Network error'); }
        finally { setCreating(false); }
    };

    const addDept = async () => {
        if (!newDept.trim()) return;
        const res = await authFetch('/auth/departments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newDept.trim() }) });
        if (res.ok) { toast.success('Department added'); setNewDept(''); authFetch('/auth/departments').then(r => r.json()).then(setDepartments); }
        else toast.error('Failed');
    };

    const addDiv = async () => {
        if (!newDiv.trim()) return;
        const res = await authFetch('/auth/divisions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newDiv.trim() }) });
        if (res.ok) { toast.success('Division added'); setNewDiv(''); authFetch('/auth/divisions').then(r => r.json()).then(setDivisions); }
        else toast.error('Failed');
    };

    return (
        <div className="students-container">
            <div className="students-card">
                {/* Header */}
                <div className="students-header">
                    <GraduationCap size={20} style={{ color: '#0061a1' }} />
                    <div className="students-header-info">
                        <h1>Students</h1>
                        <p>{students.length} student(s)</p>
                    </div>
                </div>

                {/* Filters */}
                <div className="students-filters">
                    <Filter size={14} style={{ color: '#6B7280' }} />
                    <select className="students-filter-select" value={filterDept} onChange={e => setFilterDept(e.target.value)}>
                        <option value="">All Departments</option>
                        {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                    <select className="students-filter-select" value={filterYear} onChange={e => setFilterYear(e.target.value)}>
                        <option value="">All Years</option>
                        {years.map(y => <option key={y.id} value={y.id}>{y.label}</option>)}
                    </select>
                    <select className="students-filter-select" value={filterDiv} onChange={e => setFilterDiv(e.target.value)}>
                        <option value="">All Divisions</option>
                        {divisions.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                </div>

                {/* Body: table + detail */}
                <div className="students-body">
                    {/* Student Table */}
                    <div className="students-list-panel">
                        {loading ? (
                            <div className="students-empty">Loading…</div>
                        ) : students.length === 0 ? (
                            <div className="students-empty">No students found.</div>
                        ) : (
                            <table className="students-table">
                                <thead>
                                    <tr>
                                        {['Name', 'Email', 'Department', 'Year', 'Division'].map(h =>
                                            <th key={h}>{h}</th>
                                        )}
                                    </tr>
                                </thead>
                                <tbody>
                                    {students.map(s => (
                                        <tr key={s.id}
                                            className={selectedStudent?.id === s.id ? 'active' : ''}
                                            onClick={() => selectStudent(s)}>
                                            <td>
                                                <div className="student-name-cell">
                                                    <div className="student-avatar">{s.full_name?.charAt(0).toUpperCase()}</div>
                                                    <span className="student-name">{s.full_name}</span>
                                                </div>
                                            </td>
                                            <td>{s.email}</td>
                                            <td>{s.department?.name || '—'}</td>
                                            <td>{s.year_of_study?.label || '—'}</td>
                                            <td>{s.division?.name || '—'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>

                    {/* Detail Panel */}
                    <div className="students-detail-panel">
                        {!selectedStudent ? (
                            <div className="detail-placeholder">
                                <div>
                                    <Users size={32} style={{ color: '#D1D5DB', marginBottom: '0.5rem' }} />
                                    <p>Click a student to view their exam history</p>
                                </div>
                            </div>
                        ) : (
                            <>
                                {/* Student info */}
                                <div className="detail-header">
                                    <div className="detail-avatar">{selectedStudent.full_name?.charAt(0).toUpperCase()}</div>
                                    <div>
                                        <p className="detail-name">{selectedStudent.full_name}</p>
                                        <p className="detail-email">{selectedStudent.email}</p>
                                        <p className="detail-meta">
                                            {selectedStudent.department?.name || '—'} · {selectedStudent.year_of_study?.label || '—'} · Div {selectedStudent.division?.name || '—'}
                                        </p>
                                    </div>
                                </div>

                                {/* Exam history */}
                                <div className="detail-section-title">
                                    <ClipboardList size={12} style={{ marginRight: '0.375rem', verticalAlign: 'middle' }} />
                                    Exam History
                                </div>
                                <div className="detail-exam-list">
                                    {loadingHistory ? (
                                        <div className="detail-no-exams">Loading…</div>
                                    ) : !examHistory?.exams?.length ? (
                                        <div className="detail-no-exams">No exam attempts yet</div>
                                    ) : (
                                        examHistory.exams.map((ex, i) => (
                                            <div key={i} className="detail-exam-item">
                                                <p className="detail-exam-title">{ex.exam_title}</p>
                                                <p className="detail-exam-subject">{ex.subject_name}</p>
                                                <div className="detail-exam-score-row">
                                                    {ex.score !== null ? (
                                                        <>
                                                            <span className="detail-exam-score">{ex.score}/{ex.total_questions}</span>
                                                            <span className={`detail-exam-pct ${(ex.percentage || 0) >= 50 ? 'pass' : 'fail'}`}>
                                                                {ex.percentage}%
                                                            </span>
                                                        </>
                                                    ) : (
                                                        <span style={{ fontSize: '0.8rem', color: '#9CA3AF' }}>In progress</span>
                                                    )}
                                                    <span className="detail-exam-date">
                                                        {ex.submitted_at ? dayjs(ex.submitted_at).format('MMM D, HH:mm') : '—'}
                                                    </span>
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>

                                {/* Add Student (admin only) */}
                                {isAdmin && (
                                    <div className="add-student-section">
                                        <div className="add-student-header" onClick={() => setShowAddForm(v => !v)}>
                                            <UserPlus size={14} style={{ color: '#0061a1' }} />
                                            Add Student
                                            {showAddForm ? <ChevronUp size={14} style={{ marginLeft: 'auto' }} /> : <ChevronDown size={14} style={{ marginLeft: 'auto' }} />}
                                        </div>
                                        {showAddForm && (
                                            <>
                                                <form onSubmit={handleCreate} className="add-student-form">
                                                    <input type="text" className="form-input" placeholder="Full Name" value={form.full_name}
                                                        onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} required />
                                                    <input type="email" className="form-input" placeholder="Email" value={form.email}
                                                        onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required />
                                                    <div className="pw-wrapper">
                                                        <input type={showPw ? 'text' : 'password'} className="form-input" placeholder="Password"
                                                            value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required />
                                                        <button type="button" className="pw-toggle" onClick={() => setShowPw(!showPw)}>
                                                            {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                                                        </button>
                                                    </div>
                                                    <select className="form-select" value={form.department_id}
                                                        onChange={e => setForm(f => ({ ...f, department_id: e.target.value }))}>
                                                        <option value="">Department</option>
                                                        {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                                                    </select>
                                                    <select className="form-select" value={form.year_id}
                                                        onChange={e => setForm(f => ({ ...f, year_id: e.target.value }))}>
                                                        <option value="">Year</option>
                                                        {years.map(y => <option key={y.id} value={y.id}>{y.label}</option>)}
                                                    </select>
                                                    <select className="form-select" value={form.division_id}
                                                        onChange={e => setForm(f => ({ ...f, division_id: e.target.value }))}>
                                                        <option value="">Division</option>
                                                        {divisions.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                                                    </select>
                                                    <button type="submit" className="add-student-submit" disabled={creating}>
                                                        {creating ? 'Creating…' : 'Create Student'}
                                                    </button>
                                                </form>
                                                {/* Quick add dept/div */}
                                                <div className="quick-add-row">
                                                    <input type="text" className="form-input" placeholder="New department…" value={newDept}
                                                        onChange={e => setNewDept(e.target.value)} />
                                                    <button className="quick-add-btn" onClick={addDept}>Add</button>
                                                </div>
                                                <div className="quick-add-row">
                                                    <input type="text" className="form-input" placeholder="New division…" value={newDiv}
                                                        onChange={e => setNewDiv(e.target.value)} />
                                                    <button className="quick-add-btn" onClick={addDiv}>Add</button>
                                                </div>
                                                <div className="quick-add-meta">
                                                    Depts: {departments.map(d => d.name).join(', ') || '—'}<br />
                                                    Divs: {divisions.map(d => d.name).join(', ') || '—'}
                                                </div>
                                            </>
                                        )}
                                    </div>
                                )}
                            </>
                        )}

                        {/* If no student selected and admin, still show add form */}
                        {!selectedStudent && isAdmin && (
                            <div className="add-student-section">
                                <div className="add-student-header" onClick={() => setShowAddForm(v => !v)}>
                                    <UserPlus size={14} style={{ color: '#0061a1' }} />
                                    Add Student
                                    {showAddForm ? <ChevronUp size={14} style={{ marginLeft: 'auto' }} /> : <ChevronDown size={14} style={{ marginLeft: 'auto' }} />}
                                </div>
                                {showAddForm && (
                                    <>
                                        <form onSubmit={handleCreate} className="add-student-form">
                                            <input type="text" className="form-input" placeholder="Full Name" value={form.full_name}
                                                onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} required />
                                            <input type="email" className="form-input" placeholder="Email" value={form.email}
                                                onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required />
                                            <div className="pw-wrapper">
                                                <input type={showPw ? 'text' : 'password'} className="form-input" placeholder="Password"
                                                    value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required />
                                                <button type="button" className="pw-toggle" onClick={() => setShowPw(!showPw)}>
                                                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                                                </button>
                                            </div>
                                            <select className="form-select" value={form.department_id}
                                                onChange={e => setForm(f => ({ ...f, department_id: e.target.value }))}>
                                                <option value="">Department</option>
                                                {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                                            </select>
                                            <select className="form-select" value={form.year_id}
                                                onChange={e => setForm(f => ({ ...f, year_id: e.target.value }))}>
                                                <option value="">Year</option>
                                                {years.map(y => <option key={y.id} value={y.id}>{y.label}</option>)}
                                            </select>
                                            <select className="form-select" value={form.division_id}
                                                onChange={e => setForm(f => ({ ...f, division_id: e.target.value }))}>
                                                <option value="">Division</option>
                                                {divisions.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                                            </select>
                                            <button type="submit" className="add-student-submit" disabled={creating}>
                                                {creating ? 'Creating…' : 'Create Student'}
                                            </button>
                                        </form>
                                        <div className="quick-add-row">
                                            <input type="text" className="form-input" placeholder="New department…" value={newDept}
                                                onChange={e => setNewDept(e.target.value)} />
                                            <button className="quick-add-btn" onClick={addDept}>Add</button>
                                        </div>
                                        <div className="quick-add-row">
                                            <input type="text" className="form-input" placeholder="New division…" value={newDiv}
                                                onChange={e => setNewDiv(e.target.value)} />
                                            <button className="quick-add-btn" onClick={addDiv}>Add</button>
                                        </div>
                                        <div className="quick-add-meta">
                                            Depts: {departments.map(d => d.name).join(', ') || '—'}<br />
                                            Divs: {divisions.map(d => d.name).join(', ') || '—'}
                                        </div>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default StudentsList;
