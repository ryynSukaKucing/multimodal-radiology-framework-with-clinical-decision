// =====================================================================
//  Peta Opsi Hasil Pemindaian ("Area Pemindaian"): klik temuan pada citra
//  membuka 7 opsi (tumpukan kotak tanpa garis penghubung) di samping kotak temuan, uraian tampil di panel kiri.
//  Klik cabang untuk memuat uraian AI; uraian tampil sebagai kartu mengambang di samping node yang diklik.
//  Hasil disimpan pada anomaly.insights[branchKey] dan di server (riwayat pemindaian).
// =====================================================================
let __imCatalog = null;
const __im = { frameId: null, idx: -1, branch: null, item: null, busy: {}, cancelAll: false, pos: null, fs: 1 };
try { const v = parseFloat(localStorage.getItem('radio_im_fs')); if (v >= 0.8 && v <= 1.6) __im.fs = v; } catch (e) { /* abaikan */ }

function findingIndexAt(frame, n) {
    const anomalies = (frame.result && frame.result.data && frame.result.data.anomalies) || [];
    const pad = 0.01;
    let best = -1, bestArea = Infinity;
    anomalies.forEach((a, i) => {
        if (!a.box) return;
        const b = a.box;
        if (n[0] >= b.xmin - pad && n[0] <= b.xmax + pad && n[1] >= b.ymin - pad && n[1] <= b.ymax + pad) {
            const area = (b.xmax - b.xmin) * (b.ymax - b.ymin);
            if (area < bestArea) { best = i; bestArea = area; }
        }
    });
    return best;
}

async function imLoadCatalog() {
    if (__imCatalog) return __imCatalog;
    const res = await apiFetch('/api/insight/catalog');
    __imCatalog = res.branches || [];
    return __imCatalog;
}

function imCurrent() {
    const frame = __frames.find(f => f.id === __im.frameId);
    const anomalies = (frame && frame.result && frame.result.data && frame.result.data.anomalies) || [];
    return { frame, anomaly: anomalies[__im.idx] };
}

async function openFindingInsight(frameId, idx) {
    const frame = __frames.find(f => f.id === frameId);
    const anomaly = frame && frame.result && frame.result.data && (frame.result.data.anomalies || [])[idx];
    if (!anomaly) { showToast('Finding not found.', 'error'); return; }
    if (__im.frameId !== frameId || __im.idx !== idx) __im.pos = null, __im.stackPos = null;   // temuan lain: posisi panel kembali otomatis
    __im.frameId = frameId; __im.idx = idx; __im.branch = null; __im.item = null; __im.busy = {}; __im.cancelAll = false;
    logLine(`Option map opened for finding: ${anomaly.label || 'Abnormality'} (${anomaly.severity || 'no severity'}) on Frame ${__frames.indexOf(frame) + 1}`);

    document.getElementById('im-title').textContent = anomaly.label || 'Abnormality';
    const data = frame.result.data;
    const hist = frame.result.history || {};
    const pid = imPatientId(frame);
    const pname = (window.__scanPatients || []).find(p => String(p.id) === String(pid));
    const sevCls = severityClass(anomaly.severity);
    document.getElementById('im-sub').innerHTML =
        `<span class="temuan-chip ${sevCls}"><span class="sev-dot ${sevCls}"></span>${escapeHtml(anomaly.severity || 'Unspecified')}</span>` +
        `<span>Diagnosis: ${escapeHtml(data.diagnosis || '-')}</span>` +
        `<span>${pname ? 'Patient: ' + escapeHtml(pname.name) : 'No patient (general analysis)'}</span>` +
        (hist.jenis_pemeriksaan || hist.anatomical_area ? `<span>${escapeHtml([hist.jenis_pemeriksaan, hist.anatomical_area].filter(Boolean).join(' / '))}</span>` : '');
    document.getElementById('im-progress').textContent = '';
    imCloseDetail();
    // frame kecil (grid banyak frame): perbesar dulu agar peta muat di atas citra yang sama
    __im.autoMax = false;
    const cellEl = cellOf(frameId);
    {
        const area = cellEl && cellEl.querySelector('.frame-area');
        if (area && (area.clientWidth < 620 || area.clientHeight < 440) && __maximizedId !== frameId) {
            __maximizedId = frameId; __im.autoMax = true; renderFrameGrid();
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        }
    }
    imPlacePanel();
    document.getElementById('insight-modal').classList.add('active');
    document.getElementById('rv-viewer').classList.add('im-open');
    imApplyFs();
    imPlacePanel();
    drawFrameAnnotations(frameId);

    try {
        await imLoadCatalog();
        imRenderMap();
    } catch (e) {
        document.getElementById('im-map').innerHTML = `<div class="empty-state">Failed to load option map: ${escapeHtml(e.message)}</div>`;
    }
}

