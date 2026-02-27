import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import Webcam from "react-webcam";
import axios from "axios";

export default function GiveExam() {
  const navigate = useNavigate();
  const webcamRef = useRef(null);
  
  // Phase 1: Identity Verification State
  const [isVerified, setIsVerified] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState("Please verify your identity to begin the exam.");
  
  // Phase 2: Active Exam State
  const [isExamStarted, setIsExamStarted] = useState(false);
  const [warnings, setWarnings] = useState([]); // Stores cheating flags to show the user

  // --- 1. VERIFICATION LOGIC (Existing) ---
  const verifyIdentityForExam = async () => {
    setIsLoading(true);
    setMessage("📸 Analyzing live facial structure...");
    
    const imageSrc = webcamRef.current.getScreenshot();
    const token = localStorage.getItem("access_token");

    try {
      const response = await axios.post(
        "http://127.0.0.1:8000/api/verify-face", 
        { image_base64: imageSrc },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      setMessage(`✅ ${response.data.message}`);
      setIsVerified(true);
    } catch (error) {
      setMessage(`❌ Error: ${error.response?.data?.detail || "Verification failed"}`);
      setIsVerified(false);
    } finally {
      setIsLoading(false);
    }
  };

  // --- 2. BACKEND LOGGING FUNCTION ---
  const logEventToBackend = async (eventType, details) => {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    try {
      // Sends the event to FastAPI, which tosses it into the Redis Queue!
      await axios.post(
        "http://127.0.0.1:8000/api/exam/log-event", 
        { event_type: eventType, details: details },
        { headers: { Authorization: `Bearer ${token}` } }
      );
    } catch (error) {
      console.error("Failed to log event:", error);
    }
  };

  // --- 3. START EXAM & LOCK BROWSER ---
  const startExam = async () => {
    try {
      // Force the browser into Full-Screen mode (Requires user interaction like this button click)
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
      setIsExamStarted(true);
      logEventToBackend("EXAM_STARTED", "Student entered the exam and went full-screen.");
    } catch (err) {
      alert("⚠️ You must allow full-screen mode to start the exam.");
    }
  };

  const handleLogout = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    }
    localStorage.clear();
    navigate("/login");
  };

  // --- 4. CONTINUOUS MONITORING HOOK ---
  useEffect(() => {
    // Only start spying on the browser IF the exam has started
    if (!isExamStarted) return;

    // Triggered when user switches tabs or minimizes Chrome
    const handleVisibilityChange = () => {
      if (document.hidden) {
        setWarnings((prev) => [...prev, "⚠️ TAB SWITCH DETECTED: You left the exam environment!"]);
        logEventToBackend("TAB_SWITCH", "Student switched to another browser tab or minimized the window.");
      }
    };

    // Triggered when user presses ESC to exit full-screen
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        setWarnings((prev) => [...prev, "⚠️ FULL-SCREEN EXITED: You must remain in full-screen!"]);
        logEventToBackend("FULLSCREEN_EXITED", "Student exited full-screen mode.");
      }
    };

    // Prevent Right-Clicking to copy/paste
    const handleContextMenu = (e) => {
      e.preventDefault();
      // Uncomment the line below if you want to log every right-click to the database!
      // logEventToBackend("RIGHT_CLICK", "Student attempted to right-click.");
    };

    // Attach native browser listeners
    document.addEventListener("visibilitychange", handleVisibilityChange);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("contextmenu", handleContextMenu);

    // Cleanup listeners if the component unmounts
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener("contextmenu", handleContextMenu);
    };
  }, [isExamStarted]);


  return (
    <div style={{ maxWidth: "800px", margin: "50px auto", textAlign: "center", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "2px solid #eee", paddingBottom: "10px" }}>
        <h2>📝 Live Examination Portal</h2>
        <button onClick={handleLogout} style={{ padding: "8px 16px", background: "#dc3545", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}>
          Logout
        </button>
      </div>

      <div style={{ marginTop: "30px", padding: "20px", background: "#f8f9fa", borderRadius: "8px" }}>
        
        {/* Verification Screen */}
        {!isVerified && (
          <div>
            <div style={{ marginBottom: "20px", padding: "10px", fontWeight: "bold", color: "#333" }}>{message}</div>
            <div style={{ border: "3px solid #333", background: "#000", marginBottom: "15px" }}>
              <Webcam audio={true} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ width: 640, height: 480, facingMode: "user" }} style={{ width: "100%" }} />
            </div>
            <button onClick={verifyIdentityForExam} disabled={isLoading} style={{ padding: "12px", background: isLoading ? "#ccc" : "#007BFF", color: "white", width: "100%", border: "none", cursor: "pointer", fontSize: "16px" }}>
              {isLoading ? "Comparing with Database..." : "Verify Identity & Unlock Exam"}
            </button>
          </div>
        )}

        {/* Start Exam Screen */}
        {isVerified && !isExamStarted && (
           <div style={{ padding: "40px", border: "2px solid #28a745", borderRadius: "8px", background: "#e9ecef" }}>
             <h3 style={{ color: "#28a745" }}>Identity Confirmed.</h3>
             <p>Clicking start will lock your browser into Full-Screen mode. Leaving the screen will be flagged.</p>
             <button onClick={startExam} style={{ padding: "15px 30px", fontSize: "18px", background: "#28a745", color: "white", border: "none", borderRadius: "5px", marginTop: "20px", cursor: "pointer" }}>
               Enter Full-Screen & Start Exam
             </button>
           </div>
        )}

        {/* Active Exam Screen */}
        {isExamStarted && (
          <div style={{ textAlign: "left" }}>
            <h3 style={{ color: "#007BFF" }}>Question 1:</h3>
            <p>Explain the architectural benefits of using a Redis Queue in an Event-Driven Architecture.</p>
            <textarea rows="10" style={{ width: "100%", padding: "10px", marginTop: "10px", fontSize: "16px", resize: "none" }} placeholder="Type your answer here..."></textarea>
            
            {/* Warning Log Feed */}
            {warnings.length > 0 && (
              <div style={{ marginTop: "30px", padding: "15px", background: "#ffebee", border: "1px solid #f44336", borderRadius: "5px" }}>
                <h4 style={{ color: "#d32f2f", marginTop: 0 }}>🚨 Proctoring Alerts</h4>
                <ul style={{ color: "#d32f2f", textAlign: "left", margin: 0 }}>
                  {warnings.map((warn, index) => (
                    <li key={index}>{warn}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}