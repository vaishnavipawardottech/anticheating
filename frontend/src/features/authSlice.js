import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

// Fetch user data from localStorage
const userData = JSON.parse(localStorage.getItem('authData')) || null;

// Initial state
const initialState = {
    user: userData || null,
    isAuthenticated: !!userData,
    loading: false,
    error: null,
};

// Login thunk - Mock implementation
export const login = createAsyncThunk('auth/login', async ({ username, password }, { rejectWithValue }) => {
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve({
                user: {
                    _id: 'mock-user-id-123',
                    username: username,
                    email: `${username}@assessease.com`,
                    fullName: 'Rushikesh Ghodke',
                    role: 'Admin',
                    department: 'IT Support',
                    isActive: true,
                },
                accessToken: 'mock-access-token-123456789',
                refreshToken: 'mock-refresh-token-987654321'
            });
        }, 500);
    });
});

// Logout thunk
export const logoutThunk = createAsyncThunk('auth/logout', async (_, { dispatch }) => {
    dispatch(logout());
});

// Slice
const authSlice = createSlice({
    name: 'auth',
    initialState,
    reducers: {
        logout: (state) => {
            state.user = null;
            state.isAuthenticated = false;
            state.loading = false;
            state.error = null;
            localStorage.removeItem('authData');
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(login.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(login.fulfilled, (state, action) => {
                state.loading = false;
                state.isAuthenticated = true;
                state.user = action.payload;
                state.accessToken = action.payload.accessToken;
                state.refreshToken = action.payload.refreshToken;
                localStorage.setItem('authData', JSON.stringify(action.payload));
            })
            .addCase(login.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload || 'Login failed';
            });
    },
});

export const { logout } = authSlice.actions;
export default authSlice.reducer;
