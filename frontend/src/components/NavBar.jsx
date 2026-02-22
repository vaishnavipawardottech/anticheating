import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import './NavBar.css';

const NavBar = () => {
  const navigate = useNavigate();
  const teacher = useSelector((state) => state.auth.teacher);

  const displayName = teacher?.full_name || teacher?.email || 'User';

  const getInitial = (name) => name.charAt(0).toUpperCase();

  return (
    <div className="navbar">
      <div className="navbar-title">Pareeksha</div>
      <div className="navbar-right">
        <span className="navbar-username">{displayName}</span>
        <div className="navbar-avatar" onClick={() => navigate('/profile')} title={displayName}>
          {getInitial(displayName)}
        </div>
      </div>
    </div>
  );
};

export default NavBar;
