import React, { useState } from 'react';
import { Lock, Eye, EyeOff, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import './ChangePassword.css';

const ChangePassword = () => {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({
        currentPassword: '',
        newPassword: '',
        confirmPassword: ''
    });
    const [showPasswords, setShowPasswords] = useState({
        current: false,
        new: false,
        confirm: false
    });
    const [errors, setErrors] = useState({});
    const [isLoading, setIsLoading] = useState(false);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
        // Clear error when user starts typing
        if (errors[name]) {
            setErrors(prev => ({
                ...prev,
                [name]: ''
            }));
        }
    };

    const togglePasswordVisibility = (field) => {
        setShowPasswords(prev => ({
            ...prev,
            [field]: !prev[field]
        }));
    };

    const validateForm = () => {
        const newErrors = {};

        if (!formData.currentPassword) {
            newErrors.currentPassword = 'Current password is required';
        }

        if (!formData.newPassword) {
            newErrors.newPassword = 'New password is required';
        } else if (formData.newPassword.length < 8) {
            newErrors.newPassword = 'Password must be at least 8 characters long';
        } else if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(formData.newPassword)) {
            newErrors.newPassword = 'Password must contain at least one uppercase letter, one lowercase letter, and one number';
        }

        if (!formData.confirmPassword) {
            newErrors.confirmPassword = 'Please confirm your new password';
        } else if (formData.newPassword !== formData.confirmPassword) {
            newErrors.confirmPassword = 'Passwords do not match';
        }

        if (formData.currentPassword === formData.newPassword) {
            newErrors.newPassword = 'New password must be different from current password';
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        if (!validateForm()) {
            return;
        }

        setIsLoading(true);

        try {
            // Simulate API call
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Here you would make an actual API call to change the password
            console.log('Password change request:', {
                currentPassword: formData.currentPassword,
                newPassword: formData.newPassword
            });

            // Show success message and redirect
            alert('Password changed successfully!');
            navigate('/profile');
        } catch (error) {
            setErrors({ submit: 'Failed to change password. Please try again.' });
        } finally {
            setIsLoading(false);
        }
    };

    const handleBack = () => {
        navigate('/profile');
    };

    return (
        <div className="change-password-container">
            <div className="change-password-card">
                <div className="change-password-header">
                    <button className="back-btn" onClick={handleBack}>
                        <ArrowLeft size={20} />
                    </button>
                    <h1 className="change-password-title">Change Password</h1>
                </div>

                <div className="change-password-info">
                    <form onSubmit={handleSubmit} className="change-password-form">
                        {errors.submit && (
                            <div className="error-message submit-error">
                                {errors.submit}
                            </div>
                        )}

                        <div className="form-group">
                            <label className="form-label">Current Password</label>
                            <div className="password-input-container">
                                <Lock size={20} className="input-icon" />
                                <input
                                    type={showPasswords.current ? 'text' : 'password'}
                                    name="currentPassword"
                                    value={formData.currentPassword}
                                    onChange={handleChange}
                                    className={`form-input ${errors.currentPassword ? 'error' : ''}`}
                                    placeholder="Enter your current password"
                                />
                                <button
                                    type="button"
                                    className="password-toggle"
                                    onClick={() => togglePasswordVisibility('current')}
                                >
                                    {showPasswords.current ? <EyeOff size={20} /> : <Eye size={20} />}
                                </button>
                            </div>
                            {errors.currentPassword && (
                                <span className="error-message">{errors.currentPassword}</span>
                            )}
                        </div>

                        <div className="form-group">
                            <label className="form-label">New Password</label>
                            <div className="password-input-container">
                                <Lock size={20} className="input-icon" />
                                <input
                                    type={showPasswords.new ? 'text' : 'password'}
                                    name="newPassword"
                                    value={formData.newPassword}
                                    onChange={handleChange}
                                    className={`form-input ${errors.newPassword ? 'error' : ''}`}
                                    placeholder="Enter your new password"
                                />
                                <button
                                    type="button"
                                    className="password-toggle"
                                    onClick={() => togglePasswordVisibility('new')}
                                >
                                    {showPasswords.new ? <EyeOff size={20} /> : <Eye size={20} />}
                                </button>
                            </div>
                            {errors.newPassword && (
                                <span className="error-message">{errors.newPassword}</span>
                            )}
                        </div>

                        <div className="form-group">
                            <label className="form-label">Confirm New Password</label>
                            <div className="password-input-container">
                                <Lock size={20} className="input-icon" />
                                <input
                                    type={showPasswords.confirm ? 'text' : 'password'}
                                    name="confirmPassword"
                                    value={formData.confirmPassword}
                                    onChange={handleChange}
                                    className={`form-input ${errors.confirmPassword ? 'error' : ''}`}
                                    placeholder="Confirm your new password"
                                />
                                <button
                                    type="button"
                                    className="password-toggle"
                                    onClick={() => togglePasswordVisibility('confirm')}
                                >
                                    {showPasswords.confirm ? <EyeOff size={20} /> : <Eye size={20} />}
                                </button>
                            </div>
                            {errors.confirmPassword && (
                                <span className="error-message">{errors.confirmPassword}</span>
                            )}
                        </div>

                        <div className="password-requirements">
                            <h3>Password Requirements:</h3>
                            <ul>
                                <li>At least 8 characters long</li>
                                <li>Contains at least one uppercase letter</li>
                                <li>Contains at least one lowercase letter</li>
                                <li>Contains at least one number</li>
                            </ul>
                        </div>
                    </form>
                </div>

                <div className="change-password-actions">

                    <button
                        type="submit"
                        className="submit-btn"
                        onClick={handleSubmit}
                        disabled={isLoading}
                    >
                        {isLoading ? 'Changing Password...' : 'Change Password'}
                    </button>
                    <button
                        type="button"
                        className="cancel-btn"
                        onClick={handleBack}
                        disabled={isLoading}
                    >
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ChangePassword;