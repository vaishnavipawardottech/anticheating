import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Sparkles, History, Trash2 } from 'lucide-react';
import './CreateExam.css';

const API_BASE = 'http://localhost:8001';

const CreateExam = () => {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Select a subject and units below, set question counts, then click "Generate exam" to create a paper from your ingested content.'
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [chatToDelete, setChatToDelete] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Blueprint state for real /exams/generate
  const [subjects, setSubjects] = useState([]);
  const [units, setUnits] = useState([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState(null);
  const [selectedUnitIds, setSelectedUnitIds] = useState([]);
  const [counts, setCounts] = useState({ mcq: 10, short: 5, long: 2 });
  const [includeAnswerKey, setIncludeAnswerKey] = useState(true);
  const [generateLoading, setGenerateLoading] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [lastExamResult, setLastExamResult] = useState(null);
  const navigate = useNavigate();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    fetch(`${API_BASE}/subjects/`).then(r => r.json()).then(setSubjects).catch(() => setSubjects([]));
  }, []);

  useEffect(() => {
    if (!selectedSubjectId) {
      setUnits([]);
      setSelectedUnitIds([]);
      return;
    }
    fetch(`${API_BASE}/subjects/${selectedSubjectId}/complete`)
      .then(r => r.json())
      .then((data) => {
        const u = data.units || [];
        setUnits(u);
        setSelectedUnitIds(u.map(unit => unit.id));
      })
      .catch(() => setUnits([]));
  }, [selectedSubjectId]);

  const autoResizeTextarea = () => {
    const textarea = inputRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 44 + (1.5 * 16 * 6)) + 'px';
    }
  };

  useEffect(() => {
    autoResizeTextarea();
  }, [inputMessage]);

  const handleGenerateExam = async (e) => {
    e.preventDefault();
    if (!selectedSubjectId) {
      setGenerateError('Please select a subject.');
      return;
    }
    setGenerateLoading(true);
    setGenerateError(null);
    setLastExamResult(null);
    try {
      const res = await fetch(`${API_BASE}/exams/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject_id: selectedSubjectId,
          unit_ids: selectedUnitIds.length ? selectedUnitIds : null,
          concept_ids: null,
          counts: { mcq: counts.mcq, short: counts.short, long: counts.long },
          include_answer_key: includeAnswerKey,
          seed: Math.floor(Math.random() * 0x7fffffff),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail.map(d => d.msg || d.loc).join(', ') : (data.detail || data.message || `Request failed (${res.status})`);
        if (res.status === 404) {
          throw new Error('Exams API not found (404). Restart the backend so /exams/generate is available.');
        }
        throw new Error(msg);
      }
      setLastExamResult(data);
      setMessages(prev => [...prev,
        { role: 'user', content: `Generate exam: ${counts.mcq} MCQ, ${counts.short} short, ${counts.long} long` },
        { role: 'assistant', content: `Exam created! ${data.questions_generated} questions generated. Redirecting...` }
      ]);
      setTimeout(() => navigate(`/exams/${data.exam_id}`), 800);
    } catch (err) {
      setGenerateError(err.message || 'Failed to generate exam.');
      setMessages(prev => [...prev,
        { role: 'assistant', content: `Error: ${err.message}. Ensure you have ingested documents and (optionally) aligned concepts.` }
      ]);
    } finally {
      setGenerateLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim()) return;
    const userMessage = { role: 'user', content: inputMessage };
    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsTyping(true);
    setTimeout(() => {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Use the blueprint form above to generate an exam from your ingested content, or ask me anything about exam creation.'
      }]);
      setIsTyping(false);
    }, 800);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  const handleDeleteClick = (chatTitle) => {
    setChatToDelete(chatTitle);
    setShowDeleteModal(true);
  };

  const handleConfirmDelete = () => {
    // Here you would implement the actual delete logic
    // For now, we'll just close the modal
    console.log(`Deleting chat: ${chatToDelete}`);
    setShowDeleteModal(false);
    setChatToDelete(null);
  };

  const handleCancelDelete = () => {
    setShowDeleteModal(false);
    setChatToDelete(null);
  };

  return (
    <>
      <div className="create-exam-container">
        <div className="create-exam-header">
          <h1>Create Exam</h1>
          <button className="history-btn" onClick={() => setShowHistory(!showHistory)}>
            <History size={20} />
          </button>
        </div>

        <section className="exam-blueprint">
          <h2>Exam Blueprint</h2>
          <div className="blueprint-row">
            <label>Subject</label>
            <select
              value={selectedSubjectId ?? ''}
              onChange={(e) => setSelectedSubjectId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Select subject</option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          {units.length > 0 && (
            <div className="blueprint-row">
              <label>Units</label>
              <div className="unit-multiselect">
                {units.map((u) => (
                  <label key={u.id} className="unit-check">
                    <input
                      type="checkbox"
                      checked={selectedUnitIds.includes(u.id)}
                      onChange={(e) => setSelectedUnitIds(prev => e.target.checked ? [...prev, u.id] : prev.filter(id => id !== u.id))}
                    />
                    {u.name}
                  </label>
                ))}
              </div>
            </div>
          )}
          <div className="blueprint-row counts-row">
            <label>MCQ</label>
            <input type="number" min={0} max={50} value={counts.mcq} onChange={(e) => setCounts(c => ({ ...c, mcq: +e.target.value || 0 }))} />
            <label>Short</label>
            <input type="number" min={0} max={20} value={counts.short} onChange={(e) => setCounts(c => ({ ...c, short: +e.target.value || 0 }))} />
            <label>Long</label>
            <input type="number" min={0} max={10} value={counts.long} onChange={(e) => setCounts(c => ({ ...c, long: +e.target.value || 0 }))} />
          </div>
          <div className="blueprint-row">
            <label className="answer-key-toggle">
              <input type="checkbox" checked={includeAnswerKey} onChange={(e) => setIncludeAnswerKey(e.target.checked)} />
              Include answer key
            </label>
          </div>
          {generateError && <p className="blueprint-error">{generateError}</p>}
          {lastExamResult && <p className="blueprint-success">Exam ID: {lastExamResult.exam_id}, Questions: {lastExamResult.questions_generated}</p>}
          <button type="button" className="generate-exam-btn" onClick={handleGenerateExam} disabled={generateLoading || !selectedSubjectId}>
            {generateLoading ? 'Generating…' : 'Generate exam'}
          </button>
        </section>

        <div className="chat-container">
          <div className="messages-area">
          {messages.map((message, index) => (
            <div key={index} className={`message ${message.role}`}>
              <div className="message-icon">
                {message.role === 'assistant' ? (
                  <Sparkles size={20} />
                ) : (
                  <div className="user-avatar">R</div>
                )}
              </div>
              <div className="message-content">
                <div className="message-text">{message.content}</div>
              </div>
            </div>
          ))}
          
          {isTyping && (
            <div className="message assistant">
              <div className="message-icon">
                <Sparkles size={20} />
              </div>
              <div className="message-content">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSendMessage} className="input-area">
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Describe the exam you want to create... (e.g., 'Create a 10-question MCQ exam on JavaScript basics')"
              rows="1"
              className="message-input"
            />
            <button
              type="submit"
              disabled={!inputMessage.trim() || isTyping}
              className="send-btn"
            >
              <Send size={18} />
            </button>
          </div>
        </form>
      </div>

      {/* History Sidebar */}
      <div className={`history-sidebar ${showHistory ? 'show' : ''}`}>
        <div className="history-header">
          <h2>Chat History</h2>
          <button className="close-history-btn" onClick={() => setShowHistory(false)}>
            ×
          </button>
        </div>
        <div className="history-content">
          <div className="chat-item">
            <div className="chat-item-header">
              <h3>MongoDB Assessment</h3>
              <button className="delete-chat-btn" onClick={() => handleDeleteClick('MongoDB Assessment')}>
                <Trash2 size={16} />
              </button>
            </div>
            <span className="chat-date">2 hours ago</span>
          </div>
          <div className="chat-item">
            <div className="chat-item-header">
              <h3>MySQL Database Quiz</h3>
              <button className="delete-chat-btn" onClick={() => handleDeleteClick('MySQL Database Quiz')}>
                <Trash2 size={16} />
              </button>
            </div>
            <span className="chat-date">Yesterday</span>
          </div>
          <div className="chat-item">
            <div className="chat-item-header">
              <h3>Python Programming Test</h3>
              <button className="delete-chat-btn" onClick={() => handleDeleteClick('Python Programming Test')}>
                <Trash2 size={16} />
              </button>
            </div>
            <span className="chat-date">3 days ago</span>
          </div>
        </div>
      </div>

        {/* Overlay */}
        {showHistory && <div className="history-overlay" onClick={() => setShowHistory(false)} />}
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="delete-modal-overlay" onClick={handleCancelDelete}>
          <div className="delete-modal" onClick={(e) => e.stopPropagation()}>
            <div className="delete-modal-header">
              <h3>Delete Chat</h3>
            </div>
            <div className="delete-modal-body">
              <p>Are you sure you want to delete "{chatToDelete}"?</p>
              <p className="delete-warning">This action cannot be undone.</p>
            </div>
            <div className="delete-modal-footer">
              <button className="delete-modal-cancel" onClick={handleCancelDelete}>
                Cancel
              </button>
              <button className="delete-modal-confirm" onClick={handleConfirmDelete}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default CreateExam;
