import React, { useState, useEffect } from 'react';
import { ClipboardList, Plus, Calendar, Users, Clock, Trash2, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';
import dayjs from 'dayjs';
import './McqExamList.css';

const McqExamList = () => {
    const navigate = useNavigate();
    const [exams, setExams] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchExams = () => {
        setLoading(true);
        authFetch('/mcq-exams/').then(r => r.json()).then(data => {
            setExams(Array.isArray(data) ? data : []);
            setLoading(false);
        }).catch(() => setLoading(false));
    };

    useEffect(() => { fetchExams(); }, []);

    const handleDelete = async (id) => {
        if (!confirm('Delete this exam?')) return;
        const res = await authFetch(`/mcq-exams/${id}`, { method: 'DELETE' });
        if (res.ok) { toast.success('Exam deleted'); fetchExams(); }
        else toast.error('Failed to delete');
    };

    const getStatus = (exam) => {
        const now = dayjs();
        const start = dayjs(exam.start_time);
        const end = dayjs(exam.end_time);
        if (now.isBefore(start)) return { label: 'Upcoming', color: '#3B82F6', bg: '#DBEAFE' };
        if (now.isAfter(end)) return { label: 'Ended', color: '#6B7280', bg: '#F3F4F6' };
        return { label: 'Live', color: '#059669', bg: '#D1FAE5' };
    };

    return (
        <div className="mcq-list-container">
            <div className="mcq-list-card">
                <div className="mcq-list-header">
                    <ClipboardList size={20} style={{ color: '#0061a1' }} />
                    <div className="mcq-list-header-info">
                        <h1>MCQ Exams</h1>
                        <p>{exams.length} exam(s)</p>
                    </div>
                    <button className="mcq-list-create-btn" onClick={() => navigate('/mcq-exams/create')}>
                        <Plus size={16} /> Create Exam
                    </button>
                </div>

                <div className="mcq-list-content">
                    {loading ? (
                        <div className="mcq-list-empty">Loading…</div>
                    ) : exams.length === 0 ? (
                        <div className="mcq-list-empty">No exams yet. Create your first MCQ exam!</div>
                    ) : (
                        exams.map(exam => {
                            const st = getStatus(exam);
                            return (
                                <div key={exam.id} className="mcq-exam-card">
                                    <div className="mcq-exam-card-info">
                                        <div className="mcq-exam-card-title-row">
                                            <span className="mcq-exam-card-title">{exam.title}</span>
                                            <span className="mcq-status-badge" style={{ background: st.bg, color: st.color }}>{st.label}</span>
                                            <span className="mcq-mode-badge"
                                                style={{
                                                    background: exam.exam_mode === 'dynamic' ? '#EDE9FE' : '#F3F4F6',
                                                    color: exam.exam_mode === 'dynamic' ? '#5B21B6' : '#374151',
                                                }}>{exam.exam_mode}</span>
                                        </div>
                                        <div className="mcq-exam-card-meta">
                                            <span><Calendar size={13} /> {dayjs(exam.start_time).format('MMM D, HH:mm')} – {dayjs(exam.end_time).format('HH:mm')}</span>
                                            <span><Clock size={13} /> {exam.duration_minutes} min</span>
                                            <span>{exam.total_questions} Qs</span>
                                            <span><Users size={13} /> {exam.assignment_count} group(s)</span>
                                        </div>
                                    </div>
                                    <div className="mcq-exam-card-actions">
                                        <button className="mcq-icon-btn view" onClick={() => navigate(`/mcq-exams/${exam.id}`)}>
                                            <Eye size={16} />
                                        </button>
                                        <button className="mcq-icon-btn delete" onClick={() => handleDelete(exam.id)}>
                                            <Trash2 size={16} />
                                        </button>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>
        </div>
    );
};

export default McqExamList;
