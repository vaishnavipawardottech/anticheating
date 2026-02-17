import React from 'react';
import './AllExams.css';

const exams = [
  { id: 1, title: 'Python Programming', date: '2026-01-20', subject: 'Python' },
  { id: 2, title: 'Web Development - HTML', date: '2025-12-31', subject: 'HTML' },
  { id: 3, title: 'MongoDB Database', date: '2026-01-02', subject: 'MongoDB' },
  // Add more static exam data or fetch from backend
];

const AllExams = () => {
  return (
    <div className="all-exams-container">
      <h2>All Exams</h2>
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
  );
};

export default AllExams;
