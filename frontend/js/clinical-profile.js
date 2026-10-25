// =====================================================================
//  Profil Klinis Terstruktur (bagian bawah tab Riwayat Klinis): 5 panel + kode diagnosis
//  (ICD-10/11, ICD-O-3, SNOMED CT, ICPC-2, NANDA-I, SDKI, manual). Auto-simpan ke server.
//  Pasien mengikuti pilihan Nama Pasien di sidebar.
// =====================================================================
const __cp = { q: '', cat: 'all', pid: null, data: null, meta: null, system: 'icd10', filter: null, sortRisk: false, priority: false, overrideMode: false, saveTimer: null, loaded: false };

const CP_DAMPAK = {
    primary: { label: 'Primary Focus', cls: 'c-red', rank: 0 },
    critical: { label: 'Critical Impact', cls: 'c-red', rank: 1 },
    high: { label: 'High Impact', cls: 'c-amber', rank: 2 },
    moderate: { label: 'Moderate Impact', cls: 'c-amber', rank: 3 },
    low: { label: 'Low Impact', cls: 'c-green', rank: 4 },
};
// Display vocabulary: stored keys stay as-is (backend), only the shown text is English.
const CP_VOC = { Onkologi: 'Oncology', Endokrin: 'Endocrine', Renal: 'Renal', Kardiovaskular: 'Cardiovascular', Neurologi: 'Neurology', Respirasi: 'Respiratory', Muskuloskeletal: 'Musculoskeletal', Infeksi: 'Infection', Hematologi: 'Hematology', Gastrointestinal: 'Gastrointestinal', Lainnya: 'Other', Kritis: 'Critical', Tinggi: 'High', Sedang: 'Moderate', Rendah: 'Low', Akut: 'Acute', Kronis: 'Chronic', Maligna: 'Malignant', Ringan: 'Mild', Berat: 'Severe' };
function cpT(s) { return s === null || s === undefined ? s : String(s).replace(/Risiko (Tinggi|Sedang|Ringan|Rendah)/g, (m, g) => ({ Tinggi: 'High', Sedang: 'Moderate', Ringan: 'Mild', Rendah: 'Low' })[g] + ' Risk').replace(/\b(Onkologi|Endokrin|Kardiovaskular|Neurologi|Respirasi|Muskuloskeletal|Infeksi|Hematologi|Lainnya|Kritis|Tinggi|Sedang|Rendah|Akut|Kronis|Maligna|Ringan|Berat)\b/g, m => CP_VOC[m] || m); }
const CP_TONE = { merah: 'c-red', kuning: 'c-amber', hijau: 'c-green', biru: 'c-blue' };
const CP_HZ_CLS = { Kritis: 'hz-crit', Tinggi: 'hz-high', Sedang: 'hz-mid', Rendah: 'hz-low' };
const CP_ORGAN_FIELDS = [
    { k: 'ecog', label: 'ECOG (0 to 4)', step: '1' }, { k: 'egfr', label: 'eGFR (mL/min)', step: 'any' },
    { k: 'gds', label: 'GDS (mg/dL)', step: 'any' }, { k: 'lvef', label: 'LVEF (%)', step: 'any' },
    { k: 'sgot', label: 'SGOT (U/L)', step: 'any' }, { k: 'sgpt', label: 'SGPT (U/L)', step: 'any' }, { k: 'hb', label: 'Hemoglobin (g/dL)', step: 'any' },
];

function cpAi() {
    const apiKey = document.getElementById('api-key').value.trim();
    if (!apiKey && !window.__routerKeyManaged) { showToast('Enter the 9Router API Key in the sidebar first.', 'error'); return null; }
    return { model: document.getElementById('model-select').value, authorization: apiKey ? `Bearer ${apiKey}` : null };
}
function cpLog(msg, cls) { logLine(msg, cls || '', 'clinical-history'); }
function cpStatus(t) { const el = document.getElementById('cp-status'); if (el) el.textContent = t || ''; }
function cpSysLabel(k) { const s = (__cp.meta && __cp.meta.code_systems || []).find(x => x.key === k); return s ? s.label : k; }
function cpFmt(v) { return v === null || v === undefined ? '-' : (Math.round(v * 10) / 10).toString(); }

// ------------------------------------------------------------ sub-tab & muat
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('cp-code-system').addEventListener('change', (e) => { __cp.system = e.target.value; cpLog(`Clinical Profile, diagnosis code system: ${cpSysLabel(__cp.system)}`); cpRender(); cpPersistSoon(); });
    let searchLogTimer = null;
    document.getElementById('cp-search').addEventListener('input', (e) => {
        __cp.q = e.target.value.trim(); cpRenderView();
        clearTimeout(searchLogTimer); searchLogTimer = setTimeout(() => { if (__cp.q) cpLog(`Clinical Profile, search: ${__cp.q}`); }, 900);
    });
    document.getElementById('cp-cat').addEventListener('change', (e) => { __cp.cat = e.target.value; cpLog(`Clinical Profile, display category: ${e.target.selectedOptions[0].textContent.trim()}`); cpRenderView(); });
    document.getElementById('cp-btn-pdf').addEventListener('click', cpExportPdf);
    document.getElementById('cp-btn-ai').addEventListener('click', cpRunAi);
    document.getElementById('cp-btn-ai-codes').addEventListener('click', cpRunAiCodes);
    document.getElementById('cp-btn-add').addEventListener('click', () => cpOpenEdit(null));
    document.getElementById('cp-btn-save').addEventListener('click', () => cpPersist(true));
    document.getElementById('cp-btn-filter').addEventListener('click', (e) => { e.stopPropagation(); cpToggleFilter(); });
    document.getElementById('cp-filter-pop').addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('click', () => document.getElementById('cp-filter-pop').classList.remove('open'));
    document.getElementById('cp-btn-priority').addEventListener('click', () => {
        __cp.priority = !__cp.priority;
        cpLog(`Clinical Profile, set-priority mode ${__cp.priority ? 'on' : 'off'}`);
        document.getElementById('cp-btn-priority').classList.toggle('on', __cp.priority);
        cpRenderCards();
        if (__cp.priority) showToast('Priority mode: use the arrows to reorder, or Make Primary.', 'info');
    });
    document.getElementById('cp-btn-sort').addEventListener('click', () => {
        __cp.sortRisk = !__cp.sortRisk;
        cpLog(`Clinical Profile, sort matrix by risk ${__cp.sortRisk ? 'on' : 'off'}`);
        document.getElementById('cp-btn-sort').classList.toggle('on', __cp.sortRisk);
        cpRenderMatrix();
    });
    document.getElementById('cp-btn-print').addEventListener('click', cpPrintMatrix);
    document.getElementById('cp-btn-recalc').addEventListener('click', () => {
        __cp.data.skor.cci_manual = false;
        cpRecalc(); cpRenderScores(); cpPersistSoon(); showToast(`CCI score recalculated from each diagnosis' Charlson category: ${__cp.data.skor.cci_nilai} (${__cp.data.skor.cci_label})`, 'success');
    });
    document.getElementById('cp-btn-addhz').addEventListener('click', () => cpOpenHazard(null));
    document.getElementById('cp-btn-override').addEventListener('click', () => {
        __cp.overrideMode = !__cp.overrideMode;
        cpLog(`Clinical Profile, alert override mode ${__cp.overrideMode ? 'on' : 'off'}`);
        document.getElementById('cp-btn-override').classList.toggle('on', __cp.overrideMode);
        cpRenderHazards();
    });
    document.getElementById('cp-btn-lab').addEventListener('click', cpOpenLab);
    const addBtn = document.getElementById('btn-add-to-profile');
    if (addBtn) addBtn.addEventListener('click', cpAddFromScan);
});

// Simpan dulu perubahan yang masih menunggu sebelum pasien diganti.
async function cpFlush() { if (__cp.saveTimer) { clearTimeout(__cp.saveTimer); __cp.saveTimer = null; await cpPersist(false); } }

