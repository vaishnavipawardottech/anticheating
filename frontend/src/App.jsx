import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './Layout'
import Profile from './pages/Profile'
import CreateExam from './pages/CreateExam'
import AllExams from './pages/AllExams'
import ChangePassword from './pages/ChangePassword'
import Login from './pages/Login'
import IngestDocument from './pages/IngestDocument'
import SubjectsList from './pages/SubjectsList'
import SubjectDetail from './pages/SubjectDetail'
import VectorsExplorer from './pages/VectorsExplorer'
import './App.css'

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={
          <Layout>
            <Routes>
              <Route path="/" element={
                <div className="App">
                  <h1>Smart Assessment</h1>
                  <p>Question Paper and MCQ Exam Generator</p>
                </div>
              } />
              <Route path="/profile" element={<Profile />} />
              <Route path="/profile/change-password" element={<ChangePassword />} />
              <Route path="/exams" element={<AllExams />} />
              <Route path="/exams/create" element={<CreateExam />} />
              <Route path="/ingest" element={<IngestDocument />} />
              <Route path="/subjects" element={<SubjectsList />} />
              <Route path="/subjects/:subjectId" element={<SubjectDetail />} />
              <Route path="/vectors" element={<VectorsExplorer />} />
            </Routes>
          </Layout>
        } />
      </Routes>
    </Router>
  )
}

export default App
