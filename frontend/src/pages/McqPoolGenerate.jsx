import React, { useState, useEffect } from 'react';
import { Sparkles, ArrowLeft, Loader2, CheckCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';
import './McqPoolGenerate.css';

const McqPoolGenerate = () => {
    const navigate = useNavigate();
    const [subjects, setSubjects] = useState([]);
    const [units, setUnits] = useState([]);
    const [subjectId, setSubjectId] = useState('');
    const [selectedUnits, setSelectedUnits] = useState([]);
    const [count, setCount] = useState(10);
    const [difficulty, setDifficulty] = useState('');
    const [bloomsLevel, setBloomsLevel] = useState('');
    const [generating, setGenerating] = useState(false);
    const [result, setResult] = useState(null);

    useEffect(() => {
        authFetch('/subjects').then(r => r.json()).then(setSubjects).catch(() => { });
    }, []);

    useEffect(() => {
        if (subjectId) {
            authFetch(`/units/subject/${subjectId}`).then(r => r.json()).then(setUnits).catch(() => setUnits([]));
            setSelectedUnits([]);
        } else {
            setUnits([]);
        }
    }, [subjectId]);

    const toggleUnit = (uid) => {
        setSelectedUnits(prev => prev.includes(uid) ? prev.filter(id => id !== uid) : [...prev, uid]);
    };

    const handleGenerate = async () => {
        if (!subjectId || selectedUnits.length === 0) {
            toast.error('Select a subject and at least one unit');
            return;
        }
        setGenerating(true);
        setResult(null);
        try {
            const res = await authFetch('/mcq-pool/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subject_id: parseInt(subjectId),
                    unit_ids: selectedUnits,
                    count,
                    difficulty: difficulty || null,
                    blooms_level: bloomsLevel || null,
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || 'Generation failed');
            } else {
                const data = await res.json();
                setResult(data);
                toast.success(`Generated ${data.generated} questions!`);
            }
        } catch {
            toast.error('Network error');
        } finally {
            setGenerating(false);
        }
    };

    return (
        <div className="pool-gen-container">
            <div className="pool-gen-card">
                <div className="pool-gen-header">
                    <button className="back-btn" onClick={() => navigate('/mcq-pool')}>
                        <ArrowLeft size={20} />
                    </button>
                    <Sparkles size={18} style={{ color: '#0061a1' }} />
                    <h1 className="pool-gen-title">Generate MCQ Questions</h1>
                </div>

                <div className="pool-gen-content">
                    <div className="pool-gen-form">
                        <div className="pool-gen-group">
                            <label className="pool-gen-label">Subject *</label>
                            <select className="pool-gen-select" value={subjectId} onChange={e => setSubjectId(e.target.value)}>
                                <option value="">Select subject…</option>
                                {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </select>
                        </div>

                        {units.length > 0 && (
                            <div className="pool-gen-group">
                                <label className="pool-gen-label">Select Units *</label>
                                <div className="pool-gen-units">
                                    {units.map(u => (
                                        <button key={u.id} onClick={() => toggleUnit(u.id)}
                                            className={`pool-gen-unit-btn ${selectedUnits.includes(u.id) ? 'selected' : ''}`}>
                                            {u.name}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="pool-gen-row">
                            <div className="pool-gen-group">
                                <label className="pool-gen-label">Questions per Unit</label>
                                <input type="number" min={1} max={50} value={count}
                                    onChange={e => setCount(parseInt(e.target.value) || 10)} className="pool-gen-input" />
                            </div>
                            <div className="pool-gen-group">
                                <label className="pool-gen-label">Difficulty (optional)</label>
                                <select className="pool-gen-select" value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                                    <option value="">Any</option>
                                    <option value="easy">Easy</option>
                                    <option value="medium">Medium</option>
                                    <option value="hard">Hard</option>
                                </select>
                            </div>
                            <div className="pool-gen-group">
                                <label className="pool-gen-label">Bloom's Level (optional)</label>
                                <select className="pool-gen-select" value={bloomsLevel} onChange={e => setBloomsLevel(e.target.value)}>
                                    <option value="">Any</option>
                                    {['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'].map(b =>
                                        <option key={b} value={b}>{b.charAt(0).toUpperCase() + b.slice(1)}</option>
                                    )}
                                </select>
                            </div>
                        </div>

                        <button className="pool-gen-submit-btn" onClick={handleGenerate}
                            disabled={generating || !subjectId || selectedUnits.length === 0}>
                            {generating ? <><Loader2 size={18} className="animate-spin" /> Generating…</> : <><Sparkles size={18} /> Generate Questions</>}
                        </button>
                    </div>

                    {/* Results */}
                    {result && (
                        <div className="pool-gen-results">
                            <div className="pool-gen-results-header">
                                <CheckCircle2 size={16} style={{ color: '#059669' }} />
                                Generated {result.generated} questions
                            </div>
                            {result.questions?.map((q, i) => (
                                <div key={q.id} className="pool-gen-result-item">
                                    <p className="pool-gen-result-q">{q.question_text}</p>
                                    <div className="pool-gen-result-opts">
                                        {q.options?.map(opt => (
                                            <span key={opt.label}
                                                className={`pool-gen-result-opt ${opt.label === q.correct_answer ? 'correct' : 'wrong'}`}>
                                                {opt.label}. {opt.text}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default McqPoolGenerate;