function imPatientId(frame) {
    const hist = (frame && frame.result && frame.result.history) || {};
    return hist.patient_id || frame.patientId || document.getElementById('patient-select').value || '';
}

function imDetailEmpty() {
    return `<div class="im-detail-empty">
        <strong>Select a branch or sub-option on the map.</strong>
        <p>The AI will elaborate on that part for this finding, tailored to the patient's clinical history and clinical profile when available.</p>
    </div>`;
}

// ------------------------------------------------------------------ peta
function imNodeState(branchKey) {
    const { anomaly } = imCurrent();
    const loaded = !!(anomaly && anomaly.insights && anomaly.insights[branchKey]);
    const busy = !!__im.busy[branchKey];
    return busy ? 'busy' : (loaded ? 'loaded' : '');
}

function imGroupHtml(b) {
    const st = imNodeState(b.key);
    return `<button type="button" class="im-node im-branch-node ${st}${__im.branch === b.key ? ' sel' : ''}" data-branch="${b.key}" id="imb-${b.key}">
        <span>${escapeHtml(b.label)}</span><i class="im-dot" title="${st === 'loaded' ? 'Analyzed' : st === 'busy' ? 'Analyzing' : 'Not analyzed'}"></i></button>`;
}

function imRenderMap() {
    document.getElementById('im-map').innerHTML = `
        <div class="im-stack" id="im-stack"><div class="im-stack-grip" id="im-stack-grip" title="Drag to move. Double-click to reset."><i class="im-grip"></i>Analysis Options</div>${(__imCatalog || []).map(imGroupHtml).join('')}</div>`;
    document.querySelectorAll('#im-map .im-node[data-branch]').forEach(n => {
        n.addEventListener('click', () => imSelect(n.dataset.branch, null));
    });
    imRenderDetail();
    imInitStackDrag();
    imPlacePanel();
}

function imRefreshStates() {
    (__imCatalog || []).forEach(b => {
        const el = document.getElementById(`imb-${b.key}`);
        if (!el) return;
        const st = imNodeState(b.key);
        el.classList.remove('loaded', 'busy');
        if (st) el.classList.add(st);
        el.classList.toggle('sel', __im.branch === b.key);
    });
    
}

function imIsOpen() { return document.getElementById('insight-modal').classList.contains('active'); }
window.addEventListener('resize', () => { if (imIsOpen()) imPlacePanel(); });
document.addEventListener('DOMContentLoaded', () => {
    const v = document.getElementById('rv-viewer');
    if (v && window.ResizeObserver) new ResizeObserver(() => { if (imIsOpen()) imPlacePanel(); }).observe(v);
});

// Posisikan overlay tepat di atas area citra frame, dan kotak "Area Pemindaian" tepat di atas lokasi temuan.
function imBoxRect(frame, cell, box) {
    const area = cell.querySelector('.frame-area'), r = area.getBoundingClientRect(), v = frame.view, f = frame._fit;
    if (!f) return null;
    const rot = (v.rotate || 0) * Math.PI / 180, cos = Math.cos(rot), sin = Math.sin(rot);
    const xs = [], ys = [];
    [[box.xmin, box.ymin], [box.xmax, box.ymin], [box.xmax, box.ymax], [box.xmin, box.ymax]].forEach(([nx, ny]) => {
        const [sx, sy] = n2s(frame, nx, ny);
        const rx = (sx - f.W / 2) * (v.flipH ? -1 : 1), ry = (sy - f.H / 2) * (v.flipV ? -1 : 1);
        const dx = rx * cos - ry * sin, dy = rx * sin + ry * cos;   // kebalikan dari clientToN
        xs.push(r.left + r.width / 2 + v.tx + dx * v.scale); ys.push(r.top + r.height / 2 + v.ty + dy * v.scale);
    });
    return { l: Math.min(...xs), r: Math.max(...xs), t: Math.min(...ys), b: Math.max(...ys) };
}

