import React, { useState, useEffect } from 'react';
import { UserPlus, Users, ShieldCheck, Shield, Eye, EyeOff } from 'lucide-react';
import { useSelector } from 'react-redux';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';
import './Teachers.css';

const Teachers = () => {
  const currentTeacher = useSelector((state) => state.auth.teacher);
  const isAdmin = currentTeacher?.is_admin;

  const [teachers, setTeachers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [form, setForm] = useState({ email: '', full_name: '', password: '', is_admin: false });
  const [showPassword, setShowPassword] = useState(false);
  const [creating, setCreating] = useState(false);

  const fetchTeachers = () => {
    setLoading(true);
    authFetch('/auth/teachers')
      .then(r => { if (r.status === 401) return []; return r.ok ? r.json() : []; })
      .then(data => { setTeachers(data); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { fetchTeachers(); }, []);

  const handleFormChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const res = await authFetch('/auth/teachers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.status === 401) return;
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to create teacher');
      } else {
        toast.success(`Teacher ${form.full_name} created successfully`);
        setForm({ email: '', full_name: '', password: '', is_admin: false });
        fetchTeachers();
      }
    } catch { toast.error('Unable to create teacher.'); }
    finally { setCreating(false); }
  };

  return (
    <div className="teachers-container">
      <div className="teachers-card">
        {/* Header */}
        <div className="teachers-header">
          <Users size={20} style={{ color: '#0061a1' }} />
          <div className="teachers-header-info">
            <h1>Teachers</h1>
            <p>Manage teacher accounts · {teachers.length} teacher(s)</p>
          </div>
        </div>

        {/* Body */}
        <div className="teachers-body">
          {/* Teacher Table */}
          <div className="teachers-list-panel">
            {loading ? (
              <div className="teachers-empty">Loading…</div>
            ) : teachers.length === 0 ? (
              <div className="teachers-empty">No teachers found.</div>
            ) : (
              <table className="teachers-table">
                <thead>
                  <tr>
                    {['Name', 'Email', 'Role', 'Status'].map(h => <th key={h}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {teachers.map(t => (
                    <tr key={t.id} className={t.email === currentTeacher?.email ? 'highlight' : ''}>
                      <td>
                        <div className="teacher-name-cell">
                          <div className="teacher-avatar">{t.full_name.charAt(0).toUpperCase()}</div>
                          <span className="teacher-name">
                            {t.full_name}
                            {t.email === currentTeacher?.email && <span className="teacher-you-badge">You</span>}
                          </span>
                        </div>
                      </td>
                      <td>{t.email}</td>
                      <td>
                        <span className={`role-badge ${t.is_admin ? 'admin' : 'teacher'}`}>
                          {t.is_admin ? <><ShieldCheck size={12} /> Admin</> : <><Shield size={12} /> Teacher</>}
                        </span>
                      </td>
                      <td>
                        <span className={`status-badge ${t.is_active ? 'active' : 'inactive'}`}>
                          {t.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Add Teacher Panel (admin only) */}
          {isAdmin && (
            <div className="teachers-add-panel">
              <div className="add-teacher-header">
                <UserPlus size={16} style={{ color: '#0061a1' }} />
                Add Teacher
              </div>
              <form onSubmit={handleCreate} className="add-teacher-form">
                <div className="add-teacher-group">
                  <label className="add-teacher-label">Full Name</label>
                  <input type="text" name="full_name" value={form.full_name} onChange={handleFormChange}
                    className="add-teacher-input" placeholder="e.g. Dr. Anita Sharma" required />
                </div>
                <div className="add-teacher-group">
                  <label className="add-teacher-label">Email</label>
                  <input type="email" name="email" value={form.email} onChange={handleFormChange}
                    className="add-teacher-input" placeholder="teacher@org.com" required />
                </div>
                <div className="add-teacher-group">
                  <label className="add-teacher-label">Password</label>
                  <div className="add-teacher-pw-wrapper">
                    <input type={showPassword ? 'text' : 'password'} name="password" value={form.password}
                      onChange={handleFormChange} className="add-teacher-input" placeholder="Any password" required />
                    <button type="button" className="add-teacher-pw-toggle" onClick={() => setShowPassword(!showPassword)}>
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
                <div className="add-teacher-checkbox-row">
                  <input type="checkbox" id="is_admin" name="is_admin" checked={form.is_admin} onChange={handleFormChange} />
                  <label htmlFor="is_admin">Grant Admin privileges</label>
                </div>
                <button type="submit" className="add-teacher-submit" disabled={creating}>
                  <UserPlus size={15} />
                  {creating ? 'Creating…' : 'Create Teacher'}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Teachers;
