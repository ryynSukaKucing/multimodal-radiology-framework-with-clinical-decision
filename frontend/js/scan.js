// ===== State (frame/pasien/hasil). Engine viewer ada di viewer.js =====
let __frames = [];         // lihat makeFrame() di viewer.js
let __activeFrameId = null;
let __frameSeq = 0;
let __maximizedId = null;

// Implikasi Tujuan Analisis: judul singkat per modul, ditampilkan pada hasil diagnosis.
const IMPLIKASI_TUJUAN_LABEL = {
    otomatis: 'Analysis Purpose Implications (Automatic)',
    screening: 'Screening & Detection Implications',
    segmentation: 'Segmentation & Quantitative Analysis Implications',
    classification: 'Classification & Grading Implications',
    therapeutics: 'Therapeutics & Decision Support Implications',
    prognostics: 'Prognostics & Longitudinal Implications',
};

// ===== Snapshot setting scan per frame =====
// Tiap frame menyimpan setting yang dipakai saat dipindai (model AI, area, kode diagnosis),
// sehingga overlay info frame tidak ikut berubah saat setting global diganti untuk frame lain.
function selText(id) {
    const el = document.getElementById(id);
    const t = el && el.selectedIndex >= 0 ? (el.options[el.selectedIndex].textContent || '').trim() : '';
    return t && t !== '-' ? t : '-';
}
// ===== Objek pindai: anatomi / lesi / anatomi_lesi =====
const SCAN_TARGETS = {
    anatomi: { label: 'Anatomy', note: 'Call 1 detects organs/anatomical structures (thorax taxonomy) as boxes. Press Segmentation (call 2) to outline them; the colour legend appears on the image.' },
    lesi: { label: 'Lesions', note: 'Call 1 detects lesions as boxes with a severity score. Press Segmentation (call 2) to outline them as a severity heatmap (blue = safest, red = most severe).' },
    anatomi_lesi: { label: 'Anatomy + Lesions', note: 'Call 1 detects organs and lesions as boxes. Press Segmentation (call 2) to outline them; the anatomy legend and severity heatmap appear on the image.' },
};
function currentScanTarget() {
    const r = document.querySelector('input[name="scan-target"]:checked');
    return r ? r.value : 'anatomi_lesi';
}
function targetLabel(key) { return (SCAN_TARGETS[key] || SCAN_TARGETS.anatomi_lesi).label; }
function codeSystemLabel(key) {
    const el = document.getElementById('diagnosis-code-system-select'); if (!el) return key || 'auto';
    const o = [...el.options].find(x => x.value === key);
    return o ? o.textContent.replace(/\s*\(.*\)\s*$/, '').trim() : (key || 'auto');
}
function updateTargetNote() {
    const n = document.getElementById('scan-target-note');
    if (n) n.textContent = (SCAN_TARGETS[currentScanTarget()] || {}).note || '';
}
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input[name="scan-target"]').forEach(r => r.addEventListener('change', () => {
        updateTargetNote();
        logLine(`Objek pindai: ${targetLabel(currentScanTarget())}`, '', 'scan');
    }));
    const j = document.getElementById('jenis-pemeriksaan-select');
    if (j) j.addEventListener('change', () => logLine(`Imaging type: ${selText('jenis-pemeriksaan-select')}`, '', 'scan'));
    const c = document.getElementById('diagnosis-code-system-select');
    if (c) c.addEventListener('change', () => logLine(`Diagnosis code: ${codeSystemLabel(c.value)}`, '', 'scan'));
    updateTargetNote();
});

function currentScanCfg() {
    return {
        model: (document.getElementById('model-select') || {}).value || '-',
        jenis: selText('jenis-pemeriksaan-select'),
        area: selText('anatomical-area-select'),
        tujuan: selText('tujuan-analisis-select'),
        codeSystem: (document.getElementById('diagnosis-code-system-select') || {}).value || 'auto',
        target: currentScanTarget(),
        llmSynth: !!window.__llmSynth,
    };
}
function optTextByValue(selId, value) {
    const el = document.getElementById(selId); if (!el) return value || '-';
    const o = [...el.options].find(x => x.value === value);
    const t = o ? (o.textContent || '').trim() : (value || '');
    return t && t !== '-' ? t : '-';
}
// Setting frame riwayat (read-only) dibaca dari data yang tersimpan di server.
function cfgFromHistory(item) {
    return {
        model: (item && item.model_used) || '-',
        jenis: (item && item.jenis_pemeriksaan) || '-',
        area: (item && item.anatomical_area) || '-',
        tujuan: optTextByValue('tujuan-analisis-select', item && item.tujuan_analisis),
        codeSystem: (item && item.diagnosis_code_system) || 'auto',
        target: (item && item.mode_pindai) || 'anatomi_lesi',
        llmSynth: false,
    };
}