function imPlacePanel() {
    const panel = document.getElementById('insight-modal'), viewer = document.getElementById('rv-viewer');
    const { frame, anomaly } = imCurrent();
    const cell = frame && cellOf(frame.id);
    if (!panel || !viewer || !cell) return;
    const vr = viewer.getBoundingClientRect();
    const ar = cell.querySelector('.frame-area').getBoundingClientRect();
    Object.assign(panel.style, { left: `${ar.left - vr.left}px`, top: `${ar.top - vr.top}px`, width: `${ar.width}px`, height: `${ar.height}px` });
    const stack = document.getElementById('im-stack'), det = document.getElementById('im-detail');
    if (!stack || !det) return;
    const W = ar.width, H = ar.height, margin = 8, gap = 22;
    const stackW = Math.min(196, Math.max(120, W * 0.2));
    stack.style.width = `${stackW}px`;
    const sh = stack.offsetHeight;
    let boxL = W * 0.5, boxR = W * 0.5, boxT = H * 0.4, boxB = H * 0.6;
    const br = anomaly && anomaly.box ? imBoxRect(frame, cell, anomaly.box) : null;
    if (br) { boxL = br.l - ar.left; boxR = br.r - ar.left; boxT = br.t - ar.top; boxB = br.b - ar.top; }
    // tumpukan opsi menempel di sisi kanan kotak temuan (kiri bila tidak muat)
    let sx, side = 'right';
    if (boxR + gap + stackW <= W - 70) sx = boxR + gap;
    else { side = 'left'; sx = Math.max(margin, boxL - gap - stackW); }
    let sy = (boxT + boxB) / 2 - sh / 2;
    sy = Math.max(52, Math.min(H - sh - margin, sy));
    if (__im.stackPos) {
        sx = Math.max(0, Math.min(__im.stackPos.x, Math.max(0, W - stackW)));
        sy = Math.max(0, Math.min(__im.stackPos.y, Math.max(0, H - 40)));
    }
    Object.assign(stack.style, { left: `${sx}px`, top: `${sy}px` });
    // panel detail di sisi berlawanan (atau di posisi yang digeser pengguna)
    const dw = Math.min(380, Math.max(240, W * 0.32));
    if (!det.dataset.userSized) { const w0 = Math.min(dw, Math.max(160, W - 24)); det.style.width = `${w0}px`; det._autoW = w0; }
    const curW = det.getBoundingClientRect().width || dw;
    let dx = side === 'right' ? margin + 36 : W - curW - 80;
    let dy = 96;
    if (__im.pos) { dx = __im.pos.x; dy = __im.pos.y; }
    dx = Math.max(margin, Math.min(dx, Math.max(margin, W - curW - margin)));
    dy = Math.max(margin, Math.min(dy, Math.max(margin, H - 60)));
    Object.assign(det.style, { left: `${dx}px`, top: `${dy}px`, maxHeight: `${Math.max(200, H - dy - margin)}px` });
}

