import React from 'react';
import { useNavigate } from 'react-router-dom';
import './NavBar.css';

const NavBar = () => {
  const navigate = useNavigate();
  const user = {
    name: 'Rushikesh Ghodke',
    email: 'admin@smartassessment.com',
    avatar: null
  };

  const getInitial = (name) => {
    return name.charAt(0).toUpperCase();
  };

  const handleProfileClick = () => {
    navigate('/profile');
  };

  return (
    <div className="navbar">
      <div className="navbar-title">AssessEase</div>
      <div className="navbar-right">
        <div className="navbar-avatar" onClick={handleProfileClick}>
          {user.avatar ? (
            <img src={user.avatar} alt={user.name} />
          ) : (
            getInitial(user.name)
          )}
        </div>
      </div>
    </div>
  );
};

export default NavBar;
