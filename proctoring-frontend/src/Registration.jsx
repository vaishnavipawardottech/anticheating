import React, { useRef, useState } from "react";
import Webcam from "react-webcam";
import axios from "axios";

const Registration = () => {
  const webcamRef = useRef(null);
  const [studentId, setStudentId] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // Force high-quality 720p capture for the AI
  const videoConstraints = {
    width: 1280,
    height: 720,
    facingMode: "user"
  };

  const captureAndRegister = async () => {
    if (!studentId) {
      setStatusMessage("❌ Please enter a Student ID first.");
      return;
    }

    setIsLoading(true);
    setStatusMessage("📸 Capturing image and analyzing bone structure...");

    // 1. Capture the frame as a Base64 string
    const imageSrc = webcamRef.current.getScreenshot();

    try {
      // 2. Send the payload exactly as FastAPI's Pydantic schema expects
      const response = await axios.post("http://127.0.0.1:8000/api/register", {
        student_id: studentId,
        image_base64: imageSrc
      });

      // 3. Handle Success
      setStatusMessage(`✅ Success! ${response.data.message}`);
      
    } catch (error) {
      // 4. Handle Errors (e.g., No face detected, or ID already exists)
      if (error.response) {
        setStatusMessage(`❌ Error: ${error.response.data.detail}`);
      } else {
        setStatusMessage("❌ Network error. Is FastAPI running?");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "600px", margin: "50px auto", textAlign: "center", fontFamily: "sans-serif" }}>
      <h2>Phase 1: Identity Registration</h2>
      
      <div style={{ marginBottom: "20px" }}>
        <input 
          type="text" 
          placeholder="Enter Student ID (e.g., CS-101)" 
          value={studentId}
          onChange={(e) => setStudentId(e.target.value)}
          style={{ padding: "10px", width: "80%", fontSize: "16px" }}
        />
      </div>

      <div style={{ border: "2px solid #ccc", padding: "10px", borderRadius: "8px", background: "#000" }}>
        <Webcam
          audio={false}
          ref={webcamRef}
          screenshotFormat="image/jpeg"
          videoConstraints={videoConstraints}
          style={{ width: "100%", borderRadius: "8px" }}
        />
      </div>

      <button 
        onClick={captureAndRegister} 
        disabled={isLoading}
        style={{ 
          marginTop: "20px", 
          padding: "12px 24px", 
          fontSize: "18px", 
          cursor: isLoading ? "not-allowed" : "pointer",
          backgroundColor: isLoading ? "#ccc" : "#007BFF",
          color: "white",
          border: "none",
          borderRadius: "5px"
        }}
      >
        {isLoading ? "Processing AI..." : "Capture & Register Identity"}
      </button>

      {statusMessage && (
        <div style={{ marginTop: "20px", padding: "15px", backgroundColor: "#f4f4f4", borderRadius: "5px" }}>
          <strong>{statusMessage}</strong>
        </div>
      )}
    </div>
  );
};

export default Registration;