// ===== Severity -> warna (biru / hijau / kuning / merah) =====
function severityClass(sev) {
    const s = (sev || '').toString().toLowerCase();
    if (s.includes('tinggi') || s.includes('high') || s.includes('critical') || s.includes('darurat') || s.includes('berat')) return 'sev-red';
    if (s.includes('sedang') || s.includes('moderate') || s.includes('medium')) return 'sev-yellow';
    if (s.includes('rendah') || s.includes('low') || s.includes('mild') || s.includes('ringan')) return 'sev-green';
    return 'sev-blue';
}
function severityHex(sev) {
    const cls = severityClass(sev);
    if (cls === 'sev-red') return '#ef4444';
    if (cls === 'sev-yellow') return '#f59e0b';
    if (cls === 'sev-green') return '#22c55e';
    return '#3b82f6';
}

// ===== Derajat keparahan lesi (0..1) -> warna heatmap: biru (aman) ... merah (parah) =====
const HEAT_STOPS = [[0, '#2563eb'], [0.2, '#06b6d4'], [0.4, '#22c55e'], [0.6, '#facc15'], [0.8, '#f97316'], [1, '#dc2626']];
function heatColor(v) {
    v = Math.min(1, Math.max(0, Number(v) || 0));
    for (let i = 1; i < HEAT_STOPS.length; i++) {
        if (v <= HEAT_STOPS[i][0]) {
            const [a, ca] = HEAT_STOPS[i - 1], [b, cb] = HEAT_STOPS[i], t = (v - a) / (b - a || 1);
            const pa = [1, 3, 5].map(k => parseInt(ca.substr(k, 2), 16)), pb = [1, 3, 5].map(k => parseInt(cb.substr(k, 2), 16));
            return '#' + pa.map((x, k) => Math.round(x + (pb[k] - x) * t).toString(16).padStart(2, '0')).join('');
        }
    }
    return HEAT_STOPS[HEAT_STOPS.length - 1][1];
}
function heatGradientCss(dir) { return `linear-gradient(${dir || 'to right'}, ${HEAT_STOPS.map(s => `${s[1]} ${Math.round(s[0] * 100)}%`).join(',')})`; }
function lesionScore(item) {
    if (item && typeof item.severity_score === 'number' && isFinite(item.severity_score)) return Math.min(1, Math.max(0, item.severity_score));
    const c = severityClass(item && item.severity);     // riwayat lama tanpa skor: turunkan dari label
    return c === 'sev-red' ? 0.82 : c === 'sev-yellow' ? 0.5 : c === 'sev-green' ? 0.2 : 0.5;
}
function scoreBand(v) { return v < 0.34 ? 'Low' : v < 0.67 ? 'Moderate' : 'High'; }

async function loadPatientOptionsForScan() {
    try {
        const patients = await apiFetch('/api/patients');
        window.__scanPatients = patients;
        const select = document.getElementById('patient-select');
        const currentVal = select.value;
        select.innerHTML = '<option value="">No patient (optional)</option>' +
            patients.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (${escapeHtml(p.mrn)})</option>`).join('');
        select.value = currentVal;
        if (typeof refreshAllFrameInfo === 'function') refreshAllFrameInfo();
    } catch (e) {
        // diamkan; tidak kritikal untuk halaman scan
    }
}

function onScanPatientChange() {
    loadFramesForSelectedPatient();
    if (typeof refreshAllFrameInfo === 'function') refreshAllFrameInfo();
}

async function loadFramesForSelectedPatient() {
    const patientId = document.getElementById('patient-select').value;

    if (__frames.length > 0) {
        const proceed = confirm('Changing the patient will clear the current session images/results. Continue?');
        if (!proceed) {
            logLine('Patient change cancelled, session images kept', 'warn');
            // batalkan perpindahan: kembalikan pilihan lama tidak trivial, jadi cukup jangan reset
            return;
        }
    }
    __frames = [];
    __activeFrameId = null;
    __maximizedId = null;
    clearResultsPanel();

    if (!patientId) {
        logLine('No patient selected, canvas cleared');
        renderFrameGrid();
        renderFrameThumbList();
        return;
    }
    logLine(`Loading patient image history: ${currentPatientName()}`);

    // "memuat apa yang pasien dipilih": tampilkan riwayat pemindaian pasien ini (read-only)
    // sebagai frame awal, alih-alih membiarkan kanvas kosong / tetap memakai citra pasien lain.
    document.getElementById('status-indicator').textContent = 'Status: Loading patient image history...';
    try {
        const items = await apiFetch(`/api/history?patient_id=${patientId}`);
        const recent = items.slice(0, 6); // batasi agar grid tidak terlalu penuh
        for (const item of recent) {
            const dataUrl = await fetchAuthedImageAsDataUrl(`/api/history/${item.id}/image`);
            if (!dataUrl) continue;
            let anomalies = item.anomalies || [];
            __frames.push(makeFrame({
                id: `h${item.id}`,
                file: null,
                name: item.original_filename,
                dataUrl,
                isDicom: !!item.is_dicom,
                status: item.status === 'success' ? 'done' : 'error',
                result: { data: { diagnosis: item.diagnosis, confidence: item.confidence, summary: item.summary, anomalies, structures: item.structures || [], segmented: !!item.segmented, diagnosis_code: item.diagnosis_code, diagnosis_code_system: item.diagnosis_code_system, mode_pindai: item.mode_pindai }, history: item },
                readOnly: true,
                cfg: cfgFromHistory(item),
                patientId: item.patient_id,
                examAt: item.created_at ? new Date(item.created_at) : new Date(),
            }));
        }
        if (__frames.length > 0) {
            __activeFrameId = __frames[0].id;
            document.getElementById('status-indicator').textContent = `Status: Loaded ${__frames.length} image(s) from this patient's history. Upload a new image to scan again.`;
            logLine(`${__frames.length} patient history image(s) loaded as read-only frames (from ${items.length} saved records)`, 'ok');
        } else {
            document.getElementById('status-indicator').textContent = 'Status: This patient has no image history yet. Upload a new image to start.';
            logLine('This patient has no image history yet');
        }
    } catch (e) {
        logLine(`Failed to load patient image history: ${e.message}`, 'err');
        document.getElementById('status-indicator').textContent = 'Status: Waiting for File';
    }

    renderFrameGrid();
    renderFrameThumbList();
    renderResultsForActiveFrame();
    updateScanButtonState();
}

