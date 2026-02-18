import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Eye, Trash2, Plus, Loader2 } from 'lucide-react';
import './AllExams.css';

const API_BASE = 'http://localhost:8001';

const AllExams = () => {
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteId, setDeleteId] = useState(null);
  const navigate = useNavigate();

  const fetchExams = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/exams/list`);
      if (!res.ok) throw new Error(`Failed to fetch exams (${res.status})`);
      const data = await res.json();
      setExams(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchExams(); }, []);

  const handleDelete = async (examId) => {
    try {
      const res = await fetch(`${API_BASE}/exams/${examId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      setExams(prev => prev.filter(e => e.id !== examId));
      setDeleteId(null);
    } catch (err) {
      setError(err.message);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="all-exams-container">
      <div className="all-exams-header">
        <h1>All Exams</h1>
        <button className="create-btn" onClick={() => navigate('/exams/create')}>
          <Plus size={18} /> Create Exam
        </button>
      </div>

      {error && <p className="exams-error">{error}</p>}

      {loading ? (
        <div className="exams-loading">
          <Loader2 size={28} className="spin" />
          <span>Loading exams...</span>
        </div>
      ) : exams.length === 0 ? (
        <div className="exams-empty">
          <FileText size={48} strokeWidth={1} />
          <p>No exams generated yet.</p>
          <button className="create-btn" onClick={() => navigate('/exams/create')}>
            <Plus size={18} /> Create your first exam
          </button>
        </div>
      ) : (
        <div className="exams-grid">
          {exams.map((exam) => (
            <div key={exam.id} className="exam-card" onClick={() => navigate(`/exams/${exam.id}`)}>
              <div className="exam-card-top">
                <span className="exam-subject">{exam.subject_name}</span>
                <span className="exam-date">{formatDate(exam.created_at)}</span>
              </div>
              <h3 className="exam-title">Exam #{exam.id}</h3>
              <div className="exam-stats">
                {exam.question_counts?.mcq > 0 && <span className="stat mcq">{exam.question_counts.mcq} MCQ</span>}
                {exam.question_counts?.short > 0 && <span className="stat short">{exam.question_counts.short} Short</span>}
                {exam.question_counts?.long > 0 && <span className="stat long">{exam.question_counts.long} Long</span>}
                <span className="stat total">{exam.total_questions} total</span>
              </div>
              <div className="exam-card-actions">
                <button className="action-view" onClick={(e) => { e.stopPropagation(); navigate(`/exams/${exam.id}`); }}>
                  <Eye size={16} /> View
                </button>
                <button className="action-delete" onClick={(e) => { e.stopPropagation(); setDeleteId(exam.id); }}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {deleteId && (
        <div className="delete-overlay" onClick={() => setDeleteId(null)}>
          <div className="delete-dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Exam #{deleteId}?</h3>
            <p>This will permanently remove the exam and all its questions.</p>
            <div className="delete-actions">
              <button className="btn-cancel" onClick={() => setDeleteId(null)}>Cancel</button>
              <button className="btn-confirm-delete" onClick={() => handleDelete(deleteId)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AllExams;
