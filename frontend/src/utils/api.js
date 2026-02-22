/**
 * Authenticated fetch wrapper.
 * Uses token from store or localStorage. On 401, tries refresh_token before logging out; retries request with new token.
 */
import store from '../store/store';
import { loadSession, logout, rehydrateFromStorage, setSession } from '../features/authSlice';

export const API_BASE = 'http://localhost:8001';

async function tryRefresh() {
    const session = loadSession();
    if (!session?.refresh_token) return null;
    const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: session.refresh_token }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    store.dispatch(setSession(data));
    return data.access_token;
}

export function authFetch(path, options = {}) {
    let token = store.getState().auth.token;
    if (!token) {
        const session = loadSession();
        if (session?.token) {
            store.dispatch(rehydrateFromStorage());
            token = session.token;
        }
    }
    const hadToken = !!token;
    const headers = {
        ...(options.headers || {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    return fetch(`${API_BASE}${path}`, { ...options, headers }).then(async (res) => {
        if (res.status === 401 && hadToken) {
            const newToken = await tryRefresh();
            if (newToken) {
                const retryHeaders = { ...(options.headers || {}), Authorization: `Bearer ${newToken}` };
                return fetch(`${API_BASE}${path}`, { ...options, headers: retryHeaders }).then((retryRes) => {
                    if (retryRes.status === 401) store.dispatch(logout());
                    return retryRes;
                });
            }
            store.dispatch(logout());
        }
        return res;
    });
}