async function cpLoad() {
    const pid = currentPatientId();
    const body = document.getElementById('cp-body');
    if (!pid) { body.style.display = 'none'; __cp.pid = null; __cp.data = null; return; }
    try {
        cpLog(`Loading patient clinical profile: ${currentPatientName()}`);
        if (!__cp.meta) __cp.meta = await apiFetch('/api/clinical-profile/meta');
        const res = await apiFetch(`/api/clinical-profile/${pid}`);
        __cp.pid = pid; __cp.data = res.data; __cp.system = res.code_system || 'icd10'; __cp.loaded = true; __cp.filter = null;
        const sel = document.getElementById('cp-code-system');
        sel.innerHTML = __cp.meta.code_systems.map(s => `<option value="${s.key}">${escapeHtml(s.label)}</option>`).join('');
        sel.value = __cp.system;
        body.style.display = '';
        cpStatus(res.updated_at ? 'Loaded from storage.' : 'No profile yet. Click "AI Build Clinical Profile" or add manually.');
        cpRender();
        cpLog(`Clinical profile loaded: ${__cp.data.diagnoses.length} diagnoses, ${__cp.data.hazards.length} clinical hazards, code system ${cpSysLabel(__cp.system)}`, 'ok');
    } catch (e) { cpLog(`Failed to load clinical profile: ${e.message}`, 'err'); showToast(`Failed to load clinical profile: ${e.message}`, 'error'); }
}

// ------------------------------------------------------------ simpan
function cpPersistSoon() { cpStatus('Menyimpan...'); clearTimeout(__cp.saveTimer); __cp.saveTimer = setTimeout(() => cpPersist(false), 700); }
async function cpPersist(manual) {
    if (!__cp.pid || !__cp.data) return;
    clearTimeout(__cp.saveTimer); __cp.saveTimer = null;
    try {
        const res = await apiFetch(`/api/clinical-profile/${__cp.pid}`, { method: 'PUT', body: JSON.stringify({ data: __cp.data, code_system: __cp.system }) });
        __cp.data = res.data;
        cpStatus('Tersimpan.');
        cpLog(`Clinical profile saved${manual ? ' (manual)' : ' automatically'}: ${__cp.data.diagnoses.length} diagnoses`, 'ok');
        if (manual) showToast('Clinical profile saved.', 'success');
        cpRender();
    } catch (e) { cpStatus('Failed to save.'); showToast(`Failed to save profile: ${e.message}`, 'error'); }
}

// ------------------------------------------------------------ AI
async function cpRunAi() {
    const ai = cpAi(); if (!ai || !__cp.pid) return;
    let merge = false;
    if (__cp.data.diagnoses.length) {
        merge = confirm('The profile already contains diagnoses.\nOK = merge the AI result with the existing profile.\nCancel = do nothing.');
        if (!merge) return;
    }
    const btn = document.getElementById('cp-btn-ai'); btn.disabled = true; cpStatus('AI is building the clinical profile...');
    cpLog(`AI building clinical profile (${merge ? 'merged with the existing profile' : 'new profile'}), model ${ai.model}`, 'head');
    try {
        const res = await apiFetch(`/api/clinical-profile/${__cp.pid}/ai-generate`, { method: 'POST', body: JSON.stringify({ ...ai, code_system: __cp.system, merge }) });
        __cp.data = res.data; cpStatus('Profile built by AI. Review and correct if needed.'); cpRender();
        showToast(`Clinical profile built by AI and saved: ${__cp.data.diagnoses.length} diagnoses, ${__cp.data.hazards.length} clinical hazards`, 'success');
    } catch (e) { cpStatus(''); cpLog(`AI failed to build the clinical profile: ${e.message}`, 'err'); showToast(`Failed: ${e.message}`, 'error'); }
    btn.disabled = false;
}
async function cpRunAiCodes() {
    const ai = cpAi(); if (!ai || !__cp.pid) return;
    if (__cp.system === 'lainnya') { showToast('The "Other" system is filled in manually.', 'error'); return; }
    if (!__cp.data.diagnoses.length) { showToast('No diagnoses yet.', 'error'); return; }
    const btn = document.getElementById('cp-btn-ai-codes'); btn.disabled = true; cpStatus(`AI filling ${cpSysLabel(__cp.system)} codes...`);
    cpLog(`AI filling ${cpSysLabel(__cp.system)} codes for ${__cp.data.diagnoses.length} diagnoses`);
    try {
        const res = await apiFetch(`/api/clinical-profile/${__cp.pid}/ai-codes`, { method: 'POST', body: JSON.stringify({ ...ai, code_system: __cp.system }) });
        __cp.data = res.data; cpStatus('Codes filled. Verify against the official release.'); cpRender();
        const filled = __cp.data.diagnoses.filter(d => d.kodes && d.kodes[__cp.system]).length;
        cpLog(`AI finished filling ${cpSysLabel(__cp.system)} codes: ${filled} of ${__cp.data.diagnoses.length} diagnoses coded. Verify against the official release`, 'ok');
    } catch (e) { cpStatus(''); cpLog(`AI failed to fill codes: ${e.message}`, 'err'); showToast(`Failed: ${e.message}`, 'error'); }
    btn.disabled = false;
}

// ------------------------------------------------------------ hitung
function cpRecalc() {
    const cats = (__cp.meta && __cp.meta.cci_categories) || [];
    const w = {}, f = {}; cats.forEach(c => { w[c.key] = c.weight; f[c.key] = c.family; });
    const fam = {}; let total = 0;
    __cp.data.diagnoses.forEach(d => {
        const k = d.cci_kategori || 'none', wt = w[k] || 0, fm = f[k] || '';
        if (!wt) return;
        if (fm) fam[fm] = Math.max(fam[fm] || 0, wt); else total += wt;
    });
    total += Object.values(fam).reduce((a, b) => a + b, 0);
    __cp.data.skor.cci_nilai = total;
    __cp.data.skor.cci_label = total >= 5 ? 'High Risk' : total >= 3 ? 'Moderate Risk' : total >= 1 ? 'Mild Risk' : 'Low Risk';
}

// ------------------------------------------------------------ render
function cpRender() {
    if (!__cp.data) return;
    cpRenderHeader(); cpRenderCards(); cpRenderMatrix(); cpRenderScores(); cpRenderHazards(); cpRenderOrgan();
}
function cpRenderView() { cpRenderCards(); cpRenderMatrix(); cpRenderHazards(); }