async function fetchAuthedImageAsDataUrl(path) {
    try {
        const res = await fetch(`${API_BASE}${path}`, { headers: { 'Authorization': `Bearer ${getToken()}` } });
        if (!res.ok) return null;
        const blob = await res.blob();
        return await new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = (ev) => resolve(ev.target.result);
            reader.readAsDataURL(blob);
        });
    } catch (e) {
        return null;
    }
}


// ===== Upload =====
document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('file-input');
    document.getElementById('btn-upload').addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFilesSelect);
    document.getElementById('btn-scan').addEventListener('click', runBatchScan);
    document.getElementById('btn-segment')?.addEventListener('click', runSegmentation);
    document.getElementById('btn-save-edit')?.addEventListener('click', saveEditedResult);
});

async function handleFilesSelect(e) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    logLine(`Uploading ${files.length} image file(s): ${files.map(f => f.name).join(', ')}`);

    for (const file of files) {
        const frame = makeFrame({
            id: `f${++__frameSeq}`, file, name: file.name,
            isDicom: file.name.toLowerCase().endsWith('.dcm'),
        });
        __frames.push(frame);

        if (frame.isDicom) {
            try {
                const formData = new FormData();
                formData.append('file', file);
                const result = await apiFetch('/api/dicom/preview', { method: 'POST', body: formData });
                frame.dataUrl = result.base64_preview;
                frame.meta = result.meta || {};
                if (frame.meta.pixel_spacing_mm) frame.pxMm = frame.meta.pixel_spacing_mm;
                logLine(`DICOM ${file.name} converted for preview${frame.meta.pixel_spacing_mm ? ', pixel spacing ' + frame.meta.pixel_spacing_mm + ' mm' : ''}`, 'ok');
            } catch (err) {
                logLine(`Failed to open DICOM ${file.name}: ${err.message}`, 'err');
                frame.status = 'error';
                frame.error = `Failed to open DICOM (${file.name}): ${err.message}`;
                showToast(frame.error, 'error');
            }
        } else {
            frame.dataUrl = await readFileAsDataUrl(file);
            logLine(`Image ${file.name} ready (${Math.round(file.size / 1024)} KB)`, 'ok');
        }
    }

    if (!__activeFrameId && __frames.length > 0) __activeFrameId = __frames[0].id;
    e.target.value = '';
    renderFrameGrid();
    renderFrameThumbList();
    syncImageSettingUI();
    updateScanButtonState();
}

function readFileAsDataUrl(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (ev) => resolve(ev.target.result);
        reader.readAsDataURL(file);
    });
}

function removeFrame(id) {
    const rf = __frames.find(f => f.id === id);
    if (rf) logLine(`Frame ${frameNo(rf)} removed from canvas: ${rf.name}`);
    __frames = __frames.filter(f => f.id !== id);
    if (__maximizedId === id) __maximizedId = null;
    if (__activeFrameId === id) __activeFrameId = __frames.length > 0 ? __frames[0].id : null;
    renderFrameGrid();
    renderFrameThumbList();
    updateScanButtonState();
    syncImageSettingUI();
    if (!__activeFrameId) clearResultsPanel(); else renderResultsForActiveFrame();
}

