import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Layers, FileText, ArrowLeft, Eye, Trash2 } from 'lucide-react';
import './SubjectsList.css';

const SubjectsList = () => {
    const navigate = useNavigate();
    const [subjects, setSubjects] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchSubjects();
    }, []);

    const fetchSubjects = async () => {
        try {
            setLoading(true);
            setError(null);
            const res = await fetch('http://localhost:8001/subjects/with-stats/all');
            const data = await res.json();
            setSubjects(res.ok ? data : []);
            if (!res.ok) setError(data.detail || 'Failed to load subjects');
        } catch (e) {
            setError(e.message || 'Failed to load subjects');
            setSubjects([]);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id, name) => {
        if (!window.confirm(`Delete "${name}"? This will remove all units, concepts, documents and exams for this subject.`)) return;
        setError(null);
        try {
            const res = await fetch(`http://localhost:8001/subjects/${id}`, { method: 'DELETE' });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                const msg = data.detail || `Delete failed (${res.status})`;
                setError(msg);
                return;
            }
            await fetchSubjects();
        } catch (e) {
            setError(e.message || 'Delete failed');
        }
    };

    return (
        <div className="subjects-container">
            <div className="subjects-card">

                <div className="subjects-header">
                    <button className="back-btn" onClick={() => navigate('/dashboard')}>
                        <ArrowLeft size={20} />
                    </button>
                    <h1 className="subjects-title">Subjects</h1>
                </div>

                <div className="subjects-content">
                    {error && <p className="subjects-error">{error}</p>}
                    {loading && <p>Loading...</p>}

                    {!loading && subjects.length === 0 && (
                        <div className="subjects-empty">
                            <BookOpen size={40} />
                            <p>No subjects created yet</p>
                        </div>
                    )}

                    <div className="subjects-list">
                        {subjects.map(subject => (
                            <div key={subject.id} className="subject-item">

                                <div className="subject-info">
                                    <h3>{subject.name}</h3>
                                    <div className="subject-stats">
                                        <span><Layers size={14} /> {subject.unit_count}</span>
                                        <span><FileText size={14} /> {subject.concept_count}</span>
                                        <span><FileText size={14} /> {subject.document_count}</span>
                                    </div>
                                </div>

                                <div className="subject-actions">
                                    <button
                                        className="action-btn primary"
                                        onClick={() => navigate(`/subjects/${subject.id}`)}
                                    >
                                        <Eye size={16} /> View
                                    </button>

                                    <button
                                        className="action-btn neutral"
                                        onClick={() => handleDelete(subject.id, subject.name)}
                                    >
                                        <Trash2 size={16} /> Delete
                                    </button>
                                </div>

                            </div>
                        ))}
                    </div>

                </div>

            </div>
        </div>
    );
};

export default SubjectsList;
