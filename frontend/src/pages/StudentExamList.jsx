import React, { useState, useEffect } from 'react';
import { ClipboardList, Clock, CheckCircle2, Play, Lock, LogOut, BarChart3, User, BookOpen, FileText } from 'lucide-react';
import { toast } from 'react-toastify';
import dayjs from 'dayjs';
import './StudentExamList.css';

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

const STATUS_CONFIG = {
    available: { bg: '#D1FAE5', color: '#065F46', label: 'Available', Icon: Play },
    upcoming: { bg: '#DBEAFE', color: '#1E40AF', label: 'Upcoming', Icon: Clock },
    in_progress: { bg: '#FEF3C7', color: '#92400E', label: 'In Progress', Icon: Clock },
    completed: { bg: '#D1FAE5', color: '#065F46', label: 'Completed', Icon: CheckCircle2 },
    expired: { bg: '#F3F4F6', color: '#6B7280', label: 'Expired', Icon: Lock },
};

const StudentExamList = () => {
    const [exams, setExams] = useState([]);
    const [loading, setLoading] = useState(true);
    const session = getSession();

    useEffect(() => {
        if (!session?.token) { window.location.href = '/student/login'; return; }
        studentFetch('/student/exams/').then(r => {
            if (r.status === 401) { window.location.href = '/student/login'; return []; }
            return r.json();
        }).then(data => {
            setExams(Array.isArray(data) ? data : []);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, []);

    const handleLogout = () => {
        localStorage.removeItem('pareeksha_student_session');
        window.location.href = '/student/login';
    };

    const isExamEnded = (exam) => dayjs().isAfter(dayjs(exam.end_time));

    // Stats
    const completed = exams.filter(e => e.status === 'completed').length;
    const available = exams.filter(e => e.status === 'available' || e.status === 'in_progress').length;
    const upcoming = exams.filter(e => e.status === 'upcoming').length;

    return (
        <div className="student-portal">
            {/* Navigation */}
            <nav className="student-nav">
                <div className="student-nav-left">
                    <div className="student-nav-brand">
                        <BookOpen size={18} /> Pareeksha
                    </div>
                    <div className="student-nav-links">
                        <a href="/student/exams" className="student-nav-link active">
                            <FileText size={14} /> My Exams
                        </a>
                        <a href="/student/profile" className="student-nav-link">
                            <User size={14} /> Profile
                        </a>
                    </div>
                </div>
                <div className="student-nav-right">
                    <a href="/student/profile" className="student-nav-user">
                        <div className="student-nav-avatar">
                            {session?.student?.full_name?.charAt(0) || 'S'}
                        </div>
                        <span className="student-nav-name">{session?.student?.full_name || 'Student'}</span>
                    </a>
                    <button className="student-logout-btn" onClick={handleLogout}>
                        <LogOut size={12} /> Logout
                    </button>
                </div>
            </nav>

            {/* Content */}
            <div className="student-main">
                <div className="student-page-header">
                    <h1>My Exams</h1>
                    <p>{exams.length} exam(s) assigned</p>
                </div>

                {/* Stats */}
                {exams.length > 0 && (
                    <div className="student-stats">
                        <div className="student-stat">
                            <div className="student-stat-value">{available}</div>
                            <div className="student-stat-label">Active</div>
                        </div>
                        <div className="student-stat">
                            <div className="student-stat-value">{completed}</div>
                            <div className="student-stat-label">Completed</div>
                        </div>
                        <div className="student-stat">
                            <div className="student-stat-value">{upcoming}</div>
                            <div className="student-stat-label">Upcoming</div>
                        </div>
                    </div>
                )}

                {loading ? (
                    <div className="student-list-empty"><p>Loading…</p></div>
                ) : exams.length === 0 ? (
                    <div className="student-list-empty">
                        <ClipboardList size={36} style={{ color: '#D1D5DB' }} />
                        <p>No exams assigned to you yet.</p>
                    </div>
                ) : (
                    <div className="student-exam-grid">
                        {exams.map(exam => {
                            const cfg = STATUS_CONFIG[exam.status] || STATUS_CONFIG.expired;
                            const StatusIcon = cfg.Icon;
                            return (
                                <div key={exam.id} className="student-exam-card">
                                    <div className={`student-exam-icon ${exam.status}`}>
                                        <StatusIcon size={20} />
                                    </div>
                                    <div className="student-exam-body">
                                        <div className="student-exam-top">
                                            <span className="student-exam-title">{exam.title}</span>
                                            <span className="student-status-badge" style={{ background: cfg.bg, color: cfg.color }}>
                                                {cfg.label}
                                            </span>
                                        </div>
                                        <div className="student-exam-details">
                                            <span>{exam.subject_name}</span>
                                            <span><Clock size={12} /> {exam.duration_minutes} min</span>
                                            <span>{exam.total_questions} Qs</span>
                                            <span>{dayjs(exam.start_time).format('MMM D, HH:mm')}</span>
                                        </div>
                                    </div>
                                    <div className="student-exam-action">
                                        {/* Available */}
                                        {exam.status === 'available' && (
                                            <a href={`/student/exams/${exam.id}/take`} className="student-action-btn primary">
                                                <Play size={14} /> Start
                                            </a>
                                        )}
                                        {/* In Progress & not ended */}
                                        {exam.status === 'in_progress' && !isExamEnded(exam) && (
                                            <a href={`/student/exams/${exam.id}/take`} className="student-action-btn primary">
                                                <Play size={14} /> Resume
                                            </a>
                                        )}
                                        {/* In Progress but ended */}
                                        {exam.status === 'in_progress' && isExamEnded(exam) && (
                                            <span className="student-expired-label"><Lock size={14} /> Time Expired</span>
                                        )}
                                        {/* Completed with result visible */}
                                        {exam.status === 'completed' && exam.show_result_to_student && (
                                            <a href={`/student/exams/${exam.id}/result`} className="student-action-btn outline">
                                                Result
                                            </a>
                                        )}
                                        {/* Completed, result hidden */}
                                        {exam.status === 'completed' && !exam.show_result_to_student && (
                                            <span className="student-completed-label"><CheckCircle2 size={14} /> Submitted</span>
                                        )}
                                        {/* Upcoming */}
                                        {exam.status === 'upcoming' && (
                                            <span className="student-expired-label"><Clock size={14} /> {dayjs(exam.start_time).format('MMM D')}</span>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
};

export default StudentExamList;
