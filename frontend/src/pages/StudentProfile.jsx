import React, { useState, useEffect, useRef } from 'react';
import {
    User, Mail, Building2, GraduationCap, BookOpen, FileText,
    LogOut, Lock, Calendar, TrendingUp, CheckCircle2, ClipboardList, BarChart3, Camera, Shield
} from 'lucide-react';
import { toast } from 'react-toastify';
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from 'recharts';
import Webcam from 'react-webcam';
import './StudentExamList.css';
import './StudentProfile.css';
import './Dashboard.css';

const API = 'http://localhost:8001';

const getSession = () => {
    try { return JSON.parse(localStorage.getItem('pareeksha_student_session') || 'null'); } catch { return null; }
};

const studentFetch = (path, opts = {}) => {
    const s = getSession();
    return fetch(`${API}${path}`, {
        ...opts,
        headers: { ...(opts.headers || {}), ...(s?.token ? { Authorization: `Bearer ${s.token}` } : {}) },
    });
};

const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="dash-tooltip">
            <p className="dash-tooltip-label">{label}</p>
            <p>Score: <strong>{payload[0]?.value}%</strong></p>
        </div>
    );
};

const StudentProfile = () => {
    const session = getSession();
    const student = session?.student;

    const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
    const [changing, setChanging] = useState(false);
    const [exams, setExams] = useState([]);
    const [loadingExams, setLoadingExams] = useState(true);

    // Face registration state
    const webcamRef = useRef(null);
    const [photoUrl, setPhotoUrl] = useState(student?.face_photo_url || null);
    const [hasEmbedding, setHasEmbedding] = useState(student?.has_embedding || false);
    const [registering, setRegistering] = useState(false);
    const [faceMessage, setFaceMessage] = useState('');

    if (!session?.token) { window.location.href = '/student/login'; return null; }

    useEffect(() => {
        studentFetch('/student/exams/')
            .then(r => r.ok ? r.json() : [])
            .then(data => { setExams(Array.isArray(data) ? data : []); })
            .catch(() => { })
            .finally(() => setLoadingExams(false));

        // Fetch current photo
        studentFetch('/student/photo')
            .then(r => r.ok ? r.json() : null)
            .then(data => { if (data?.photo_url) setPhotoUrl(data.photo_url); })
            .catch(() => { });
    }, []);

    const handleLogout = () => {
        localStorage.removeItem('pareeksha_student_session');
        window.location.href = '/student/login';
    };

    const handleChangePw = async (e) => {
        e.preventDefault();
        if (pwForm.new_password !== pwForm.confirm_password) { toast.error('Passwords do not match'); return; }
        if (pwForm.new_password.length < 4) { toast.error('Password must be at least 4 characters'); return; }
        setChanging(true);
        try {
            const res = await studentFetch('/student/auth/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_password: pwForm.current_password, new_password: pwForm.new_password }),
            });
            if (res.ok) { toast.success('Password changed successfully'); setPwForm({ current_password: '', new_password: '', confirm_password: '' }); }
            else { const err = await res.json().catch(() => ({})); toast.error(err.detail || 'Failed to change password'); }
        } catch { toast.error('Network error'); }
        finally { setChanging(false); }
    };

    const handleFaceRegistration = async () => {
        if (!webcamRef.current) return;
        setRegistering(true);
        setFaceMessage('Processing facial structure...');
        try {
            const imageSrc = webcamRef.current.getScreenshot();
            if (!imageSrc) { setFaceMessage('Could not capture image. Please allow camera access.'); setRegistering(false); return; }

            const res = await studentFetch('/student/register-face', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_base64: imageSrc }),
            });

            if (res.ok) {
                const data = await res.json();
                setFaceMessage('Face registered successfully. Your identity is now securely saved.');
                setPhotoUrl(data.photo_url);
                setHasEmbedding(true);
                toast.success('Face registered successfully!');
                // Update session
                const sess = getSession();
                if (sess?.student) {
                    sess.student.has_photo = true;
                    sess.student.has_embedding = true;
                    sess.student.face_photo_url = data.photo_url;
                    localStorage.setItem('pareeksha_student_session', JSON.stringify(sess));
                }
            } else {
                const err = await res.json().catch(() => ({}));
                setFaceMessage(err.detail || 'Face registration failed. Ensure your face is clearly visible.');
            }
        } catch { setFaceMessage('Network error. Please try again.'); }
        finally { setRegistering(false); }
    };

    // Analytics
    const completedExams = exams.filter(e => e.status === 'completed' && e.score !== null && e.total_questions > 0);
    const totalAssigned = exams.length;
    const avgPct = completedExams.length
        ? Math.round(completedExams.reduce((s, e) => s + (e.score / e.total_questions) * 100, 0) / completedExams.length)
        : null;
    const bestPct = completedExams.length
        ? Math.max(...completedExams.map(e => Math.round((e.score / e.total_questions) * 100)))
        : null;

    const chartData = completedExams.map(e => ({
        name: e.title.length > 14 ? e.title.slice(0, 13) + '...' : e.title,
        pct: Math.round((e.score / e.total_questions) * 100),
    }));

    return (
        <div className="student-portal">
            {/* Nav */}
            <nav className="student-nav">
                <div className="student-nav-left">
                    <div className="student-nav-brand"><BookOpen size={18} /> Pareeksha</div>
                    <div className="student-nav-links">
                        <a href="/student/exams" className="student-nav-link"><FileText size={14} /> My Exams</a>
                        <a href="/student/profile" className="student-nav-link active"><User size={14} /> Profile</a>
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

            <div className="student-main">
                <div className="dash-header">
                    <div>
                        <h1 className="dash-title">My Profile</h1>
                        <p className="dash-subtitle">Account details &amp; performance</p>
                    </div>
                </div>

                <div className="sp-layout">
                    {/* Left column */}
                    <div className="sp-left">
                        <div className="student-profile-card">
                            <div className="student-profile-header">
                                <div className="student-profile-avatar">
                                    {student?.full_name?.charAt(0)?.toUpperCase() || 'S'}
                                </div>
                                <p className="student-profile-name">{student?.full_name || 'Student'}</p>
                                <p className="student-profile-email">{student?.email || '—'}</p>
                            </div>
                            <div className="student-profile-info">
                                <div className="student-profile-row">
                                    <span className="student-profile-row-label"><Mail size={14} /> Email</span>
                                    <span className="student-profile-row-value">{student?.email || '—'}</span>
                                </div>
                                <div className="student-profile-row">
                                    <span className="student-profile-row-label"><Building2 size={14} /> Department</span>
                                    <span className="student-profile-row-value">{student?.department?.name || '—'}</span>
                                </div>
                                <div className="student-profile-row">
                                    <span className="student-profile-row-label"><GraduationCap size={14} /> Year</span>
                                    <span className="student-profile-row-value">{student?.year_of_study?.label || '—'}</span>
                                </div>
                                <div className="student-profile-row">
                                    <span className="student-profile-row-label"><Calendar size={14} /> Division</span>
                                    <span className="student-profile-row-value">{student?.division?.name || '—'}</span>
                                </div>
                            </div>
                        </div>

                        {/* Face Registration Card — Webcam based */}
                        <div className="student-profile-card">
                            <div className="student-profile-section-title"><Shield size={14} /> Biometric Setup (Proctoring)</div>
                            <p style={{ fontSize: '0.8rem', color: '#6B7280', margin: '0 0 0.75rem' }}>
                                {hasEmbedding
                                    ? 'Your face is registered. You can re-register anytime.'
                                    : 'You must register your face before taking proctored exams.'}
                            </p>

                            {photoUrl && (
                                <div style={{ textAlign: 'center', marginBottom: '0.75rem' }}>
                                    <img
                                        src={`${API}${photoUrl}`}
                                        alt="Registered face"
                                        style={{
                                            width: 100, height: 100, borderRadius: '50%',
                                            objectFit: 'cover', border: `3px solid ${hasEmbedding ? '#059669' : '#D1D5DB'}`,
                                        }}
                                    />
                                </div>
                            )}

                            <div style={{
                                border: '1px solid #E5E7EB', background: '#1F2937',
                                borderRadius: '0.5rem', overflow: 'hidden', marginBottom: '0.75rem',
                            }}>
                                <Webcam
                                    ref={webcamRef}
                                    audio={false}
                                    screenshotFormat="image/jpeg"
                                    videoConstraints={{ width: 640, height: 480, facingMode: 'user' }}
                                    style={{ width: '100%', display: 'block' }}
                                />
                            </div>

                            {faceMessage && (
                                <div style={{
                                    padding: '0.5rem 0.75rem', marginBottom: '0.75rem', borderRadius: '0.375rem',
                                    fontSize: '0.8rem', fontWeight: 500,
                                    background: faceMessage.includes('failed') || faceMessage.includes('error') || faceMessage.includes('Error') || faceMessage.includes('Network') ? '#FEF2F2' : faceMessage.includes('registered') || faceMessage.includes('successfully') ? '#F0FDF4' : '#EFF6FF',
                                    color: faceMessage.includes('failed') || faceMessage.includes('error') || faceMessage.includes('Error') || faceMessage.includes('Network') ? '#991B1B' : faceMessage.includes('registered') || faceMessage.includes('successfully') ? '#166534' : '#1E40AF',
                                }}>
                                    {faceMessage}
                                </div>
                            )}

                            <button
                                onClick={handleFaceRegistration}
                                disabled={registering}
                                className="student-profile-submit"
                                style={{ width: '100%', padding: '0.625rem', fontSize: '0.875rem', fontWeight: 600 }}
                            >
                                {registering ? 'Processing...' : hasEmbedding ? 'Re-Register Face' : 'Capture & Register Face'}
                            </button>
                        </div>

                        <div className="student-profile-card">
                            <div className="student-profile-section-title"><Lock size={14} /> Change Password</div>
                            <form onSubmit={handleChangePw} className="student-profile-form">
                                <div className="student-profile-input-group">
                                    <label>Current Password</label>
                                    <input type="password" className="student-profile-input"
                                        value={pwForm.current_password}
                                        onChange={e => setPwForm(f => ({ ...f, current_password: e.target.value }))} required />
                                </div>
                                <div className="student-profile-input-group">
                                    <label>New Password</label>
                                    <input type="password" className="student-profile-input"
                                        value={pwForm.new_password}
                                        onChange={e => setPwForm(f => ({ ...f, new_password: e.target.value }))} required />
                                </div>
                                <div className="student-profile-input-group">
                                    <label>Confirm New Password</label>
                                    <input type="password" className="student-profile-input"
                                        value={pwForm.confirm_password}
                                        onChange={e => setPwForm(f => ({ ...f, confirm_password: e.target.value }))} required />
                                </div>
                                <button type="submit" className="student-profile-submit" disabled={changing}>
                                    {changing ? 'Changing...' : 'Change Password'}
                                </button>
                            </form>
                        </div>
                    </div>

                    {/* Right column — analytics */}
                    <div className="sp-right">
                        <div className="dash-stats-row" style={{ gridTemplateColumns: 'repeat(2,1fr)' }}>
                            <div className="dash-stat-card">
                                <div className="dash-stat-icon" style={{ background: '#DBEAFE22', color: '#0061a1' }}>
                                    <ClipboardList size={18} />
                                </div>
                                <div className="dash-stat-body">
                                    <div className="dash-stat-value">{totalAssigned}</div>
                                    <div className="dash-stat-label">Assigned</div>
                                </div>
                            </div>
                            <div className="dash-stat-card">
                                <div className="dash-stat-icon" style={{ background: '#05906922', color: '#059669' }}>
                                    <CheckCircle2 size={18} />
                                </div>
                                <div className="dash-stat-body">
                                    <div className="dash-stat-value">{completedExams.length}</div>
                                    <div className="dash-stat-label">Completed</div>
                                </div>
                            </div>
                            <div className="dash-stat-card">
                                <div className="dash-stat-icon" style={{ background: '#D9770622', color: '#D97706' }}>
                                    <TrendingUp size={18} />
                                </div>
                                <div className="dash-stat-body">
                                    <div className="dash-stat-value">{avgPct !== null ? `${avgPct}%` : '—'}</div>
                                    <div className="dash-stat-label">Avg Score</div>
                                </div>
                            </div>
                            <div className="dash-stat-card">
                                <div className="dash-stat-icon" style={{ background: '#7C3AED22', color: '#7C3AED' }}>
                                    <BarChart3 size={18} />
                                </div>
                                <div className="dash-stat-body">
                                    <div className="dash-stat-value">{bestPct !== null ? `${bestPct}%` : '—'}</div>
                                    <div className="dash-stat-label">Best Score</div>
                                </div>
                            </div>
                        </div>

                        <div className="dash-card">
                            <div className="dash-card-header">
                                <BarChart3 size={15} /> Score History
                            </div>
                            {loadingExams ? (
                                <div className="dash-empty-chart">Loading...</div>
                            ) : chartData.length === 0 ? (
                                <div className="dash-empty-chart">No completed exams yet</div>
                            ) : (
                                <ResponsiveContainer width="100%" height={180}>
                                    <BarChart data={chartData} barSize={28} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                                        <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6B7280' }} axisLine={false} tickLine={false} />
                                        <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fontSize: 10, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                                        <Tooltip content={<ChartTooltip />} cursor={{ fill: '#F3F4F6' }} />
                                        <Bar dataKey="pct" name="Score %" radius={[4, 4, 0, 0]}>
                                            {chartData.map((entry, i) => (
                                                <Cell key={i} fill={entry.pct >= 60 ? '#0061a1' : '#BFDBFE'} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                            {chartData.length > 0 && (
                                <div className="dash-legend-row">
                                    <div className="dash-legend-item">
                                        <span className="dash-legend-dot" style={{ background: '#0061a1' }} /> Pass (60%+)
                                    </div>
                                    <div className="dash-legend-item">
                                        <span className="dash-legend-dot" style={{ background: '#BFDBFE' }} /> Below 60%
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="dash-card">
                            <div className="dash-card-header">
                                <ClipboardList size={15} /> Exam History
                            </div>
                            {completedExams.length === 0 ? (
                                <div className="dash-empty-chart" style={{ height: 80 }}>No submitted exams yet</div>
                            ) : (
                                <table className="dash-table">
                                    <thead>
                                        <tr>
                                            <th>Exam</th>
                                            <th>Subject</th>
                                            <th>Score</th>
                                            <th>%</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {completedExams.map(e => {
                                            const pct = Math.round((e.score / e.total_questions) * 100);
                                            const pass = pct >= 60;
                                            return (
                                                <tr key={e.id}>
                                                    <td style={{ fontWeight: 500, color: '#111827' }}>{e.title}</td>
                                                    <td className="dash-cell-muted">{e.subject_name || '—'}</td>
                                                    <td className="dash-cell-muted">{e.score}/{e.total_questions}</td>
                                                    <td>
                                                        <span className="dash-status-badge" style={{
                                                            background: pass ? '#D1FAE5' : '#FEE2E2',
                                                            color: pass ? '#065F46' : '#991B1B',
                                                        }}>{pct}%</span>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default StudentProfile;
