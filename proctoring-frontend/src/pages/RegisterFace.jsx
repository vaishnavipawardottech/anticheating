import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import Webcam from "react-webcam";
import axios from "axios";

export default function RegisterFace() {
  const [message, setMessage] = useState("Please look directly at the camera to register your identity.");
  const [isLoading, setIsLoading] = useState(false);
  const webcamRef = useRef(null);
  const navigate = useNavigate();

  const handleFaceRegistration = async () => {
    setIsLoading(true);
    setMessage("📸 Processing facial structure...");
    
    const imageSrc = webcamRef.current.getScreenshot();
    const token = localStorage.getItem("access_token");

    if (!token) {
      setMessage("❌ Unauthorized. Please log in first.");
      navigate("/login");
      return;
    }

    try {
      await axios.post(
        "http://127.0.0.1:8000/api/register-face", 
        { image_base64: imageSrc },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      setMessage("✅ Face registered securely! Redirecting to Exam Dashboard...");
      setTimeout(() => navigate("/exam"), 1500);
      
    } catch (error) {
      setMessage(`❌ Error: ${error.response?.data?.detail || "Face registration failed"}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "600px", margin: "50px auto", textAlign: "center", fontFamily: "sans-serif" }}>
      <h2>Biometric Setup Required</h2>
      
      {message && (
        <div style={{ marginBottom: "20px", padding: "15px", background: message.includes("❌") ? "#ffebee" : "#e8f5e9", borderRadius: "5px" }}>
          <strong>{message}</strong>
        </div>
      )}

      <div style={{ border: "3px solid #333", background: "#000", marginBottom: "20px", borderRadius: "8px", overflow: "hidden" }}>
        <Webcam
          audio={false}
          ref={webcamRef}
          screenshotFormat="image/jpeg"
          videoConstraints={{ width: 640, height: 480, facingMode: "user" }}
          style={{ width: "100%", display: "block" }}
        />
      </div>
      
      <button 
        onClick={handleFaceRegistration} 
        disabled={isLoading} 
        style={{ padding: "15px", background: isLoading ? "#ccc" : "#28a745", color: "white", width: "100%", border: "none", borderRadius: "5px", cursor: isLoading ? "not-allowed" : "pointer", fontSize: "18px", fontWeight: "bold" }}
      >
        {isLoading ? "Saving Mathematical Data..." : "Capture Face & Complete Setup"}
      </button>
    </div>
  );
}