// ===== Mode pemindaian: semua frame / satu frame (frame yang sedang dipilih) =====
window.__scanMode = localStorage.getItem('radio_scan_mode') === 'one' ? 'one' : 'all';
function frameNo(f) { return __frames.indexOf(f) + 1; }
function updateScanModeLabel() {
    const n = __frames.filter(f => f.file).length;
    const af = __frames.find(f => f.id === __activeFrameId);
    if (typeof updateSegmentButtonState === 'function') updateSegmentButtonState();
    const lab = document.getElementById('scan-mode-label');
    if (lab) lab.textContent = window.__scanMode === 'one' ? (af ? `Frame ${frameNo(af)} only` : 'Single frame') : (n > 1 ? `All frames (${n})` : 'All frames');
    const menu = document.getElementById('scan-mode-menu'); if (!menu) return;
    menu.innerHTML = `<div class="dd-title">Scan mode</div>
        <div class="dd-item${window.__scanMode === 'all' ? ' sel' : ''}" data-mode="all"><span class="chk${window.__scanMode === 'all' ? ' on' : ''}"></span>
            <span class="lb">Scan all frames<br><small>${n} frame(s) processed at once</small></span></div>
        <div class="dd-item${window.__scanMode === 'one' ? ' sel' : ''}" data-mode="one"><span class="chk${window.__scanMode === 'one' ? ' on' : ''}"></span>
            <span class="lb">Scan a single frame only<br><small>${af ? `Frame ${frameNo(af)} (currently selected)` : 'select a frame in the photo column'}</small></span></div>`;
    menu.querySelectorAll('[data-mode]').forEach(it => it.addEventListener('click', () => {
        window.__scanMode = it.dataset.mode; localStorage.setItem('radio_scan_mode', window.__scanMode);
        logLine(`Scan mode: ${window.__scanMode === 'one' ? 'single frame only' : 'all frames'}`);
        updateScanModeLabel(); if (typeof closeDropdowns === 'function') closeDropdowns();
    }));
}
function updateScanButtonState() {
    const can = __frames.some(f => f.file);
    document.getElementById('btn-scan').disabled = !can;
    const caret = document.getElementById('btn-scan-mode'); if (caret) caret.disabled = !can;
    updateScanModeLabel();
}

// ===== Scanning: all frames at once (batch) =====
async function runBatchScan() {
    let scanFrames = __frames.filter(f => f.file); // lewati frame riwayat read-only (tidak punya file)
    if (scanFrames.length === 0) {
        showToast('No new images to scan (history frames are read-only).', 'error');
        return;
    }
    if (window.__scanMode === 'one') {
        const af = __frames.find(f => f.id === __activeFrameId);
        if (!af || !af.file) {
            showToast('The selected frame cannot be scanned (empty / read-only history). Choose another frame in the photo column.', 'error');
            return;
        }
        scanFrames = [af];
    }
    const modeText = window.__scanMode === 'one' ? `single frame (Frame ${frameNo(scanFrames[0])})` : `${scanFrames.length} frames`;

    const apiKey = document.getElementById('api-key').value.trim();
    const model = document.getElementById('model-select').value;
    const patientId = document.getElementById('patient-select').value;
    const jenisPemeriksaan = document.getElementById('jenis-pemeriksaan-select').value;
    const anatomicalArea = document.getElementById('anatomical-area-select').value;
    const tujuanAnalisis = document.getElementById('tujuan-analisis-select').value;
    const diagnosisCodeSystem = document.getElementById('diagnosis-code-system-select').value;
    const modePindai = currentScanTarget();
    const statusIndicator = document.getElementById('status-indicator');

    if (!jenisPemeriksaan) {
        showToast('Choose the imaging type first (X-Ray, CT Scan, etc.).', 'error');
        document.getElementById('jenis-pemeriksaan-select').focus();
        return;
    }
    if (!apiKey && !window.__routerKeyManaged) {
        showToast('Enter the 9Router API Key first.', 'error');
        return;
    }

    // Kunci setting frame yang dipindai kali ini. Frame lain (sudah dipindai sebelumnya) tetap memakai setting miliknya.
    const scanCfg = currentScanCfg();
    scanFrames.forEach(f => { f.cfg = scanCfg; });
    refreshAllFrameInfo();
    logLine(`Object detection started (call 1 of 2): ${modeText}, model ${model}`, 'head');
    logLine(`Patient: ${currentPatientName() || 'no patient'}`);
    logLine(`Imaging: ${jenisPemeriksaan} | Scan object: ${targetLabel(modePindai)} | Area: ${anatomicalArea || '-'} | Diagnosis code: ${codeSystemLabel(diagnosisCodeSystem)}`);
    if (window.__llmSynth) logLine('LLM Synthesis: SOAP and ICD-11 enabled');
    scanFrames.forEach(f => { f.status = 'scanning'; });
    document.getElementById('btn-scan').disabled = true;
    statusIndicator.textContent = `Status: Detecting objects in ${modeText}...`;
    renderFrameGrid();
    renderFrameThumbList();

    try {
        const fd = new FormData();
        scanFrames.forEach((f) => fd.append('files', f.file));
        fd.append('frame_labels', JSON.stringify(scanFrames.map((f) => `Frame ${frameNo(f)}`)));
        fd.append('model', model);
        if (apiKey) fd.append('authorization', `Bearer ${apiKey}`);
        if (patientId) fd.append('patient_id', patientId);
        fd.append('jenis_pemeriksaan', jenisPemeriksaan);
        fd.append('anatomical_area', anatomicalArea);
        fd.append('tujuan_analisis', tujuanAnalisis);
        fd.append('diagnosis_code_system', diagnosisCodeSystem);
        fd.append('mode_pindai', modePindai);
        fd.append('llm_synthesis', window.__llmSynth ? 'true' : 'false');
        logLine('Uploading images and waiting for the server (step log appears after the response)...');

        const res = await apiFetch('/api/scan/batch', { method: 'POST', body: fd });
        res.results.forEach((r, idx) => {
            const frame = scanFrames[idx];
            if (!frame) return;
            if (r.status === 'success') {
                frame.result = r; frame.status = 'done';
                logServer(r.log, `Frame ${frameNo(frame)}: ${frame.name}`);
                logScanSummary(frame);
            } else {
                frame.status = 'error'; frame.error = r.detail || 'Scan failed.';
                logLine(`Frame ${frameNo(frame)} failed: ${frame.error}`, 'err');
            }
        });

        const nDone = scanFrames.filter(f => f.status === 'done').length;
        statusIndicator.textContent = nDone ? 'Status: Object detection complete & saved. Press Segmentation to draw contours (call 2 of 2).' : 'Status: Scan failed.';
        logLine(`Object detection complete (call 1 of 2): ${nDone} of ${scanFrames.length} frame(s) succeeded and saved to history. Press Segmentation for contours.`, 'ok');
        if (nDone) showToast('Object detection complete. Press Segmentation to draw contours.', 'success');
    } catch (error) {
        statusIndicator.textContent = `Status Error: ${error.message}`;
        logLine('Error: ' + error.message, 'err');
        showToast(`Scan failed: ${error.message}`, 'error');
        scanFrames.forEach(f => { if (f.status === 'scanning') f.status = 'error'; });
    }

    updateScanButtonState();
    renderFrameGrid();
    renderFrameThumbList();
    renderResultsForActiveFrame();
}

