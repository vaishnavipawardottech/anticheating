import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useSelector } from 'react-redux'
import Layout from './Layout'
import Profile from './pages/Profile'
import CreateExam from './pages/CreateExam'
import AllExams from './pages/AllExams'
import ViewExam from './pages/ViewExam'
import ChangePassword from './pages/ChangePassword'
import Login from './pages/Login'
import IngestDocument from './pages/IngestDocument'
import SubjectsList from './pages/SubjectsList'
import SubjectDetail from './pages/SubjectDetail'
import VectorsExplorer from './pages/VectorsExplorer'
import GenerateMCQExam from './pages/GenerateMCQExam'
import GenerateSubjectiveExam from './pages/GenerateSubjectiveExam'
import ViewPaper from './pages/ViewPaper'
import AllPapers from './pages/AllPapers'
import MCQPapers from './pages/MCQPapers'
import SubjectivePapers from './pages/SubjectivePapers'
import Teachers from './pages/Teachers'

// MCQ Examination System (teacher)
import McqPoolList from './pages/McqPoolList'
import McqPoolGenerate from './pages/McqPoolGenerate'
import McqExamList from './pages/McqExamList'
import McqExamCreate from './pages/McqExamCreate'
import McqExamDetail from './pages/McqExamDetail'
import StudentsList from './pages/StudentsList'

import Dashboard from './pages/Dashboard'

// Student pages
import StudentLogin from './pages/StudentLogin'
import StudentExamList from './pages/StudentExamList'
import StudentExamTake from './pages/StudentExamTake'
import StudentProfile from './pages/StudentProfile'
import StudentExamResult from './pages/StudentExamResult'

import './App.css'

// Redirects unauthenticated users to /login
function PrivateRoute({ children }) {
  const isAuthenticated = useSelector((state) => state.auth.isAuthenticated)
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />

        {/* Student routes (separate auth) */}
        <Route path="/student/login" element={<StudentLogin />} />
        <Route path="/student/exams" element={<StudentExamList />} />
        <Route path="/student/exams/:examId/take" element={<StudentExamTake />} />
        <Route path="/student/exams/:examId/result" element={<StudentExamResult />} />
        <Route path="/student/profile" element={<StudentProfile />} />

        <Route path="/*" element={
          <PrivateRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                {/* Profile */}
                <Route path="/profile" element={<Profile />} />
                <Route path="/profile/change-password" element={<ChangePassword />} />

                {/* Document Ingestion */}
                <Route path="/ingest" element={<IngestDocument />} />
                <Route path="/subjects" element={<SubjectsList />} />
                <Route path="/subjects/:subjectId" element={<SubjectDetail />} />
                <Route path="/vectors" element={<VectorsExplorer />} />

                {/* Exam Generation */}
                <Route path="/generate-mcq" element={<GenerateMCQExam />} />
                <Route path="/generate-subjective" element={<GenerateSubjectiveExam />} />
                <Route path="/papers" element={<AllPapers />} />
                <Route path="/papers/mcq" element={<MCQPapers />} />
                <Route path="/papers/subjective" element={<SubjectivePapers />} />
                <Route path="/papers/:paperId" element={<ViewPaper />} />

                {/* MCQ Examination System */}
                <Route path="/mcq-pool" element={<McqPoolList />} />
                <Route path="/mcq-pool/generate" element={<McqPoolGenerate />} />
                <Route path="/mcq-exams" element={<McqExamList />} />
                <Route path="/mcq-exams/create" element={<McqExamCreate />} />
                <Route path="/mcq-exams/:examId" element={<McqExamDetail />} />
                <Route path="/students" element={<StudentsList />} />

                {/* Teachers (admin) */}
                <Route path="/users" element={<Teachers />} />

                {/* Old Exam System (deprecated, keeping for reference) */}
                <Route path="/exams" element={<AllExams />} />
                <Route path="/exams/create" element={<CreateExam />} />
                <Route path="/exams/:examId" element={<ViewExam />} />
              </Routes>
            </Layout>
          </PrivateRoute>
        } />
      </Routes>
    </Router>
  )
}

export default App
