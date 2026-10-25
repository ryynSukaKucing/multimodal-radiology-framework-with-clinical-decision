// Base URL relatif -> otomatis mengikuti alamat tempat backend FastAPI menyajikan frontend ini.
const API_BASE = '';

function getToken() {
    return localStorage.getItem('radio_token') || '';
}

function setSession(token, user) {
    localStorage.setItem('radio_token', token);
    localStorage.setItem('radio_user', JSON.stringify(user));
}

function clearSession() {
    localStorage.removeItem('radio_token');
    localStorage.removeItem('radio_user');
}

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('radio_user') || 'null');
    } catch {
        return null;
    }
}

// Konfigurasi publik dari server: bila API key router sudah diset di .env, kolom "API" disembunyikan.
window.__routerKeyManaged = false;
async function loadPublicConfig() {
    try {
        const res = await fetch(`${API_BASE}/api/config`);
        if (!res.ok) return;
        const cfg = await res.json();
        window.__routerKeyManaged = !!cfg.router_key_managed;
    } catch {}
    const box = document.querySelector('.sidebar-api-box');
    if (box) box.style.display = window.__routerKeyManaged ? 'none' : '';
}

async function apiFetch(path, options = {}) {
    const headers = options.headers || {};
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (!(options.body instanceof FormData) && options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (res.status === 401) {
        clearSession();
        showLoginScreen();
        throw new Error('Session expired, please sign in again.');
    }

    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const errJson = await res.json();
            detail = errJson.detail || detail;
        } catch {}
        throw new Error(detail);
    }

    if (res.status === 204) return null;
    return res.json();
}

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast show ${type}`;
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(() => {
        toast.className = 'toast';
    }, 4000);
}