// ------------------------------------------------------------------ panel detail: geser, ukuran teks, ukuran panel
function imApplyFs() {
    const det = document.getElementById('im-detail'); if (det) det.style.setProperty('--im-fs', String(__im.fs));
}
function imFontStep(dir) {
    __im.fs = Math.max(0.8, Math.min(1.6, Math.round((__im.fs + dir * 0.1) * 10) / 10));
    try { localStorage.setItem('radio_im_fs', String(__im.fs)); } catch (e) { /* abaikan */ }
    imApplyFs();
    logLine(`Analysis text size: ${Math.round(__im.fs * 100)}%`);
}
// Drag the analysis-options stack by its header (delegated, bound once on the overlay).
function imInitStackDrag() {
    const panel = document.getElementById('insight-modal');
    if (!panel || panel.dataset.stackDrag) return;
    panel.dataset.stackDrag = '1';
    let drag = null;
    panel.addEventListener('pointerdown', (e) => {
        const grip = e.target.closest('#im-stack-grip');
        if (!grip || e.button !== 0) return;
        const stack = document.getElementById('im-stack'); if (!stack) return;
        const sr = stack.getBoundingClientRect();
        drag = { dx: e.clientX - sr.left, dy: e.clientY - sr.top, id: e.pointerId, grip };
        try { grip.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
        stack.classList.add('dragging'); e.preventDefault();
    });
    panel.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const stack = document.getElementById('im-stack'); if (!stack) return;
        const pr = panel.getBoundingClientRect(), w = stack.offsetWidth;
        const x = Math.max(0, Math.min(e.clientX - pr.left - drag.dx, Math.max(0, pr.width - w)));
        const y = Math.max(0, Math.min(e.clientY - pr.top - drag.dy, Math.max(0, pr.height - 40)));
        __im.stackPos = { x, y };
        Object.assign(stack.style, { left: `${x}px`, top: `${y}px` });
    });
    const end = () => {
        if (!drag) return; drag = null;
        const stack = document.getElementById('im-stack'); if (stack) stack.classList.remove('dragging');
        logLine('Analysis options moved');
    };
    panel.addEventListener('pointerup', end); panel.addEventListener('pointercancel', end);
    panel.addEventListener('dblclick', (e) => {
        if (!e.target.closest('#im-stack-grip')) return;
        __im.stackPos = null; imPlacePanel(); logLine('Analysis options position reset');
    });
}
function imResetPos() {
    const det = document.getElementById('im-detail'); if (!det) return;
    __im.pos = null; __im.stackPos = null; delete det.dataset.userSized; det.style.height = ''; det.style.width = '';
    imPlacePanel();
    logLine('Analysis panel position and size reset automatically');
}
function imInitDetailInteractions() {
    const det = document.getElementById('im-detail'), panel = document.getElementById('insight-modal');
    if (!det || !panel) return;
    let drag = null;
    det.addEventListener('pointerdown', (e) => {
        const h = e.target.closest('.im-detail-title');
        if (!h || e.target.closest('button') || e.button !== 0) return;
        const dr = det.getBoundingClientRect();
        drag = { dx: e.clientX - dr.left, dy: e.clientY - dr.top };
        try { h.setPointerCapture(e.pointerId); } catch (err) { /* abaikan */ }
        det.classList.add('dragging'); e.preventDefault();
    });
    det.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const pr = panel.getBoundingClientRect(), W = pr.width, H = pr.height, w = det.offsetWidth;
        const x = Math.max(0, Math.min(e.clientX - pr.left - drag.dx, Math.max(0, W - w)));
        const y = Math.max(0, Math.min(e.clientY - pr.top - drag.dy, Math.max(0, H - 48)));
        __im.pos = { x, y };
        Object.assign(det.style, { left: `${x}px`, top: `${y}px`, maxHeight: `${Math.max(200, H - y - 8)}px` });
    });
    const end = () => { if (!drag) return; drag = null; det.classList.remove('dragging'); logLine('Analysis panel moved'); };
    det.addEventListener('pointerup', end); det.addEventListener('pointercancel', end);
    det.addEventListener('dblclick', (e) => { if (e.target.closest('.im-detail-title') && !e.target.closest('button')) imResetPos(); });
    det.addEventListener('click', (e) => {
        const fs = e.target.closest('[data-fs]'); if (fs) { imFontStep(Number(fs.dataset.fs)); return; }
        if (e.target.closest('#im-pos-reset')) imResetPos();
    });
    if (window.ResizeObserver) new ResizeObserver(() => {
        if (!imIsOpen() || det._autoW === undefined) return;
        const w = det.getBoundingClientRect().width; if (!w) return;
        if (Math.abs(w - det._autoW) > 3) det.dataset.userSized = '1';
    }).observe(det);
}

