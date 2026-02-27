import React, { useState, useEffect } from 'react';
import { Database, Plus, Filter, Trash2, Edit3, BookOpen } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';
import './McqPoolList.css';

const BLOOMS_LEVELS = ['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'];
const DIFFICULTIES = ['easy', 'medium', 'hard'];
const BLOOMS_COLORS = {
  remember: { bg: '#DBEAFE', text: '#1E40AF' },
  understand: { bg: '#D1FAE5', text: '#065F46' },
  apply: { bg: '#FEF3C7', text: '#92400E' },
  analyze: { bg: '#EDE9FE', text: '#5B21B6' },
  evaluate: { bg: '#FCE7F3', text: '#9D174D' },
  create: { bg: '#FFEDD5', text: '#9A3412' },
};
const DIFF_COLORS = {
  easy: { bg: '#D1FAE5', text: '#065F46' },
  medium: { bg: '#FEF3C7', text: '#92400E' },
  hard: { bg: '#FEE2E2', text: '#991B1B' },
};

const McqPoolList = () => {
  const navigate = useNavigate();
  const [questions, setQuestions] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [subjects, setSubjects] = useState([]);
  const [units, setUnits] = useState([]);
  const [filters, setFilters] = useState({ subject_id: '', unit_id: '', blooms_level: '', difficulty: '' });
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  useEffect(() => {
    authFetch('/subjects').then(r => r.json()).then(setSubjects).catch(() => { });
  }, []);

  useEffect(() => {
    if (filters.subject_id) {
      authFetch(`/units/subject/${filters.subject_id}`).then(r => r.json()).then(setUnits).catch(() => setUnits([]));
    } else { setUnits([]); }
  }, [filters.subject_id]);

  const fetchQuestions = () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filters.subject_id) params.append('subject_id', filters.subject_id);
    if (filters.unit_id) params.append('unit_id', filters.unit_id);
    if (filters.blooms_level) params.append('blooms_level', filters.blooms_level);
    if (filters.difficulty) params.append('difficulty', filters.difficulty);
    params.append('limit', '100');

    authFetch(`/mcq-pool/?${params}`).then(r => r.json()).then(data => {
      setQuestions(data.questions || []);
      setTotal(data.total || 0);
      setLoading(false);
    }).catch(() => setLoading(false));
  };

  useEffect(() => { fetchQuestions(); }, [filters]);

  const handleDelete = async (id) => {
    if (!confirm('Delete this question?')) return;
    const res = await authFetch(`/mcq-pool/${id}`, { method: 'DELETE' });
    if (res.ok) { toast.success('Question deleted'); fetchQuestions(); }
    else toast.error('Failed to delete');
  };

  const startEdit = (q) => {
    setEditingId(q.id);
    setEditForm({
      question_text: q.question_text,
      correct_answer: q.correct_answer,
      explanation: q.explanation || '',
      blooms_level: q.blooms_level || '',
      difficulty: q.difficulty || '',
      options: q.options ? q.options.map(o => ({ label: o.label, text: o.text })) : [
        { label: 'A', text: '' }, { label: 'B', text: '' },
        { label: 'C', text: '' }, { label: 'D', text: '' },
      ],
    });
  };

  const updateOption = (idx, text) => {
    setEditForm(f => ({
      ...f,
      options: f.options.map((o, i) => i === idx ? { ...o, text } : o),
    }));
  };

  const saveEdit = async (id) => {
    const res = await authFetch(`/mcq-pool/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editForm),
    });
    if (res.ok) { toast.success('Updated'); setEditingId(null); fetchQuestions(); }
    else toast.error('Update failed');
  };

  return (
    <div className="pool-list-container">
      <div className="pool-list-card">
        <div className="pool-list-header">
          <Database size={20} style={{ color: '#0061a1' }} />
          <div className="pool-list-header-info">
            <h1>MCQ Question Pool</h1>
            <p>{total} questions in pool</p>
          </div>
          <button className="pool-list-gen-btn" onClick={() => navigate('/mcq-pool/generate')}>
            <Plus size={16} /> Generate MCQs
          </button>
        </div>

        {/* Filters */}
        <div className="pool-list-filters">
          <Filter size={16} style={{ color: '#6B7280' }} />
          <select className="pool-list-filter-select" value={filters.subject_id}
            onChange={e => setFilters(f => ({ ...f, subject_id: e.target.value, unit_id: '' }))}>
            <option value="">All Subjects</option>
            {subjects.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select className="pool-list-filter-select" value={filters.unit_id}
            onChange={e => setFilters(f => ({ ...f, unit_id: e.target.value }))} disabled={!filters.subject_id}>
            <option value="">All Units</option>
            {units.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <select className="pool-list-filter-select" value={filters.blooms_level}
            onChange={e => setFilters(f => ({ ...f, blooms_level: e.target.value }))}>
            <option value="">All Bloom's</option>
            {BLOOMS_LEVELS.map(b => <option key={b} value={b}>{b.charAt(0).toUpperCase() + b.slice(1)}</option>)}
          </select>
          <select className="pool-list-filter-select" value={filters.difficulty}
            onChange={e => setFilters(f => ({ ...f, difficulty: e.target.value }))}>
            <option value="">All Difficulty</option>
            {DIFFICULTIES.map(d => <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>)}
          </select>
        </div>

        {/* Content */}
        <div className="pool-list-content">
          {loading ? (
            <div className="pool-list-empty">Loading…</div>
          ) : questions.length === 0 ? (
            <div className="pool-list-empty">
              <BookOpen size={32} style={{ color: '#D1D5DB', marginBottom: '0.5rem' }} />
              <p>No questions found. Generate or add MCQs to get started.</p>
            </div>
          ) : (
            questions.map(q => (
              editingId === q.id ? (
                <div key={q.id} className="pool-list-edit-form">
                  <textarea className="pool-list-edit-textarea" rows={2} value={editForm.question_text}
                    onChange={e => setEditForm(f => ({ ...f, question_text: e.target.value }))}
                    placeholder="Question text" />
                  {/* Option editing */}
                  <div className="pool-list-edit-options">
                    {editForm.options?.map((opt, idx) => (
                      <div key={opt.label} className="pool-list-edit-opt-row">
                        <span className={`pool-list-edit-opt-label ${opt.label === editForm.correct_answer ? 'correct' : ''}`}>
                          {opt.label}.
                        </span>
                        <input type="text" className="pool-list-edit-opt-input" value={opt.text}
                          onChange={e => updateOption(idx, e.target.value)}
                          placeholder={`Option ${opt.label}`} />
                      </div>
                    ))}
                  </div>
                  <div className="pool-list-edit-row">
                    <select className="pool-list-filter-select" value={editForm.correct_answer}
                      onChange={e => setEditForm(f => ({ ...f, correct_answer: e.target.value }))}>
                      {['A', 'B', 'C', 'D'].map(l => <option key={l} value={l}>Correct: {l}</option>)}
                    </select>
                    <select className="pool-list-filter-select" value={editForm.blooms_level}
                      onChange={e => setEditForm(f => ({ ...f, blooms_level: e.target.value }))}>
                      <option value="">Bloom's</option>
                      {BLOOMS_LEVELS.map(b => <option key={b} value={b}>{b}</option>)}
                    </select>
                    <select className="pool-list-filter-select" value={editForm.difficulty}
                      onChange={e => setEditForm(f => ({ ...f, difficulty: e.target.value }))}>
                      <option value="">Difficulty</option>
                      {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                  <div className="pool-list-edit-actions">
                    <button className="pool-list-save-btn" onClick={() => saveEdit(q.id)}>Save</button>
                    <button className="pool-list-cancel-btn" onClick={() => setEditingId(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div key={q.id} className="pool-list-item">
                  <div className="pool-list-item-info">
                    <p className="pool-list-q-text">{q.question_text}</p>
                    <div className="pool-list-options">
                      {q.options?.map(opt => (
                        <span key={opt.label}
                          className={`pool-list-opt ${opt.label === q.correct_answer ? 'correct' : 'wrong'}`}>
                          <span className="opt-label">{opt.label}.</span>
                          <span>{opt.text}</span>
                        </span>
                      ))}
                    </div>
                    <div className="pool-list-tags">
                      {q.unit_name && <span className="pool-list-tag" style={{ background: '#EFF6FF', color: '#0061a1' }}>{q.unit_name}</span>}
                      {q.blooms_level && <span className="pool-list-tag" style={{ background: BLOOMS_COLORS[q.blooms_level]?.bg, color: BLOOMS_COLORS[q.blooms_level]?.text }}>{q.blooms_level}</span>}
                      {q.difficulty && <span className="pool-list-tag" style={{ background: DIFF_COLORS[q.difficulty]?.bg, color: DIFF_COLORS[q.difficulty]?.text }}>{q.difficulty}</span>}
                    </div>
                  </div>
                  <div className="pool-list-actions">
                    <button className="pool-list-icon-btn edit" onClick={() => startEdit(q)}><Edit3 size={14} /></button>
                    <button className="pool-list-icon-btn delete" onClick={() => handleDelete(q.id)}><Trash2 size={14} /></button>
                  </div>
                </div>
              )
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default McqPoolList;
