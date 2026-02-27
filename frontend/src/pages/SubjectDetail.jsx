import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Layers, FileText, ArrowLeft, Trash2, Upload, Settings, Save } from 'lucide-react';
import './SubjectDetail.css';

const API_BASE = 'http://localhost:8001';

const SubjectDetail = () => {
    const { subjectId } = useParams();
    const navigate = useNavigate();
    const [subject, setSubject] = useState(null);
    const [removingId, setRemovingId] = useState(null);
    const [error, setError] = useState(null);
    const [savingSettings, setSavingSettings] = useState(false);
    const [mathMode, setMathMode] = useState(false);

    const fetchSubject = () => {
        fetch(`${API_BASE}/subjects/${subjectId}/with-documents`)
            .then(res => res.json())
            .then((data) => {
                setSubject(data);
                setMathMode(!!data.math_mode);
            });
    };

    useEffect(() => {
        fetchSubject();
    }, [subjectId]);

    const handleSaveSettings = async () => {
        setError(null);
        setSavingSettings(true);
        try {
            const body = {
                math_mode: mathMode,
                formula_mode: mathMode,
                vision_budget: mathMode ? 10 : null,
            };
            const res = await fetch(`${API_BASE}/subjects/${subjectId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.detail || 'Failed to save settings');
                return;
            }
            setSubject(prev => prev ? { ...prev, ...body } : null);
        } catch (e) {
            setError(e.message || 'Failed to save settings');
        } finally {
            setSavingSettings(false);
        }
    };

    const handleRemoveDocument = async (doc) => {
        if (!window.confirm(`Remove "${doc.filename}"? This will delete the document and its parsed data.`)) return;
        setError(null);
        setRemovingId(doc.id);
        try {
            const res = await fetch(`${API_BASE}/documents/${doc.id}`, { method: 'DELETE' });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.detail || `Remove failed (${res.status})`);
                return;
            }
            setSubject(prev => prev ? {
                ...prev,
                documents: (prev.documents || []).filter(d => d.id !== doc.id),
            } : null);
        } catch (e) {
            setError(e.message || 'Remove failed');
        } finally {
            setRemovingId(null);
        }
    };

    if (!subject) return null;

    return (
        <div className="subject-detail-container">
            <div className="subject-detail-card">

                <div className="subject-detail-header">
                    <button className="back-btn" onClick={() => navigate('/subjects')}>
                        <ArrowLeft size={20} />
                    </button>
                    <h1 className="subject-detail-title">{subject.name}</h1>
                    <button
                        className="add-docs-btn"
                        onClick={() => navigate(`/ingest?subjectId=${subjectId}`)}
                        title="Add more documents to this subject"
                    >
                        <Upload size={16} /> Add Documents
                    </button>
                </div>

                <div className="subject-detail-content">

                    <div className="detail-section subject-settings-section">
                        <h2><Settings size={18} /> Subject settings</h2>
                        {error && <p className="subject-detail-error">{error}</p>}
                        <div className="settings-row">
                            <label className="settings-check">
                                <input
                                    type="checkbox"
                                    checked={mathMode}
                                    onChange={(e) => setMathMode(e.target.checked)}
                                />
                                <span>Math Mode</span>
                            </label>
                            <span className="settings-hint">For math-heavy subjects (e.g. Discrete Mathematics): preserve symbols, extract figures, link to chunks.</span>
                        </div>
                        <button
                            type="button"
                            className="settings-save-btn"
                            onClick={handleSaveSettings}
                            disabled={savingSettings}
                        >
                            {savingSettings ? 'Saving...' : <><Save size={14} /> Save settings</>}
                        </button>
                    </div>

                    <div className="detail-section">
                        <h2><Layers size={18} /> Structure</h2>

                        {subject.units?.map(unit => (
                            <div key={unit.id} className="unit-block">
                                <strong>{unit.name}</strong>
                                <ul>
                                    {unit.concepts?.map(concept => (
                                        <li key={concept.id}>{concept.name}</li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </div>

                    <div className="detail-section">
                        <h2><FileText size={18} /> Documents</h2>
                        {error && <p className="subject-detail-error">{error}</p>}
                        {subject.documents?.map(doc => (
                            <div key={doc.id} className="doc-item">
                                <span>{doc.filename}</span>
                                <button
                                    type="button"
                                    className="action-btn neutral"
                                    onClick={() => handleRemoveDocument(doc)}
                                    disabled={removingId === doc.id}
                                    title="Remove document"
                                >
                                    <Trash2 size={14} /> {removingId === doc.id ? 'Removing…' : 'Remove'}
                                </button>
                            </div>
                        ))}
                    </div>

                </div>

            </div>
        </div>
    );
};

export default SubjectDetail;
