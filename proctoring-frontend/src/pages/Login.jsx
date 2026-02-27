import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async () => {
    if (!email || !password) {
      setMessage("❌ Please enter your email and password.");
      return;
    }

    setIsLoading(true);
    setMessage("🔐 Verifying credentials...");

    try {
      const response = await axios.post("http://127.0.0.1:8000/api/login", { email, password });
      
      const { access_token, refresh_token, has_embedding } = response.data;
      
      localStorage.setItem("access_token", access_token);
      localStorage.setItem("refresh_token", refresh_token);

      // Smart Redirect Logic
      if (has_embedding) {
        setMessage("✅ Login Successful! Entering exam dashboard...");
        setTimeout(() => navigate("/exam"), 1000);
      } else {
        setMessage("⚠️ Face not registered. Redirecting to setup...");
        setTimeout(() => navigate("/register-face"), 1000);
      }
      
    } catch (error) {
      const errorDetail = error.response?.data?.detail;
      if (Array.isArray(errorDetail)) {
        setMessage(`❌ Invalid Input: ${errorDetail[0].msg}`);
      } else {
        setMessage(`❌ Error: ${errorDetail || "Authentication failed"}`);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "400px", margin: "50px auto", textAlign: "center", fontFamily: "sans-serif" }}>
      <h2>Secure Login</h2>
      
      {message && (
        <div style={{ marginBottom: "15px", padding: "10px", background: message.includes("❌") ? "#ffebee" : "#e8f5e9", borderRadius: "5px" }}>
          <strong>{message}</strong>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "20px" }}>
        <input 
          type="email" 
          placeholder="Email" 
          value={email} 
          onChange={(e) => setEmail(e.target.value)} 
          style={{ padding: "10px", fontSize: "16px", borderRadius: "4px", border: "1px solid #ccc" }}
        />
        <input 
          type="password" 
          placeholder="Password" 
          value={password} 
          onChange={(e) => setPassword(e.target.value)} 
          style={{ padding: "10px", fontSize: "16px", borderRadius: "4px", border: "1px solid #ccc" }}
        />
      </div>

      <button 
        onClick={handleLogin} 
        disabled={isLoading} 
        style={{ padding: "12px", background: isLoading ? "#ccc" : "#007BFF", color: "white", width: "100%", border: "none", borderRadius: "5px", cursor: isLoading ? "not-allowed" : "pointer", fontSize: "18px" }}
      >
        {isLoading ? "Logging in..." : "Login"}
      </button>
      
      <p style={{ cursor: "pointer", color: "blue", marginTop: "20px" }} onClick={() => navigate("/register")}>
        Need an account? Register here.
      </p>
    </div>
  );
}