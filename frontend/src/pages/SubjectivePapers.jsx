import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    FileText, Zap, ChevronRight, Calendar, Tag, FileSearch,
    Trash2, AlertTriangle, X, CheckCircle, ArrowLeft
} from 'lucide-react';
import { authFetch } from '../utils/api';
import './AllPapers.css';

const API = 'http://localhost:8001';

// ─── Confirm Dialog ───────────────────────────────────────────────────────────
const ConfirmDialog = ({ paperId, onConfirm, onCancel, deleting }) => (
    <div className="dialog-overlay" onClick={onCancel}>
        <div className="dialog-box" onClick={e => e.stopPropagation()}>
            <div className="dialog-icon"><AlertTriangle size={28} /></div>
            <h3 className="dialog-title">Delete Paper #{paperId}?</h3>
            <p className="dialog-body">This will permanently remove the paper and cannot be undone.</p>
            <div className="dialog-actions">
                <button className="dialog-cancel" onClick={onCancel} disabled={deleting}>
                    <X size={14} /> Cancel
                </button>
                <button className="dialog-confirm" onClick={onConfirm} disabled={deleting}>
                    <Trash2 size={14} /> {deleting ? 'Deleting…' : 'Delete'}
                </button>
            </div>
        </div>
    </div>
);

// ─── Main Page ────────────────────────────────────────────────────────────────
const SubjectivePapers = () => {
    const navigate = useNavigate();
    const [papers, setPapers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [subjectFilter, setSubjectFilter] = useState('');
    const [confirmId, setConfirmId] = useState(null);
    const [deleting, setDeleting] = useState(false);

    // ── Fetch ─────────────────────────────────────────────────────────────────
    const fetchPapers = useCallback((filter) => {
        setLoading(true);
        setError('');
        const path = filter
            ? `/generation/papers?subject_id=${encodeURIComponent(filter)}&limit=50`
            : `/generation/papers?limit=50`;

        authFetch(path)
            .then(res => {
                if (!res.ok) throw new Error(`Server error ${res.status}`);
                return res.json();
            })
            .then(data => {
                // Filter only Subjective papers
                const subjectivePapers = Array.isArray(data) ? data.filter(p => p.paper_type === 'subjective') : [];
                setPapers(subjectivePapers);
                setLoading(false);
            })
            .catch(err => {
                setError(err.message);
                setLoading(false);
            });
    }, []);

    useEffect(() => {
        fetchPapers(subjectFilter);
    }, [subjectFilter, fetchPapers]);

    // ── Delete ────────────────────────────────────────────────────────────────
    const handleDelete = async () => {
        setDeleting(true);
        try {
            const res = await authFetch(`/generation/papers/${confirmId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
            setPapers(prev => prev.filter(p => p.paper_id !== confirmId));
            setConfirmId(null);
        } catch (e) {
            setError(e.message);
        } finally {
            setDeleting(false);
        }
    };

    const formatDate = (iso) => {
        if (!iso) return '—';
        try {
            return new Date(iso).toLocaleString('en-IN', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });
        } catch { return iso; }
    };

    return (
        <div className="ap-container">
            {/* ── Confirm Dialog ── */}
            {confirmId !== null && (
                <ConfirmDialog
                    paperId={confirmId}
                    onConfirm={handleDelete}
                    onCancel={() => !deleting && setConfirmId(null)}
                    deleting={deleting}
                />
            )}

            <div className="ap-header">
                <button className="back-btn" onClick={() => navigate('/')} type="button" aria-label="Back">
                    <ArrowLeft size={20} />
                </button>
                <h1 className="ap-title">Subjective Question Papers</h1>
                <button className="ap-generate-btn" onClick={() => navigate('/generate-subjective')}>
                    <Zap size={16} /> Generate Subjective Paper
                </button>
            </div>

            {/* ── Toolbar ── */}
            <div className="ap-toolbar">
                <div className="ap-filter">
                    <Tag size={14} />
                    <input
                        type="number"
                        placeholder="Filter by Subject ID…"
                        value={subjectFilter}
                        onChange={e => setSubjectFilter(e.target.value)}
                        className="ap-filter-input"
                    />
                </div>
                {!loading && !error && (
                    <span className="ap-count">{papers.length} paper{papers.length !== 1 ? 's' : ''}</span>
                )}
            </div>

            {/* ── Body ── */}
            {loading ? (
                <div className="ap-loading">
                    <div className="ap-spinner" />
                    <span>Loading papers…</span>
                </div>
            ) : error ? (
                <div className="ap-error">
                    <AlertTriangle size={18} />
                    <span>{error}</span>
                    <button className="ap-retry-btn" onClick={() => fetchPapers(subjectFilter)}>Retry</button>
                </div>
            ) : papers.length === 0 ? (
                <div className="ap-empty">
                    <FileSearch size={48} className="ap-empty-icon" />
                    <h2>No subjective papers yet</h2>
                    <p>Generate your first subjective question paper to get started.</p>
                    <button className="ap-generate-btn" onClick={() => navigate('/generate-subjective')}>
                        <Zap size={16} /> Generate Subjective Paper
                    </button>
                </div>
            ) : (
                <div className="ap-list">
                    {papers.map((p, idx) => {
                        const id = p.paper_id ?? p.id ?? idx;
                        return (
                            <div key={id} className="ap-card">
                                {/* ── Clickable left area ── */}
                                <div className="ap-card-left" onClick={() => navigate(`/papers/${id}`)}>
                                    <div className="ap-card-id">#{id}</div>
                                    <div className="ap-card-info">
                                        <div className="ap-card-meta">
                                            <span className="ap-badge subject-badge">
                                                <Tag size={11} /> Subject {p.subject_id}
                                            </span>
                                            <span className="ap-badge type-badge subjective">Subjective</span>
                                            <span className="ap-badge marks-badge">{p.total_marks} Marks</span>
                                            <span className="ap-badge sections-badge">
                                                {p.sections_count ?? 0} Question{(p.sections_count ?? 0) !== 1 ? 's' : ''}
                                            </span>
                                            {p.finalised && (
                                                <span className="ap-badge finalised-badge">
                                                    <CheckCircle size={11} /> Finalised
                                                </span>
                                            )}
                                        </div>
                                        <div className="ap-card-date">
                                            <Calendar size={12} />
                                            {formatDate(p.created_at)}
                                        </div>
                                    </div>
                                </div>

                                {/* ── Right actions ── */}
                                <div className="ap-card-right">
                                    <button
                                        className="ap-delete-btn"
                                        title="Delete paper"
                                        onClick={e => { e.stopPropagation(); setConfirmId(id); }}
                                    >
                                        <Trash2 size={15} />
                                    </button>
                                    <ChevronRight
                                        size={18}
                                        className="ap-card-arrow"
                                        onClick={() => navigate(`/papers/${id}`)}
                                    />
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default SubjectivePapers;
