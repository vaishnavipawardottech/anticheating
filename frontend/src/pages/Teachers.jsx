import React, { useState, useEffect } from 'react';
import { UserPlus, Users, ShieldCheck, Shield, Eye, EyeOff } from 'lucide-react';
import { useSelector } from 'react-redux';
import { authFetch } from '../utils/api';
import { toast } from 'react-toastify';

const API = 'http://localhost:8001';

const Teachers = () => {
  const currentTeacher = useSelector((state) => state.auth.teacher);
  const isAdmin = currentTeacher?.is_admin;

  const [teachers, setTeachers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [form, setForm] = useState({
    email: '',
    full_name: '',
    password: '',
    is_admin: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [creating, setCreating] = useState(false);

  const fetchTeachers = () => {
    setLoading(true);
    authFetch('/auth/teachers')
      .then(r => {
        if (r.status === 401) return [];
        return r.ok ? r.json() : [];
      })
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
    } catch {
      toast.error('Unable to create teacher. Please try again.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ padding: '1.5rem', maxWidth: '960px', margin: '0 auto' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <div style={{
          width: '2.5rem', height: '2.5rem', borderRadius: '0.5rem',
          background: '#EFF6FF', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Users size={20} style={{ color: '#0061a1' }} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#111827', margin: 0 }}>Teachers</h1>
          <p style={{ fontSize: '0.875rem', color: '#6B7280', margin: 0 }}>Manage teacher accounts</p>
        </div>
      </div>

      <div style={{ display: 'grid', gap: '1.5rem', gridTemplateColumns: isAdmin ? '1fr 380px' : '1fr' }}>

        {/* ── Teacher List ── */}
        <div style={{
          background: '#ffffff', borderRadius: '0.75rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.08)', overflow: 'hidden',
        }}>
          <div style={{
            padding: '1rem 1.25rem',
            borderBottom: '1px solid #E5E7EB',
            display: 'flex', alignItems: 'center', gap: '0.5rem',
          }}>
            <Users size={16} style={{ color: '#0061a1' }} />
            <span style={{ fontWeight: 600, color: '#111827', fontSize: '0.9375rem' }}>
              All Teachers ({teachers.length})
            </span>
          </div>

          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#6B7280' }}>Loading…</div>
          ) : teachers.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#6B7280' }}>No teachers found.</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#F9FAFB' }}>
                  {['Name', 'Email', 'Role', 'Status'].map(h => (
                    <th key={h} style={{
                      padding: '0.625rem 1.25rem',
                      textAlign: 'left', fontSize: '0.75rem',
                      fontWeight: 600, color: '#6B7280',
                      textTransform: 'uppercase', letterSpacing: '0.05em',
                      borderBottom: '1px solid #E5E7EB',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {teachers.map((t, i) => (
                  <tr key={t.id} style={{
                    borderBottom: i < teachers.length - 1 ? '1px solid #F3F4F6' : 'none',
                    background: t.email === currentTeacher?.email ? '#EFF6FF' : 'transparent',
                  }}>
                    <td style={{ padding: '0.75rem 1.25rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                        <div style={{
                          width: '2rem', height: '2rem', borderRadius: '50%',
                          background: '#0061a1', color: '#fff',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontWeight: 600, fontSize: '0.8125rem', flexShrink: 0,
                        }}>
                          {t.full_name.charAt(0).toUpperCase()}
                        </div>
                        <span style={{ fontWeight: 500, color: '#111827', fontSize: '0.875rem' }}>
                          {t.full_name}
                          {t.email === currentTeacher?.email && (
                            <span style={{
                              marginLeft: '0.4rem', fontSize: '0.7rem',
                              background: '#EFF6FF', color: '#0061a1',
                              padding: '0.1rem 0.4rem', borderRadius: '0.25rem', fontWeight: 500,
                            }}>You</span>
                          )}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 1.25rem', color: '#374151', fontSize: '0.875rem' }}>
                      {t.email}
                    </td>
                    <td style={{ padding: '0.75rem 1.25rem' }}>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                        fontSize: '0.75rem', fontWeight: 500, padding: '0.2rem 0.5rem',
                        borderRadius: '9999px',
                        background: t.is_admin ? '#FEF3C7' : '#F3F4F6',
                        color: t.is_admin ? '#92400E' : '#374151',
                      }}>
                        {t.is_admin
                          ? <><ShieldCheck size={12} /> Admin</>
                          : <><Shield size={12} /> Teacher</>
                        }
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1.25rem' }}>
                      <span style={{
                        display: 'inline-block', fontSize: '0.75rem', fontWeight: 500,
                        padding: '0.2rem 0.5rem', borderRadius: '9999px',
                        background: t.is_active ? '#D1FAE5' : '#FEE2E2',
                        color: t.is_active ? '#065F46' : '#991B1B',
                      }}>
                        {t.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* ── Add Teacher Form (admin only) ── */}
        {isAdmin && (
          <div style={{
            background: '#ffffff', borderRadius: '0.75rem',
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)', height: 'fit-content',
          }}>
            <div style={{
              padding: '1rem 1.25rem',
              borderBottom: '1px solid #E5E7EB',
              display: 'flex', alignItems: 'center', gap: '0.5rem',
            }}>
              <UserPlus size={16} style={{ color: '#0061a1' }} />
              <span style={{ fontWeight: 600, color: '#111827', fontSize: '0.9375rem' }}>Add Teacher</span>
            </div>

            <form onSubmit={handleCreate} style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: '#374151', marginBottom: '0.375rem' }}>
                  Full Name
                </label>
                <input
                  type="text"
                  name="full_name"
                  value={form.full_name}
                  onChange={handleFormChange}
                  placeholder="e.g. Dr. Anita Sharma"
                  required
                  style={{
                    width: '100%', padding: '0.5rem 0.75rem',
                    border: '1px solid #D1D5DB', borderRadius: '0.375rem',
                    fontSize: '0.875rem', color: '#111827', outline: 'none', boxSizing: 'border-box',
                  }}
                  onFocus={e => e.target.style.borderColor = '#0061a1'}
                  onBlur={e => e.target.style.borderColor = '#D1D5DB'}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: '#374151', marginBottom: '0.375rem' }}>
                  Email
                </label>
                <input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handleFormChange}
                  placeholder="teacher@org.com"
                  required
                  style={{
                    width: '100%', padding: '0.5rem 0.75rem',
                    border: '1px solid #D1D5DB', borderRadius: '0.375rem',
                    fontSize: '0.875rem', color: '#111827', outline: 'none', boxSizing: 'border-box',
                  }}
                  onFocus={e => e.target.style.borderColor = '#0061a1'}
                  onBlur={e => e.target.style.borderColor = '#D1D5DB'}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 500, color: '#374151', marginBottom: '0.375rem' }}>
                  Password
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    value={form.password}
                    onChange={handleFormChange}
                    placeholder="Any password"
                    required
                    style={{
                      width: '100%', padding: '0.5rem 2.5rem 0.5rem 0.75rem',
                      border: '1px solid #D1D5DB', borderRadius: '0.375rem',
                      fontSize: '0.875rem', color: '#111827', outline: 'none', boxSizing: 'border-box',
                    }}
                    onFocus={e => e.target.style.borderColor = '#0061a1'}
                    onBlur={e => e.target.style.borderColor = '#D1D5DB'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      position: 'absolute', right: '0.5rem', top: '50%', transform: 'translateY(-50%)',
                      background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF',
                      display: 'flex', alignItems: 'center',
                    }}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  id="is_admin"
                  name="is_admin"
                  checked={form.is_admin}
                  onChange={handleFormChange}
                  style={{ width: '1rem', height: '1rem', accentColor: '#0061a1', cursor: 'pointer' }}
                />
                <label htmlFor="is_admin" style={{ fontSize: '0.875rem', color: '#374151', cursor: 'pointer', userSelect: 'none' }}>
                  Grant Admin privileges
                </label>
              </div>

              <button
                type="submit"
                disabled={creating}
                style={{
                  width: '100%', padding: '0.5625rem',
                  background: creating ? '#9CA3AF' : '#0061a1',
                  color: '#ffffff', border: 'none', borderRadius: '0.375rem',
                  fontSize: '0.875rem', fontWeight: 500, cursor: creating ? 'not-allowed' : 'pointer',
                  transition: 'background 0.15s', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem',
                }}
                onMouseEnter={e => { if (!creating) e.target.style.background = '#004d82'; }}
                onMouseLeave={e => { if (!creating) e.target.style.background = '#0061a1'; }}
              >
                <UserPlus size={15} />
                {creating ? 'Creating…' : 'Create Teacher'}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};

export default Teachers;
