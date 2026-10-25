// =====================================================================
//  Log Proses global (sidebar). Semua tab menulis ke sini lewat logLine().
//  - Tiap baris: jam, label tab, keterangan.
//  - Keterangan dibersihkan dari tanda pisah panjang (em dash dan en dash).
//  - Semua toast ikut tercatat otomatis, jadi setiap hasil aksi (berhasil atau gagal) ada di log.
//  - Disimpan di sessionStorage sehingga tidak hilang saat halaman dimuat ulang.
// =====================================================================
const LOG_TAB_LABEL = {
    login: 'Account', dashboard: 'Dashboard', patients: 'Patient Database', 'clinical-history': 'Clinical History',
    history: 'Scan History', scan: 'AI Scan',
};
const LOG_EMPTY = 'No activity yet. The log records activity across all tabs.';
const LOG_MAX = 500;
window.__logView = window.__logView || 'login';
let __logBuf = [];
try { __logBuf = JSON.parse(sessionStorage.getItem('radio_log') || '[]'); } catch (e) { __logBuf = []; }

// Buang em dash, en dash, dan sejenisnya dari teks keterangan.
function logClean(s) {
    return String(s === null || s === undefined ? '' : s)
        .replace(/\s*[‒–—―⸺⸻]+\s*/g, ', ')
        .replace(/\s+/g, ' ').trim();
}
function logTabName(tab) { return LOG_TAB_LABEL[tab || window.__logView] || LOG_TAB_LABEL.login; }

function logPersist() { try { sessionStorage.setItem('radio_log', JSON.stringify(__logBuf.slice(-LOG_MAX))); } catch (e) { /* abaikan */ } }

function logRenderEntry(e, el) {
    const d = document.createElement('span');
    d.className = 'ln ' + (e.cls || '');
    const t = document.createElement('span'); t.className = 't'; t.textContent = e.t;
    const tb = document.createElement('span'); tb.className = 'tb'; tb.textContent = e.tab;
    d.appendChild(t); d.appendChild(tb); d.appendChild(document.createTextNode(e.msg));
    el.appendChild(d);
}

function logEnsureEl() { return document.getElementById('scan-log'); }

function logClear() {
    __logBuf = []; logPersist();
    const el = logEnsureEl(); if (el) el.innerHTML = `<div class="log-empty">${LOG_EMPTY}</div>`;
}

// cls: '' | 'ok' | 'warn' | 'err' | 'head' | 'srv'. tab: kunci tab (opsional, default tab yang sedang dibuka).
function logLine(msg, cls = '', tab) {
    const text = logClean(msg);
    if (!text) return;
    const t = new Date().toLocaleTimeString('id-ID', { hour12: false });
    const e = { t, tab: logTabName(tab), msg: text, cls: cls || '' };
    const last = __logBuf[__logBuf.length - 1];
    if (last && last.msg === e.msg && last.tab === e.tab && Date.now() - (last._ts || 0) < 1500) return; // cegah baris ganda (aksi + toast)
    e._ts = Date.now();
    __logBuf.push(e);
    if (__logBuf.length > LOG_MAX) __logBuf = __logBuf.slice(-LOG_MAX);
    logPersist();
    const el = logEnsureEl(); if (!el) return;
    el.querySelector('.log-empty')?.remove();
    logRenderEntry(e, el);
    while (el.children.length > LOG_MAX) el.removeChild(el.firstChild);
    el.scrollTop = el.scrollHeight;
}

// Baris log dari server (hasil pemindaian). Dibersihkan juga dari em dash.
function logServer(lines, label) {
    if (label) logLine(label, 'head', 'scan');
    (lines || []).forEach(l => {
        const cls = /gagal|failed|error|tidak terbaca|unreadable|Peringatan|warning/i.test(l) ? 'warn' : (/Selesai|berhasil|complete|success|saved/i.test(l) ? 'ok' : 'srv');
        logLine(l, cls, 'scan');
    });
}

function logRestore() {
    const el = logEnsureEl(); if (!el) return;
    if (!__logBuf.length) { el.innerHTML = `<div class="log-empty">${LOG_EMPTY}</div>`; return; }
    el.innerHTML = ''; __logBuf.forEach(e => logRenderEntry(e, el));
    el.scrollTop = el.scrollHeight;
}

// Semua toast otomatis masuk log.
(function hookToast() {
    const orig = window.showToast;
    if (typeof orig !== 'function') return;
    window.showToast = function (message, type = 'info') {
        orig(message, type);
        logLine(message, type === 'error' ? 'err' : type === 'success' ? 'ok' : '');
    };
})();

window.addEventListener('error', (ev) => { logLine(`Script error: ${ev.message}`, 'err'); });
window.addEventListener('unhandledrejection', (ev) => { logLine(`Unhandled error: ${(ev.reason && ev.reason.message) || ev.reason}`, 'err'); });

document.addEventListener('DOMContentLoaded', () => {
    logRestore();
    document.getElementById('btn-clear-log')?.addEventListener('click', logClear);
    // Pengaturan sidebar (berlaku untuk semua tab)
    document.getElementById('model-select')?.addEventListener('change', (e) => logLine(`Model AI diganti: ${e.target.value}`));
    document.getElementById('api-key')?.addEventListener('change', (e) => logLine(e.target.value.trim() ? 'API key diisi' : 'API key dikosongkan'));
    document.getElementById('patient-select')?.addEventListener('change', (e) => {
        const o = e.target.selectedOptions[0];
        logLine(e.target.value ? `Patient selected in sidebar: ${o ? o.textContent.trim() : e.target.value}` : 'Sidebar patient selection cleared');
    });
});
