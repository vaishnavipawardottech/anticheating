import React from 'react';
import { User, Mail, Phone, MapPin, Calendar, ArrowLeft, ShieldCheck, Shield } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import './Profile.css';

const Profile = () => {
  const navigate = useNavigate();
  const teacher = useSelector((state) => state.auth.teacher);

  const handleBack = () => navigate(-1);

  const user = {
    name: teacher?.full_name || 'Teacher',
    email: teacher?.email || '',
    role: teacher?.is_admin ? 'Admin' : 'Teacher',
    avatar: null,
  };

  const getInitial = (name) => {
    return name.charAt(0).toUpperCase();
  };

  return (
    <div className="profile-container">
      <div className="profile-card">
        <div className="change-password-header">
          <button className="back-btn" onClick={handleBack}>
            <ArrowLeft size={20} />
          </button>
          <h1 className="change-password-title">Profile</h1>
        </div>

        <div className="profile-header">
          <div className="profile-avatar-large">
            {user.avatar ? (
              <img src={user.avatar} alt={user.name} />
            ) : (
              getInitial(user.name)
            )}
          </div>
          <div className="profile-header-text">
            <h1 className="profile-name">{user.name}</h1>
            <p className="profile-role">{user.role}</p>
          </div>
        </div>

        <div className="profile-info">
          <div className="profile-info-item">
            <Mail size={20} className="profile-icon" />
            <div className="profile-info-content">
              <span className="profile-info-label">Email</span>
              <span className="profile-info-value">{user.email}</span>
            </div>
          </div>

          <div className="profile-info-item">
            <Phone size={20} className="profile-icon" />
            <div className="profile-info-content">
              <span className="profile-info-label">Phone</span>
              <span className="profile-info-value">{user.phone}</span>
            </div>
          </div>

          <div className="profile-info-item">
            <MapPin size={20} className="profile-icon" />
            <div className="profile-info-content">
              <span className="profile-info-label">Location</span>
              <span className="profile-info-value">{user.location}</span>
            </div>
          </div>

          <div className="profile-info-item">
            <Calendar size={20} className="profile-icon" />
            <div className="profile-info-content">
              <span className="profile-info-label">Joined</span>
              <span className="profile-info-value">{user.joinDate}</span>
            </div>
          </div>
        </div>

        <div className="profile-actions">
          <button className="profile-btn primary">Edit Profile</button>
          <button className="profile-btn secondary" onClick={() => navigate('/profile/change-password')}>Change Password</button>
        </div>
      </div>
    </div>
  );
};

export default Profile;
