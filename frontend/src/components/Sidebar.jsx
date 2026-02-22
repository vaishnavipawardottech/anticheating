import React, { useState } from 'react';
import { useDispatch } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  HelpCircle,
  Users,
  BarChart3,
  Settings,
  ChevronRight,
  Plus,
  List,
  Calendar,
  UserPlus,
  UserCog,
  Book,
  FileInput,
  ClipboardList,
  LogOut,
  Upload,
  Database,
  Zap,
  ScrollText,
  FileSearch,
  Library,
  Sparkles,
  ListChecks
} from 'lucide-react';
import { logoutThunk } from '../features/authSlice';
import './Sidebar.css';

const Sidebar = () => {
  const [openMenus, setOpenMenus] = useState({});
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const toggleSubmenu = (menuKey) => {
    setOpenMenus(prev => ({
      ...prev,
      [menuKey]: !prev[menuKey]
    }));
  };

  const handleMouseLeave = () => {
    setOpenMenus({});
  };

  const menuItems = [
    {
      key: 'dashboard',
      icon: <LayoutDashboard size={20} />,
      text: 'Dashboard',
      path: '/'
    },
    {
      key: 'subjects',
      icon: <Library size={20} />,
      text: 'Subjects',
      submenu: [
        { icon: <List size={18} />, text: 'All Subjects', path: '/subjects' },
        { icon: <Upload size={18} />, text: 'Ingest Document', path: '/ingest' },
        { icon: <Database size={18} />, text: 'View Embeddings', path: '/vectors' },
      ]
    },
    {
      key: 'papers',
      icon: <ScrollText size={20} />,
      text: 'Question Papers',
      submenu: [
        { icon: <ListChecks size={18} />, text: 'MCQ Papers', path: '/papers/mcq' },
        { icon: <FileText size={18} />, text: 'Subjective Papers', path: '/papers/subjective' },
        { icon: <FileSearch size={18} />, text: 'All Papers', path: '/papers' },
      ]
    },
    {
      key: 'generate',
      icon: <Sparkles size={20} />,
      text: 'Generate Papers',
      submenu: [
        { icon: <ListChecks size={18} />, text: 'MCQ Test', path: '/generate-mcq' },
        { icon: <FileText size={18} />, text: 'Subjective Exam', path: '/generate-subjective' },
      ]
    },
    {
      key: 'exams',
      icon: <FileText size={20} />,
      text: 'MCQ Exams',
      submenu: [
        { icon: <List size={18} />, text: 'All Exams', path: '/exams' },
        { icon: <Plus size={18} />, text: 'Create Exam', path: '/exams/create' },
        { icon: <Calendar size={18} />, text: 'Scheduled', path: '/exams/scheduled' }
      ]
    },
    // {
    //   key: 'questions',
    //   icon: <HelpCircle size={20} />,
    //   text: 'Question Bank',
    //   submenu: [
    //     { icon: <Book size={18} />, text: 'Browse Bank', path: '/questions' },
    //     { icon: <Plus size={18} />, text: 'Add Question', path: '/questions/create' },
    //     { icon: <FileInput size={18} />, text: 'Import Questions', path: '/questions/import' }
    //   ]
    // },
    {
      key: 'users',
      icon: <Users size={20} />,
      text: 'Users',
      submenu: [
        { icon: <List size={18} />, text: 'All Users', path: '/users' },
        { icon: <UserPlus size={18} />, text: 'Add User', path: '/users/create' },
        { icon: <UserCog size={18} />, text: 'Roles', path: '/users/roles' }
      ]
    },
    {
      key: 'results',
      icon: <BarChart3 size={20} />,
      text: 'Results',
      path: '/results'
    },
    {
      key: 'settings',
      icon: <Settings size={20} />,
      text: 'Settings',
      path: '/settings'
    }
  ];

  return (
    <div
      className="sidebar"
      onMouseLeave={handleMouseLeave}
    >
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <span className="sidebar-logo-icon"><ClipboardList size={24} /></span>
          <span className="sidebar-logo-text">Pareeksha</span>
        </div>
      </div>
      <ul className="sidebar-menu">
        {menuItems.map(item => (
          <li key={item.key} className="sidebar-menu-item">
            {item.submenu ? (
              <>
                <div
                  className="sidebar-menu-link"
                  onClick={() => toggleSubmenu(item.key)}
                >
                  <span className="sidebar-menu-icon">{item.icon}</span>
                  <span className="sidebar-menu-text">{item.text}</span>
                  <span className={`sidebar-menu-arrow ${openMenus[item.key] ? 'open' : ''}`}>
                    <ChevronRight size={16} />
                  </span>
                </div>
                <ul className={`sidebar-submenu ${openMenus[item.key] ? 'open' : ''}`}>
                  {item.submenu.map((subItem, idx) => (
                    <li key={idx}>
                      <a href={subItem.path} className="sidebar-submenu-link">
                        <span className="sidebar-menu-icon">{subItem.icon}</span>
                        <span className="sidebar-menu-text">{subItem.text}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <a href={item.path} className="sidebar-menu-link">
                <span className="sidebar-menu-icon">{item.icon}</span>
                <span className="sidebar-menu-text">{item.text}</span>
              </a>
            )}
          </li>
        ))}
      </ul>
      <div className="sidebar-footer">
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            dispatch(logoutThunk()).then(() => navigate('/login', { replace: true }));
          }}
          className="sidebar-menu-link logout"
        >
          <span className="sidebar-menu-icon"><LogOut size={20} /></span>
          <span className="sidebar-menu-text">Logout</span>
        </a>
      </div>
    </div>
  );
};

export default Sidebar;