function cpPatientName() { return currentPatientName(); }
function cpRecordId() { return `RAD-${new Date().getFullYear()}-${String(__cp.pid || 0).padStart(4, '0')}`; }
function cpRenderHeader() {
    document.getElementById('cp-id').textContent = `ID: ${cpRecordId()}`;
    const n = cpPatientName();
    document.getElementById('cp-subtitle').textContent = `Multi-Diagnosis Evaluation Panel | Integrated Medical Record and Radiology Evaluation${n ? ' | ' + n : ''}`;
}
// Sorot kata yang dicari
function cpHl(text) {
    const t = escapeHtml(text || '');
    if (!__cp.q) return t;
    const q = escapeHtml(__cp.q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    try { return t.replace(new RegExp(q, 'ig'), (m) => `<mark class="cp-hl">${m}</mark>`); } catch (e) { return t; }
}
function cpDiagText(d) {
    const kodes = Object.values(d.kodes || {}).map(k => `${k.kode} ${k.nama || ''}`).join(' ');
    return [d.nama, d.kelompok, d.onset, d.severity, d.trajektori, d.status_kontrol, d.aksi_medis, d.catatan_kartu, d.catatan_klinis, d.dampak_ket, (d.obat || []).join(' '), kodes].join(' ').toLowerCase();
}
function cpHazardText(h) { return [h.judul, h.deskripsi, (h.aksi || []).join(' '), h.tingkat].join(' ').toLowerCase(); }

function cpCodeHtml(d, compact) {
    const k = d.kodes && d.kodes[__cp.system];
    if (!k) return `<span class="cp-code none">${escapeHtml(cpSysLabel(__cp.system))} code: none yet</span>`;
    const warn = k.format_valid === false ? ' <span class="cp-badge warn" title="Format does not match this system">format?</span>' : '';
    const src = k.sumber === 'ai' ? ' <span class="cp-badge" title="Suggested by AI">AI</span>' : k.sumber === 'lokal' ? ' <span class="cp-badge" title="From the local list">local</span>' : '';
    return `<span class="cp-code"><b>${escapeHtml(cpSysLabel(__cp.system))} ${escapeHtml(k.kode)}</b>${compact || !k.nama ? '' : ' ' + escapeHtml(k.nama)}${warn}${src}</span>`;
}

function cpVisible() {
    let list = __cp.data.diagnoses;
    if (__cp.filter) list = list.filter(d => __cp.filter.has(d.kelompok) || (__cp.filter.has('__utama') && d.peran === 'utama'));
    const cat = __cp.cat;
    if (cat === 'utama') list = list.filter(d => d.peran === 'utama');
    else if (cat === 'kritis') list = list.filter(d => d.peran !== 'utama' && (d.dampak === 'critical' || d.dampak === 'high'));
    else if (cat === 'kronis') list = list.filter(d => /kronis|chronic/i.test(d.onset || ''));
    else if (cat === 'akut') list = list.filter(d => /akut|acute|maligna|malignant/i.test(d.onset || ''));
    if (__cp.q) { const q = __cp.q.toLowerCase(); list = list.filter(d => cpDiagText(d).includes(q)); }
    return list;
}

function cpRenderCards() {
    const el = document.getElementById('cp-cards');
    const all = __cp.data.diagnoses;
    if (!all.length) { el.innerHTML = '<div class="empty-state">No diagnoses yet. Click "AI Build Clinical Profile" or "+ Add Diagnosis".</div>'; return; }
    let komorbidNo = 0;
    const numbered = all.map(d => ({ d, no: d.peran === 'utama' ? 0 : ++komorbidNo }));
    const vis = numbered.filter(x => cpVisible().includes(x.d));
    el.innerHTML = vis.map(({ d, no }) => {
        const utama = d.peran === 'utama';
        const dm = CP_DAMPAK[d.dampak] || CP_DAMPAK.moderate;
        const sub = [d.severity, d.trajektori ? `Trajectory: ${d.trajektori}` : '', utama ? '' : `Impact: ${dm.label.replace(' Impact', '')}`].filter(Boolean).join(' | ');
        const link = d.tautan && d.tautan.teks ? `<button type="button" class="cp-link" data-act="link" data-id="${d.id}">${escapeHtml(d.tautan.teks)}</button>` : '';
        const pri = __cp.priority ? `<div class="cp-pri"><button type="button" data-act="up" data-id="${d.id}" title="Move up">&#9650;</button><button type="button" data-act="down" data-id="${d.id}" title="Move down">&#9660;</button>${utama ? '' : `<button type="button" data-act="main" data-id="${d.id}">Make Primary</button>`}</div>` : '';
        return `<article class="cp-card ${utama ? 'main' : ''}" data-id="${d.id}">
            <div class="cp-tags"><span class="cp-tag ${utama ? 'tag-main' : 'tag-co'}">${utama ? 'Primary Diagnosis' : 'Comorbidity ' + no}</span>
                <span class="cp-tag ${utama && /maligna|malignant|akut|acute/i.test(d.onset) ? 'tag-red' : 'tag-grey'}">${escapeHtml(cpT(d.onset || d.kelompok))}</span></div>
            <h4>${cpHl(d.nama)}</h4>
            <p class="cp-sub">${cpHl(sub) || '&nbsp;'}</p>
            ${d.catatan_klinis ? `<div class="cp-detail">${cpHl(d.catatan_klinis)}</div>` : ''}
            ${(d.obat || []).length ? `<div class="cp-meds"><span>Medication:</span>${d.obat.map(o => `<span class="cp-med">${cpHl(o)}</span>`).join('')}</div>` : ''}
            <div class="cp-codeline">${cpCodeHtml(d, false)}</div>
            ${pri}
            <div class="cp-card-foot"><span class="${CP_TONE[d.catatan_tone] || 'c-blue'}">${escapeHtml(d.catatan_kartu || d.status_kontrol || '')}</span>${link}</div>
        </article>`;
    }).join('') || '<div class="empty-state">No diagnoses match this search / category.</div>';

    el.querySelectorAll('.cp-card').forEach(c => c.addEventListener('click', (e) => { if (e.target.closest('button')) return; cpOpenEdit(c.dataset.id); }));
    el.querySelectorAll('button[data-act]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); cpCardAction(b.dataset.act, b.dataset.id); }));
}

function cpCardAction(act, id) {
    const list = __cp.data.diagnoses, i = list.findIndex(d => d.id === id); if (i === -1) return;
    if (act === 'link') {
        const t = list[i].tautan && list[i].tautan.target;
        cpLog(`Clinical Profile, card link opened: ${list[i].nama}`);
        if (t === 'lab') cpOpenLab(); else if (t === 'scan') switchView('scan');
        else cpOpenEdit(id);
        return;
    }
    cpLog(`Clinical Profile, ${act === 'up' ? 'move up' : act === 'down' ? 'move down' : 'make primary diagnosis'}: ${list[i].nama}`);
    if (act === 'up' && i > 0) [list[i - 1], list[i]] = [list[i], list[i - 1]];
    if (act === 'down' && i < list.length - 1) [list[i + 1], list[i]] = [list[i], list[i + 1]];
    if (act === 'main') { list.forEach(d => { d.peran = d.id === id ? 'utama' : 'komorbid'; }); const d = list[i]; list.splice(i, 1); list.unshift(d); d.dampak = 'primary'; }
    cpRecalc(); cpRender(); cpPersistSoon();
}

function cpRenderMatrix() {
    const t = document.getElementById('cp-matrix');
    let list = cpVisible().slice();
    if (__cp.sortRisk) list.sort((a, b) => (CP_DAMPAK[a.dampak] || CP_DAMPAK.moderate).rank - (CP_DAMPAK[b.dampak] || CP_DAMPAK.moderate).rank);
    if (!list.length) { t.innerHTML = ''; return; }
    t.innerHTML = `<thead><tr><th>Diagnosis Name</th><th>Code (${escapeHtml(cpSysLabel(__cp.system))})</th><th>Onset Category</th><th>Severity / Stage</th><th>Care Trajectory</th><th>Impact on Primary Diagnosis</th><th>Control Status</th><th>Medical Action</th></tr></thead><tbody>` +
        list.map(d => {
            const dm = CP_DAMPAK[d.dampak] || CP_DAMPAK.moderate;
            const k = d.kodes && d.kodes[__cp.system];
            const onsetCls = /maligna|malignant|akut|acute/i.test(d.onset) ? 'pill-red' : 'pill-amber';
            return `<tr>
                <td><strong>${cpHl(d.nama)}</strong>${(d.obat || []).length ? `<br><span class="cp-muted">Medication: ${cpHl(d.obat.join(', '))}</span>` : ''}</td>
                <td class="cp-mono">${k ? escapeHtml(k.kode) : '<span class="cp-muted">-</span>'}</td>
                <td><span class="cp-pill ${onsetCls}">${escapeHtml(cpT(d.onset) || '-')}</span></td>
                <td>${escapeHtml(d.severity || '-')}</td><td>${escapeHtml(d.trajektori || '-')}</td>
                <td><span class="${dm.cls} cp-strong">${dm.label}</span>${d.dampak_ket ? `<br><span class="cp-muted">${escapeHtml(d.dampak_ket)}</span>` : ''}</td>
                <td>${escapeHtml(d.status_kontrol || '-')}</td>
                <td>${d.aksi_medis ? `<button type="button" class="cp-act" data-id="${d.id}">${escapeHtml(d.aksi_medis)}</button>` : `<button type="button" class="cp-act" data-id="${d.id}">Edit</button>`}</td></tr>`;
        }).join('') + '</tbody>';
    t.querySelectorAll('.cp-act').forEach(b => b.addEventListener('click', () => cpOpenEdit(b.dataset.id)));
}

function cpRenderScores() {
    const s = __cp.data.skor, el = document.getElementById('cp-scores');
    const cciPct = Math.min(100, (s.cci_nilai || 0) / 8 * 100);
    const cciCls = s.cci_nilai >= 5 ? 'c-red' : s.cci_nilai >= 3 ? 'c-amber' : 'c-green';
    const bar = (label, valHtml, pct, color) => `<div class="cp-score"><div class="cp-score-row"><span>${label}</span><b class="${color}">${valHtml}</b></div><div class="cp-bar"><i class="bg-${color}" style="width:${pct}%"></i></div></div>`;
    const base = s.pemulihan_baseline, corr = s.pemulihan_terkoreksi;
    const prim = (__cp.data.diagnoses.find(d => d.peran === 'utama') || {}).nama || 'Primary Diagnosis';
    const primShort = prim.length > 34 ? prim.slice(0, 32).trim() + '…' : prim;
    el.innerHTML =
        bar('Charlson Comorbidities Index (CCI)', `Score ${s.cci_nilai} (${escapeHtml(cpT(s.cci_label))})${s.cci_manual ? ' *' : ''}`, cciPct, cciCls) +
        bar(`Baseline Recovery Estimate (${escapeHtml(primShort)} Only)`, base === null ? 'Not filled in' : base + '%', base || 0, 'c-green') +
        bar(`Adjusted Recovery Estimate (Aggregate Comorbidity${__cp.data.diagnoses.length > 1 ? ' x' + (__cp.data.diagnoses.length - 1) : ''})`, corr === null ? 'Not filled in' : corr + '%', corr || 0, 'c-red') +
        bar('Adjusted Recovery Timeline Target', escapeHtml(s.timeline_terkoreksi || 'Not filled in'), s.timeline_terkoreksi ? 55 : 0, 'c-amber') +
        `<div class="cp-note">${s.cci_manual ? '* CCI score entered manually. ' : ''}${escapeHtml(s.catatan || 'Recovery estimates and timeline come from AI or manual input. Clinician confirmation required.')}
            <button type="button" class="cp-link" id="cp-edit-scores">Edit values</button></div>`;
    document.getElementById('cp-edit-scores').addEventListener('click', cpOpenScores);
}

function cpRenderHazards() {
    const el = document.getElementById('cp-hazards');
    const hzAll = __cp.data.hazards;
    const hz = __cp.q ? hzAll.filter(h => cpHazardText(h).includes(__cp.q.toLowerCase())) : hzAll;
    if (hzAll.length && !hz.length) { el.innerHTML = '<div class="empty-state">No clinical hazards match the search.</div>'; return; }
    if (!hz.length) { el.innerHTML = '<div class="empty-state">No clinical hazards recorded yet.</div>'; return; }
    el.innerHTML = hz.map(h => `<div class="cp-hz ${CP_HZ_CLS[h.tingkat] || 'hz-mid'}${h.override ? ' overridden' : ''}" data-id="${h.id}">
        <div class="cp-hz-head"><h4>${cpHl(h.judul)}</h4><span class="cp-hz-badge">${escapeHtml(cpT(h.tingkat))}</span></div>
        <p>${cpHl(h.deskripsi)}</p>
        ${h.override ? `<div class="cp-override-note">Alert overridden${h.override.waktu ? ' (' + escapeHtml(h.override.waktu) + ')' : ''}: ${escapeHtml(h.override.alasan || 'no reason given')}</div>` : ''}
        <div class="cp-hz-actions">${(h.aksi || []).map(a => `<span class="cp-chip">${escapeHtml(a)}</span>`).join('')}
            <span class="cp-hz-tools"><button type="button" data-hz="edit" data-id="${h.id}">Edit</button>
            ${__cp.overrideMode ? (h.override ? `<button type="button" data-hz="undo" data-id="${h.id}">Undo Override</button>` : `<button type="button" class="warn" data-hz="ovr" data-id="${h.id}">Override</button>`) : ''}
            <button type="button" data-hz="del" data-id="${h.id}">Delete</button></span></div></div>`).join('');
    el.querySelectorAll('[data-hz]').forEach(b => b.addEventListener('click', () => cpHazardAction(b.dataset.hz, b.dataset.id)));
}

function cpHazardAction(act, id) {
    const hz = __cp.data.hazards, h = hz.find(x => x.id === id); if (!h) return;
    if (act === 'edit') return cpOpenHazard(id);
    if (act === 'del') { if (!confirm('Delete this clinical hazard?')) return; cpLog(`Clinical hazard deleted: ${h.judul}`, 'warn'); __cp.data.hazards = hz.filter(x => x.id !== id); }
    if (act === 'ovr') {
        const alasan = prompt('Reason for the alert override (required, recorded in the profile):', '');
        if (alasan === null) return;
        if (!alasan.trim()) { showToast('An override reason is required.', 'error'); return; }
        h.override = { alasan: alasan.trim(), waktu: new Date().toLocaleString('en-US') };
        cpLog(`Alert overridden: ${h.judul}. Reason: ${alasan.trim()}`, 'warn');
    }
    if (act === 'undo') { h.override = null; cpLog(`Alert override cancelled: ${h.judul}`); }
    cpRenderHazards(); cpPersistSoon();
}

function cpOrganInfo(k, v, o) {
    if (v === null || v === undefined) return { text: '-', cls: 'c-grey', pct: 0, note: 'Not filled in' };
    const pick = (cls, note, pct) => ({ cls, note, pct: Math.max(0, Math.min(100, pct)) });
    const keterangan = (o.keterangan || {})[k];
    let r;
    if (k === 'ecog') r = v <= 1 ? pick('c-green', 'Independent, light physical activity', (4 - v) / 4 * 100) : v === 2 ? pick('c-amber', 'Independent, unable to work', 50) : pick('c-red', 'Limited self-care', (4 - v) / 4 * 100);
    else if (k === 'egfr') r = v >= 60 ? pick('c-green', 'Good kidney function', v / 1.2) : v >= 30 ? pick('c-amber', 'Moderate / dose adjustment needed', v / 1.2) : pick('c-red', 'Severe / avoid nephrotoxic drugs', v / 1.2);
    else if (k === 'gds') r = v < 140 ? pick('c-green', 'Within controlled range', v / 3) : v < 200 ? pick('c-amber', 'Elevated / monitor', v / 3) : pick('c-red', 'High / insulin regimen needed', v / 3);
    else if (k === 'lvef') r = v >= 55 ? pick('c-green', 'Normal heart pump function', v) : v >= 40 ? pick('c-amber', 'Mildly reduced', v) : pick('c-red', 'Significantly reduced', v);
    else r = v >= 12 ? pick('c-green', 'Within normal limits', v / 16 * 100) : v >= 10 ? pick('c-amber', 'Mild anemia / surgery preparation', v / 16 * 100) : pick('c-red', 'Moderate to severe anemia', v / 16 * 100);
    if (keterangan) r.note = keterangan;
    return r;
}

function cpRenderOrgan() {
    const o = __cp.data.organ, el = document.getElementById('cp-organ');
    const card = (title, text, info) => `<div class="cp-organ-card"><span class="cp-muted">${title}</span><b class="cp-organ-val ${info.cls}">${text}</b>
        <div class="cp-bar"><i class="bg-${info.cls}" style="width:${info.pct}%"></i></div><span class="cp-muted small">${escapeHtml(info.note)}</span></div>`;
    const ecog = cpOrganInfo('ecog', o.ecog, o), egfr = cpOrganInfo('egfr', o.egfr, o), gds = cpOrganInfo('gds', o.gds, o), lvef = cpOrganInfo('lvef', o.lvef, o), hb = cpOrganInfo('hb', o.hb, o);
    let liver = { text: '-', cls: 'c-grey', pct: 0, note: 'Not filled in' };
    if (o.sgot !== null || o.sgpt !== null) {
        const mx = Math.max(o.sgot || 0, o.sgpt || 0);
        liver = mx <= 40 ? { cls: 'c-green', note: 'Tolerates drug metabolism', pct: mx / 80 * 100 } : mx <= 120 ? { cls: 'c-amber', note: 'Elevated / beware of hepatotoxic drugs', pct: mx / 80 * 100 } : { cls: 'c-red', note: 'Significantly elevated', pct: 100 };
        liver.text = `${cpFmt(o.sgot)} / ${cpFmt(o.sgpt)} U/L`;
        if ((o.keterangan || {}).sgot) liver.note = o.keterangan.sgot;
    }
    el.innerHTML = card('Performance Status (ECOG)', o.ecog === null ? '-' : `ECOG ${cpFmt(o.ecog)}`, ecog) + card('Kidney Function (eGFR)', o.egfr === null ? '-' : `${cpFmt(o.egfr)} mL/min`, egfr) +
        card('Glycemic Status (GDS)', o.gds === null ? '-' : `${cpFmt(o.gds)} mg/dL`, gds) + card('Cardiac Capacity (LVEF)', o.lvef === null ? '-' : `${cpFmt(o.lvef)}%`, lvef) +
        card('Liver Function (SGOT/SGPT)', liver.text, liver) + card('Hematology (Hemoglobin)', o.hb === null ? '-' : `${cpFmt(o.hb)} g/dL`, hb);
    document.getElementById('cp-organ-note').textContent = 'Colour thresholds are general indicators only (not a clinical decision). Values come from written data or manual input.';
}

// ------------------------------------------------------------ ekspor PDF (dialog cetak > Simpan sebagai PDF, tanpa tab baru)
function cpPrintHtml(title, bodyHtml) {
    const old = document.getElementById('cp-print-frame'); if (old) old.remove();
    const fr = document.createElement('iframe'); fr.id = 'cp-print-frame';
    fr.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;';
    document.body.appendChild(fr);
    const doc = fr.contentWindow.document;
    doc.open(); doc.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><style>
        body{font-family:Arial,sans-serif;color:#111;padding:18px;font-size:12px}h1{font-size:18px;margin:0}h2{font-size:13px;margin:16px 0 6px;border-bottom:1px solid #888;padding-bottom:3px;text-transform:uppercase}
        .meta{color:#444;margin:3px 0 10px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #999;padding:5px 7px;text-align:left;vertical-align:top}th{background:#eee}
        .bar{height:6px;background:#ddd;border-radius:3px;margin-top:3px}.bar i{display:block;height:100%;background:#444;border-radius:3px}
        .hz{border:1px solid #999;border-left:4px solid #b91c1c;padding:6px 8px;margin-bottom:6px}.hz.t-Tinggi,.hz.t-Sedang{border-left-color:#d97706}.hz.t-Rendah{border-left-color:#16a34a}
        .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.cell{border:1px solid #999;padding:6px}.small{color:#555;font-size:11px}
        </style></head><body>${bodyHtml}</body></html>`);
    doc.close();
    setTimeout(() => { fr.contentWindow.focus(); fr.contentWindow.print(); }, 250);
}
function cpExportPdf() {
    if (!__cp.data) return;
    cpLog('Clinical Profile exported to PDF via the print dialog');
    const e = escapeHtml, d = __cp.data, s = d.skor, o = d.organ;
    const dm = (x) => (CP_DAMPAK[x.dampak] || CP_DAMPAK.moderate).label;
    const rows = d.diagnoses.map(x => { const k = x.kodes && x.kodes[__cp.system]; return `<tr><td><b>${e(x.nama)}</b>${x.catatan_klinis ? `<br><span class="small">${e(x.catatan_klinis)}</span>` : ''}${(x.obat || []).length ? `<br><span class="small">Medication: ${e(x.obat.join(', '))}</span>` : ''}</td>
        <td>${k ? e(k.kode) : '-'}</td><td>${e(x.peran === 'utama' ? 'Primary Diagnosis' : 'Comorbidity')} / ${e(cpT(x.onset) || '-')}</td><td>${e(x.severity || '-')}</td><td>${e(x.trajektori || '-')}</td><td>${dm(x)}${x.dampak_ket ? '<br><span class="small">' + e(x.dampak_ket) + '</span>' : ''}</td><td>${e(x.status_kontrol || '-')}</td></tr>`; }).join('');
    const bar = (l, v, p) => `<div style="margin-bottom:7px"><div style="display:flex;justify-content:space-between"><span>${e(l)}</span><b>${v}</b></div><div class="bar"><i style="width:${p}%"></i></div></div>`;
    const prim = (d.diagnoses.find(x => x.peran === 'utama') || {}).nama || 'Primary Diagnosis';
    const hz = d.hazards.map(h => `<div class="hz t-${e(h.tingkat)}"><b>${e(h.judul)}</b> [${e(cpT(h.tingkat))}]${h.override ? ' (override: ' + e(h.override.alasan) + ')' : ''}<br>${e(h.deskripsi)}${(h.aksi || []).length ? '<br><span class="small">Actions: ' + e(h.aksi.join('; ')) + '</span>' : ''}</div>`).join('') || '<p class="small">No clinical hazards recorded.</p>';
    const org = [['Performance Status (ECOG)', o.ecog === null ? '-' : 'ECOG ' + cpFmt(o.ecog), cpOrganInfo('ecog', o.ecog, o)], ['Kidney Function (eGFR)', o.egfr === null ? '-' : cpFmt(o.egfr) + ' mL/min', cpOrganInfo('egfr', o.egfr, o)],
        ['Glycemic Status (GDS)', o.gds === null ? '-' : cpFmt(o.gds) + ' mg/dL', cpOrganInfo('gds', o.gds, o)], ['Cardiac Capacity (LVEF)', o.lvef === null ? '-' : cpFmt(o.lvef) + '%', cpOrganInfo('lvef', o.lvef, o)],
        ['Liver Function (SGOT/SGPT)', (o.sgot === null && o.sgpt === null) ? '-' : `${cpFmt(o.sgot)} / ${cpFmt(o.sgpt)} U/L`, { note: (o.keterangan || {}).sgot || '' }], ['Hematology (Hemoglobin)', o.hb === null ? '-' : cpFmt(o.hb) + ' g/dL', cpOrganInfo('hb', o.hb, o)]]
        .map(([l, v, i]) => `<div class="cell"><span class="small">${e(l)}</span><br><b>${e(v)}</b><br><span class="small">${e(i.note || '')}</span></div>`).join('');
    cpPrintHtml('Patient Clinical Profile', `<h1>Patient Clinical Profile</h1>
        <div class="meta">${e(cpRecordId())} | ${e(cpPatientName())} | Code system: ${e(cpSysLabel(__cp.system))} | Printed ${new Date().toLocaleString('en-US')}</div>
        <h2>1-2. Diagnoses, Comorbidities, and Impact Assessment</h2><table><thead><tr><th>Diagnosis</th><th>Code</th><th>Role / Onset</th><th>Severity / Stage</th><th>Trajectory</th><th>Impact</th><th>Control Status</th></tr></thead><tbody>${rows}</tbody></table>
        <h2>3. Aggregate Scores and Indicators</h2>${bar('Charlson Comorbidities Index (CCI)', `Score ${s.cci_nilai} (${e(cpT(s.cci_label))})`, Math.min(100, s.cci_nilai / 8 * 100))}
        ${bar(`Baseline Recovery Estimate (${prim} Only)`, s.pemulihan_baseline === null ? '-' : s.pemulihan_baseline + '%', s.pemulihan_baseline || 0)}
        ${bar('Adjusted Recovery Estimate (Aggregate Comorbidity)', s.pemulihan_terkoreksi === null ? '-' : s.pemulihan_terkoreksi + '%', s.pemulihan_terkoreksi || 0)}
        <div>Adjusted Recovery Timeline Target: <b>${e(s.timeline_terkoreksi || '-')}</b></div>${s.catatan ? `<div class="small">${e(s.catatan)}</div>` : ''}
        <h2>4. Clinical Hazards Matrix</h2>${hz}<h2>5. Organ Capacity and Baseline Functional Status</h2><div class="grid">${org}</div>
        <p class="small" style="margin-top:14px">Clinical decision support, not a final diagnosis. AI estimates and codes must be verified by medical personnel.</p>`);
}

// ------------------------------------------------------------ filter & cetak
function cpToggleFilter() {
    const pop = document.getElementById('cp-filter-pop');
    const groups = [...new Set(__cp.data.diagnoses.map(d => d.kelompok))];
    const on = (g) => !__cp.filter || __cp.filter.has(g);
    pop.innerHTML = `<div class="cp-pop-title">Show groups</div>` + groups.map(g => `<label><input type="checkbox" data-g="${escapeHtml(g)}" ${on(g) ? 'checked' : ''}> ${escapeHtml(cpT(g))}</label>`).join('') +
        `<button type="button" class="btn-secondary btn-sm" id="cp-filter-reset">Show all</button>`;
    pop.classList.toggle('open');
    pop.querySelectorAll('input[data-g]').forEach(i => i.addEventListener('change', () => {
        const checked = [...pop.querySelectorAll('input[data-g]:checked')].map(x => x.dataset.g);
        __cp.filter = checked.length === groups.length ? null : new Set(checked);
        cpLog(`Clinical Profile, group filter: ${checked.length === groups.length ? 'all' : checked.map(cpT).join(', ') || 'none'}`);
        cpRenderCards(); cpRenderMatrix();
    }));
    pop.querySelector('#cp-filter-reset').addEventListener('click', () => { __cp.filter = null; pop.classList.remove('open'); cpRenderCards(); cpRenderMatrix(); });
}

function cpPrintMatrix() {
    cpLog('Classification matrix printed');
    const html = document.getElementById('cp-matrix').outerHTML;
    const pname = currentPatientName();
    const w = window.open('', '_blank');
    if (!w) { showToast('Pop-up blocked by the browser. Allow pop-ups to print.', 'error'); return; }
    w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Classification Matrix</title><style>
        body{font-family:Arial,sans-serif;padding:20px;color:#111}h2{font-size:16px;margin:0 0 4px}p{font-size:12px;margin:0 0 12px;color:#444}
        table{border-collapse:collapse;width:100%;font-size:12px}th,td{border:1px solid #888;padding:6px 8px;text-align:left;vertical-align:top}th{background:#eee}
        .cp-muted{color:#555}button{all:unset}</style></head><body><h2>Classification Matrix and Impact Assessment</h2>
        <p>${escapeHtml(pname)} | Code system: ${escapeHtml(cpSysLabel(__cp.system))} | Printed ${new Date().toLocaleString('en-US')}</p>${html}</body></html>`);
    w.document.close(); w.focus(); setTimeout(() => w.print(), 300);
}

// ------------------------------------------------------------ modal generik
function cpModal(title, bodyHtml, onSave, opts = {}) {
    let m = document.getElementById('cp-modal');
    if (m) m.remove();
    m = document.createElement('div'); m.id = 'cp-modal'; m.className = 'modal-backdrop active';
    m.innerHTML = `<div class="modal-box cp-modal-box"><h3>${escapeHtml(title)}</h3><div id="cp-modal-body">${bodyHtml}</div>
        <div class="modal-actions">${opts.onDelete ? '<button type="button" class="btn-danger" id="cp-m-del" style="margin-right:auto;">Delete</button>' : ''}
        <button type="button" class="btn-secondary" id="cp-m-cancel">Cancel</button><button type="button" class="btn-primary" id="cp-m-save">Save</button></div></div>`;
    document.body.appendChild(m);
    const close = () => m.remove();
    m.addEventListener('mousedown', (e) => { if (e.target === m) close(); });
    m.querySelector('#cp-m-cancel').addEventListener('click', close);
    m.querySelector('#cp-m-save').addEventListener('click', () => { if (onSave(m) !== false) close(); });
    if (opts.onDelete) m.querySelector('#cp-m-del').addEventListener('click', () => { if (confirm('Delete this item?')) { opts.onDelete(); close(); } });
    return m;
}
const cpV = (m, id) => m.querySelector('#' + id).value.trim();

// ------------------------------------------------------------ edit diagnosis + kode
function cpOpenEdit(id) {
    const isNew = !id;
    cpLog(isNew ? 'Opening add diagnosis form' : `Opening edit diagnosis form: ${(__cp.data.diagnoses.find(x => x.id === id) || {}).nama || id}`);
    const d = isNew ? { id: 'd' + Math.random().toString(16).slice(2, 10), nama: '', peran: __cp.data.diagnoses.length ? 'komorbid' : 'utama', kelompok: 'Lainnya', onset: 'Kronis', severity: '', trajektori: '', dampak: 'moderate', dampak_ket: '', status_kontrol: '', aksi_medis: '', catatan_kartu: '', catatan_klinis: '', obat: [], catatan_tone: 'biru', tautan: { teks: '', target: 'edit' }, cci_kategori: 'none', kodes: {} }
        : JSON.parse(JSON.stringify(__cp.data.diagnoses.find(x => x.id === id)));
    const kel = (__cp.meta.kelompok || []).map(k => `<option value="${escapeHtml(k)}" ${d.kelompok === k ? 'selected' : ''}>${escapeHtml(cpT(k))}</option>`).join('');
    const cci = (__cp.meta.cci_categories || []).map(c => `<option value="${c.key}" ${d.cci_kategori === c.key ? 'selected' : ''}>${escapeHtml(c.label)}${c.weight ? ' (' + c.weight + ')' : ''}</option>`).join('');
    const dam = Object.entries(CP_DAMPAK).map(([k, v]) => `<option value="${k}" ${d.dampak === k ? 'selected' : ''}>${v.label}</option>`).join('');
    const sys = __cp.meta.code_systems.map(s => `<option value="${s.key}" ${__cp.system === s.key ? 'selected' : ''}>${escapeHtml(s.label)}</option>`).join('');
    const body = `
      <div class="field"><label>Diagnosis name*</label><input type="text" id="cpe-nama" value="${escapeHtml(d.nama)}"></div>
      <div class="cp-codebox">
        <div class="cp-codebox-head"><b>Diagnosis code</b><span class="cp-muted small" id="cpe-codes-have"></span></div>
        <div class="field-row"><div class="field"><label>Code system</label><select id="cpe-sys">${sys}</select></div>
            <div class="field"><label>Code</label><input type="text" id="cpe-kode" placeholder=""></div></div>
        <div class="field"><label>Code name (optional)</label><input type="text" id="cpe-kname"></div>
        <div class="cp-valid" id="cpe-valid"></div>
        <div class="cp-search"><input type="text" id="cpe-q" placeholder="Search the local list, e.g. diabetes or acute pain"><button type="button" class="btn-secondary btn-sm" id="cpe-find">Search</button></div>
        <div class="cp-results" id="cpe-results"></div>
        <button type="button" class="btn-secondary btn-sm" id="cpe-ai-one">AI suggest a code for this diagnosis</button>
      </div>
      <div class="field-row"><div class="field"><label>Role</label><select id="cpe-peran"><option value="utama" ${d.peran === 'utama' ? 'selected' : ''}>Primary diagnosis</option><option value="komorbid" ${d.peran !== 'utama' ? 'selected' : ''}>Comorbidity</option></select></div>
        <div class="field"><label>Group</label><select id="cpe-kel">${kel}</select></div></div>
      <div class="field-row"><div class="field"><label>Onset category</label><input type="text" id="cpe-onset" value="${escapeHtml(d.onset)}"></div>
        <div class="field"><label>Severity / stage</label><input type="text" id="cpe-sev" value="${escapeHtml(d.severity)}"></div></div>
      <div class="field-row"><div class="field"><label>Care trajectory</label><input type="text" id="cpe-traj" value="${escapeHtml(d.trajektori)}"></div>
        <div class="field"><label>Control status</label><input type="text" id="cpe-ctrl" value="${escapeHtml(d.status_kontrol)}"></div></div>
      <div class="field-row"><div class="field"><label>Impact on primary diagnosis</label><select id="cpe-dampak">${dam}</select></div>
        <div class="field"><label>Impact note</label><input type="text" id="cpe-dket" value="${escapeHtml(d.dampak_ket)}"></div></div>
      <div class="field-row"><div class="field"><label>Medical action (matrix button)</label><input type="text" id="cpe-aksi" value="${escapeHtml(d.aksi_medis)}"></div>
        <div class="field"><label>Charlson category (CCI)</label><select id="cpe-cci">${cci}</select></div></div>
      <div class="field-row"><div class="field"><label>Card note</label><input type="text" id="cpe-cat" value="${escapeHtml(d.catatan_kartu)}"></div>
        <div class="field"><label>Note colour</label><select id="cpe-tone">${['merah', 'kuning', 'hijau', 'biru'].map(t => `<option value="${t}" ${d.catatan_tone === t ? 'selected' : ''}>${({ merah: 'red', kuning: 'yellow', hijau: 'green', biru: 'blue' })[t]}</option>`).join('')}</select></div></div>
      <div class="field"><label>Detailed clinical note (shown on the card)</label><textarea id="cpe-detail" rows="2">${escapeHtml(d.catatan_klinis || '')}</textarea></div>
      <div class="field"><label>Medication / regimen (comma-separated)</label><input type="text" id="cpe-obat" value="${escapeHtml((d.obat || []).join(', '))}"></div>
      <div class="field-row"><div class="field"><label>Card link text</label><input type="text" id="cpe-ltxt" value="${escapeHtml(d.tautan.teks)}"></div>
        <div class="field"><label>Link target</label><select id="cpe-ltgt"><option value="edit" ${d.tautan.target === 'edit' ? 'selected' : ''}>Edit diagnosis</option><option value="scan" ${d.tautan.target === 'scan' ? 'selected' : ''}>Open AI Scan</option><option value="lab" ${d.tautan.target === 'lab' ? 'selected' : ''}>Update lab results</option></select></div></div>`;
    const m = cpModal(isNew ? 'Add Diagnosis' : 'Edit Diagnosis', body, (mm) => {
        if (!cpV(mm, 'cpe-nama')) { showToast('Diagnosis name is required.', 'error'); return false; }
        cpCommitCode(mm, d);
        Object.assign(d, { nama: cpV(mm, 'cpe-nama'), peran: cpV(mm, 'cpe-peran'), kelompok: cpV(mm, 'cpe-kel'), onset: cpV(mm, 'cpe-onset'), severity: cpV(mm, 'cpe-sev'), trajektori: cpV(mm, 'cpe-traj'),
            status_kontrol: cpV(mm, 'cpe-ctrl'), dampak: cpV(mm, 'cpe-dampak'), dampak_ket: cpV(mm, 'cpe-dket'), aksi_medis: cpV(mm, 'cpe-aksi'), cci_kategori: cpV(mm, 'cpe-cci'),
            catatan_kartu: cpV(mm, 'cpe-cat'), catatan_klinis: cpV(mm, 'cpe-detail'), obat: cpV(mm, 'cpe-obat').split(',').map(x => x.trim()).filter(Boolean), catatan_tone: cpV(mm, 'cpe-tone'), tautan: { teks: cpV(mm, 'cpe-ltxt'), target: cpV(mm, 'cpe-ltgt') } });
        if (d.peran === 'utama') { __cp.data.diagnoses.forEach(x => { if (x.id !== d.id && x.peran === 'utama') x.peran = 'komorbid'; }); d.dampak = 'primary'; }
        const list = __cp.data.diagnoses, i = list.findIndex(x => x.id === d.id);
        if (i === -1) list.push(d); else list[i] = d;
        if (d.peran === 'utama' && list.indexOf(d) > 0) { list.splice(list.indexOf(d), 1); list.unshift(d); }
        if (__cp.data.skor && !__cp.data.skor.cci_manual) cpRecalc();
        cpLog(`Diagnosis ${isNew ? 'added' : 'updated'}: ${d.nama}${Object.keys(d.kodes || {}).length ? ' (code ' + Object.entries(d.kodes).map(([s, k]) => cpSysLabel(s) + ' ' + k.kode).join(', ') + ')' : ''}`, 'ok');
        cpRender(); cpPersistSoon();
    }, isNew ? {} : { onDelete: () => { cpLog(`Diagnosis deleted: ${d.nama}`, 'warn'); __cp.data.diagnoses = __cp.data.diagnoses.filter(x => x.id !== d.id); if (!__cp.data.skor.cci_manual) cpRecalc(); cpRender(); cpPersistSoon(); } });

    // perilaku bagian kode
    const loadSys = () => {
        const sk = cpV(m, 'cpe-sys'), k = d.kodes[sk];
        m.querySelector('#cpe-kode').value = k ? k.kode : ''; m.querySelector('#cpe-kname').value = k ? k.nama : '';
        const hint = (__cp.meta.code_systems.find(s => s.key === sk) || {}).hint || '';
        m.querySelector('#cpe-kode').placeholder = hint;
        const have = Object.entries(d.kodes).filter(([, v]) => v && v.kode).map(([s, v]) => `${cpSysLabel(s)} ${v.kode}`).join(' | ');
        m.querySelector('#cpe-codes-have').textContent = have ? 'Saved: ' + have : '';
        m.querySelector('#cpe-results').innerHTML = ''; checkFmt();
    };
    let t;
    const checkFmt = () => {
        clearTimeout(t); const el = m.querySelector('#cpe-valid'); const code = cpV(m, 'cpe-kode');
        if (!code) { el.textContent = ''; el.className = 'cp-valid'; return; }
        t = setTimeout(async () => {
            try { const r = await apiFetch(`/api/code-systems/validate?system=${cpV(m, 'cpe-sys')}&code=${encodeURIComponent(code)}`);
                el.textContent = r.message; el.className = 'cp-valid ' + (r.valid === true ? 'ok' : r.valid === false ? 'bad' : ''); } catch (e) { /* abaikan */ }
        }, 300);
    };
    // simpan isian kode saat berganti sistem agar tidak hilang
    let prevSys = cpV(m, 'cpe-sys');
    m.querySelector('#cpe-sys').addEventListener('change', () => {
        const cur = cpV(m, 'cpe-sys'); const keep = cpV(m, 'cpe-sys'); void keep;
        // tulis balik isian sistem sebelumnya
        const code = cpV(m, 'cpe-kode');
        if (code) d.kodes[prevSys] = { kode: code, nama: cpV(m, 'cpe-kname'), sumber: 'manual' }; else delete d.kodes[prevSys];
        prevSys = cur; loadSys();
    });
    m.querySelector('#cpe-kode').addEventListener('input', checkFmt);
    const find = async () => {
        const q = cpV(m, 'cpe-q') || cpV(m, 'cpe-nama');
        try {
            const r = await apiFetch(`/api/code-systems/search?system=${cpV(m, 'cpe-sys')}&q=${encodeURIComponent(q)}`);
            m.querySelector('#cpe-results').innerHTML = r.results.length ? r.results.map(x => `<button type="button" class="cp-res" data-c="${escapeHtml(x.code)}" data-n="${escapeHtml(x.name)}"><b>${escapeHtml(x.code)}</b> ${escapeHtml(x.name)}</button>`).join('') + `<div class="cp-muted small">${escapeHtml(r.note)}</div>` : '<div class="cp-muted small">No results in the local list. Enter the code manually or use AI.</div>';
            m.querySelectorAll('.cp-res').forEach(b => b.addEventListener('click', () => { m.querySelector('#cpe-kode').value = b.dataset.c; m.querySelector('#cpe-kname').value = b.dataset.n; checkFmt(); }));
        } catch (e) { showToast(e.message, 'error'); }
    };
    m.querySelector('#cpe-find').addEventListener('click', find);
    m.querySelector('#cpe-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); find(); } });
    m.querySelector('#cpe-ai-one').addEventListener('click', async () => {
        if (isNew) { showToast('Save the diagnosis first, then use AI Fill Codes.', 'error'); return; }
        const ai = cpAi(); if (!ai) return;
        const sk = cpV(m, 'cpe-sys'); if (sk === 'lainnya') { showToast('The "Other" system is filled in manually.', 'error'); return; }
        const btn = m.querySelector('#cpe-ai-one'); btn.disabled = true; btn.textContent = 'AI bekerja...';
        try {
            cpLog(`AI suggesting ${cpSysLabel(sk)} code for diagnosis: ${d.nama}`);
            const res = await apiFetch(`/api/clinical-profile/${__cp.pid}/ai-codes`, { method: 'POST', body: JSON.stringify({ ...ai, code_system: sk, diagnosis_ids: [d.id] }) });
            const upd = res.data.diagnoses.find(x => x.id === d.id);
            if (upd && upd.kodes[sk]) { d.kodes[sk] = upd.kodes[sk]; __cp.data = res.data; loadSys(); cpRender(); cpLog(`AI suggested ${cpSysLabel(sk)} ${upd.kodes[sk].kode} for ${d.nama}`, 'ok'); } else showToast('The AI did not give a confident code for this diagnosis.', 'error');
        } catch (e) { showToast(e.message, 'error'); }
        btn.disabled = false; btn.textContent = 'AI suggest a code for this diagnosis';
    });
    loadSys();
}

function cpCommitCode(m, d) {
    const sk = cpV(m, 'cpe-sys'), code = cpV(m, 'cpe-kode');
    if (code) d.kodes[sk] = { kode: code, nama: cpV(m, 'cpe-kname'), sumber: (d.kodes[sk] && d.kodes[sk].kode === code && d.kodes[sk].sumber) || 'manual' };
    else delete d.kodes[sk];
}

// ------------------------------------------------------------ modal lain
function cpOpenHazard(id) {
    const h = id ? JSON.parse(JSON.stringify(__cp.data.hazards.find(x => x.id === id))) : { id: 'h' + Math.random().toString(16).slice(2, 10), judul: '', tingkat: 'Sedang', deskripsi: '', aksi: [], override: null };
    cpModal(id ? 'Edit Clinical Hazard' : 'Add Clinical Hazard', `
        <div class="field"><label>Title*</label><input type="text" id="cph-judul" value="${escapeHtml(h.judul)}"></div>
        <div class="field"><label>Level</label><select id="cph-tingkat">${['Kritis', 'Tinggi', 'Sedang', 'Rendah'].map(t => `<option value="${t}" ${h.tingkat === t ? 'selected' : ''}>${cpT(t)}</option>`).join('')}</select></div>
        <div class="field"><label>Description</label><textarea id="cph-desk" rows="3">${escapeHtml(h.deskripsi)}</textarea></div>
        <div class="field"><label>Actions (one per line, maximum 4)</label><textarea id="cph-aksi" rows="3">${escapeHtml((h.aksi || []).join('\n'))}</textarea></div>`, (m) => {
        if (!cpV(m, 'cph-judul')) { showToast('Title is required.', 'error'); return false; }
        Object.assign(h, { judul: cpV(m, 'cph-judul'), tingkat: cpV(m, 'cph-tingkat'), deskripsi: cpV(m, 'cph-desk'), aksi: cpV(m, 'cph-aksi').split('\n').map(x => x.trim()).filter(Boolean).slice(0, 4) });
        const list = __cp.data.hazards, i = list.findIndex(x => x.id === h.id); if (i === -1) list.push(h); else list[i] = h;
        cpLog(`Clinical hazard ${i === -1 ? 'added' : 'updated'}: ${h.judul} (${h.tingkat})`, 'ok');
        cpRenderHazards(); cpPersistSoon();
    });
}

function cpOpenLab() {
    if (!__cp.data) return;
    cpLog('Opening update lab results form');
    const o = __cp.data.organ;
    cpModal('Update Lab Results and Functional Status', `<div class="field-row cp-lab-grid">${CP_ORGAN_FIELDS.map(f => `<div class="field"><label>${f.label}</label><input type="number" step="${f.step}" id="cpl-${f.k}" value="${o[f.k] === null || o[f.k] === undefined ? '' : o[f.k]}"></div>`).join('')}</div>
        <div class="cp-muted small">Leave blank if not yet examined. Indicator colours follow general thresholds.</div>`, (m) => {
        CP_ORGAN_FIELDS.forEach(f => { const v = m.querySelector('#cpl-' + f.k).value.trim(); o[f.k] = v === '' ? null : Number(v); });
        cpLog(`Lab results and functional status updated: ${CP_ORGAN_FIELDS.filter(f => o[f.k] !== null).map(f => f.k.toUpperCase() + ' ' + o[f.k]).join(', ') || 'all empty'}`, 'ok');
        cpRenderOrgan(); cpPersistSoon();
    });
}

function cpOpenScores() {
    const s = __cp.data.skor;
    cpModal('Edit Scores and Estimates', `
        <div class="field"><label>CCI score (leave blank to calculate automatically from Charlson categories)</label><input type="number" min="0" id="cps-cci" value="${s.cci_manual ? s.cci_nilai : ''}"></div>
        <div class="field-row"><div class="field"><label>Baseline recovery estimate (%)</label><input type="number" min="0" max="100" id="cps-base" value="${s.pemulihan_baseline ?? ''}"></div>
        <div class="field"><label>Adjusted estimate (%)</label><input type="number" min="0" max="100" id="cps-corr" value="${s.pemulihan_terkoreksi ?? ''}"></div></div>
        <div class="field"><label>Adjusted recovery timeline target</label><input type="text" id="cps-time" value="${escapeHtml(s.timeline_terkoreksi)}" placeholder="e.g. 10 - 14 months"></div>
        <div class="field"><label>Assumption notes</label><textarea id="cps-note" rows="2">${escapeHtml(s.catatan)}</textarea></div>`, (m) => {
        const c = cpV(m, 'cps-cci');
        s.cci_manual = c !== ''; if (c !== '') s.cci_nilai = Number(c); else cpRecalc();
        s.cci_label = s.cci_nilai >= 5 ? 'High Risk' : s.cci_nilai >= 3 ? 'Moderate Risk' : s.cci_nilai >= 1 ? 'Mild Risk' : 'Low Risk';
        const b = cpV(m, 'cps-base'), r = cpV(m, 'cps-corr');
        s.pemulihan_baseline = b === '' ? null : Number(b); s.pemulihan_terkoreksi = r === '' ? null : Number(r);
        s.timeline_terkoreksi = cpV(m, 'cps-time'); s.catatan = cpV(m, 'cps-note');
        cpLog(`Scores and estimates updated: CCI ${s.cci_nilai} (${s.cci_label}), baseline ${s.pemulihan_baseline ?? '-'}%, adjusted ${s.pemulihan_terkoreksi ?? '-'}%`, 'ok');
        cpRenderScores(); cpPersistSoon();
    });
}

// ------------------------------------------------------------ dari hasil pemindaian
async function cpAddFromScan() {
    logLine('Adding scan diagnosis to the Clinical Profile', '', 'scan');
    const frame = __frames.find(f => f.id === __activeFrameId);
    const data = frame && frame.result && frame.result.data;
    if (!data || !data.diagnosis) { showToast('There is no diagnosis result on this frame yet.', 'error'); return; }
    const hist = frame.result.history || {};
    const pid = hist.patient_id || frame.patientId || document.getElementById('patient-select').value;
    if (!pid) { showToast('Select a patient in the sidebar first so the diagnosis can be added to the Clinical Profile.', 'error'); return; }
    try {
        const cur = await apiFetch(`/api/clinical-profile/${pid}`);
        const prof = cur.data;
        if (prof.diagnoses.some(d => d.nama.toLowerCase() === data.diagnosis.toLowerCase())) { showToast('This diagnosis is already in the Clinical Profile.', 'info'); return; }
        const sysKey = data.diagnosis_code_system ? mapCodeSystemBack(data.diagnosis_code_system) : 'auto';
        const kodes = {};
        const m = (data.diagnosis_code || '').match(/^\s*(?:ICD-?\s?10|ICD-?\s?11|SNOMED(?:\s*CT)?|SDKI|NANDA-?I?)\s+([A-Za-z0-9.\/]+)\s*(.*)$/i);
        const sk = sysKey === 'auto' ? ((data.diagnosis_code || '').toLowerCase().includes('icd-11') ? 'icd11' : (data.diagnosis_code || '').toLowerCase().includes('snomed') ? 'snomed' : 'icd10') : sysKey;
        if (m) kodes[sk] = { kode: m[1], nama: m[2] || '', sumber: 'ai' };
        const sev = ((data.anomalies || [])[0] || {}).severity || '';
        prof.diagnoses.push({ id: 'd' + Math.random().toString(16).slice(2, 10), nama: data.diagnosis, peran: prof.diagnoses.length ? 'komorbid' : 'utama', kelompok: 'Lainnya', onset: '', severity: sev, trajektori: '',
            dampak: prof.diagnoses.length ? 'moderate' : 'primary', dampak_ket: '', status_kontrol: '', aksi_medis: '', catatan_kartu: 'From AI scan', catatan_tone: 'biru', tautan: { teks: 'View ROI Image', target: 'scan' }, cci_kategori: 'none', kodes });
        await apiFetch(`/api/clinical-profile/${pid}`, { method: 'PUT', body: JSON.stringify({ data: prof, code_system: cur.code_system }) });
        showToast(`Diagnosis ${data.diagnosis} added to the Clinical Profile. Complete its category and code in Clinical History, under the Structured Clinical Profile.`, 'success');
    } catch (e) { showToast(`Failed to add: ${e.message}`, 'error'); }
}
