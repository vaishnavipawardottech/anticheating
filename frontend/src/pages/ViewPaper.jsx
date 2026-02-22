import React, { useState, useEffect, useCallback } from 'react';
import {
    ArrowLeft, Download, Printer, ChevronDown, ChevronUp,
    Tag, BookOpen, Edit3, RefreshCw, Check, X, CheckCircle2,
    AlertCircle, Loader2, Lock, Share2, Users
} from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { toast } from 'react-toastify';
import { authFetch } from '../utils/api';
import './ViewPaper.css';

const API = 'http://localhost:8001';

const BLOOM_COLORS = {
    remember: '#6B7280', understand: '#2563EB', apply: '#7C3AED',
    analyze: '#D97706', evaluate: '#DC2626', create: '#059669',
};

// ─── Marking scheme mini-editor ──────────────────────────────────────────────

const SchemeEditor = ({ scheme, onChange }) => {
    const update = (i, field, val) => {
        const next = scheme.map((p, idx) =>
            idx === i ? { ...p, [field]: field === 'marks' ? parseInt(val) || 0 : val } : p
        );
        onChange(next);
    };
    const remove = (i) => onChange(scheme.filter((_, idx) => idx !== i));
    const add = () => onChange([...scheme, { point: '', marks: 1 }]);
    const total = scheme.reduce((s, p) => s + (p.marks || 0), 0);

    return (
        <div className="scheme-editor">
            {scheme.map((p, i) => (
                <div key={i} className="scheme-edit-row">
                    <input
                        className="scheme-point-input"
                        value={p.point}
                        onChange={e => update(i, 'point', e.target.value)}
                        placeholder="Marking point…"
                    />
                    <input
                        className="scheme-marks-input"
                        type="number"
                        min={0}
                        value={p.marks}
                        onChange={e => update(i, 'marks', e.target.value)}
                    />
                    <button className="scheme-remove-btn" onClick={() => remove(i)} title="Remove">
                        <X size={12} />
                    </button>
                </div>
            ))}
            <div className="scheme-editor-footer">
                <button className="scheme-add-btn" onClick={add}>+ Add point</button>
                <span className={`scheme-total ${total > 0 ? '' : 'scheme-total-warning'}`}>
                    Total: {total}M
                </span>
            </div>
        </div>
    );
};

// ─── Single question/variant card ─────────────────────────────────────────────

