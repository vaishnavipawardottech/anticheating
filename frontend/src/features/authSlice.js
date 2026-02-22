import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

const API_BASE = 'http://localhost:8001';
const STORAGE_KEY = 'pareeksha_session';

// ─── Storage helpers ─────────────────────────────────────────────────────────

function saveSessionLocal(token, teacher, refreshToken = null) {
    const payload = { token, teacher };
    if (refreshToken != null) payload.refresh_token = refreshToken;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function loadSession() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    } catch {
        return null;
    }
}

function clearSession() {
    localStorage.removeItem(STORAGE_KEY);
    // also clear any old keys from previous implementations
    localStorage.removeItem('authData');
    localStorage.removeItem('teacherData');
}

// ─── Bootstrap from localStorage (runs synchronously before first render) ────

const _session = loadSession();

const initialState = {
    teacher: _session?.teacher || null,
    token: _session?.token || null,
    isAuthenticated: !!(_session?.token),
    loading: false,
    error: null,
};

// ─── Thunks ───────────────────────────────────────────────────────────────────

export const login = createAsyncThunk(
    'auth/login',
    async ({ email, password }, { rejectWithValue }) => {
        try {
            const res = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                return rejectWithValue(err.detail || 'Invalid email or password');
            }
            return await res.json(); // { access_token, teacher }
        } catch {
            return rejectWithValue('Unable to reach the server. Please try again.');
        }
    }
);

export const logoutThunk = createAsyncThunk('auth/logout', async (_, { dispatch, getState }) => {
    const token = getState().auth?.token;
    if (token) {
        try {
            await fetch(`${API_BASE}/auth/logout`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
        } catch (_) { /* offline: still clear local */ }
    }
    dispatch(logout());
});

// ─── Slice ────────────────────────────────────────────────────────────────────

const authSlice = createSlice({
    name: 'auth',
    initialState,
    reducers: {
        logout: (state) => {
            state.teacher = null;
            state.token = null;
            state.isAuthenticated = false;
            state.loading = false;
            state.error = null;
            clearSession();
        },
        rehydrateFromStorage: (state) => {
            const s = loadSession();
            if (s?.token) {
                state.token = s.token;
                state.teacher = s.teacher ?? state.teacher;
                state.isAuthenticated = true;
            }
        },
        // Set session from refresh response (new access_token + refresh_token)
        setSession: (state, action) => {
            const { access_token, refresh_token, teacher } = action.payload;
            state.token = access_token;
            state.teacher = teacher ?? state.teacher;
            state.isAuthenticated = true;
            state.error = null;
            saveSessionLocal(access_token, state.teacher, refresh_token ?? null);
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(login.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(login.fulfilled, (state, action) => {
                const { access_token, refresh_token, teacher } = action.payload;
                state.loading = false;
                state.isAuthenticated = true;
                state.teacher = teacher;
                state.token = access_token;
                saveSessionLocal(access_token, teacher, refresh_token ?? null);
            })
            .addCase(login.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload || 'Login failed';
            });
    },
});

export const { logout, rehydrateFromStorage, setSession } = authSlice.actions;
export default authSlice.reducer;