// ===== Segmentasi: panggilan 2 dari 2 (kontur untuk objek yang sudah dideteksi) =====
let __segmenting = false;
function frameIsSegmented(f) {
    const d = f && f.result && f.result.data; if (!d) return false;
    if (d.segmented === true) return true;
    return (d.anomalies || []).some(a => a.polygon) || (d.structures || []).some(s => (s.polygon || s.polyline) && !s.derived);
}
function frameCanSegment(f) {
    const h = f && f.result && f.result.history, d = f && f.result && f.result.data;
    if (!f || f.status !== 'done' || !d || !h || !h.id || frameIsSegmented(f)) return false;
    return (d.anomalies || []).some(a => a.box) || (d.structures || []).some(s => s.box && !s.derived);
}
function segmentTargets() {
    if (window.__scanMode === 'one') {
        const af = __frames.find(f => f.id === __activeFrameId);
        return af && frameCanSegment(af) ? [af] : [];
    }
    return __frames.filter(frameCanSegment);
}
function updateSegmentButtonState() {
    const btn = document.getElementById('btn-segment'); if (!btn) return;
    const lab = document.getElementById('segment-label');
    const t = segmentTargets();
    btn.disabled = __segmenting || t.length === 0;
    if (!lab) return;
    if (__segmenting) lab.textContent = 'Memproses...';
    else if (t.length) lab.textContent = window.__scanMode === 'one' ? `Frame ${frameNo(t[0])} ready` : `${t.length} frames ready`;
    else lab.textContent = __frames.some(f => f.result && f.result.data) ? 'Already segmented' : 'Run detection first';
}

async function runSegmentation() {
    const targets = segmentTargets();
    if (targets.length === 0) {
        showToast('No detection results are waiting for segmentation. Run object detection first.', 'error');
        return;
    }
    const apiKey = document.getElementById('api-key').value.trim();
    const model = document.getElementById('model-select').value;
    if (!apiKey && !window.__routerKeyManaged) {
        showToast('Enter the 9Router API Key first.', 'error');
        return;
    }
    const statusIndicator = document.getElementById('status-indicator');
    __segmenting = true;
    targets.forEach(f => { f.status = 'scanning'; });
    document.getElementById('btn-scan').disabled = true;
    updateSegmentButtonState();
    renderFrameGrid();
    renderFrameThumbList();
    logLine(`Segmentation started (call 2 of 2): ${targets.length} frame(s), model ${model}`, 'head');

    let ok = 0;
    for (let i = 0; i < targets.length; i++) {
        const frame = targets[i];
        statusIndicator.textContent = `Status: Segmenting frame ${frameNo(frame)} (${i + 1} of ${targets.length})...`;
        try {
            const fd = new FormData();
            fd.append('model', model);
            if (apiKey) fd.append('authorization', `Bearer ${apiKey}`);
            const r = await apiFetch(`/api/scan/${frame.result.history.id}/segment`, { method: 'POST', body: fd });
            frame.result.data = Object.assign({}, frame.result.data, r.data);
            frame.result.history = r.history;
            logServer(r.log, `Frame ${frameNo(frame)} segmentation: ${frame.name}`);
            const an = frame.result.data.anomalies || [], st = frame.result.data.structures || [];
            logLine(`Frame ${frameNo(frame)} segmentation: ${an.filter(a => a.polygon).length} lesion outlines (heatmap) + ${st.filter(x => (x.polygon || x.polyline) && !x.derived).length} anatomy outlines/lines`, 'ok');
            ok++;
        } catch (e) {
            logLine(`Frame ${frameNo(frame)} segmentation failed: ${e.message}`, 'err');
            showToast(`Frame ${frameNo(frame)} segmentation failed: ${e.message}`, 'error');
        }
        frame.status = 'done';        // hasil deteksi tetap utuh walau segmentasi gagal
    }

    __segmenting = false;
    statusIndicator.textContent = ok ? `Status: Segmentation complete (${ok} of ${targets.length} frame(s)) & saved to history.` : 'Status: Segmentation failed. Detection results unchanged; press Segmentation to retry.';
    if (ok) showToast(`Segmentation complete (${ok} frame(s)).`, 'success');
    updateScanButtonState();
    renderFrameGrid();
    renderFrameThumbList();
    renderResultsForActiveFrame();
    refreshAllFrameInfo();
}