function imCloseDetail() {
    __im.branch = null; __im.item = null;
    if (document.getElementById('im-detail') && __imCatalog) { imRenderDetail(); imRefreshStates(); }
}

// ------------------------------------------------------------------ detail & pemuatan
async function imSelect(branchKey, itemKey) {
    // klik node yang sama sekali lagi menutup kartu
    if (__im.branch === branchKey && !itemKey) { imCloseDetail(); return; }
    __im.branch = branchKey; __im.item = itemKey || null;
    imRefreshStates();
    logLine(`Analysis branch selected: ${((__imCatalog || []).find(x => x.key === branchKey) || {}).label || branchKey}`);
    const { anomaly } = imCurrent();
    if (anomaly && anomaly.insights && anomaly.insights[branchKey]) { imRenderDetail(); return; }
    document.getElementById('im-detail').innerHTML = imDetailShell(branchKey, imLoading(branchKey));
    imBindDetailX();
    await imFetchBranch(branchKey, false);
}

function imLoading(branchKey) {
    const b = (__imCatalog || []).find(x => x.key === branchKey);
    return `<div class="im-detail-empty"><div class="im-spinner"></div><p>The AI is preparing the explanation for this branch...</p></div>`;
}

async function imFetchBranch(branchKey, silent) {
    const { frame, anomaly } = imCurrent();
    if (!frame || !anomaly || __im.busy[branchKey]) return false;
    const apiKey = document.getElementById('api-key').value.trim();
    if (!apiKey && !window.__routerKeyManaged) {
        showToast('Enter the 9Router API Key in the sidebar first.', 'error');
        if (!silent) imRenderDetail('Enter the 9Router API Key in the sidebar, then click this branch again.');
        return false;
    }
    __im.busy[branchKey] = true; imRefreshStates();
    const branchLabel = ((__imCatalog || []).find(x => x.key === branchKey) || {}).label || branchKey;
    logLine(`AI analyzing branch ${branchLabel} for finding ${anomaly.label || 'Abnormality'}`);
    const hist = frame.result.history || {};
    const data = frame.result.data || {};
    const idxAtStart = __im.idx, frameAtStart = __im.frameId;
    const body = {
        branch: branchKey,
        patient_id: imPatientId(frame) ? Number(imPatientId(frame)) : null,
        history_id: hist.id || null,
        anomaly_index: idxAtStart,
        finding: { label: anomaly.label, severity: anomaly.severity, description: anomaly.description, box: anomaly.box || null },
        diagnosis: data.diagnosis || '', summary: data.summary || '',
        jenis_pemeriksaan: hist.jenis_pemeriksaan || document.getElementById('jenis-pemeriksaan-select').value || '',
        anatomical_area: hist.anatomical_area || document.getElementById('anatomical-area-select').value || '',
        model: document.getElementById('model-select').value,
        authorization: apiKey ? `Bearer ${apiKey}` : null,
    };
    let ok = false;
    try {
        const res = await apiFetch('/api/insight/generate', { method: 'POST', body: JSON.stringify(body) });
        const fr = __frames.find(f => f.id === frameAtStart);
        const an = fr && fr.result && fr.result.data && fr.result.data.anomalies && fr.result.data.anomalies[idxAtStart];
        if (an) { an.insights = an.insights || {}; an.insights[branchKey] = res; }
        ok = true;
        logLine(`Branch ${branchLabel} analysis complete${res.model ? ' (model ' + res.model + ')' : ''}`, 'ok');
    } catch (e) {
        logLine(`Branch ${branchLabel} analysis failed: ${e.message}`, 'err');
        showToast(`Failed to analyze branch: ${e.message}`, 'error');
        if (!silent && __im.branch === branchKey) imRenderDetail(`Failed: ${e.message}`);
    }
    __im.busy[branchKey] = false;
    imRefreshStates();
    if (ok && __im.branch === branchKey && frameAtStart === __im.frameId && idxAtStart === __im.idx) imRenderDetail();
    return ok;
}

