let __chSelectedPatientId = null;
let __chSelectedFiles = [];

const CH_FIELDS = ['identitas_pasien', 'keluhan_utama', 'pemeriksaan_fisik', 'pemeriksaan_penunjang', 'riwayat_medis', 'keterangan_lainnya'];
const CH_LABEL = { identitas_pasien: 'Patient Identity', keluhan_utama: 'Chief Complaint', pemeriksaan_fisik: 'Physical Examination', pemeriksaan_penunjang: 'Supporting Examinations', riwayat_medis: 'Medical History', keterangan_lainnya: 'Other Notes' };

// Pasien dipilih di sidebar (Nama Pasien). Tab ini tidak punya pemilih pasien sendiri.
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-ch-upload').addEventListener('click', () => { logLine('Selecting clinical history files to upload'); document.getElementById('ch-file-input').click(); });
    document.getElementById('ch-file-input').addEventListener('change', onChFilesSelected);
    document.getElementById('btn-ch-ai-parse').addEventListener('click', runChAiParse);
    document.getElementById('btn-ch-save').addEventListener('click', saveChManual);
});

async function loadClinicalHistoryView() {
    try { if (typeof cpFlush === 'function') await cpFlush(); } catch (e) { /* abaikan */ }
    await onChPatientChange();
    // Profil Klinis Terstruktur (dulu di tab Care dan Follow-Up Plan) dimuat di bagian bawah tab ini
    const empty = document.getElementById('cp-empty');
    if (empty) empty.style.display = currentPatientId() ? 'none' : '';
    if (typeof cpLoad === 'function') await cpLoad();
}

async function onChPatientChange() {
    __chSelectedPatientId = currentPatientId() || null;
    __chSelectedFiles = [];
    document.getElementById('ch-upload-status').textContent = '';
    document.getElementById('btn-ch-ai-parse').disabled = true;

    if (!__chSelectedPatientId) {
        document.getElementById('ch-empty-hint').style.display = '';
        document.getElementById('ch-form-grid').style.display = 'none';
        document.getElementById('ch-save-row').style.display = 'none';
        logLine('Clinical History is waiting for a patient to be selected in the sidebar');
        return;
    }

    document.getElementById('ch-empty-hint').style.display = 'none';
    document.getElementById('ch-form-grid').style.display = 'grid';
    document.getElementById('ch-save-row').style.display = 'flex';

    try {
        logLine(`Loading patient clinical history: ${currentPatientName()}`);
        const ch = await apiFetch(`/api/clinical-history/${__chSelectedPatientId}`);
        CH_FIELDS.forEach(f => {
            document.getElementById(`ch-${f}`).value = ch[f] || '';
        });
        const filled = CH_FIELDS.filter(f => (ch[f] || '').trim()).map(f => CH_LABEL[f]);
        logLine(`Clinical history loaded: ${filled.length} of ${CH_FIELDS.length} categories filled${filled.length ? ' (' + filled.join(', ') + ')' : ''}`, 'ok');
    } catch (e) {
        showToast(`Failed to load clinical history: ${e.message}`, 'error');
    }
}

function onChFilesSelected(e) {
    __chSelectedFiles = Array.from(e.target.files || []);
    document.getElementById('btn-ch-ai-parse').disabled = __chSelectedFiles.length === 0 || !__chSelectedPatientId;
    document.getElementById('ch-upload-status').textContent = __chSelectedFiles.length
        ? `${__chSelectedFiles.length} file(s) ready for AI splitting: ${__chSelectedFiles.map(f => f.name).join(', ')}`
        : '';
    if (__chSelectedFiles.length) logLine(`${__chSelectedFiles.length} clinical history file(s) selected: ${__chSelectedFiles.map(f => f.name).join(', ')}`);
}

async function runChAiParse() {
    if (!__chSelectedPatientId || __chSelectedFiles.length === 0) return;

    const apiKey = document.getElementById('api-key').value.trim();
    const model = document.getElementById('model-select').value;
    if (!apiKey && !window.__routerKeyManaged) {
        showToast('Enter the 9Router API Key in the API box in the sidebar first.', 'error');
        return;
    }

    const statusEl = document.getElementById('ch-upload-status');
    statusEl.textContent = 'Processing with AI...';
    document.getElementById('btn-ch-ai-parse').disabled = true;
    logLine(`AI splitting ${__chSelectedFiles.length} file(s) into six categories, model ${model}`, 'head');

    try {
        const fd = new FormData();
        __chSelectedFiles.forEach(f => fd.append('files', f));
        fd.append('model', model);
        if (apiKey) fd.append('authorization', `Bearer ${apiKey}`);

        const ch = await apiFetch(`/api/clinical-history/${__chSelectedPatientId}/ai-parse`, { method: 'POST', body: fd });
        CH_FIELDS.forEach(f => {
            document.getElementById(`ch-${f}`).value = ch[f] || '';
        });
        statusEl.textContent = 'Automatically split by AI. Review & save if correct.';
        showToast(`Clinical history automatically split by AI: ${CH_FIELDS.filter(f => (ch[f] || '').trim()).length} categories filled.`, 'success');
    } catch (e) {
        statusEl.textContent = '';
        showToast(`AI processing failed: ${e.message}`, 'error');
    }
    document.getElementById('btn-ch-ai-parse').disabled = __chSelectedFiles.length === 0;
}

async function saveChManual() {
    if (!__chSelectedPatientId) return;
    const payload = {};
    CH_FIELDS.forEach(f => { payload[f] = document.getElementById(`ch-${f}`).value; });
    try {
        logLine(`Saving patient clinical history: ${currentPatientName()}`);
        await apiFetch(`/api/clinical-history/${__chSelectedPatientId}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
        });
        showToast('Clinical history saved.', 'success');
    } catch (e) {
        showToast(`Failed to save: ${e.message}`, 'error');
    }
}