function logScanSummary(frame) {
    const d = frame.result && frame.result.data; if (!d) return;
    const an = d.anomalies || [];
    const conf = '';
    const st = d.structures || [];
    logLine(`Frame ${frameNo(frame)} object detection: ${an.filter(a => a.box).length} lesions + ${st.filter(x => x.box && !x.derived).length} anatomy (segmentation not run yet)`);
    logLine(`Frame ${frameNo(frame)} result: ${d.diagnosis || 'unidentified'}${d.diagnosis_code ? ' (' + d.diagnosis_code + ')' : ''}${conf}, ${an.length} findings${an.length ? ': ' + an.map(a => a.label || 'Abnormality').join(', ') : ''}`, 'ok');
}

// ===== Klik objek pada citra -> otomatis masuk ke Temuan =====
function tryConfirmFindingAtPoint(frameId, xNorm, yNorm) {
    const frame = __frames.find(f => f.id === frameId);
    if (!frame || !frame.result || !frame.result.data) return;
    const anomalies = frame.result.data.anomalies || [];
    const pad = 0.015;
    const idx = anomalies.findIndex(a => a.box &&
        xNorm >= a.box.xmin - pad && xNorm <= a.box.xmax + pad &&
        yNorm >= a.box.ymin - pad && yNorm <= a.box.ymax + pad);
    if (idx === -1) return;
    anomalies[idx].confirmed = true;
    logLine(`Finding confirmed by clicking on the image: ${anomalies[idx].label || 'Abnormality'}`);
    drawFrameAnnotations(frameId);
    if (frameId === __activeFrameId) renderResultsForActiveFrame();
    showToast(`Added to Findings: ${anomalies[idx].label || 'Abnormality'}`, 'success');
    if (typeof openFindingInsight === 'function') openFindingInsight(frameId, idx);
}

// ===== Results panel =====
function clearResultsPanel() {
    document.getElementById('results-content').style.display = 'none';
    document.getElementById('results-frame-tag').textContent = '';
}

function renderResultsForActiveFrame() {
    const frame = __frames.find(f => f.id === __activeFrameId);
    if (!frame || !frame.result || !frame.result.data) {
        clearResultsPanel();
        return;
    }
    const idx = __frames.indexOf(frame);
    const tk = (frame.result.data && frame.result.data.mode_pindai) || (frame.cfg && frame.cfg.target);
    document.getElementById('results-frame-tag').textContent = `- Frame ${idx + 1} (${frame.name})${tk ? ' · ' + targetLabel(tk) : ''}`;
    renderScanResults(frame.result.data, frame.result.history);
}

