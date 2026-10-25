async function loadDashboard() {
    logLine('Loading dashboard data');
    try {
        const stats = await apiFetch('/api/dashboard/stats');

        document.getElementById('stat-patients').textContent = stats.total_patients;
        document.getElementById('stat-scans').textContent = stats.total_scans;
        document.getElementById('stat-today').textContent = stats.scans_today;
        document.getElementById('stat-success').textContent = `${stats.success_rate}%`;

        loadTrendDay(window.__trendDate || null);
        renderSeverityBreakdown(stats.severity_breakdown);
        renderRecentList(stats.recent_history);
        logLine(`Dashboard loaded: ${stats.total_patients} patients, ${stats.total_scans} scans, ${stats.scans_today} today, success rate ${stats.success_rate}%, ${(stats.recent_history || []).length} recent activities`, 'ok');
    } catch (e) {
        showToast(`Failed to load dashboard: ${e.message}`, 'error');
    }
}

// ---- Scan trend: one day at a time, bucketed per hour (viewer's local time) ----
function trendLocalToday() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function trendShift(dateStr, delta) {
    const [y, m, d] = dateStr.split('-').map(Number);
    const t = new Date(y, m - 1, d + delta);
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
}
async function loadTrendDay(dateStr) {
    const date = dateStr || trendLocalToday();
    window.__trendDate = date;
    const inp = document.getElementById('trend-date');
    if (inp) { inp.value = date; inp.max = trendLocalToday(); }
    const next = document.getElementById('trend-next');
    if (next) next.disabled = date >= trendLocalToday();
    try {
        const tz = -new Date().getTimezoneOffset();   // minutes east of UTC
        const res = await apiFetch(`/api/dashboard/day?date=${date}&tz_offset=${tz}`);
        renderBarChart(res.hours, res.date);
        const tot = document.getElementById('trend-total');
        if (tot) tot.textContent = `${res.total} scan${res.total === 1 ? '' : 's'}`;
    } catch (e) {
        showToast(`Failed to load scan trend: ${e.message}`, 'error');
    }
}
function initTrendControls() {
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
    on('trend-prev', () => loadTrendDay(trendShift(window.__trendDate || trendLocalToday(), -1)));
    on('trend-next', () => loadTrendDay(trendShift(window.__trendDate || trendLocalToday(), 1)));
    on('trend-today', () => loadTrendDay(trendLocalToday()));
    const inp = document.getElementById('trend-date');
    if (inp) inp.addEventListener('change', () => { if (inp.value) loadTrendDay(inp.value); });
}
document.addEventListener('DOMContentLoaded', initTrendControls);

function renderBarChart(hours, date) {
    const el = document.getElementById('bar-chart');
    const max = Math.max(1, ...hours);
    const nowHour = date === trendLocalToday() ? new Date().getHours() : -1;
    el.innerHTML = hours.map((count, h) => {
        const heightPct = count > 0 ? Math.max(6, Math.round((count / max) * 100)) : 0;
        const label = String(h).padStart(2, '0');
        const cls = 'bar-col' + (count === 0 ? ' zero' : '') + (h === nowHour ? ' today' : '');
        const showLabel = h % 3 === 0;
        return `
            <div class="${cls}" title="${label}:00 - ${label}:59 : ${count} scan${count === 1 ? '' : 's'}">
                <div class="bar-value">${count > 0 ? count : ''}</div>
                <div class="bar-track"><div class="bar-fill" style="height:${heightPct}%;"></div></div>
                <div class="bar-label">${showLabel ? label : ''}</div>
            </div>`;
    }).join('');
}

function renderSeverityBreakdown(breakdown) {
    const el = document.getElementById('severity-breakdown');
    const entries = Object.entries(breakdown || {});
    if (entries.length === 0) {
        el.innerHTML = '<div class="empty-state">No data yet.</div>';
        return;
    }
    const colorMap = { 'tinggi': '#ef4444', 'high': '#ef4444', 'sedang': '#f59e0b', 'medium': '#f59e0b', 'moderate': '#f59e0b', 'rendah': '#22c55e', 'low': '#22c55e' };
    el.innerHTML = entries.map(([label, count]) => {
        const key = label.toLowerCase();
        const color = colorMap[key] || '#64748b';
        return `
            <div class="severity-row">
                <span><span class="severity-dot" style="background:${color};"></span>${label}</span>
                <strong>${count}</strong>
            </div>`;
    }).join('');
}

function renderRecentList(items) {
    const el = document.getElementById('recent-list');
    if (!items || items.length === 0) {
        el.innerHTML = '<div class="empty-state">No activity yet.</div>';
        return;
    }
    el.innerHTML = items.map(item => {
        const date = new Date(item.created_at).toLocaleString('id-ID');
        const statusBadge = item.status === 'success'
            ? '<span class="badge badge-success">Success</span>'
            : '<span class="badge badge-error">Failed</span>';
        const codeTag = item.diagnosis_code ? `<span class="badge" style="background:rgba(59,130,246,.15);color:#60a5fa;margin-left:6px;">${escapeHtml(item.diagnosis_code)}</span>` : '';
        return `
            <div class="recent-item">
                <div>
                    <div><strong>${item.diagnosis || item.original_filename}</strong>${codeTag}</div>
                    <div class="rmeta">${item.patient_name || 'No patient'} • ${date}</div>
                </div>
                ${statusBadge}
            </div>`;
    }).join('');
}
