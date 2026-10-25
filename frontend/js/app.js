function showLoginScreen() {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('app-shell').style.display = 'none';
}

function showAppShell() {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app-shell').style.display = 'block';
    const user = getUser();
    if (user) {
        document.getElementById('me-fullname').textContent = user.full_name || user.username;
        document.getElementById('me-role').textContent = user.role || '';
    }
    loadPatientOptionsForScan(); // "Nama Pasien" di sidebar dipakai bersama oleh semua tab
}

function switchView(viewName) {
    window.__logView = viewName;
    logLine(`Opened tab ${LOG_TAB_LABEL[viewName] || viewName}`);
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById(`view-${viewName}`).classList.add('active');
    document.querySelector(`.nav-item[data-view="${viewName}"]`).classList.add('active');

    if (viewName === 'dashboard') loadDashboard();
    if (viewName === 'patients') loadPatients();
    if (viewName === 'history') loadHistory();
    if (viewName === 'scan') { loadPatientOptionsForScan(); if (window.__scanPatientDirty) { window.__scanPatientDirty = false; onScanPatientChange(); } }
    if (viewName === 'clinical-history') loadClinicalHistoryView();
}

// Pemilih pasien tunggal ada di sidebar. Tab yang sedang terbuka langsung memuat ulang datanya;
// Pemindaian AI baru memuat riwayat citra saat tabnya dibuka (agar tidak muncul konfirmasi di tab lain).
function onGlobalPatientChange() {
    const v = window.__logView;
    if (v === 'scan') onScanPatientChange(); else window.__scanPatientDirty = true;
    if (v === 'clinical-history') loadClinicalHistoryView();
}

function currentPatientId() { return (document.getElementById('patient-select') || {}).value || ''; }
function currentPatientName() {
    const o = (document.getElementById('patient-select') || {}).selectedOptions;
    return o && o[0] && o[0].value ? o[0].textContent.trim() : '';
}

document.addEventListener('DOMContentLoaded', () => {
    loadPublicConfig();
    // Cek sesi tersimpan
    if (getToken() && getUser()) {
        showAppShell();
        logLine(`Session restored for ${getUser().username}`, '', 'login');
        switchView('dashboard');
    } else {
        showLoginScreen();
    }

    document.getElementById('btn-login').addEventListener('click', doLogin);
    document.getElementById('login-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') doLogin();
    });

    document.getElementById('patient-select').addEventListener('change', onGlobalPatientChange);

    document.getElementById('btn-logout').addEventListener('click', () => {
        logLine('Signed out', '', 'login');
        clearSession();
        showLoginScreen();
    });

    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => switchView(item.dataset.view));
    });

    document.getElementById('btn-refresh-dashboard').addEventListener('click', () => { logLine('Refreshing dashboard'); loadDashboard(); });
});

async function doLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errBox = document.getElementById('login-error');
    errBox.textContent = '';

    if (!username || !password) {
        errBox.textContent = 'Username and password are required.';
        logLine('Sign-in failed: username or password empty', 'warn', 'login');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Sign-in failed.');
        }
        const data = await res.json();
        setSession(data.access_token, {
            username: data.username,
            full_name: data.full_name,
            role: data.role,
        });
        showAppShell();
        logLine(`Signed in as ${data.username} (${data.role || 'user'})`, 'ok', 'login');
        switchView('dashboard');
    } catch (e) {
        errBox.textContent = e.message;
        logLine(`Sign-in failed: ${e.message}`, 'err', 'login');
    }
}