function renderScanResults(data, historyItem) {
    document.getElementById('results-content').style.display = 'flex';
    document.getElementById('diag-title').textContent = data.diagnosis || 'Unidentified';
    document.getElementById('diag-title').className = `diag-title ${severityClass((data.anomalies || [])[0] && (data.anomalies[0]).severity)}`;

    document.getElementById('diag-summary').textContent = data.summary || '-';

    const codeEl = document.getElementById('diag-code');
    let codeText = data.diagnosis_code ? `Code: ${data.diagnosis_code}` : '';
    if (data.diagnosis_code_verified === true) codeText += ' (verified in Diagnosis Database)';
    if (data.diagnosis_code_verified === false) codeText += ' (not found in Diagnosis Database)';
    if (codeText) { codeEl.textContent = codeText; codeEl.style.display = ''; }
    else { codeEl.textContent = ''; codeEl.style.display = 'none'; }
    if (data.diagnosis_code_system) {
        document.getElementById('diagnosis-code-system-select').value = mapCodeSystemBack(data.diagnosis_code_system);
    }

    // Diagnosis Alternatif
    const altEl = document.getElementById('diag-alt-content');
    const alts = data.diagnosis_alternatif || [];
    altEl.innerHTML = alts.length
        ? alts.map(a => `<div class="alt-item">- ${escapeHtml(typeof a === 'string' ? a : (a.label || JSON.stringify(a)))}</div>`).join('')
        : '-';

    // Temuan: chip berwarna per anomali (biru/hijau/kuning/merah), diklik = fokus di Detail Kelainan
    const anomalies = data.anomalies || [];
    const chipsEl = document.getElementById('temuan-chips');
    chipsEl.innerHTML = anomalies.length
        ? anomalies.map((item, i) => {
            const cls = severityClass(item.severity);
            const sourceTag = item.source && item.source !== 'llm' ? ` · ${escapeHtml(item.source)}` : '';
            const sc = lesionScore(item);
            return `<span class="temuan-chip ${cls}${item.confirmed ? ' confirmed' : ''}" data-jump="${i}">
                <span class="sev-dot ${cls}" style="background:${heatColor(sc)}"></span>${escapeHtml(item.label || 'Abnormality')} <small>${sc.toFixed(2)}</small>${sourceTag}${item.confirmed ? ' (confirmed)' : ''}
            </span>`;
        }).join('')
        : '<span class="temuan-chips-empty">No findings yet. Click an object on the image (Select mode) to mark it.</span>';
    chipsEl.querySelectorAll('[data-jump]').forEach(chip => {
        chip.addEventListener('click', () => {
            const li = document.querySelector(`.anomalies-list li[data-idx="${chip.dataset.jump}"]`);
            if (li) { li.scrollIntoView({ behavior: 'smooth', block: 'center' }); li.classList.add('flash'); setTimeout(() => li.classList.remove('flash'), 900); }
        });
    });

    const anomaliesList = document.getElementById('anomalies-list');
    anomaliesList.innerHTML = '';
    anomalies.forEach((item, i) => {
        const cls = severityClass(item.severity);
        const li = document.createElement('li');
        li.dataset.idx = i;
        const score = lesionScore(item);
        li.style.borderLeft = `3px solid ${heatColor(score)}`;
        li.style.paddingLeft = '8px';
        const sourceTag = item.source ? `<span class="anno-source-tag">${escapeHtml(item.source)}</span>` : '';
        const fixTag = (item.koreksi_lateralitas || item.koreksi_zona) ? ' \u2713 side/zone adjusted to match the position on the image' : '';
        const locTag = item.lokasi_label ? `<span class="anno-source-tag" title="Anatomical location (Thorax_Anatomy_Taxonomy)${fixTag ? ' ' + escapeHtml(fixTag) : ''}">Location: ${escapeHtml(item.lokasi_label)}${item.koreksi_lateralitas || item.koreksi_zona ? ' \u2713' : ''}</span>` : '';
        const mlTag = (typeof item.ml_risk_score === 'number') ? `<span class="anno-source-tag">ML: ${(item.ml_risk_score * 100).toFixed(0)}%</span>` : '';
        li.innerHTML = `<strong class="aedit ${cls}" contenteditable="true" data-field="label" data-idx="${i}">${escapeHtml(item.label || 'Abnormality')}</strong>
            (<span class="aedit" contenteditable="true" data-field="severity" data-idx="${i}">${escapeHtml(item.severity || 'Unspecified')}</span>,
            grade <span class="aedit sev-score" contenteditable="true" data-field="severity_score" data-idx="${i}" title="Severity grade 0-1 (0 = safe, 1 = most severe); determines the heatmap colour" style="background:${heatColor(score)}33;border-radius:3px;padding:0 4px;">${score.toFixed(2)}</span>):
            <span class="aedit" contenteditable="true" data-field="description" data-idx="${i}">${escapeHtml(item.description || '-')}</span>${sourceTag}${mlTag}${locTag}`;
        anomaliesList.appendChild(li);
    });

    const tujuan = (historyItem && historyItem.tujuan_analisis) || document.getElementById('tujuan-analisis-select').value || 'otomatis';
    renderExtraFields(data, tujuan);

    // history id tracked for "Save Changes"
    document.getElementById('results-content').dataset.historyId = historyItem ? historyItem.id : '';
}

function mapCodeSystemBack(val) {
    const v = (val || '').toLowerCase().replace(/[\s-]/g, '');
    if (v.includes('icd10')) return 'icd10';
    if (v.includes('icd11')) return 'icd11';
    if (v.includes('snomed')) return 'snomed';
    if (v.includes('sdki')) return 'sdki';
    if (v.includes('nanda')) return 'nanda';
    return 'auto';
}

// Model kadang mengirim string/objek, bukan array: jangan sampai .map() menggagalkan seluruh tampilan hasil.
const toArr = (v) => Array.isArray(v) ? v : (v && typeof v === 'object' ? [v] : (v ? [String(v)] : []));

