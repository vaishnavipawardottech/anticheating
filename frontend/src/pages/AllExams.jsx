import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import './AllExams.css';

const exams = [
  { id: 1, title: 'Python Programming', date: '2026-01-20', subject: 'Python' },
  { id: 2, title: 'Web Development - HTML', date: '2025-12-31', subject: 'HTML' },
  { id: 3, title: 'MongoDB Database', date: '2026-01-02', subject: 'MongoDB' },
  // Add more static exam data or fetch from backend
];

const AllExams = () => {
  const navigate = useNavigate();
  return (
    <div className="all-exams-container">
      <div className="all-exams-card">
        <div className="all-exams-header">
          <button className="back-btn" onClick={() => navigate('/')} type="button" aria-label="Back">
            <ArrowLeft size={20} />
          </button>
          <h1 className="all-exams-title">All Exams</h1>
        </div>
        <div className="all-exams-content">
      <table className="exams-table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Subject</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          {exams.map((exam) => (
            <tr key={exam.id}>
              <td>{exam.title}</td>
              <td>{exam.subject}</td>
              <td>{exam.date}</td>
            </tr>
          ))}
        </tbody>
      </table>
        </div>
      </div>
    </div>
  );
};

export default AllExams;
