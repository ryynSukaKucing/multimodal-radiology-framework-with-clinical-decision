let __historyCache = [];

async function loadHistory() {
    logLine('Loading scan history');
    try {
        const items = await apiFetch('/api/history');
        __historyCache = items;
        renderHistoryTable(items);
        const ok = items.filter(i => i.status === 'success').length;
        logLine(`Scan history loaded: ${items.length} records, ${ok} succeeded, ${items.length - ok} failed`, 'ok');
    } catch (e) {
        showToast(`Failed to load history: ${e.message}`, 'error');
    }
}

function renderHistoryTable(items) {
    const tbody = document.getElementById('history-tbody');
    const emptyState = document.getElementById('history-empty');

    if (!items || items.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }
    emptyState.style.display = 'none';

    tbody.innerHTML = items.map(item => {
        const date = new Date(item.created_at).toLocaleString('en-US');
        const statusBadge = item.status === 'success'
            ? '<span class="badge badge-success">Success</span>'
            : '<span class="badge badge-error">Failed</span>';
        const dicomTag = item.is_dicom ? ' [DICOM]' : '';
        const codeTag = item.diagnosis_code ? `<div class="rmeta">${escapeHtml(item.diagnosis_code)}</div>` : '';
        return `
            <tr>
                <td>${date}</td>
                <td>${escapeHtml(item.patient_name || '-')}</td>
                <td class="wrap">${escapeHtml(item.original_filename)}${dicomTag}</td>
                <td class="wrap">${escapeHtml(item.diagnosis || '-')}${codeTag}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="row-actions">
                        <button type="button" class="btn-secondary btn-sm" onclick="viewHistoryDetail(${item.id})">View</button>
                        <button type="button" class="btn-danger btn-sm" onclick="deleteHistory(${item.id})">Delete</button>
                    </div>
                </td>
            </tr>`;
    }).join('');
}

function viewHistoryDetail(id) {
    const item = __historyCache.find(x => x.id === id);
    if (!item) return;
    logLine(`Opening scan history details: ${item.original_filename}${item.patient_name ? ' (' + item.patient_name + ')' : ''}`);

    const date = new Date(item.created_at).toLocaleString('en-US');
    const anomaliesHtml = (item.anomalies || []).length
        ? `<ul class="anomalies-list">${item.anomalies.map(a =>
            `<li><strong>${escapeHtml(a.label || 'Abnormality')}</strong> (${escapeHtml(a.severity || '-')}): ${escapeHtml(a.description || '-')}</li>`
          ).join('')}</ul>`
        : '<p style="color:var(--text-secondary);font-size:.85rem;">No abnormalities detected.</p>';

    document.getElementById('history-detail-body').innerHTML = `
        <div style="margin-bottom:14px;">
            <img src="/api/history/${item.id}/image" style="max-width:100%;border-radius:8px;border:1px solid var(--border-color);" onerror="this.style.display='none'">
        </div>
        <div class="field"><label>Patient</label><div>${escapeHtml(item.patient_name || 'No patient')}</div></div>
        <div class="field"><label>Date</label><div>${date}</div></div>
        <div class="field"><label>AI Model</label><div>${escapeHtml(item.model_used)}</div></div>
        <div class="field"><label>Diagnosis</label><div><strong>${escapeHtml(item.diagnosis || '-')}</strong></div></div>
        ${item.diagnosis_code ? `<div class="field"><label>Diagnosis Code (${escapeHtml((item.diagnosis_code_system || 'auto').toUpperCase())})</label><div>${escapeHtml(item.diagnosis_code)}</div></div>` : ''}
        <div class="field"><label>Analysis Purpose</label><div>${escapeHtml(item.tujuan_analisis || 'otomatis')}</div></div>
        <div class="field"><label>Summary</label><div>${escapeHtml(item.summary || '-')}</div></div>
        <div class="field"><label>Detected Abnormalities</label>${anomaliesHtml}</div>
        ${item.status !== 'success' ? `<div class="field"><label>Error Message</label><div style="color:var(--accent-red);">${escapeHtml(item.error_message)}</div></div>` : ''}
    `;
    document.getElementById('history-modal').classList.add('active');
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-close-history').addEventListener('click', () => {
        document.getElementById('history-modal').classList.remove('active');
        logLine('Scan history details closed');
    });
});

async function deleteHistory(id) {
    if (!confirm('Delete this scan history and its image file?')) { logLine('Scan history deletion cancelled'); return; }
    try {
        logLine(`Deleting scan history # ${id}`);
        await apiFetch(`/api/history/${id}`, { method: 'DELETE' });
        showToast('History deleted successfully.', 'success');
        loadHistory();
    } catch (e) {
        showToast(`Failed to delete: ${e.message}`, 'error');
    }
}