const EXTRA_FIELD_RENDERERS = {
    detections: (v) => `<ul class="anomalies-list">${toArr(v).map(d => `<li>${escapeHtml(d.label || '-')} - score ${(d.score ? (d.score * 100).toFixed(0) : '-')}%</li>`).join('')}</ul>`,
    measurements: (v) => `<ul class="anomalies-list">${toArr(v).map(m => `<li>${escapeHtml(m.structure || '-')}: ${m.volume_ml ? m.volume_ml + ' mL' : ''} ${m.area_cm2 ? m.area_cm2 + ' cm²' : ''} ${m.density_hu ? m.density_hu + ' HU' : ''}</li>`).join('')}</ul>`,
    grading: (v) => v ? `<p>System: ${escapeHtml(v.system || '-')} | Score: ${escapeHtml(String(v.score || '-'))} | Category: ${escapeHtml(v.category || '-')}</p>` : '',
    recommendations: (v) => `<ul class="anomalies-list">${toArr(v).map(r => `<li>${escapeHtml(typeof r === 'string' ? r : (r.step || JSON.stringify(r)))}</li>`).join('')}</ul>`,
    progression: (v) => v ? `<p>ΔVolume: ${v.delta_volume_ml ?? '-'} mL | Tren: ${escapeHtml(v.trend || '-')} | RECIST: ${escapeHtml(v.recist_category || '-')}</p>` : '',
    analysis_note: (v) => `<p>${escapeHtml(v || '')}</p>`,
    soap: (v) => v ? `<div class="soap">${[['S', 'subjective'], ['O', 'objective'], ['A', 'assessment'], ['P', 'plan']].map(([l, k]) => v[k] ? `<p><b>${l} - ${k}:</b> ${escapeHtml(v[k])}</p>` : '').join('')}</div>` : '',
    medical_findings: (v) => `<p><b>TorchXRayVision:</b> ${toArr(v).map(m => `${escapeHtml(m.pathology)} ${(m.score * 100).toFixed(0)}%`).join(' · ')}</p>`,
    catatan_parser: (v) => `<p style="color:#fbbf24;">Warning: ${escapeHtml(v || '')}</p>`,
    needs_review: (v) => v ? `<p style="color:#fbbf24;"><b>Unverified result:</b> the model did not return structured data, so the content below is only a text summary without locations. Check manually or repeat the scan.</p>` : '',
    diagnosis_perlu_verifikasi: (v) => v ? `<p style="color:#fbbf24;"><b>Diagnosis needs manual verification:</b> not yet supported by findings that passed validation, confidence lowered.</p>` : '',
    catatan_sinkron: (v) => `<p style="color:#fbbf24;">${escapeHtml(v || '')}</p>`,
    catatan_lateralitas: (v) => `<p style="color:#fbbf24;"><b>Left/right:</b> ${escapeHtml(v || '')}</p>`,
    structures_dibuang: (v) => toArr(v).length ? `<p style="color:#fbbf24;"><b>Structures discarded:</b> ${toArr(v).map(d => escapeHtml(typeof d === 'string' ? d : `${d.label || '-'} (${d.alasan || '-'})`)).join('; ')}</p>` : '',
};

function renderExtraFields(data, tujuan) {
    const box = document.getElementById('extra-fields-box');
    const content = document.getElementById('extra-fields-content');
    document.getElementById('extra-fields-label').textContent = (IMPLIKASI_TUJUAN_LABEL[tujuan] || IMPLIKASI_TUJUAN_LABEL.otomatis) + ':';
    let html = '';
    Object.keys(EXTRA_FIELD_RENDERERS).forEach(key => {
        if (data[key] !== undefined && data[key] !== null && data[key] !== '') {
            try { html += EXTRA_FIELD_RENDERERS[key](data[key]); } catch (e) { /* satu bidang tambahan rusak tidak boleh menggagalkan hasil */ }
        }
    });
    if (html) {
        content.innerHTML = html;
        box.style.display = '';
    } else {
        box.style.display = 'none';
    }
}

async function saveEditedResult() {
    const frame = __frames.find(f => f.id === __activeFrameId);
    const historyId = document.getElementById('results-content').dataset.historyId;
    if (!frame || !historyId) {
        showToast('There is no saved scan result to edit on this frame.', 'error');
        return;
    }
    const diagnosis = document.getElementById('diag-title').textContent.trim();
    const summary = document.getElementById('diag-summary').textContent.trim();
    const anomalies = (frame.result.data.anomalies || []).map((item, i) => {
        const q = (field) => document.querySelector(`.aedit[data-field="${field}"][data-idx="${i}"]`);
        let sc = item.severity_score;
        if (q('severity_score')) {
            const v = parseFloat(String(q('severity_score').textContent).replace(',', '.'));
            if (isFinite(v)) sc = Math.min(1, Math.max(0, v > 1 && v <= 100 ? v / 100 : v));
        }
        const scoreChanged = typeof sc === 'number' && sc !== item.severity_score;
        return {
            ...item,
            label: q('label') ? q('label').textContent.trim() : item.label,
            severity: scoreChanged ? scoreBand(sc) : (q('severity') ? q('severity').textContent.trim() : item.severity),
            severity_score: typeof sc === 'number' ? Math.round(sc * 1000) / 1000 : item.severity_score,
            description: q('description') ? q('description').textContent.trim() : item.description,
        };
    });

    try {
        logLine(`Saving diagnosis result changes: ${diagnosis}`);
        await apiFetch(`/api/history/${historyId}`, {
            method: 'PUT',
            body: JSON.stringify({ diagnosis, summary, anomalies }),
        });
        frame.result.data.diagnosis = diagnosis;
        frame.result.data.summary = summary;
        frame.result.data.anomalies = anomalies;
        showToast('Perubahan tersimpan.', 'success');
        drawFrameAnnotations(frame.id);
        renderResultsForActiveFrame();
    } catch (e) {
        showToast(`Failed to save changes: ${e.message}`, 'error');
    }
}