const QuestionCard = ({
    variant, sectionIndex, variantIndex,
    approved, onApprove, onReject,
    paperId, subjectId, sectionData,
    showAnswers, onUpdate,
}) => {
    const q = variant.question;
    const bloomColor = BLOOM_COLORS[q.bloom_level] || '#6B7280';

    const [mode, setMode] = useState('view'); // 'view' | 'edit'
    const [schemeOpen, setSchemeOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [regenerating, setRegenerating] = useState(false);
    const [error, setError] = useState('');

    // Edit state
    const [editText, setEditText] = useState(q.question_text);
    const [editAnswer, setEditAnswer] = useState(q.answer_key || '');
    const [editScheme, setEditScheme] = useState(
        (q.marking_scheme || []).map(p => ({ point: p.point || '', marks: p.marks || 0 }))
    );

    // Sync if question changes (e.g. after regenerate)
    useEffect(() => {
        setEditText(q.question_text);
        setEditAnswer(q.answer_key || '');
        setEditScheme((q.marking_scheme || []).map(p => ({ point: p.point || '', marks: p.marks || 0 })));
    }, [q]);

    const handleSave = async () => {
        setSaving(true);
        setError('');
        try {
            const res = await authFetch(`/generation/papers/${paperId}/question`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    section_index: sectionIndex,
                    variant_index: variantIndex,
                    question_text: editText,
                    answer_key: editAnswer,
                    marking_scheme: editScheme,
                }),
            });
            if (!res.ok) throw new Error('Save failed');
            onUpdate({ question_text: editText, answer_key: editAnswer, marking_scheme: editScheme, human_edited: true });
            setMode('view');
        } catch (e) {
            setError(e.message);
        } finally {
            setSaving(false);
        }
    };

    const handleRegenerate = async () => {
        setRegenerating(true);
        setError('');
        try {
            const res = await authFetch(`/generation/papers/${paperId}/regenerate-question`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    section_index: sectionIndex,
                    variant_index: variantIndex,
                    subject_id: subjectId,
                    unit_ids: q.unit_ids || [],
                    marks: q.marks,
                    bloom_targets: [q.bloom_level || 'understand'],
                    difficulty: q.difficulty || 'medium',
                    nature: sectionData?.nature || null,
                    question_type: q.question_type || 'descriptive',
                }),
            });
            if (!res.ok) throw new Error('Regeneration failed');
            const data = await res.json();
            onUpdate(data.question);
            setMode('view');
        } catch (e) {
            setError(e.message);
        } finally {
            setRegenerating(false);
        }
    };

    const isApproved = approved === true;
    const isRejected = approved === false;

    return (
        <div className={`question-block ${isApproved ? 'approved' : isRejected ? 'rejected' : ''}`}>

            {/* ── Top: Badges row + Action buttons (same line) ── */}
            <div className="question-meta">
                <div className="question-badges">
                    <span className="bloom-badge" style={{ background: `${bloomColor}18`, color: bloomColor }}>
                        {q.bloom_level}
                    </span>
                    <span className={`diff-badge diff-${q.difficulty}`}>{q.difficulty}</span>
                    {q.question_type === 'mcq' && <span className="type-badge type-mcq">MCQ</span>}
                    {q.human_edited && <span className="edited-badge">✏ Edited</span>}
                    {isApproved && <span className="approved-badge"><CheckCircle2 size={12} /> Approved</span>}
                </div>

                {/* ── HiTL action buttons ── */}
                <div className="hitl-actions">
                    {mode === 'view' ? (
                        <>
                            <button
                                className="hitl-btn edit-btn"
                                onClick={() => setMode('edit')}
                                title="Edit question"
                                disabled={regenerating}
                            >
                                <Edit3 size={14} /> Edit
                            </button>
                            <button
                                className="hitl-btn regen-btn"
                                onClick={handleRegenerate}
                                disabled={regenerating || saving}
                                title="Regenerate this question"
                            >
                                {regenerating ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
                                {regenerating ? 'Regenerating…' : 'Regenerate'}
                            </button>
                            <button
                                className={`hitl-btn approve-btn ${isApproved ? 'active' : ''}`}
                                onClick={() => onApprove(sectionIndex, variantIndex)}
                                title="Approve"
                                disabled={isApproved}
                            >
                                <Check size={14} />
                            </button>
                            <button
                                className={`hitl-btn reject-btn ${isRejected ? 'active' : ''}`}
                                onClick={() => onReject(sectionIndex, variantIndex)}
                                title="Reject / flag"
                            >
                                <X size={14} />
                            </button>
                        </>
                    ) : (
                        <>
                            <button className="hitl-btn save-btn" onClick={handleSave} disabled={saving}>
                                {saving ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
                                {saving ? 'Saving…' : 'Save'}
                            </button>
                            <button className="hitl-btn cancel-btn" onClick={() => { setMode('view'); setError(''); }}>
                                <X size={14} /> Cancel
                            </button>
                        </>
                    )}
                </div>
            </div>

            {/* ── Error ── */}
            {error && (
                <div className="inline-error">
                    <AlertCircle size={13} /> {error}
                </div>
            )}

            {/* ── Question text ── */}
            {mode === 'edit' ? (
                <textarea
                    className="edit-textarea"
                    rows={5}
                    value={editText}
                    onChange={e => setEditText(e.target.value)}
                />
            ) : (
                <p className={`question-text ${isRejected ? 'rejected-text' : ''}`} style={{ whiteSpace: 'pre-wrap' }}>
                    {q.question_text || <span style={{ color: '#9CA3AF', fontStyle: 'italic' }}>No question text available.</span>}
                </p>
            )}

            {/* ── Answers / scheme ── */}
            {(showAnswers || mode === 'edit') && (
                <div className="answer-section">

                    {/* ── MCQ options ── */}
                    {q.question_type === 'mcq' && q.options && q.options.length > 0 ? (
                        <div className="mcq-options">
                            {q.options.map(opt => {
                                const isCorrect = opt.label === q.answer_key;
                                return (
                                    <div
                                        key={opt.label}
                                        className={`mcq-option ${isCorrect ? 'mcq-option-correct' : ''}`}
                                    >
                                        <span className={`mcq-label ${isCorrect ? 'mcq-label-correct' : ''}`}>
                                            {opt.label}
                                        </span>
                                        <span className="mcq-text">{opt.text}</span>
                                        {isCorrect && <Check size={14} className="mcq-check" />}
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        /* ── Descriptive answer key ── */
                        <div className="answer-key">
                            <strong>Model Answer:</strong>
                            {mode === 'edit' ? (
                                <textarea
                                    className="edit-answer-textarea"
                                    rows={3}
                                    value={editAnswer}
                                    onChange={e => setEditAnswer(e.target.value)}
                                    placeholder="Model answer…"
                                />
                            ) : (
                                <p style={{ whiteSpace: 'pre-wrap' }}>{q.answer_key}</p>
                            )}
                        </div>
                    )}

                    {/* Marking scheme — descriptive only */}
                    {q.question_type !== 'mcq' && (
                        mode === 'edit' ? (
                            <div className="marking-scheme">
                                <div className="scheme-header">
                                    <BookOpen size={14} /> Marking Scheme
                                </div>
                                <SchemeEditor scheme={editScheme} onChange={setEditScheme} />
                            </div>
                        ) : (
                            q.marking_scheme && q.marking_scheme.length > 0 && (
                                <div className="marking-scheme">
                                    <button className="scheme-toggle" onClick={() => setSchemeOpen(o => !o)}>
                                        <BookOpen size={14} />
                                        Marking Scheme ({q.marks} marks)
                                        {schemeOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                                    </button>
                                    {schemeOpen && (
                                        <div className="scheme-rows">
                                            {q.marking_scheme.map((p, i) => (
                                                <div key={i} className="scheme-row">
                                                    <span className="scheme-point">{p.point}</span>
                                                    <span className="scheme-marks">{p.marks}M</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )
                        )
                    )}
                </div>
            )}
        </div>
    );
};

// ─── Share Modal ─────────────────────────────────────────────────────────────

const ShareModal = ({ paperId, onClose }) => {
    const [teachers, setTeachers] = useState([]);
    const [loadingTeachers, setLoadingTeachers] = useState(true);
    const [selectedEmail, setSelectedEmail] = useState('');
    const [sharing, setSharing] = useState(false);
    const currentTeacher = useSelector((state) => state.auth.teacher);

    useEffect(() => {
        authFetch('/auth/teachers')
            .then(r => r.ok ? r.json() : [])
            .then(data => {
                setTeachers(data.filter(t => t.email !== currentTeacher?.email));
                setLoadingTeachers(false);
            })
            .catch(() => setLoadingTeachers(false));
    }, [currentTeacher]);

    const handleShare = async () => {
        if (!selectedEmail) return;
        setSharing(true);
        try {
            const res = await authFetch(`/generation/papers/${paperId}/share`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ shared_with_email: selectedEmail }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || 'Failed to share paper');
            } else {
                const data = await res.json();
                toast.success(`Paper shared with ${data.shared_with}`);
                onClose();
            }
        } catch {
            toast.error('Unable to share paper. Please try again.');
        } finally {
            setSharing(false);
        }
    };

    return (
        <div
            className="share-modal-overlay"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div className="share-modal">
                <div className="share-modal-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Users size={18} style={{ color: '#0061a1' }} />
                        <h3 className="share-modal-title">Share Paper</h3>
                    </div>
                    <button className="share-modal-close" onClick={onClose}><X size={18} /></button>
                </div>

                <div className="share-modal-body">
                    <p className="share-modal-hint">Select a teacher to share this paper with:</p>
                    {loadingTeachers ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#6B7280', padding: '0.5rem 0' }}>
                            <Loader2 size={16} className="spin" /> Loading teachers…
                        </div>
                    ) : teachers.length === 0 ? (
                        <p style={{ color: '#6B7280', fontSize: '0.875rem' }}>No other teachers available.</p>
                    ) : (
                        <select
                            className="share-teacher-select"
                            value={selectedEmail}
                            onChange={(e) => setSelectedEmail(e.target.value)}
                        >
                            <option value="">— Select a teacher —</option>
                            {teachers.map(t => (
                                <option key={t.id} value={t.email}>
                                    {t.full_name} ({t.email})
                                </option>
                            ))}
                        </select>
                    )}
                </div>

                <div className="share-modal-footer">
                    <button className="share-cancel-btn" onClick={onClose}>Cancel</button>
                    <button
                        className="share-confirm-btn"
                        onClick={handleShare}
                        disabled={!selectedEmail || sharing}
                    >
                        {sharing ? <><Loader2 size={14} className="spin" /> Sharing…</> : <><Share2 size={14} /> Share</>}
                    </button>
                </div>
            </div>
        </div>
    );
};


// ─── Main ViewPaper ──────────────────────────────────────────────────────────

const ViewPaper = () => {
    const { paperId } = useParams();
    const navigate = useNavigate();
    const [paper, setPaper] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [showAnswers, setShowAnswers] = useState(false);
    const [finalising, setFinalising] = useState(false);
    const [finalised, setFinalised] = useState(false);
    const [showShareModal, setShowShareModal] = useState(false);
    const isAuthenticated = useSelector((state) => state.auth.isAuthenticated);

    // approvals[sectionIdx][variantIdx] = true | false | null
    const [approvals, setApprovals] = useState({});

    useEffect(() => {
        authFetch(`/generation/papers/${paperId}`)
            .then(r => { if (!r.ok) throw new Error('Paper not found'); return r.json(); })
            .then(data => {
                setPaper(data);
                setFinalised(!!data.finalised);
                setLoading(false);
            })
            .catch(e => { setError(e.message); setLoading(false); });
    }, [paperId]);

    const handleApprove = (si, vi) =>
        setApprovals(prev => ({ ...prev, [`${si}-${vi}`]: true }));

    const handleReject = (si, vi) =>
        setApprovals(prev => ({ ...prev, [`${si}-${vi}`]: false }));

    const handleUpdate = useCallback((sectionIndex, variantIndex, newQ) => {
        setPaper(prev => {
            const next = JSON.parse(JSON.stringify(prev));
            next.sections[sectionIndex].variants[variantIndex].question = {
                ...next.sections[sectionIndex].variants[variantIndex].question,
                ...newQ,
            };
            return next;
        });
    }, []);

    const handleFinalise = async () => {
        setFinalising(true);
        try {
            const res = await authFetch(`/generation/papers/${paperId}/finalise`, { method: 'PATCH' });
            if (res.ok) setFinalised(true);
        } catch (e) {
            console.error(e);
        } finally {
            setFinalising(false);
        }
    };

    // Count total approvals needed
    const allVariantKeys = paper
        ? paper.sections.flatMap((s, si) => s.variants.map((_, vi) => `${si}-${vi}`))
        : [];
    const approvedCount = allVariantKeys.filter(k => approvals[k] === true).length;
    const rejectedCount = allVariantKeys.filter(k => approvals[k] === false).length;
    const pendingCount = allVariantKeys.length - approvedCount - rejectedCount;
    const allApproved = allVariantKeys.length > 0 && approvedCount === allVariantKeys.length;

    if (loading) return (
        <div className="vp-container">
            <div className="vp-loading"><div className="vp-spinner" /><span>Loading paper…</span></div>
        </div>
    );

    if (error) return (
        <div className="vp-container">
            <div className="vp-error-state"><p>{error}</p>
                <button className="back-btn" onClick={() => navigate('/')}>Go back</button>
            </div>
        </div>
    );

    const meta = paper.generation_metadata || {};

    return (
        <div className="vp-container">
            <div className="vp-card">

                {/* ── Header ── */}
                <div className="vp-header no-print">
                    <div className="vp-header-left">
                        <button className="back-btn" onClick={() => navigate(-1)}><ArrowLeft size={20} /></button>
                        <h1 className="vp-title">
                            {finalised && <Lock size={14} className="finalised-icon" />}
                            Generated Paper #{paperId}
                            {finalised && <span className="finalised-label">Finalised</span>}
                            {paper.paper_type && (
                                <span className={`paper-type-badge ${paper.paper_type}`}>
                                    {paper.paper_type === 'mcq' ? 'MCQ' : 'Subjective'}
                                </span>
                            )}
                        </h1>
                    </div>
                    <div className="vp-header-actions">
                        <button
                            className={`answers-toggle ${showAnswers ? 'active' : ''}`}
                            onClick={() => setShowAnswers(o => !o)}
                        >
                            {showAnswers ? 'Hide Answers' : 'Show Answers & Scheme'}
                        </button>

                        {isAuthenticated && (
                            <button
                                className="share-paper-btn no-print"
                                onClick={() => setShowShareModal(true)}
                                title="Share this paper with another teacher"
                            >
                                <Share2 size={15} /> Share
                            </button>
                        )}
                        
                        {/* PDF Export Buttons (authFetch so token is sent) */}
                        <button 
                            className="export-btn question-paper"
                            onClick={async () => {
                                const res = await authFetch(`/generation/papers/${paperId}/export/question-paper`);
                                if (!res.ok) return;
                                const blob = await res.blob();
                                const url = URL.createObjectURL(blob);
                                window.open(url, '_blank');
                                setTimeout(() => URL.revokeObjectURL(url), 60000);
                            }}
                            title="Download Question Paper (PDF)"
                        >
                            <Download size={16} />
                            Question Paper
                        </button>
                        
                        <button 
                            className="export-btn answer-key"
                            onClick={async () => {
                                const res = await authFetch(`/generation/papers/${paperId}/export/answer-key`);
                                if (!res.ok) return;
                                const blob = await res.blob();
                                const url = URL.createObjectURL(blob);
                                window.open(url, '_blank');
                                setTimeout(() => URL.revokeObjectURL(url), 60000);
                            }}
                            title="Download Answer Key (PDF)"
                        >
                            <Download size={16} />
                            Answer Key
                        </button>
                        
                        <button 
                            className="export-btn marking-scheme"
                            onClick={async () => {
                                const res = await authFetch(`/generation/papers/${paperId}/export/marking-scheme`);
                                if (!res.ok) return;
                                const blob = await res.blob();
                                const url = URL.createObjectURL(blob);
                                window.open(url, '_blank');
                                setTimeout(() => URL.revokeObjectURL(url), 60000);
                            }}
                            title="Download Marking Scheme (PDF)"
                        >
                            <Download size={16} />
                            Marking Scheme
                        </button>
                        
                        <button className="icon-btn" onClick={() => window.print()} title="Print">
                            <Printer size={16} />
                        </button>
                        <button
                            className="icon-btn"
                            title="Export JSON"
                            onClick={() => {
                                const blob = new Blob([JSON.stringify(paper, null, 2)], { type: 'application/json' });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.href = url; a.download = `paper_${paperId}.json`; a.click();
                                URL.revokeObjectURL(url);
                            }}
                        >
                            <Download size={16} />
                        </button>
                    </div>
                </div>

                {/* ── Approval status bar ── */}
                {!finalised && (
                    <div className="approval-bar no-print">
                        <div className="approval-stats">
                            <div className="approval-stat approved-stat">
                                <CheckCircle2 size={14} /> {approvedCount} Approved
                            </div>
                            <div className="approval-stat pending-stat">
                                <AlertCircle size={14} /> {pendingCount} Pending
                            </div>
                            {rejectedCount > 0 && (
                                <div className="approval-stat rejected-stat">
                                    <X size={14} /> {rejectedCount} Flagged
                                </div>
                            )}
                        </div>
                        <button
                            className={`finalise-btn ${allApproved ? 'ready' : ''}`}
                            onClick={handleFinalise}
                            disabled={!allApproved || finalising}
                            title={allApproved ? 'Finalise paper' : 'Approve all questions first'}
                        >
                            {finalising ? <Loader2 size={14} className="spin" /> : <Lock size={14} />}
                            {finalising ? 'Finalising…' : 'Finalise Paper'}
                        </button>
                    </div>
                )}

                {finalised && (
                    <div className="finalised-bar no-print">
                        <CheckCircle2 size={16} />
                        This paper has been reviewed and finalised.
                    </div>
                )}

                {/* ── Info Bar ── */}
                <div className="vp-info-bar no-print">
                    <div className="info-pill"><Tag size={12} /><span>Subject {paper.subject_id}</span></div>
                    <div className="info-pill">Total: {paper.total_marks}M</div>
                    {meta.bloom_distribution && Object.entries(meta.bloom_distribution).map(([bl, cnt]) => (
                        <div key={bl} className="info-pill bloom-pill" style={{
                            background: `${BLOOM_COLORS[bl] || '#6B7280'}18`,
                            color: BLOOM_COLORS[bl] || '#6B7280',
                            borderColor: `${BLOOM_COLORS[bl] || '#6B7280'}35`,
                        }}>
                            {bl}: {cnt}
                        </div>
                    ))}
                </div>

                {/* ── Sections ── */}
                <div className="vp-body">
                    {(paper.sections || []).map((section, si) => (
                        <div key={si} className="section-block">
                            <div className="section-header">
                                <span className="section-label">
                                    {section.variants.length > 1
                                        ? `Q${section.variants.map(v => v.variant_label.replace('Q', '')).join(' OR Q')}`
                                        : `Q${section.question_no}`}
                                </span>
                                <span className="section-marks">{section.marks} Marks</span>
                                {section.co_mapped && <span className="section-co">{section.co_mapped}</span>}
                            </div>

                            {section.variants.length > 1 && (
                                <div className="or-divider-hint">Answer any ONE of the following:</div>
                            )}

                            {section.variants.map((variant, vi) => (
                                <React.Fragment key={vi}>
                                    {vi > 0 && <div className="or-separator"><span>OR</span></div>}
                                    <QuestionCard
                                        variant={variant}
                                        sectionIndex={si}
                                        variantIndex={vi}
                                        approved={approvals[`${si}-${vi}`] ?? null}
                                        onApprove={handleApprove}
                                        onReject={handleReject}
                                        paperId={paperId}
                                        subjectId={paper.subject_id}
                                        sectionData={section}
                                        showAnswers={showAnswers}
                                        onUpdate={(newQ) => handleUpdate(si, vi, newQ)}
                                    />
                                </React.Fragment>
                            ))}
                        </div>
                    ))}
                </div>

                <div className="print-footer print-only">
                    <p>Generated Paper #{paperId} · Total Marks: {paper.total_marks}</p>
                </div>
            </div>

            {showShareModal && (
                <ShareModal paperId={paperId} onClose={() => setShowShareModal(false)} />
            )}
        </div>
    );
};

export default ViewPaper;