function imDetailShell(branchKey, inner) {
    const b = (__imCatalog || []).find(x => x.key === branchKey);
    return `<div class="im-detail-title" title="Drag the title to move the panel. Double-click to reset the position."><span class="im-grip" aria-hidden="true"></span>
        <span class="im-detail-name">${escapeHtml(b ? b.label : 'Analysis')}</span>
        <span class="im-tools"><button type="button" class="im-tool" data-fs="-1" title="Decrease text size" aria-label="Decrease text size">A-</button><button type="button" class="im-tool" data-fs="1" title="Increase text size" aria-label="Increase text size">A+</button><button type="button" class="im-tool" id="im-pos-reset" title="Reset panel position and size" aria-label="Reset panel position">&#8634;</button>${b ? '<button type="button" class="im-detail-x" id="im-detail-x" title="Close details" aria-label="Close details">&times;</button>' : ''}</span></div><div class="im-detail-body">${inner}</div>`;
}
function imBindDetailX() { const x = document.getElementById('im-detail-x'); if (x) x.addEventListener('click', imCloseDetail); }

function imRenderDetail(errorText) {
    const el = document.getElementById('im-detail');
    if (!el) return;
    const b = (__imCatalog || []).find(x => x.key === __im.branch);
    const { anomaly } = imCurrent();
    if (!b) {
        el.innerHTML = imDetailShell(null, imDetailEmpty());
        imPlacePanel(); return;
    }
    const ins = anomaly && anomaly.insights && anomaly.insights[b.key];
    if (!ins) {
        el.innerHTML = imDetailShell(b.key, `<div class="im-detail-empty"><p>${escapeHtml(errorText || 'Not analyzed yet.')}</p>
            <button type="button" class="btn-primary btn-sm" id="im-btn-gen">Analyze with AI</button></div>`);
        imBindDetailX();
        document.getElementById('im-btn-gen').addEventListener('click', () => { el.innerHTML = imDetailShell(b.key, imLoading(b.key)); imBindDetailX(); imFetchBranch(b.key, false); });
        return;
    }
    const levelCls = (t) => { const s = (t || '').toLowerCase(); return (s.startsWith('tinggi') || s.startsWith('high')) ? 'sev-red' : (s.startsWith('sedang') || s.startsWith('medium') || s.startsWith('moderate')) ? 'sev-yellow' : (s.startsWith('rendah') || s.startsWith('low')) ? 'sev-green' : ''; };
    const cards = b.items.map(it => {
        const v = (ins.items || {})[it.key] || {};
        const poin = (v.poin || []).map(p => `<li>${escapeHtml(p)}</li>`).join('');
        return `<div class="im-card${__im.item === it.key ? ' sel' : ''}" id="imc-${it.key}">
            <div class="im-card-head"><strong>${escapeHtml(it.label)}</strong>${v.tingkat ? `<span class="temuan-chip ${levelCls(v.tingkat)}">${escapeHtml(({ tinggi: 'High', sedang: 'Medium', rendah: 'Low' })[String(v.tingkat).toLowerCase()] || v.tingkat)}</span>` : ''}</div>
            <p>${escapeHtml(v.ringkasan || 'Not enough data for this section.')}</p>${poin ? `<ul>${poin}</ul>` : ''}
        </div>`;
    }).join('');
    const when = ins.generated_at ? new Date(ins.generated_at).toLocaleString('en-US') : '';
    el.innerHTML = imDetailShell(b.key, `<div class="im-detail-actions"><button type="button" class="btn-secondary btn-sm" id="im-btn-regen">Regenerate</button>
            <button type="button" class="btn-secondary btn-sm" id="im-btn-copy">Copy</button></div>
        ${errorText ? `<div class="im-warn">${escapeHtml(errorText)}</div>` : ''}
        ${cards}
        ${ins.keterbatasan ? `<div class="im-note">Data limitations: ${escapeHtml(ins.keterbatasan)}</div>` : ''}
        <div class="im-note">${ins.patient_aware ? 'Tailored to the stored patient data.' : 'General analysis, no patient data.'} Model: ${escapeHtml(ins.model || '-')}${when ? ' (' + escapeHtml(when) + ')' : ''}.
            Decision support, not a final diagnosis. Review by medical personnel.</div>`);
    imBindDetailX();
    document.getElementById('im-btn-regen').addEventListener('click', () => {
        logLine(`Branch ${b.label} analysis regenerated`);
        const a = imCurrent().anomaly; if (a && a.insights) delete a.insights[b.key];
        el.innerHTML = imDetailShell(b.key, imLoading(b.key)); imBindDetailX(); imRefreshStates(); imFetchBranch(b.key, false);
    });
    document.getElementById('im-btn-copy').addEventListener('click', () => {
        const text = b.label + '\n\n' + b.items.map(it => {
            const v = (ins.items || {})[it.key] || {};
            return `${it.label}\n${v.ringkasan || ''}\n${(v.poin || []).map(p => '- ' + p).join('\n')}`;
        }).join('\n\n');
        navigator.clipboard.writeText(text).then(() => showToast(`Uraian ${b.label} disalin.`, 'success'), () => showToast('Failed to copy.', 'error'));
    });
    if (__im.item) { const c = document.getElementById(`imc-${__im.item}`); if (c) c.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
}

async function imAnalyzeAll() {
    const { anomaly } = imCurrent();
    if (!anomaly) return;
    const apiKey = document.getElementById('api-key').value.trim();
    if (!apiKey && !window.__routerKeyManaged) { showToast('Enter the 9Router API Key in the sidebar first.', 'error'); return; }
    __im.cancelAll = false;
    const todo = (__imCatalog || []).filter(b => !(anomaly.insights && anomaly.insights[b.key]));
    const prog = document.getElementById('im-progress');
    const btn = document.getElementById('im-btn-all');
    if (!todo.length) { prog.textContent = 'All branches have already been analyzed.'; logLine('All branches already analyzed'); return; }
    btn.disabled = true;
    logLine(`Analyze-all started: ${todo.length} branch(es) for finding ${anomaly.label || 'Abnormality'}`, 'head');
    let done = 0;
    for (const b of todo) {
        if (__im.cancelAll) break;
        prog.textContent = `Analyzing branch ${done + 1} of ${todo.length}: ${b.label}...`;
        const ok = await imFetchBranch(b.key, true);
        if (!ok) { prog.textContent = `Stopped at branch "${b.label}" because it failed.`; btn.disabled = false; return; }
        done++;
    }
    prog.textContent = __im.cancelAll ? 'Dibatalkan.' : `Done: ${done} branch(es) analyzed.`;
    logLine(__im.cancelAll ? `Analyze-all cancelled after ${done} branch(es)` : `Analyze-all complete: ${done} branch(es)`, __im.cancelAll ? 'warn' : 'ok');
    btn.disabled = false;
    imRenderDetail();
}

function closeInsightModal() {
    __im.cancelAll = true;
    imCloseDetail();
    document.getElementById('insight-modal').classList.remove('active');
    document.getElementById('rv-viewer').classList.remove('im-open');
    if (__im.frameId) drawFrameAnnotations(__im.frameId);
    __im.pos = null; const dd = document.getElementById('im-detail'); if (dd) { delete dd.dataset.userSized; dd.style.height = ''; dd.style.width = ''; }
    logLine('Option map closed');
    if (__im.autoMax) { __im.autoMax = false; __maximizedId = null; renderFrameGrid(); }
}

document.addEventListener('DOMContentLoaded', () => {
    imInitDetailInteractions();
    document.getElementById('im-btn-close').addEventListener('click', closeInsightModal);
    document.getElementById('im-btn-all').addEventListener('click', imAnalyzeAll);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && imIsOpen()) { if (__im.branch) imCloseDetail(); else closeInsightModal(); } });

    // Tombol pada panel hasil: buka peta opsi untuk temuan pertama
    const openBtn = document.getElementById('btn-open-insight');
    if (openBtn) openBtn.addEventListener('click', () => {
        const frame = __frames.find(f => f.id === __activeFrameId);
        const anomalies = (frame && frame.result && frame.result.data && frame.result.data.anomalies) || [];
        if (!anomalies.length) { showToast('No findings yet. Run a scan or click a finding on the image.', 'error'); return; }
        const first = anomalies.findIndex(a => a.box);
        openFindingInsight(frame.id, first === -1 ? 0 : first);
    });
});
