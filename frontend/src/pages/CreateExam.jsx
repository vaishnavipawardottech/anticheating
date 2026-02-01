import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, History } from 'lucide-react';
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

  return (
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
          <p className="history-empty">No previous conversations yet</p>
        </div>
      </div>

      {/* Overlay */}
      {showHistory && <div className="history-overlay" onClick={() => setShowHistory(false)} />}
    </div>
  );
};

export default CreateExam;
