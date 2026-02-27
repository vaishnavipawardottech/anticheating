import React, { useState } from 'react';
import { toast } from 'react-toastify';
import { GraduationCap, Eye, EyeOff } from 'lucide-react';
import './StudentLogin.css';

const API = 'http://localhost:8001';

const StudentLogin = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPw, setShowPw] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await fetch(`${API}/auth/student/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || 'Invalid credentials');
                setLoading(false);
                return;
            }
            const data = await res.json();
            localStorage.setItem('pareeksha_student_session', JSON.stringify({
                token: data.access_token,
                refresh_token: data.refresh_token,
                student: data.student,
            }));
            window.location.href = '/student/exams';
        } catch {
            toast.error('Network error');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="student-login-page">
            <div className="student-login-card">
                <div className="student-login-branding">
                    <div className="student-login-icon">
                        <GraduationCap size={28} />
                    </div>
                    <h1>Student Portal</h1>
                    <p>Smart Assessment System</p>
                </div>

                <form onSubmit={handleSubmit} className="student-login-form">
                    <div className="student-login-group">
                        <label className="student-login-label">Email</label>
                        <input type="email" className="student-login-input" value={email}
                            onChange={e => setEmail(e.target.value)} required placeholder="student@example.com" />
                    </div>
                    <div className="student-login-group">
                        <label className="student-login-label">Password</label>
                        <div className="student-login-pw-wrapper">
                            <input type={showPw ? 'text' : 'password'} className="student-login-input"
                                value={password} onChange={e => setPassword(e.target.value)}
                                required placeholder="••••••••" />
                            <button type="button" className="student-login-pw-toggle" onClick={() => setShowPw(!showPw)}>
                                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                            </button>
                        </div>
                    </div>
                    <button type="submit" className="student-login-submit" disabled={loading}>
                        {loading ? 'Signing in…' : 'Sign In'}
                    </button>
                </form>

                <div className="student-login-footer">
                    <a href="/">← Teacher Login</a>
                </div>
            </div>
        </div>
    );
};

export default StudentLogin;
