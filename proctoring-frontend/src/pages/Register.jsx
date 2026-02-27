import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const navigate = useNavigate();

  const handleRegister = async () => {
    try {
      await axios.post("http://127.0.0.1:8000/api/register", { email, password });
      setMessage("✅ Registered successfully! Redirecting to login...");
      
      // Send them to the login page after 1.5 seconds
      setTimeout(() => navigate("/login"), 1500);
    } catch (error) {
      setMessage(`❌ Error: ${error.response?.data?.detail || "Registration failed"}`);
    }
  };

  return (
    <div style={{ maxWidth: "400px", margin: "50px auto", textAlign: "center", fontFamily: "sans-serif" }}>
      <h2>Student Registration</h2>
      {message && <div style={{ marginBottom: "15px", padding: "10px", background: "#f0f0f0" }}>{message}</div>}
      
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} style={{ padding: "10px" }}/>
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ padding: "10px" }}/>
        
        <button onClick={handleRegister} style={{ padding: "10px", background: "#007BFF", color: "white", border: "none", cursor: "pointer" }}>
          Register
        </button>
      </div>
      
      <p style={{ cursor: "pointer", color: "blue", marginTop: "20px" }} onClick={() => navigate("/login")}>
        Already have an account? Login here.
      </p>
    </div>
  );
}