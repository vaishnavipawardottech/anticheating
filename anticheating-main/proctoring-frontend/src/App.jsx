import { useState, useRef } from 'react'
import Webcam from "react-webcam";
import axios from "axios";
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Register from "./pages/Register";
import Login from "./pages/Login";
import GiveExam from "./pages/GiveExam";
import RegisterFace from "./pages/RegisterFace";  

function App() {

  return (
    <BrowserRouter>
      <Routes>
        {/* Default route redirects to login */}
        <Route path="/" element={<Navigate to="/login" />} />
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register-face" element={<RegisterFace />} />
        <Route path="/exam" element={<GiveExam />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
