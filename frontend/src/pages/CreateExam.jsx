import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, History, Trash2 } from 'lucide-react';
import './CreateExam.css';

const CreateExam = () => {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I\'m your AI assistant. I can help you create exams, generate questions, and customize your assessment. What would you like to create today?'
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [chatToDelete, setChatToDelete] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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

  const handleSendMessage = async (e) => {
    e.preventDefault();
    
    if (!inputMessage.trim()) return;

    const userMessage = {
      role: 'user',
      content: inputMessage
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsTyping(true);

    // Simulate AI response (replace with actual API call)
    setTimeout(() => {
      const aiResponse = {
        role: 'assistant',
        content: 'This is a simulated response. In production, this will connect to your AI backend to generate exams and questions.'
      };
      setMessages(prev => [...prev, aiResponse]);
      setIsTyping(false);
    }, 1500);
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
