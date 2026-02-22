import React from 'react';
import Sidebar from './components/Sidebar';
import NavBar from './components/NavBar';
import './Layout.css';

const Layout = ({ children }) => {
  return (
    <div className="layout-grid">
      <div className="layout-sidebar">
        <Sidebar />
      </div>
      <div className="layout-main">
        <div className="layout-navbar">
          <NavBar />
        </div>
        <div className="layout-content">
          {children}
        </div>
      </div>
    </div>
  );
};

export default Layout;
