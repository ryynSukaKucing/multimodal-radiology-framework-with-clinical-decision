// =====================================================================
//  Viewer engine - Pemindaian AI (mengikuti mockup layout)
//  State frame (__frames, __activeFrameId, __maximizedId) ada di scan.js
// =====================================================================
const SVGNS = 'http://www.w3.org/2000/svg';
const $id = (i) => document.getElementById(i);

let __tool = null;             // null | draw | erase | select | measure | note | crop
let __mtool = 'line';
let __selMode = 'rect';        // rect | free
let __selTransparent = false;
let __continuous = false;
let __showAngles = true;
let __showInfo = true;
let __layout = null;           // {key, cols, rows} | null = auto
let __drawColor = '#ef4444';
let __drawSize = 3;
let __draft = null;
let __drag = null;
let __markSeq = 0;
// Sistem anatomi (Thorax_Anatomy_Taxonomy): tiap sistem punya layer sendiri; zona paru (turunan dari kontur paru) mati secara bawaan.
const ANAT_SYSTEMS = [
    { k: 'respiratory_system', l: 'Respiratory System' }, { k: 'cardiovascular_and_mediastinum', l: 'Cardiovascular & Mediastinum' },
    { k: 'pleura_and_diaphragm', l: 'Pleura & Diaphragm' }, { k: 'skeletal_system', l: 'Skeletal System' },
    { k: 'soft_tissue_and_abdominal', l: 'Soft Tissue & Abdominal' },
];
let __layers = Object.assign({ image: true, adet: true, aseg: true, albl: true, azone: false, ldet: true, lseg: true, llbl: true, dx: true, legend: true, grid: true },
    Object.fromEntries(ANAT_SYSTEMS.map(x => ['sys_' + x.k, true])));   // menu Layer (info pasien memakai __showInfo / tombol mata)
const LAYER_ITEMS = [
    { k: 'image', l: 'Image' },
    { t: 'Anatomy' }, { k: 'adet', l: 'Anatomy object detection' }, { k: 'aseg', l: 'Anatomy segmentation' },
    { k: 'albl', l: 'Anatomy labels' }, { k: 'azone', l: 'Lung zones (derived from outline)' },
    { t: 'Anatomical systems' }, ...ANAT_SYSTEMS.map(x => ({ k: 'sys_' + x.k, l: x.l })),
    { t: 'Lesions' }, { k: 'ldet', l: 'Lesion object detection' }, { k: 'lseg', l: 'Lesion segmentation (heatmap)' }, { k: 'llbl', l: 'Lesion labels' },
    { t: 'Annotations' }, { k: 'dx', l: 'Diagnosis on image' }, { k: 'legend', l: 'Anatomy legend & heatmap' },
    { k: 'grid', l: 'Grid & Ruler' }, { k: 'info', l: 'Patient info' },
];
// Batas bar warna: merah = kecerahan citra, hijau = opasitas visualisasi AI
const CONTRAST_MIN = 20, CONTRAST_MAX = 300;      // bar vertikal = kontras
const HUE_OFF = 0;                                // strip pelangi penuh, tanpa zona 'asli'
const HUE_DEFAULT = 200;                          // hue awal saat derajat pewarnaan dinaikkan

// Warna struktur anatomi toraks pada layer Segmentation / Object Detection (berdasarkan kata kunci label)
// Tiap struktur punya warna sendiri agar legenda tidak ambigu (kiri/kanan dibedakan). Label di luar daftar
// memakai palet cadangan yang dipilih stabil dari teks labelnya.
const STRUCT_COLORS = [
    [/paru kanan|right lung/i, '#38bdf8'], [/paru kiri|left lung/i, '#34d399'], [/jantung|heart|cardiac/i, '#f472b6'],
    [/mediastinum/i, '#a78bfa'], [/trakea|trachea|bronkus/i, '#fbbf24'], [/aort/i, '#fb923c'],
    [/hilus kanan|right hilum/i, '#2dd4bf'], [/hilus kiri|left hilum/i, '#a3e635'], [/hilus|hilum/i, '#2dd4bf'],
    [/diafragma kanan|right diaphragm/i, '#71717a'], [/diafragma kiri|left diaphragm/i, '#d4d4d8'], [/diafragma|diaphragm/i, '#94a3b8'],
];
const STRUCT_FALLBACK = ['#22d3ee', '#4ade80', '#fde047', '#c084fc', '#fdba74', '#67e8f9', '#bef264', '#f0abfc'];
function structColor(label) {
    const m = STRUCT_COLORS.find(c => c[0].test(label || ''));
    if (m) return m[1];
    let h = 0; for (const ch of String(label || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return STRUCT_FALLBACK[h % STRUCT_FALLBACK.length];
}
// Warna struktur: dari taksonomi backend (st.color); riwayat lama tanpa warna memakai pemetaan kata kunci di atas.
function stColor(st) { return (st && st.color) || structColor(st && st.label); }
const LAYER_NOTE = 'Anatomy (thorax taxonomy ids; dashed boxes, coloured outlines/lines) and Lesions (boxes + severity heatmap, linked to anatomy) are produced automatically by the AI model; hide them per layer or per system in the Layer menu.';
const LAYOUT_OPTIONS = [
    { key: '1x1', cols: 1, rows: 1 }, { key: '1x2', cols: 2, rows: 1 }, { key: '1x3', cols: 3, rows: 1 },
    { key: '1x4', cols: 4, rows: 1 }, { key: '2x1', cols: 1, rows: 2 }, { key: '2x2', cols: 2, rows: 2 },
    { key: '2x3', cols: 3, rows: 2 }, { key: '2x4', cols: 4, rows: 2 }, { key: '3x1', cols: 1, rows: 3 },
    { key: '3x2', cols: 2, rows: 3 }, { key: '3x3', cols: 3, rows: 3 }, { key: '4x2', cols: 2, rows: 4 },
    { key: '4x4', cols: 4, rows: 4 },
];
const DRAW_COLORS = ['#ef4444', '#f59e0b', '#facc15', '#22c55e', '#22d3ee', '#3b82f6', '#d946ef', '#ffffff', '#000000'];

// ----- Color palette (Image Setting > Color Palette) -----
const PALETTES = [
    { key: 'hotiron', label: 'Hot iron', stops: [[0, '#000000'], [.35, '#d00000'], [.7, '#ffe000'], [1, '#ffffff']] },
    { key: 'pet', label: 'PET', stops: [[0, '#001b1b'], [.2, '#0a3a8a'], [.4, '#6a1bb0'], [.65, '#e0301e'], [.85, '#ffb000'], [1, '#ffff60']] },
    { key: 'hotmetalblue', label: 'Hot metal blue', stops: [[0, '#000030'], [.3, '#2020c0'], [.55, '#a040c0'], [.8, '#ffa060'], [1, '#ffffff']] },
    { key: 'pet20', label: 'PET 20 step', steps: 20, stops: [[0, '#001b1b'], [.2, '#0a3a8a'], [.4, '#6a1bb0'], [.65, '#e0301e'], [.85, '#ffb000'], [1, '#ffff60']] },
    { key: 'spring', label: 'Spring', stops: [[0, '#ff00ff'], [1, '#ffff00']] },
    { key: 'summer', label: 'Summer', stops: [[0, '#00ff40'], [1, '#0080ff']] },
    { key: 'fall', label: 'Fall', stops: [[0, '#ffff00'], [1, '#ff2000']] },
    { key: 'winter', label: 'Winter', stops: [[0, '#0000ff'], [1, '#40ff80']] },
    { key: 'spectrum2', label: 'Spectrum2', stops: [[0, '#0000ff'], [.25, '#00ffff'], [.5, '#00ff00'], [.75, '#ffff00'], [1, '#ff0000']] },
];
const __lutCache = {};
function hexRgb(h) { h = h.replace('#', ''); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; }
function paletteLUT(key) {
    if (__lutCache[key]) return __lutCache[key];
    const p = PALETTES.find(x => x.key === key); const lut = new Uint8Array(768);
    for (let i = 0; i < 256; i++) {
        let t = i / 255;
        if (p.steps) t = Math.min(1, Math.floor(t * p.steps) / (p.steps - 1));
        let a = p.stops[0], b = p.stops[p.stops.length - 1];
        for (let s = 0; s < p.stops.length - 1; s++) if (t >= p.stops[s][0] && t <= p.stops[s + 1][0]) { a = p.stops[s]; b = p.stops[s + 1]; break; }
        const f = b[0] === a[0] ? 0 : (t - a[0]) / (b[0] - a[0]); const ca = hexRgb(a[1]), cb = hexRgb(b[1]);
        for (let c = 0; c < 3; c++) lut[i * 3 + c] = Math.round(ca[c] + (cb[c] - ca[c]) * f);
    }
    return (__lutCache[key] = lut);
}
function paletteCss(p, dir) { return `linear-gradient(${dir}, ${p.stops.map(s => `${s[1]} ${Math.round(s[0] * 100)}%`).join(',')})`; }

// ----- Measurement definitions (menu = gambar 5 & 6) -----
// n = jumlah klik; drag = seret kotak; free = coret bebas; closed = poligon
const MT = {
    line: { n: 2, hint: 'click 2 points' }, angle: { n: 3, hint: 'click 3 points (2nd point = vertex)' },
    cobb: { n: 4, hint: 'click 4 points (2 lines)' }, polyline: { n: Infinity, min: 2, hint: 'click points, double-click to finish' },
    area: { n: Infinity, min: 3, closed: true, hint: 'click corner points, click the start point / double-click to close' },
    ellipse: { drag: true, hint: 'drag to create an ellipse' }, rectangle: { drag: true, hint: 'drag to create a rectangle' },
    heightdiff: { n: 2, hint: 'click 2 points (height difference)' }, ctr: { n: 4, hint: 'click 2 points for heart width, then 2 points for thorax width' },
    flatfoot: { n: 3, hint: 'click 3 points (foot arch angle)' }, gonio: { n: 3, hint: 'click 3 points (joint angle)' },
    hto: { n: 4, hint: 'click 4 points (2 axis lines)' }, vertebra: { n: 4, hint: 'click 4 points (2 end-plates)' },
    spine: { n: 1, hint: 'click on each vertebra (C1, C2, ...)' },
    roi: { n: Infinity, min: 3, closed: true, hint: 'click ROI corner points, double-click to finish (computes mean intensity)' },
    closedpoly: { n: Infinity, min: 3, closed: true, hint: 'click corner points, double-click to close' },
    flexpoly: { free: true, hint: 'hold & draw a freeform shape (closes automatically)' },
    arrow: { n: 2, hint: 'click the arrow base, then the tip' }, text: { n: 1, hint: 'click the text location' },
    intensity: { n: 1, hint: 'click a point to read pixel intensity' }, ruler: { n: 2, hint: 'click 2 points' },
    calibration: { n: 2, hint: 'click 2 points on an object of known size, then enter its length (mm)' },
    mask: { drag: true, hint: 'drag the area to be blacked out' },
};
const MEAS_ITEMS = [
    { k: 'line', l: 'Line', s: 'D', i: 'M4 20L20 4' }, { k: 'angle', l: 'Angle', s: 'A', i: 'M4 20h16M4 20L15 6M9 20a5 5 0 0 0-1.5-3.5' },
    { k: 'cobb', l: 'Cobb Angle', i: 'M4 18l10-4M6 6l12 4M12 8l1 6' }, { k: 'polyline', l: 'Polyline', i: 'M4 18l5-8 5 5 6-9' },
    { k: 'area', l: 'Area', i: 'M5 5h14v14H5z' }, { k: 'ellipse', l: 'Ellipse', i: 'M3 12a9 6 0 1 0 18 0a9 6 0 1 0-18 0' },
    { k: 'rectangle', l: 'Rectangle', i: 'M3 7h18v10H3z' }, { k: 'volume', l: 'Volume', i: 'M12 3l8 4v10l-8 4-8-4V7zM12 12l8-5M12 12v9M12 12L4 7', off: 'Requires volumetric/series data (multi-slice CT/MRI)' },
    { k: 'cardiacvol', l: 'Cardiac Volume', i: 'M12 3c5 0 8 5 6 10s-6 8-6 8-8-4-8-10 3-8 8-8z', off: 'Requires cardiac series data' },
    { k: 'heightdiff', l: 'Height Difference', i: 'M4 18h6V8h10' }, { k: 'ctr', l: 'CTR', i: 'M4 20h16M12 4v16M6 12h4M14 12h4' },
    { k: 'flatfoot', l: 'Flatfoot', i: 'M3 18l8-9 10 9' }, { k: 'gonio', l: 'Goniometry', i: 'M5 20L19 8M5 20h14M9 20a6 6 0 0 0-1-4' },
    { k: 'hto', l: 'HTO angles', i: 'M12 3v18M8 8h8M8 16h8' }, { k: 'vertebra', l: 'Vertebra Angle', i: 'M7 5h10M6 10h12M7 15h10M9 20h6' },
    { k: 'spine', l: 'Spine Labeling', i: 'M8 4h8v4H8zM8 10h8v4H8zM8 16h8v4H8z' },
    { k: 'tic', l: 'Time-Intensity Curve', i: 'M3 18l5-7 4 4 5-9 4 6', off: 'Requires a time series (cine/dynamic)' },
    { k: 'roi', l: 'ROI', i: 'M5 9l7-5 7 5-2 9H7z' }, { k: 'closedpoly', l: 'Closed polygon', i: 'M4 12c0-5 6-8 10-6s6 6 3 10-9 4-11 1z' },
    { k: 'flexpoly', l: 'Flexpoly', s: 'N', i: 'M3 13c2-6 8-8 12-5s6 2 6 6-6 6-10 4-6-1-8-5z' },
    { k: 'pencil', l: 'Pencil', s: 'B', i: 'M4 20l1-4L17 4l3 3L8 19z' }, { k: 'arrow', l: 'Arrow', s: 'G', i: 'M4 20L19 5M19 5h-7M19 5v7' },
    { k: 'text', l: 'Text', i: 'M5 20L12 4l7 16M8 15h8' }, { k: 'myocardium', l: 'Myocardium ROI', i: 'M12 4a8 7 0 1 0 0 14a8 7 0 1 0 0-14M12 8a4 3 0 1 0 0 6a4 3 0 1 0 0-6', off: 'Requires short-axis cardiac images' },
    { sep: true },
    { k: 'continuous', l: 'Continuous measurement', s: 'H', i: 'M14 4l6 6-3 1-4 4-1 4-2-2-5 5M9 9l6 6', toggle: true },
    { k: 'intensity', l: 'Intensity', s: 'V', i: 'M3 19h18L3 9z' }, { k: 'showangles', l: 'Show Angles', i: 'M4 20h16M4 20L15 6M9 20a5 5 0 0 0-1.5-3.5', toggle: true },
    { k: 'ruler', l: 'Ruler', i: 'M3 15l12-12 6 6-12 12zM7 11l2 2M10 8l2 2M13 5l2 2' },
    { k: 'calibration', l: 'Calibration line', i: 'M4 20L20 4M3 21l2-2M19 5l2-2' }, { k: 'mask', l: 'Mask', i: 'M4 4h16v16H4z' },
    { sep: true },
    { k: 'delselected', l: 'Delete Selected', s: 'Shift + D, Delete', i: 'M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13' },
    { k: 'delall', l: 'Delete All', s: 'Ctrl + Delete, E', i: 'M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13' },
];
const SPINE_LABELS = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12', 'L1', 'L2', 'L3', 'L4', 'L5', 'S1'];
const ANGLE_TYPES = ['angle', 'cobb', 'gonio', 'flatfoot', 'hto', 'vertebra'];

// ===================== Frame model =====================
function defaultView() {
    return { scale: 1, tx: 0, ty: 0, brightness: 100, contrast: 100, rotate: 0, flipH: false, flipV: false,
             invert: false, sharpen: 0, opacity: 100, he: false, palette: 'none', aiOpacity: 100,
             hue: null, aiHue: null, aiContrast: 100, colorDeg: 0 };   // colorDeg 0 = warna asli (hitam putih hasil upload)
}
function makeFrame(o) {
    return Object.assign({
        id: '', file: null, name: '', dataUrl: null, isDicom: false, status: 'pending', result: null,
        readOnly: false, view: defaultView(), strokes: [], marks: [], selection: null, selMark: null,
        meta: {}, cfg: null, pxMm: null, crop: null, patientId: null, examAt: new Date(),
        natW: 0, natH: 0, srcImg: null, _proc: null, _procKey: '', _fit: null, _orig: null,
    }, o);
}
const getFrame = (id) => __frames.find(f => f.id === id);
const activeFrame = () => getFrame(__activeFrameId);
const cellOf = (id) => document.querySelector(`.frame-cell[data-id="${id}"]`);
const nextMarkId = () => `m${++__markSeq}`;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// ===================== Init =====================
document.addEventListener('DOMContentLoaded', () => {
    setupDropdowns();
    renderLayoutTypeList();
    buildSelectMenu();
    buildRotateMenu();
    buildMeasureMenu();
    buildDrawMenu();
    buildImageSettingMenu();
    buildLayerMenu();
    document.querySelectorAll('.tool-btn[data-tool]').forEach(b => b.addEventListener('click', () => {
        const t = b.dataset.tool;
        if (t === 'measure') return; // Measurement: cukup buka menu, alat dipilih dari daftar
        setTool(__tool === t ? null : t);
    }));
    $id('btn-zoom-in').addEventListener('click', () => nudgeZoom(1.25));
    $id('btn-zoom-out').addEventListener('click', () => nudgeZoom(0.8));
    $id('btn-view-reset').addEventListener('click', resetActiveView);
    $id('btn-print').addEventListener('click', printScan);
    document.addEventListener('keydown', onKeyDown);
    if (window.ResizeObserver) {
        let raf = 0;
        new ResizeObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(relayoutAll); }).observe($id('frame-grid'));
    }
    window.addEventListener('afterprint', () => document.body.classList.remove('printing-scan'));
    renderFrameGrid();
    renderFrameThumbList();
    updateHint();
});

function setupDropdowns() {
    document.querySelectorAll('.dropdown').forEach(dd => {
        const toggle = dd.querySelector(':scope > .dropdown-toggle');
        if (!toggle) return;
        toggle.addEventListener('click', (ev) => {
            ev.stopPropagation();
            const wasOpen = dd.classList.contains('open');
            closeDropdowns();
            if (!wasOpen) dd.classList.add('open');
        });
        dd.querySelector(':scope > .dropdown-panel')?.addEventListener('click', (ev) => ev.stopPropagation());
    });
    document.addEventListener('click', closeDropdowns);
}
function closeDropdowns() {
    document.querySelectorAll('.dropdown.open').forEach(o => o.classList.remove('open'));
    document.querySelectorAll('.sub-open').forEach(o => o.classList.remove('sub-open'));
}

// ===================== Layer (Citra / Visualisasi AI / Grid / Info) =====================
function buildLayerMenu() {
    const m = $id('menu-layer');
    m.innerHTML = '<div class="dd-title">Layer</div>' + LAYER_ITEMS.map(i => i.t
        ? `<div class="dd-title dd-sub">${i.t}</div>`
        : `<div class="dd-item" data-layer="${i.k}"><span class="lb">${i.l}</span><span class="chk" data-lc="${i.k}"></span></div>`).join('');
    m.querySelectorAll('[data-layer]').forEach(it => it.addEventListener('click', () => {
        const k = it.dataset.layer;
        if (k === 'info') __showInfo = !__showInfo; else __layers[k] = !__layers[k];
        applyLayers();
        logLine(`Layer ${(LAYER_ITEMS.find(i => i.k === k) || {}).l || k}: ${(k === 'info' ? __showInfo : __layers[k]) ? 'shown' : 'hidden'}`);
    }));
    applyLayers();
}
function applyLayers() {
    const g = $id('frame-grid');
    g.classList.toggle('layer-off-image', !__layers.image);
    Object.keys(__layers).filter(k => k !== 'image').forEach(k => g.classList.toggle('layer-off-' + k, !__layers[k]));
    g.classList.toggle('hide-info', !__showInfo);
    document.querySelectorAll('#menu-layer [data-lc]').forEach(e => {
        const k = e.dataset.lc; e.classList.toggle('on', k === 'info' ? __showInfo : !!__layers[k]);
    });
    if (typeof __frames !== 'undefined') __frames.forEach(f => { const c = cellOf(f.id); if (c && f._fit) positionLabels(f, c); });   // susun ulang label setelah layer berubah
}

function layoutGlyph(c, r) {
    return `<span class="lg" style="grid-template-columns:repeat(${c},1fr)">${'<i></i>'.repeat(Math.min(c * r, 16))}</span>`;
}
function renderLayoutTypeList() {
    const el = $id('layout-type-list');
    el.innerHTML = `<div class="layout-type-item${!__layout ? ' active' : ''}" data-layout="auto">Auto</div>` +
        LAYOUT_OPTIONS.map(l => `<div class="layout-type-item${__layout && __layout.key === l.key ? ' active' : ''}" data-layout="${l.key}">${layoutGlyph(l.cols, l.rows)}${l.key}</div>`).join('');
    el.querySelectorAll('.layout-type-item').forEach(item => item.addEventListener('click', () => {
        __layout = item.dataset.layout === 'auto' ? null : LAYOUT_OPTIONS.find(l => l.key === item.dataset.layout);
        __maximizedId = null; renderLayoutTypeList(); renderFrameGrid(); closeDropdowns();
        logLine(`Layout frame: ${item.dataset.layout === 'auto' ? 'Auto' : item.dataset.layout}`);
    }));
}

// ===================== Menu Select (gambar 3) =====================
function buildSelectMenu() {
    const m = $id('menu-select');
    m.innerHTML = `
        <div class="dd-item" data-act="sel-rect"><span class="chk" data-c="sel-rect"></span>Rectangle</div>
        <div class="dd-item" data-act="sel-free"><span class="chk" data-c="sel-free"></span>Free-form</div>
        <div class="dd-sep"></div>
        <div class="dd-item" data-act="sel-all">Select all<span class="sc">Ctrl+A</span></div>
        <div class="dd-item" data-act="sel-invert">Invert selection</div>
        <div class="dd-item" data-act="sel-transp"><span class="chk" data-c="sel-transp"></span>Transparent selection</div>
        <div class="dd-item" data-act="sel-delete">Delete<span class="sc">Delete</span></div>`;
    m.querySelectorAll('.dd-item').forEach(it => it.addEventListener('click', () => {
        if (it.classList.contains('disabled')) return;
        const a = it.dataset.act;
        if (a === 'sel-rect' || a === 'sel-free') { __selMode = a === 'sel-rect' ? 'rect' : 'free'; setTool('select'); }
        logLine(`Select menu: ${({ 'sel-rect': 'Rectangle', 'sel-free': 'Free-form', 'sel-all': 'Select all', 'sel-invert': 'Invert selection', 'sel-transp': 'Transparent selection', 'sel-delete': 'Delete selection contents' })[a] || a}`);
        if (a === 'sel-all') selectAll();
        if (a === 'sel-invert') { const f = activeFrame(); if (f && f.selection) { f.selection.invert = !f.selection.invert; drawFrameAnnotations(f.id); } }
        if (a === 'sel-transp') { __selTransparent = !__selTransparent; __frames.forEach(f => drawFrameAnnotations(f.id)); }
        if (a === 'sel-delete') deleteSelectionContent();
        updateSelectMenuState(); closeDropdowns();
    }));
    updateSelectMenuState();
}
function updateSelectMenuState() {
    const f = activeFrame(); const has = !!(f && f.selection);
    document.querySelectorAll('#menu-select [data-act="sel-invert"], #menu-select [data-act="sel-delete"]').forEach(e => e.classList.toggle('disabled', !has));
    const setC = (c, on) => { const e = document.querySelector(`#menu-select [data-c="${c}"]`); if (e) e.classList.toggle('on', on); };
    setC('sel-rect', __selMode === 'rect'); setC('sel-free', __selMode === 'free'); setC('sel-transp', __selTransparent);
}
function selectAll() {
    const f = activeFrame(); if (!f) return;
    f.selection = { pts: [[0, 0], [1, 0], [1, 1], [0, 1]], invert: false };
    updateSelectMenuState(); drawFrameAnnotations(f.id);
}
function deleteSelectionContent() {
    const f = activeFrame(); if (!f || !f.selection) return;
    f.marks.push({ id: nextMarkId(), type: 'mask', pts: f.selection.pts, invert: f.selection.invert });
    f.selection = null; updateSelectMenuState(); drawFrameAnnotations(f.id);
}

// ===================== Menu Rotate (gambar 4) =====================
function buildRotateMenu() {
    const m = $id('menu-rotate');
    m.innerHTML = `
        <div class="dd-item" data-act="rot-r"><svg class="mi"><use href="#i-rotate"/></svg>Rotate Right</div>
        <div class="dd-item" data-act="rot-l"><svg class="mi" style="transform:scaleX(-1)"><use href="#i-rotate"/></svg>Rotate Left</div>
        <div class="dd-sep"></div>
        <div class="dd-item" data-act="flip-h"><svg class="mi"><path d="M12 3v18M8 7l-5 10h5zM16 7l5 10h-5z"/></svg>Flip Horizontal</div>
        <div class="dd-item" data-act="flip-v"><svg class="mi"><path d="M3 12h18M7 8l10-5v5zM7 16l10 5v-5z"/></svg>Flip Vertical</div>
        <div class="dd-sep"></div>
        <div class="dd-item" data-act="clear-tf"><svg class="mi"><use href="#i-reset"/></svg>Clear Transform</div>`;
    m.querySelectorAll('.dd-item').forEach(it => it.addEventListener('click', () => {
        const f = activeFrame(); if (!f) return closeDropdowns();
        const v = f.view, a = it.dataset.act;
        if (a === 'rot-r') v.rotate = (v.rotate + 90) % 360;
        if (a === 'rot-l') v.rotate = (v.rotate + 270) % 360;
        if (a === 'flip-h') v.flipH = !v.flipH;
        if (a === 'flip-v') v.flipV = !v.flipV;
        if (a === 'clear-tf') { v.rotate = 0; v.flipH = false; v.flipV = false; v.tx = 0; v.ty = 0; v.scale = 1; }
        logLine(`Frame ${__frames.indexOf(f) + 1} transform: ${it.textContent.trim()}`);
        relayoutFrame(f); closeDropdowns();
    }));
}

// ===================== Menu Measurement (gambar 5 & 6) =====================
function buildMeasureMenu() {
    const m = $id('menu-measure');
    m.innerHTML = MEAS_ITEMS.map(it => it.sep ? '<div class="dd-sep"></div>' :
        `<div class="dd-item${it.off ? ' disabled' : ''}" data-k="${it.k}" ${it.off ? `title="${it.off}"` : ''}>
            <svg class="mi" viewBox="0 0 24 24"><path d="${it.i}"/></svg><span class="lb">${it.l}</span>
            ${it.toggle ? `<span class="chk" data-t="${it.k}"></span>` : ''}${it.s ? `<span class="sc">${it.s}</span>` : ''}</div>`).join('');
    m.querySelectorAll('.dd-item').forEach(it => it.addEventListener('click', () => {
        if (it.classList.contains('disabled')) { showToast(it.title || 'Not available for a single image.', 'error'); return; }
        pickMeasure(it.dataset.k); closeDropdowns();
    }));
    updateMeasureChecks();
}
function updateMeasureChecks() {
    const set = (k, on) => { const e = document.querySelector(`#menu-measure [data-t="${k}"]`); if (e) e.classList.toggle('on', on); };
    set('continuous', __continuous); set('showangles', __showAngles);
}
function pickMeasure(k) {
    if (k === 'continuous') { __continuous = !__continuous; updateMeasureChecks(); updateHint(); return; }
    if (k === 'showangles') { __showAngles = !__showAngles; updateMeasureChecks(); __frames.forEach(f => drawFrameAnnotations(f.id)); return; }
    if (k === 'delselected') return deleteSelectedMark();
    if (k === 'delall') return deleteAllMarks();
    if (k === 'pencil') return setTool('draw');
    setTool('measure', k);
}
function deleteSelectedMark() {
    const f = activeFrame(); if (!f || !f.selMark) { showToast('Click a measurement (with no tool active) to select it first.', 'error'); return; }
    f.marks = f.marks.filter(m => m.id !== f.selMark); f.selMark = null; drawFrameAnnotations(f.id);
    logLine('One measurement deleted');
}
function deleteAllMarks() {
    const f = activeFrame(); if (!f) return;
    if (!f.marks.length && !f.strokes.length) return;
    if (!confirm('Delete all measurements, notes, and strokes on this frame?')) return;
    f.marks = []; f.strokes = []; f.selMark = null; f.selection = null; drawFrameAnnotations(f.id);
    logLine(`All measurements, notes, and strokes on Frame ${__frames.indexOf(f) + 1} deleted`);
}

// ===================== Menu Draw (warna) =====================
function buildDrawMenu() {
    const m = $id('menu-draw');
    m.innerHTML = `<div class="dd-title">Warna coretan</div>
        <div class="swatches">${DRAW_COLORS.map(c => `<button type="button" class="swatch${c === __drawColor ? ' active' : ''}" data-c="${c}" style="background:${c}" title="${c}"></button>`).join('')}
            <input type="color" id="draw-color-custom" value="${__drawColor}" title="Warna lain"></div>
        <div class="dd-title">Ketebalan</div>
        <input type="range" id="draw-size" min="1" max="14" value="${__drawSize}">`;
    const paint = () => m.querySelectorAll('.swatch').forEach(s => s.classList.toggle('active', s.dataset.c === __drawColor));
    m.querySelectorAll('.swatch').forEach(s => s.addEventListener('click', () => { __drawColor = s.dataset.c; $id('draw-color-custom').value = __drawColor; paint(); }));
    $id('draw-color-custom').addEventListener('input', (e) => { __drawColor = e.target.value; paint(); });
    $id('draw-size').addEventListener('input', (e) => { __drawSize = parseInt(e.target.value, 10); });
    document.querySelector('[data-act="erase-all"]').addEventListener('click', () => {
        const f = activeFrame(); if (!f) return closeDropdowns();
        f.strokes = []; drawFrameAnnotations(f.id); closeDropdowns();
        logLine(`All strokes on Frame ${__frames.indexOf(f) + 1} deleted`);
    });
}

// ===================== Menu Image Setting (gambar 7 & 8) =====================
function buildImageSettingMenu() {
    const m = $id('menu-image-setting');
    m.innerHTML = `
        <div class="dd-item has-sub" data-sub="bc"><span class="lb">Contrast And Brightness</span><span class="arr">›</span>
            <div class="dd-flyout menu-dark">
                <label class="vt-slider-label">Brightness<input type="range" id="slider-brightness" min="20" max="250" value="100"></label>
                <label class="vt-slider-label">Contrast<input type="range" id="slider-contrast" min="20" max="300" value="100"></label></div></div>
        <div class="dd-item" data-act="invert"><span class="lb">Invert</span><span class="chk" data-c="invert"></span></div>
        <div class="dd-item has-sub" data-sub="sharpen"><span class="lb">Sharpen</span><span class="arr">›</span>
            <div class="dd-flyout menu-dark"><label class="vt-slider-label">Strength<input type="range" id="slider-sharpen" min="0" max="100" value="0"></label></div></div>
        <div class="dd-item has-sub" data-sub="opacity"><span class="lb">Opacity</span><span class="arr">›</span>
            <div class="dd-flyout menu-dark"><label class="vt-slider-label">Image opacity<input type="range" id="slider-opacity" min="10" max="100" value="100"></label>
                <label class="vt-slider-label">AI overlay opacity<input type="range" id="slider-ai-opacity" min="0" max="100" value="100"></label></div></div>
        <div class="dd-item" data-act="he"><span class="lb">Histogram Equalization</span><span class="chk" data-c="he"></span></div>
        <div class="dd-item has-sub" data-sub="palette"><span class="lb">Color Palette</span><span class="arr">›</span>
            <div class="dd-flyout menu-dark pal-list" id="palette-list"></div></div>`;
    const pal = $id('palette-list');
    pal.innerHTML = PALETTES.map(p => `<div class="pal-item" data-p="${p.key}" style="background:${paletteCss(p, 'to right')}"><span>${p.label}</span></div>`).join('') +
        '<div class="pal-item pal-none" data-p="none"><span>None</span></div>';
    pal.querySelectorAll('.pal-item').forEach(it => it.addEventListener('click', (ev) => {
        ev.stopPropagation(); const f = activeFrame(); if (!f) return;
        f.view.palette = it.dataset.p; syncImageSettingUI(); scheduleProcess(f);
        logLine(`Image Setting, Color Palette: ${it.textContent.trim()}`);
    }));
    m.querySelectorAll('.has-sub').forEach(it => it.addEventListener('click', (ev) => {
        if (ev.target.closest('.dd-flyout')) return;
        const open = it.classList.contains('sub-open');
        m.querySelectorAll('.sub-open').forEach(o => o.classList.remove('sub-open'));
        if (!open) { it.classList.add('sub-open'); positionFlyout(it.querySelector(':scope > .dd-flyout')); }
    }));
    m.querySelectorAll('.dd-flyout').forEach(fl => fl.addEventListener('click', (ev) => ev.stopPropagation()));
    m.querySelectorAll('[data-act]').forEach(it => it.addEventListener('click', () => {
        const f = activeFrame(); if (!f) return;
        if (it.dataset.act === 'invert') f.view.invert = !f.view.invert;
        if (it.dataset.act === 'he') f.view.he = !f.view.he;
        logLine(`Image Setting, ${it.dataset.act === 'he' ? 'Histogram Equalization' : 'Invert'}: ${f.view[it.dataset.act === 'he' ? 'he' : 'invert'] ? 'on' : 'off'}`);
        syncImageSettingUI(); scheduleProcess(f);
    }));
    const bind = (id, key, needsProcess) => $id(id).addEventListener('input', (e) => {
        const f = activeFrame(); if (!f) return;
        f.view[key] = parseInt(e.target.value, 10);
        if (needsProcess) scheduleProcess(f); else { applyFrameView(f.id); }
    });
    bind('slider-brightness', 'brightness'); bind('slider-contrast', 'contrast');
    bind('slider-opacity', 'opacity'); bind('slider-sharpen', 'sharpen', true); bind('slider-ai-opacity', 'aiOpacity');
    [['slider-brightness', 'Brightness'], ['slider-contrast', 'Contrast'], ['slider-opacity', 'Image opacity'], ['slider-sharpen', 'Sharpen'], ['slider-ai-opacity', 'AI overlay opacity']]
        .forEach(([id, n]) => $id(id).addEventListener('change', (e) => logLine(`Image Setting, ${n}: ${e.target.value}`)));
}
// Flyout submenu dibuka ke kanan; bila keluar layar -> buka ke kiri, dan geser ke atas bila melewati tepi bawah.
function positionFlyout(fl) {
    if (!fl) return;
    fl.style.left = ''; fl.style.right = ''; fl.style.top = ''; fl.style.bottom = '';
    let r = fl.getBoundingClientRect();
    if (r.right > window.innerWidth - 8) { fl.style.left = 'auto'; fl.style.right = 'calc(100% + 6px)'; r = fl.getBoundingClientRect(); }
    if (r.bottom > window.innerHeight - 8) { fl.style.top = 'auto'; fl.style.bottom = '-6px'; }
}
function syncImageSettingUI() {
    const f = activeFrame(); const v = f ? f.view : defaultView();
    $id('slider-brightness').value = v.brightness; $id('slider-contrast').value = v.contrast;
    $id('slider-opacity').value = v.opacity; $id('slider-sharpen').value = v.sharpen;
    $id('slider-ai-opacity').value = v.aiOpacity == null ? 100 : v.aiOpacity;
    document.querySelectorAll('#menu-image-setting [data-c]').forEach(e => e.classList.toggle('on', !!v[e.dataset.c]));
    document.querySelectorAll('#palette-list .pal-item').forEach(e => e.classList.toggle('active', e.dataset.p === v.palette));
    updateSelectMenuState();
}

// ===================== Tool state =====================
const TOOL_LOG_NAME = { draw: 'Draw', erase: 'Erase', select: 'Select', crop: 'Crop', note: 'Text', measure: 'Measurement' };
function setTool(tool, mt) {
    if ((tool || null) !== __tool || (tool === 'measure' && mt && mt !== __mtool)) {
        if (tool) logLine(`Alat dipilih: ${TOOL_LOG_NAME[tool] || tool}${tool === 'measure' && mt ? ' (' + ((MEAS_ITEMS.find(i => i.k === mt) || {}).l || mt) + ')' : ''}`);
        else if (__tool) logLine(`Alat ${TOOL_LOG_NAME[__tool] || __tool} dinonaktifkan`);
    }
    __tool = tool || null;
    if (tool === 'measure' && mt) __mtool = mt;
    __draft = null; __drag = null;
    document.querySelectorAll('.tool-btn[data-tool]').forEach(b => b.classList.toggle('active', b.dataset.tool === __tool));
    const v = $id('rv-viewer');
    v.className = v.className.replace(/\btool-\S+/g, '').trim() + ` tool-${__tool || 'none'}`;
    updateHint();
    if (__activeFrameId) drawFrameAnnotations(__activeFrameId);
}
function updateHint() {
    const h = $id('rv-hint'); let t;
    const lbl = (MEAS_ITEMS.find(i => i.k === __mtool) || {}).l || '';
    if (__tool === 'draw') t = 'Draw: hold & drag to draw. Change the colour in the Draw menu.';
    else if (__tool === 'erase') t = 'Erase: move the cursor over strokes to remove them.';
    else if (__tool === 'select') t = `Select (${__selMode === 'rect' ? 'Rectangle' : 'Free-form'}): drag to select an area; click an AI object to add it to Findings.`;
    else if (__tool === 'measure') t = `${lbl}: ${(MT[__mtool] || {}).hint || ''}${__continuous ? ' · Continuous ON' : ''}. Esc = cancel.`;
    else if (__tool === 'note') t = 'Note: click a location on the image to add a note.';
    else if (__tool === 'crop') t = 'Crop: drag the area to keep. Reset restores the full image.';
    else t = 'Drag = pan · Scroll = zoom · Double-click = enlarge frame · Click a measurement = select. Shift+drag = pan while a tool is active.';
    if (!__tool) t = `${LAYER_NOTE}  ${t}`;
    h.textContent = t;
}

// ===================== Thumbnails (kolom foto) =====================
function renderFrameThumbList() {
    const el = $id('frame-thumb-list');
    if (__frames.length === 0) { el.innerHTML = '<div class="thumb-empty">No images yet</div>'; return; }
    el.innerHTML = __frames.map((f, i) => `
        <div class="thumb${f.id === __activeFrameId ? ' active' : ''}" data-id="${f.id}">
            <img src="${f.dataUrl || ''}" alt="">
            <span class="thumb-idx">${i + 1}</span>
            <span class="ft-status ${f.status === 'done' ? 'done' : (f.status === 'error' ? 'error' : '')}"></span>
            <button type="button" class="ft-remove" data-remove="${f.id}" title="Remove">&times;</button>
            <div class="thumb-tip">${escapeHtml(f.name)}${f.readOnly ? ' (history)' : ''}${f.result && f.result.data ? '<br>' + escapeHtml(f.result.data.diagnosis || '') : ''}${f.error ? '<br>Peringatan: ' + escapeHtml(f.error) : ''}</div>
        </div>`).join('');
    el.querySelectorAll('.thumb').forEach(item => item.addEventListener('click', (ev) => {
        if (ev.target.dataset.remove) return; setActiveFrame(item.dataset.id);
    }));
    el.querySelectorAll('[data-remove]').forEach(btn => btn.addEventListener('click', (ev) => { ev.stopPropagation(); removeFrame(btn.dataset.remove); }));
}

function setActiveFrame(id) {
    if (__activeFrameId === id) return;
    __activeFrameId = id;
    { const af = getFrame(id); if (af) logLine(`Frame ${__frames.indexOf(af) + 1} selected: ${af.name}`); }
    if (typeof updateScanModeLabel === 'function') updateScanModeLabel();
    if (!visibleInfo().list.some(f => f.id === id)) renderFrameGrid();
    else { document.querySelectorAll('.frame-cell').forEach(c => c.classList.toggle('active', c.dataset.id === id)); updatePager(); }
    renderFrameThumbList();
    renderResultsForActiveFrame();
    syncImageSettingUI();
}

// ===================== Grid frame =====================
function gridDims(n) {
    if (__layout) return { cols: __layout.cols, rows: __layout.rows };
    if (n <= 1) return { cols: 1, rows: 1 };
    if (n === 2) return { cols: 2, rows: 1 };
    if (n <= 4) return { cols: 2, rows: 2 };
    if (n <= 6) return { cols: 3, rows: 2 };
    return { cols: 3, rows: 3 };
}
function visibleInfo() {
    const mx = __maximizedId && getFrame(__maximizedId);
    if (mx) return { list: [mx], cols: 1, rows: 1, cap: 1, start: __frames.indexOf(mx) };
    const { cols, rows } = gridDims(__frames.length); const cap = cols * rows;
    const ai = Math.max(0, __frames.findIndex(f => f.id === __activeFrameId));
    const start = Math.floor(ai / cap) * cap;
    return { list: __frames.slice(start, start + cap), cols, rows, cap, start };
}
const EYE = '<svg class="ic"><use href="#i-eye"/></svg>';

function renderFrameGrid() {
    __draft = null; __drag = null;
    const grid = $id('frame-grid');
    const info = visibleInfo();
    applyLayers();
    grid.style.gridTemplateColumns = `repeat(${info.cols}, minmax(0,1fr))`;
    grid.style.gridTemplateRows = `repeat(${info.rows}, minmax(0,1fr))`;

    if (__frames.length === 0) {
        grid.style.gridTemplateColumns = '1fr'; grid.style.gridTemplateRows = '1fr';
        grid.innerHTML = '<div class="frame-cell empty"><div class="placeholder-text">Upload one or more medical image files (X-Ray, CT-Scan, MRI, DICOM/.dcm) to get started</div></div>';
        updatePager(); return;
    }
    const cells = info.list.map(f => `
        <div class="frame-cell${f.id === __activeFrameId ? ' active' : ''}" data-id="${f.id}">
            <div class="frame-area">
                <div class="frame-viewport">
                    <canvas class="frame-canvas"></canvas>
                    <svg class="frame-svg-overlay" xmlns="${SVGNS}"></svg>
                </div>
                <div class="frame-label-overlay"></div>
                <canvas class="frame-guides"></canvas>
                <button type="button" class="frame-eye" title="Tampilkan / sembunyikan grid, ruler & detail">${EYE}</button>
                <span class="frame-label-tag">Frame ${__frames.indexOf(f) + 1}${frameStateTag(f)}</span>
                <div class="frame-info frame-info-tl"></div>
                <div class="frame-info frame-info-tr"></div>
                <div class="frame-bottom"><div class="frame-legend"></div><div class="frame-dx"></div><div class="frame-heat"></div></div>
                <div class="frame-bars">
                    <div class="cbar-wrap"><div class="cbar green readonly" data-bar="ai"><b class="cbar-fill"></b></div><span class="cbar-lbl">AI</span></div>
                    <div class="cbar-wrap"><div class="cbar red readonly" data-bar="img"><b class="cbar-fill"></b></div><span class="cbar-lbl">Citra</span></div>
                </div>
                <div class="frame-scan-line" style="display:${f.status === 'scanning' ? 'block' : 'none'};"></div>
                ${f.status === 'error' ? `<div class="frame-error-msg">${escapeHtml(f.error || 'Failed to process this file.')}</div>` : ''}
            </div>
            <canvas class="ruler-h"></canvas><canvas class="ruler-v"></canvas>
        </div>`);
    if (!__maximizedId) while (cells.length < info.cols * info.rows) cells.push('<div class="frame-cell empty"></div>');
    grid.innerHTML = cells.join('');

    grid.querySelectorAll('.frame-cell[data-id]').forEach(cell => attachCellHandlers(cell));
    info.list.forEach(f => {
        if (f.srcImg) paintFrame(f.id);
        else ensureFrameImage(f).then(() => paintFrame(f.id));
    });
    updatePager();
}

function updatePager() {
    const p = $id('rv-pager'); const info = visibleInfo();
    if (__maximizedId || __frames.length <= info.cap) { p.style.display = 'none'; return; }
    const pages = Math.ceil(__frames.length / info.cap), cur = Math.floor(info.start / info.cap) + 1;
    p.style.display = 'flex';
    p.innerHTML = `<button type="button" data-d="-1"${cur <= 1 ? ' disabled' : ''}>‹</button><span>${cur} / ${pages}</span><button type="button" data-d="1"${cur >= pages ? ' disabled' : ''}>›</button>`;
    p.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
        const idx = clamp(info.start + parseInt(b.dataset.d, 10) * info.cap, 0, __frames.length - 1);
        __activeFrameId = null; setActiveFrame(__frames[idx].id);
    }));
}

function frameStateTag(f) {
    if (f.status === 'scanning') return ' · scanning…';
    if (f.status === 'error') return ' · failed';
    let t = f.readOnly ? ' · history' : '';
    if (f.status === 'done' && f.result && f.result.data) {
        const n = (f.result.data.anomalies || []).length;
        t += n ? ` · ${n} finding(s)` : ' · no localized findings';
        if (n && typeof frameIsSegmented === 'function' && !frameIsSegmented(f)) t += ' · not segmented yet';
    }
    return t;
}
function toggleMaximize(id) {
    __maximizedId = __maximizedId === id ? null : id; renderFrameGrid();
    const f = getFrame(id); if (f) logLine(`Frame ${__frames.indexOf(f) + 1} ${__maximizedId ? 'enlarged' : 'returned to grid'}`);
}

// ===================== Image loading & processing =====================
function ensureFrameImage(frame) {
    if (frame._loading) return frame._loading;
    frame._loading = new Promise((resolve) => {
        if (!frame.dataUrl) return resolve();
        const img = new Image();
        img.onload = () => { frame.srcImg = img; frame.natW = img.naturalWidth; frame.natH = img.naturalHeight; frame._orig = null; frame._isColor = null; resolve(); };
        img.onerror = () => resolve();
        img.src = frame.dataUrl;
    });
    return frame._loading;
}

function processFrame(frame) {
    const img = frame.srcImg; if (!img) return;
    const v = frame.view, c = frame.crop || { x0: 0, y0: 0, x1: 1, y1: 1 };
    const key = [c.x0, c.y0, c.x1, c.y1, v.he, v.sharpen, v.invert, v.palette].join('|');
    if (frame._procKey === key && frame._proc) return;
    const sc = Math.min(1, 2048 / Math.max(frame.natW, frame.natH));
    const sx = c.x0 * frame.natW, sy = c.y0 * frame.natH, sw = (c.x1 - c.x0) * frame.natW, sh = (c.y1 - c.y0) * frame.natH;
    const w = Math.max(1, Math.round(sw * sc)), h = Math.max(1, Math.round(sh * sc));
    const cv = frame._proc || (frame._proc = document.createElement('canvas'));
    cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, w, h);
    frame._procKey = key;
    if (!(v.he || v.sharpen > 0 || v.invert || v.palette !== 'none')) return;
    const id = ctx.getImageData(0, 0, w, h); const d = id.data;
    if (v.he) equalize(d);
    if (v.sharpen > 0) sharpenData(d, w, h, v.sharpen / 100 * 1.5);
    if (v.invert) for (let i = 0; i < d.length; i += 4) { d[i] = 255 - d[i]; d[i + 1] = 255 - d[i + 1]; d[i + 2] = 255 - d[i + 2]; }
    if (v.palette !== 'none') {
        const lut = paletteLUT(v.palette);
        for (let i = 0; i < d.length; i += 4) {
            const L = (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) | 0;
            d[i] = lut[L * 3]; d[i + 1] = lut[L * 3 + 1]; d[i + 2] = lut[L * 3 + 2];
        }
    }
    ctx.putImageData(id, 0, 0);
}
function equalize(d) {
    const hist = new Uint32Array(256), n = d.length / 4;
    for (let i = 0; i < d.length; i += 4) hist[(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) | 0]++;
    const map = new Uint8Array(256); let cum = 0, cmin = 0;
    for (let i = 0; i < 256; i++) if (hist[i]) { cmin = hist[i]; break; }
    for (let i = 0; i < 256; i++) { cum += hist[i]; map[i] = n === cmin ? i : Math.round((cum - cmin) / (n - cmin) * 255); }
    for (let i = 0; i < d.length; i += 4) {
        const L = (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) | 0, nl = map[L];
        if (L === 0) { d[i] = d[i + 1] = d[i + 2] = nl; }
        else { const f = nl / L; d[i] = Math.min(255, d[i] * f); d[i + 1] = Math.min(255, d[i + 1] * f); d[i + 2] = Math.min(255, d[i + 2] * f); }
    }
}
function sharpenData(d, w, h, a) {
    const s = d.slice();
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
        const i = (y * w + x) * 4;
        for (let c = 0; c < 3; c++) {
            const v = s[i + c] * (1 + 4 * a) - a * (s[i + c - 4] + s[i + c + 4] + s[i + c - w * 4] + s[i + c + w * 4]);
            d[i + c] = v < 0 ? 0 : v > 255 ? 255 : v;
        }
    }
}
let __procTimer = 0;
function scheduleProcess(frame) {
    clearTimeout(__procTimer);
    __procTimer = setTimeout(() => { processFrame(frame); paintCanvas(frame); applyFrameView(frame.id); }, 60);
    applyFrameView(frame.id);
}
function paintCanvas(frame) {
    const cell = cellOf(frame.id); if (!cell || !frame._proc) return;
    const cv = cell.querySelector('.frame-canvas');
    if (cv.width !== frame._proc.width || cv.height !== frame._proc.height) { cv.width = frame._proc.width; cv.height = frame._proc.height; }
    cv.getContext('2d').drawImage(frame._proc, 0, 0);
    updateColorbar(frame, cell);
}
function paintFrame(id) {
    const frame = getFrame(id), cell = cellOf(id); if (!frame || !cell || !frame.srcImg) return;
    processFrame(frame); paintCanvas(frame); relayoutFrame(frame);
}
function origData(frame) {
    if (frame._orig) return frame._orig;
    const sc = Math.min(1, 2048 / Math.max(frame.natW, frame.natH));
    const w = Math.max(1, Math.round(frame.natW * sc)), h = Math.max(1, Math.round(frame.natH * sc));
    const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d', { willReadFrequently: true }); ctx.drawImage(frame.srcImg, 0, 0, w, h);
    return (frame._orig = { w, h, data: ctx.getImageData(0, 0, w, h).data });
}
function grayAtN(frame, nx, ny) {
    const o = origData(frame); const x = clamp(Math.round(nx * (o.w - 1)), 0, o.w - 1), y = clamp(Math.round(ny * (o.h - 1)), 0, o.h - 1);
    const i = (y * o.w + x) * 4; return Math.round(0.299 * o.data[i] + 0.587 * o.data[i + 1] + 0.114 * o.data[i + 2]);
}
function roiStats(frame, pts) {
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const o = origData(frame); const bw = Math.max(1, (x1 - x0) * o.w), bh = Math.max(1, (y1 - y0) * o.h);
    const step = Math.max(1, Math.floor(Math.sqrt(bw * bh / 40000)));
    let sum = 0, sum2 = 0, n = 0;
    for (let y = y0 * o.h; y <= y1 * o.h; y += step) for (let x = x0 * o.w; x <= x1 * o.w; x += step) {
        if (!pointInPoly([x / o.w, y / o.h], pts)) continue;
        const g = grayAtN(frame, x / o.w, y / o.h); sum += g; sum2 += g * g; n++;
    }
    if (!n) return null; const mean = sum / n; return { mean, sd: Math.sqrt(Math.max(0, sum2 / n - mean * mean)) };
}
function pointInPoly(p, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
        if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
}

// ===================== Geometri & transform =====================
const cropOf = (f) => f.crop || { x0: 0, y0: 0, x1: 1, y1: 1 };
function n2s(frame, nx, ny) {
    const c = cropOf(frame), f = frame._fit || { W: 1, H: 1 };
    return [(nx - c.x0) / (c.x1 - c.x0) * f.W, (ny - c.y0) / (c.y1 - c.y0) * f.H];
}
function s2n(frame, sx, sy) {
    const c = cropOf(frame), f = frame._fit || { W: 1, H: 1 };
    return [c.x0 + sx / f.W * (c.x1 - c.x0), c.y0 + sy / f.H * (c.y1 - c.y0)];
}
function clientToN(frame, cell, ev) {
    const r = cell.querySelector('.frame-area').getBoundingClientRect(); const v = frame.view, f = frame._fit;
    let dx = (ev.clientX - (r.left + r.width / 2) - v.tx) / v.scale, dy = (ev.clientY - (r.top + r.height / 2) - v.ty) / v.scale;
    const a = -(v.rotate || 0) * Math.PI / 180;
    const rx = dx * Math.cos(a) - dy * Math.sin(a), ry = dx * Math.sin(a) + dy * Math.cos(a);
    return s2n(frame, rx * (v.flipH ? -1 : 1) + f.W / 2, ry * (v.flipV ? -1 : 1) + f.H / 2);
}
const rectPts = (a, b) => [[Math.min(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.min(a[1], b[1])],
                           [Math.max(a[0], b[0]), Math.max(a[1], b[1])], [Math.min(a[0], b[0]), Math.max(a[1], b[1])]];
function distSeg(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1]; const l2 = dx * dx + dy * dy;
    let t = l2 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2 : 0; t = clamp(t, 0, 1);
    return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

function layoutStage(frame, cell) {
    const area = cell.querySelector('.frame-area'); const aw = area.clientWidth, ah = area.clientHeight;
    if (!aw || !ah || !frame.natW) return false;
    const c = cropOf(frame), cw = frame.natW * (c.x1 - c.x0), ch = frame.natH * (c.y1 - c.y0);
    const r90 = ((frame.view.rotate % 360) + 360) % 180 !== 0;
    const ew = r90 ? ch : cw, eh = r90 ? cw : ch;
    const s = Math.min((aw - 4) / ew, (ah - 4) / eh);
    const W = cw * s, H = ch * s; frame._fit = { W, H, s };
    const vp = cell.querySelector('.frame-viewport');
    vp.style.width = `${W}px`; vp.style.height = `${H}px`; vp.style.marginLeft = `${-W / 2}px`; vp.style.marginTop = `${-H / 2}px`;
    cell.querySelector('.frame-svg-overlay').setAttribute('viewBox', `0 0 ${W} ${H}`);
    cell.classList.toggle('compact', aw < 300 || ah < 260);
    return true;
}
function relayoutFrame(frame) {
    const cell = cellOf(frame.id); if (!cell) return;
    if (!layoutStage(frame, cell)) return;
    applyFrameView(frame.id); drawFrameAnnotations(frame.id); updateFrameInfo(frame);
}
function relayoutAll() { visibleInfo().list.forEach(f => { if (f.srcImg) relayoutFrame(f); }); }

function applyFrameView(id) {
    const frame = getFrame(id), cell = cellOf(id); if (!frame || !cell) return;
    const v = frame.view; const vp = cell.querySelector('.frame-viewport'), cv = cell.querySelector('.frame-canvas');
    const fx = v.flipH ? -1 : 1, fy = v.flipV ? -1 : 1;
    vp.style.transform = `translate(${v.tx}px,${v.ty}px) scale(${v.scale}) rotate(${v.rotate}deg) scale(${fx},${fy})`;
    cv.style.filter = imageFilter(frame);
    cv.style.opacity = v.opacity / 100;
    cell.style.setProperty('--ai-op', (v.aiOpacity == null ? 100 : v.aiOpacity) / 100);
    drawGuides(frame, cell);
    positionLabels(frame, cell);
    updateAiFilter(frame, cell);
    updateColorbar(frame, cell);
    const tr = cell.querySelector('.frame-info-tr'); if (tr && tr.dataset.ww !== wwwl(frame)) updateFrameInfo(frame);
}
// Label anotasi diletakkan di luar layer yang di-zoom, lalu diposisikan di koordinat layar.
// Dengan begitu teks selalu dirender pada ukuran aslinya dan tetap tajam di zoom berapa pun.
// Label AI (kartu lesi + nama struktur anatomi) disusun TANPA saling menimpa: prioritas lesi > struktur inti > sekunder > opsional;
// yang tergeser diberi garis penunjuk ke titik asalnya, dan label prioritas rendah yang tidak muat disembunyikan (tetap ada di legenda).
function positionLabels(frame, cell) {
    const lo = cell.querySelector('.frame-label-overlay'), area = cell.querySelector('.frame-area'), f = frame._fit;
    if (!lo || !area || !f) return;
    const aw = area.clientWidth, ah = area.clientHeight, v = frame.view;
    const rot = (v.rotate || 0) * Math.PI / 180, cos = Math.cos(rot), sin = Math.sin(rot);
    const auto = [];
    lo.querySelectorAll('.anno-label').forEach(el => {
        const x = parseFloat(el.dataset.ax), y = parseFloat(el.dataset.ay); if (Number.isNaN(x) || Number.isNaN(y)) return;
        const rx = (x - f.W / 2) * (v.flipH ? -1 : 1), ry = (y - f.H / 2) * (v.flipV ? -1 : 1);
        const sx = aw / 2 + v.tx + (rx * cos - ry * sin) * v.scale, sy = ah / 2 + v.ty + (rx * sin + ry * cos) * v.scale;
        if (el.classList.contains('ai-lbl')) { el._sx = sx; el._sy = sy; auto.push(el); return; }
        el.style.left = `${Math.round(sx * 2) / 2}px`;
        el.style.top = `${Math.round(sy * 2) / 2}px`;
    });
    layoutAiLabels(lo, auto, aw, ah);
}
function layoutAiLabels(lo, els, aw, ah) {
    const NS = 'http://www.w3.org/2000/svg';
    let sv = lo.querySelector('svg.lbl-leaders');
    if (!sv) { sv = document.createElementNS(NS, 'svg'); sv.setAttribute('class', 'lbl-leaders'); lo.insertBefore(sv, lo.firstChild); }
    sv.setAttribute('width', aw); sv.setAttribute('height', ah); sv.textContent = '';
    const items = els.filter(el => el.offsetWidth > 0).map(el => ({ el, w: el.offsetWidth, h: el.offsetHeight, sx: el._sx, sy: el._sy,
        prio: parseInt(el.dataset.prio || '0', 10), center: el.dataset.center === '1' }));     // semua pengukuran dibaca dulu, baru ditulis
    items.sort((a, b) => a.prio - b.prio || a.sy - b.sy || a.sx - b.sx);
    const placed = [], GAP = 2;
    const hit = (r) => placed.some(q => r.x < q.x + q.w + GAP && r.x + r.w + GAP > q.x && r.y < q.y + q.h + GAP && r.y + r.h + GAP > q.y);
    const inside = (r) => r.x >= 0 && r.y >= 0 && r.x + r.w <= aw && r.y + r.h <= ah;
    const clampR = (r) => ({ x: Math.min(Math.max(0, r.x), Math.max(0, aw - r.w)), y: Math.min(Math.max(0, r.y), Math.max(0, ah - r.h)), w: r.w, h: r.h });
    items.forEach(it => {
        const { el, w, h, sx, sy } = it;
        el.style.visibility = 'visible';
        const base = it.center ? { x: sx - w / 2, y: sy - h / 2, w, h } : { x: sx + 2, y: sy - h - 4, w, h };
        if (sx < -30 || sy < -30 || sx > aw + 30 || sy > ah + 30) {                       // titik asal di luar tampilan: biarkan terpotong
            el.style.left = `${Math.round(base.x)}px`; el.style.top = `${Math.round(base.y)}px`; return;
        }
        const dy = h + 3, dx = Math.max(44, w * 0.6), cand = [base];
        if (!it.center) cand.push({ x: sx + 4, y: sy + 4, w, h });                          // kartu lesi: di bawah sudut kotak (di dalam kotak)
        for (let k = 1; k <= 10; k++) {
            cand.push({ x: base.x, y: base.y + k * dy, w, h }, { x: base.x, y: base.y - k * dy, w, h });
            if (k <= 4) cand.push({ x: base.x + k * dx, y: base.y, w, h }, { x: base.x - k * dx, y: base.y, w, h },
                { x: base.x + k * dx, y: base.y + dy, w, h }, { x: base.x - k * dx, y: base.y - dy, w, h });
        }
        let pick = cand.find(r => inside(r) && !hit(r));
        if (!pick) {
            if (it.prio >= 2) { el.style.visibility = 'hidden'; return; }                    // struktur sekunder/opsional yang tidak muat: sembunyikan
            pick = clampR(base);                                                           // lesi & struktur inti selalu tampil
        }
        placed.push(pick);
        el.style.left = `${Math.round(pick.x)}px`; el.style.top = `${Math.round(pick.y)}px`;
        // garis penunjuk bila label tergeser dari titik asalnya
        const nx = Math.min(pick.x + pick.w, Math.max(pick.x, sx)), ny = Math.min(pick.y + pick.h, Math.max(pick.y, sy));
        if (Math.hypot(nx - sx, ny - sy) > 14) {
            const col = el.style.borderColor || '#94a3b8';
            const ln = document.createElementNS(NS, 'line');
            ln.setAttribute('x1', sx); ln.setAttribute('y1', sy); ln.setAttribute('x2', nx); ln.setAttribute('y2', ny);
            ln.setAttribute('stroke', col); ln.setAttribute('stroke-width', '1'); ln.setAttribute('stroke-opacity', '.85');
            const dot = document.createElementNS(NS, 'circle');
            dot.setAttribute('cx', sx); dot.setAttribute('cy', sy); dot.setAttribute('r', '2.5'); dot.setAttribute('fill', col);
            sv.appendChild(ln); sv.appendChild(dot);
        }
    });
}
// Titik label struktur anatomi (koordinat layar): tengah garis untuk polyline, titik berat poligon bila jatuh di dalamnya, selain itu tengah kotak
function pointInPolyPx(x, y, q) {
    let inside = false;
    for (let i = 0, j = q.length - 1; i < q.length; j = i++) {
        const xi = q[i][0], yi = q[i][1], xj = q[j][0], yj = q[j][1];
        if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-9) + xi) inside = !inside;
    }
    return inside;
}
function labelPointOf(frame, st) {
    const P = (pts) => pts.map(p => n2s(frame, p[0], p[1]));
    if (st.polyline && st.polyline.length >= 2) { const q = P(st.polyline); return q[Math.floor((q.length - 1) / 2)]; }
    if (st.polygon && st.polygon.length >= 3) {
        const q = P(st.polygon); let a = 0, cx = 0, cy = 0;
        for (let i = 0; i < q.length; i++) { const x1 = q[i][0], y1 = q[i][1], x2 = q[(i + 1) % q.length][0], y2 = q[(i + 1) % q.length][1], c = x1 * y2 - x2 * y1; a += c; cx += (x1 + x2) * c; cy += (y1 + y2) * c; }
        if (Math.abs(a) > 1e-6) { cx /= 3 * a; cy /= 3 * a; if (pointInPolyPx(cx, cy, q)) return [cx, cy]; }
    }
    const a1 = n2s(frame, st.box.xmin, st.box.ymin), a2 = n2s(frame, st.box.xmax, st.box.ymax);
    return [(a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2];
}
function nudgeZoom(factor) {
    const f = activeFrame(); if (!f) return;
    const os = f.view.scale, ns = clamp(os * factor, 0.3, 10);
    f.view.tx *= ns / os; f.view.ty *= ns / os; f.view.scale = ns; applyFrameView(f.id);
    logLine(`Zoom ${factor > 1 ? 'in' : 'out'} Frame ${__frames.indexOf(f) + 1}: ${Math.round(ns * 100)}%`);
}
function resetActiveView() {
    const f = activeFrame(); if (!f) return;
    logLine(`Frame ${__frames.indexOf(f) + 1} view reset (zoom, pan, rotation, crop)`);
    f.view = defaultView(); f.crop = null; f.selection = null; f._procKey = '';
    processFrame(f); paintCanvas(f); relayoutFrame(f); syncImageSettingUI();
}
function applyCrop(frame, a, b) {
    const c = cropOf(frame);
    const x0 = clamp(Math.min(a[0], b[0]), c.x0, c.x1), x1 = clamp(Math.max(a[0], b[0]), c.x0, c.x1);
    const y0 = clamp(Math.min(a[1], b[1]), c.y0, c.y1), y1 = clamp(Math.max(a[1], b[1]), c.y0, c.y1);
    if ((x1 - x0) * frame.natW < 16 || (y1 - y0) * frame.natH < 16) return;
    frame.crop = { x0, y0, x1, y1 }; frame.view.tx = 0; frame.view.ty = 0; frame.view.scale = 1;
    processFrame(frame); paintCanvas(frame); setTool(null); relayoutFrame(frame);
    showToast(`Frame ${__frames.indexOf(frame) + 1} cropped. The Reset button restores the full image.`, 'success');
}

// ===================== Guides: grid + ruler (skala nyata jika terkalibrasi) =====================
const RS = 18;
function niceStep(min) {
    const p = Math.pow(10, Math.floor(Math.log10(min)));
    for (const m of [1, 2, 5, 10]) if (m * p >= min) return m * p; return 10 * p;
}
function fitCanvas(cv, w, h) {
    const dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    cv.style.width = `${w}px`; cv.style.height = `${h}px`;
    const ctx = cv.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h); return ctx;
}
function drawGuides(frame, cell) {
    const area = cell.querySelector('.frame-area'); const aw = area.clientWidth, ah = area.clientHeight;
    if (!aw || !ah || !frame._fit) return;
    const g = fitCanvas(cell.querySelector('.frame-guides'), aw, ah);
    const rh = fitCanvas(cell.querySelector('.ruler-h'), aw, RS), rv = fitCanvas(cell.querySelector('.ruler-v'), RS, ah);
    const v = frame.view, f = frame._fit; const r90 = ((v.rotate % 360) + 360) % 180 !== 0;
    const dw = (r90 ? f.H : f.W) * v.scale, dh = (r90 ? f.W : f.H) * v.scale;
    const left = aw / 2 + v.tx - dw / 2, top = ah / 2 + v.ty - dh / 2;
    const unitPx = frame.pxMm ? 10 / frame.pxMm : 1;
    const spu = unitPx * f.s * v.scale;
    const uw = dw / spu, uh = dh / spu;
    const step = niceStep(64 / spu), minor = step / 5;
    // grid
    g.strokeStyle = 'rgba(255,255,255,.17)'; g.lineWidth = 1; g.beginPath();
    for (let u = 0; u <= uw + 1e-9; u += step) { const x = Math.round(left + u * spu) + .5; g.moveTo(x, Math.max(0, top)); g.lineTo(x, Math.min(ah, top + dh)); }
    for (let u = 0; u <= uh + 1e-9; u += step) { const y = Math.round(top + u * spu) + .5; g.moveTo(Math.max(0, left), y); g.lineTo(Math.min(aw, left + dw), y); }
    g.stroke();
    // ruler
    const paintRuler = (ctx, horizontal, origin, total, len) => {
        ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, horizontal ? len : RS, horizontal ? RS : len);
        ctx.strokeStyle = '#94a3b8'; ctx.fillStyle = '#cbd5e1'; ctx.font = '10px sans-serif'; ctx.lineWidth = 1; ctx.beginPath();
        const showMinor = minor * spu >= 5;
        for (let i = 0; ; i++) {
            const u = i * minor; if (u > total + 1e-9) break;
            const p = origin + u * spu; if (p < 0 || p > len) continue;
            const major = i % 5 === 0; if (!major && !showMinor) continue;
            const l = major ? 9 : 4; const pp = Math.round(p) + .5;
            if (horizontal) { ctx.moveTo(pp, 0); ctx.lineTo(pp, l); } else { ctx.moveTo(0, pp); ctx.lineTo(l, pp); }
            if (major) {
                const lab = String(Number(u.toFixed(3)));
                if (horizontal) ctx.fillText(lab, pp + 3, RS - 4); else { ctx.save(); ctx.translate(RS - 4, pp + 3); ctx.rotate(-Math.PI / 2); ctx.fillText(lab, 0, 0); ctx.restore(); }
            }
        }
        ctx.stroke();
    };
    paintRuler(rh, true, left, uw, aw); paintRuler(rv, false, top, uh, ah);
    rh.fillStyle = '#f59e0b'; rh.font = 'bold 10px sans-serif'; rh.textAlign = 'right';
    rh.fillText(frame.pxMm ? 'cm' : 'px (not calibrated)', aw - 4, 11);
}

// ===================== Info overlay (MRN/Age/Sex, tanggal, WW/WL, dsb) =====================
function patientFor(frame) {
    const id = frame.patientId || $id('patient-select').value; if (!id) return null;
    return (window.__scanPatients || []).find(p => String(p.id) === String(id)) || null;
}
function ageOf(p) {
    if (!p || !p.birth_date) return '-';
    const b = new Date(p.birth_date); if (isNaN(b)) return '-';
    const n = new Date(); let a = n.getFullYear() - b.getFullYear();
    if (n.getMonth() < b.getMonth() || (n.getMonth() === b.getMonth() && n.getDate() < b.getDate())) a--;
    return `${a}y`;
}
const sexOf = (p) => !p ? '-' : (p.gender === 'L' ? 'M' : p.gender === 'P' ? 'F' : '-');
function examParts(frame) {
    const m = frame.meta || {}; const d = frame.examAt instanceof Date ? frame.examAt : new Date();
    const date = m.study_date || `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    let hh = d.getHours(), mm = d.getMinutes();
    if (m.study_time) { hh = parseInt(m.study_time.slice(0, 2), 10); mm = parseInt(m.study_time.slice(3, 5), 10); }
    const ap = hh >= 12 ? 'PM' : 'AM'; const h12 = hh % 12 || 12;
    return { date, time: `${String(h12).padStart(2, '0')}:${String(mm).padStart(2, '0')} ${ap}` };
}
function wwwl(frame) {
    const m = frame.meta || {}, v = frame.view;
    const ww = m.window_width != null ? m.window_width : 255, wl = m.window_center != null ? m.window_center : 128;
    return `${Math.round(ww * 100 / v.contrast)}/${Math.round(wl * 100 / v.brightness)}`;
}
function cfgText(selId) {
    const el = $id(selId); const t = el && el.selectedIndex >= 0 ? (el.options[el.selectedIndex].textContent || '').trim() : '';
    return t && t !== '-' ? t : '-';
}
function detSegCount(frame) {
    const d = (frame.result && frame.result.data) || null;
    if (!d) return { det: '-', seg: '-' };
    const A = d.anomalies || [], S = d.structures || [];
    const ad = S.filter(x => x.box && !x.derived).length, ld = A.filter(a => a.box).length;
    const as = S.filter(x => (x.polygon || x.polyline) && !x.derived).length, ls = A.filter(a => a.polygon).length;
    const fmt = (an, le, unit) => { const p = []; if (an || !le) p.push(`anatomy ${an}`); if (le || !an) p.push(`lesions ${le}`); return p.join(' + ') + ' ' + unit; };
    const segDone = d.segmented === true || as > 0 || ls > 0;
    return { det: fmt(ad, ld, 'objects'), seg: segDone ? fmt(as, ls, 'outlines') : (ad || ld ? 'not run (press Segmentasi)' : '-') };
}
function frameTarget(frame) {
    const d = (frame.result && frame.result.data) || {};
    const k = d.mode_pindai || (frame.cfg && frame.cfg.target) || (typeof currentScanTarget === 'function' ? currentScanTarget() : 'anatomi_lesi');
    return k;
}
function frameCfgText(frame, field, selId) {
    return frame && frame.cfg ? (frame.cfg[field] || '-') : cfgText(selId);
}
function updateFrameInfo(frame) {
    const cell = cellOf(frame.id); if (!cell) return;
    const p = patientFor(frame), ex = examParts(frame), m = frame.meta || {};
    const L = (k, v) => `<div>${k} : ${escapeHtml(String(v))}</div>`;
    const ai = frame.cfg ? frame.cfg.model : (($id('model-select') || {}).value || '-');
    // kiri-atas (mockup): MRN, Age, Sex, Projection, lalu konfigurasi scan + model AI (per frame)
    cell.querySelector('.frame-info-tl').innerHTML =
        `MRN : ${p ? escapeHtml(p.mrn) : '-'}<br>Age : ${ageOf(p)}<br>Sex : ${sexOf(p)}<br>Projection : ${escapeHtml(m.projection || '-')}` +
        `<div class="cfg-lines"><div class="gap"></div>` +
        L('Imaging', frameCfgText(frame, 'jenis', 'jenis-pemeriksaan-select')) +
        L('Anatomical Area', frameCfgText(frame, 'area', 'anatomical-area-select')) +
        L('Scan Target', typeof targetLabel === 'function' ? targetLabel(frameTarget(frame)) : '-') +
        L('Diagnosis Code', typeof codeSystemLabel === 'function' ? codeSystemLabel(frame.cfg ? frame.cfg.codeSystem : ($id('diagnosis-code-system-select') || {}).value) : '-') +
        `<div class="gap"></div>` +
        L('Object Detection', detSegCount(frame).det) + L('Segmentation', detSegCount(frame).seg) +
        L('Artificial Intelligence', ai) + `</div>`;
    // kanan-atas (mockup): nama pasien, tanggal, jam, resolusi, WW/WL, nama berkas
    const tr = cell.querySelector('.frame-info-tr');
    tr.dataset.ww = wwwl(frame);
    tr.innerHTML = `<b>${p ? escapeHtml(p.name) : 'Patient Name'}</b><br>Exam Date : ${ex.date}<br>Time : ${ex.time}<br>` +
        `Image Res : ${frame.natW || '-'} x ${frame.natH || '-'} px<br>WW/WL : ${wwwl(frame)}<br>File Name : ${escapeHtml(frame.name)}`;
    updateColorbar(frame, cell);
}
function refreshAllFrameInfo() { visibleInfo().list.forEach(f => updateFrameInfo(f)); }

// ---------------------------------------------------------------------
// Bar warna (mockup): MERAH = citra, HIJAU = visualisasi AI.
//   bar vertikal (seret naik/turun)  -> KONTRAS
//   strip pelangi kecil (geser kiri/kanan) -> DERAJAT WARNA (hue, 0-359°; ujung kiri = warna asli)
// Gradien bar ikut berubah mengikuti pengaturan sehingga berfungsi sebagai legenda hasil.
// ---------------------------------------------------------------------
function frameIsColor(frame) {
    if (frame._isColor != null) return frame._isColor;
    const img = frame.srcImg; if (!img) return false;          // belum dimuat: jangan di-cache
    try {
        const c = document.createElement('canvas'); c.width = c.height = 32;
        const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(img, 0, 0, 32, 32);
        const d = x.getImageData(0, 0, 32, 32).data; let n = 0;
        for (let i = 0; i < d.length; i += 4) if (Math.max(Math.abs(d[i] - d[i + 1]), Math.abs(d[i + 1] - d[i + 2])) > 18) n++;
        return (frame._isColor = n > 32 * 32 * 0.03);
    } catch (e) { return (frame._isColor = false); }
}
// Citra abu-abu (X-Ray/CT) tidak punya warna untuk diputar, jadi 'derajat warna' memberi pewarnaan (tint) pada hue tsb;
// citra berwarna / ber-palet diputar hue-nya. Pewarnaan ini hanya tampilan, tidak mengubah data citra.
function imageFilter(frame) {
    const v = frame.view; let f = `brightness(${v.brightness}%) contrast(${v.contrast}%)`;
    const d = Math.max(0, Math.min(100, v.colorDeg || 0)) / 100, h = v.hue == null ? HUE_DEFAULT : v.hue;
    if (d > 0) f += (frameIsColor(frame) || v.palette !== 'none')
        ? ` saturate(${(1 + d * 2).toFixed(2)}) hue-rotate(${Math.round(h * d)}deg)`
        : ` sepia(${d.toFixed(2)}) saturate(${(1 + d * 3).toFixed(2)}) hue-rotate(${Math.round((h - 38) * d)}deg)`;
    return f;
}
// Statistik derajat warna dari deretan piksel RGB (flat array r,g,b,r,g,b,...)
function colorStats(px) {
    const B = 16, sr = new Array(B).fill(0), sg = new Array(B).fill(0), sb = new Array(B).fill(0), cn = new Array(B).fill(0);
    let sumS = 0, hx = 0, hy = 0, n = 0;
    for (let i = 0; i + 2 < px.length; i += 3) {
        const r = px[i], g = px[i + 1], b = px[i + 2], mx = Math.max(r, g, b), mn = Math.min(r, g, b);
        const L = Math.round(0.299 * r + 0.587 * g + 0.114 * b), k = Math.min(B - 1, L >> 4);
        sr[k] += r; sg[k] += g; sb[k] += b; cn[k]++; sumS += mx ? (mx - mn) / mx : 0; n++;
        if (mx > mn) { const ang = Math.atan2(Math.sqrt(3) * (g - b), 2 * r - g - b); hx += Math.cos(ang) * (mx - mn); hy += Math.sin(ang) * (mx - mn); }
    }
    if (!n) return null;
    const stops = [];
    for (let k = B - 1; k >= 0; k--) {
        if (cn[k]) stops.push(`rgb(${Math.round(sr[k] / cn[k])},${Math.round(sg[k] / cn[k])},${Math.round(sb[k] / cn[k])})`);
        else { const g = Math.round((k + 0.5) * 16); stops.push(`rgb(${g},${g},${g})`); }
    }
    const sat = sumS / n;
    const hue = (sat >= 0.05 && (hx || hy)) ? Math.round(((Math.atan2(hy, hx) * 180 / Math.PI) + 360) % 360) : null;
    return { sat, hue, grad: `linear-gradient(to bottom, ${stops.join(',')})` };
}
// Citra hasil upload (piksel asli, tanpa filter tampilan)
function measureImage(frame) {
    const src = frame.srcImg; if (!src) return null;
    if (frame._measImg !== undefined && frame._measImgSrc === src) return frame._measImg;
    const N = 64, c = document.createElement('canvas'); c.width = c.height = N;
    const x = c.getContext('2d', { willReadFrequently: true }); let res = null;
    try { x.drawImage(src, 0, 0, N, N); const d = x.getImageData(0, 0, N, N).data, px = [];
        for (let i = 0; i < d.length; i += 4) px.push(d[i], d[i + 1], d[i + 2]); res = colorStats(px); } catch (e) { res = null; }
    frame._measImg = res; frame._measImgSrc = src; return res;
}
// Visualisasi AI: piksel warna yang dicatat saat heatmap / peta tekstur digambar
function measureAi(frame) {
    const px = frame._aiPx; return (px && px.length) ? colorStats(px) : null;
}
function aiFilterNeutral(v) { return (v.aiContrast == null || v.aiContrast === 100) && v.aiHue == null; }
function buildAiFilter(svg, frame, W, H) {
    const v = frame.view, c = (v.aiContrast == null ? 100 : v.aiContrast) / 100;
    const id = 'aif-' + String(frame.id).replace(/[^A-Za-z0-9_-]/g, '');
    const defs = mkEl(svg, 'defs', {});
    const f = mkEl(defs, 'filter', { id, filterUnits: 'userSpaceOnUse', x: 0, y: 0, width: W, height: H, 'color-interpolation-filters': 'sRGB' });
    mkEl(f, 'feColorMatrix', { type: 'hueRotate', values: v.aiHue == null ? 0 : v.aiHue });
    const ct = mkEl(f, 'feComponentTransfer', {});
    ['feFuncR', 'feFuncG', 'feFuncB'].forEach(n => mkEl(ct, n, { type: 'linear', slope: c, intercept: 0.5 * (1 - c) }));
    return id;
}
// Terapkan kontras/hue visualisasi AI (SVG lewat <filter>, label HTML lewat CSS filter)
function updateAiFilter(frame, cell) {
    const v = frame.view, c = v.aiContrast == null ? 100 : v.aiContrast, neutral = aiFilterNeutral(v);
    const g = cell.querySelector('.ai-layer'), has = g && g.getAttribute('filter');
    cell.style.setProperty('--ai-filter', neutral ? 'none' : `contrast(${c}%)${v.aiHue != null ? ` hue-rotate(${v.aiHue}deg)` : ''}`);
    if (!g) return;
    if (neutral) { if (has) g.removeAttribute('filter'); return; }
    if (!has) { drawFrameAnnotations(frame.id); return; }       // transisi netral -> aktif: bangun <filter> sekali
    const f = cell.querySelector('.frame-svg-overlay filter'); if (!f) return;
    f.querySelector('feColorMatrix').setAttribute('values', v.aiHue == null ? 0 : v.aiHue);
    const k = c / 100; f.querySelectorAll('feComponentTransfer > *').forEach(e => { e.setAttribute('slope', k); e.setAttribute('intercept', 0.5 * (1 - k)); });
}
// Dua INDIKATOR (bukan slider, tidak bisa diedit):
//   kiri  (AI)   = derajat warna visualisasi yang dihasilkan AI
//   kanan (Citra) = derajat warna citra hasil upload
// Penanda vertikal = saturasi (derajat warna, 0% bawah), strip pelangi = hue dominan.
function setIndicator(cell, k, m) {
    const bar = cell.querySelector(`.cbar[data-bar="${k}"]`); if (!bar) return;
    const fill = bar.querySelector('.cbar-fill'); fill.style.filter = 'none';
    fill.style.background = m ? m.grad : 'linear-gradient(to bottom, #3b4658, #1b2230)';
}
function updateColorbar(frame, cell) {
    setIndicator(cell, 'ai', measureAi(frame));
    setIndicator(cell, 'img', measureImage(frame));
}
function attachBarHandlers(cell) {
    // indikator saja: tidak ada interaksi, dan jangan sampai memicu pan/zoom frame
    cell.querySelectorAll('.cbar, .hbar').forEach(el => el.addEventListener('pointerdown', (ev) => ev.stopPropagation()));
}

// ===================== Event handling per cell =====================
function attachCellHandlers(cell) {
    const id = cell.dataset.id, area = cell.querySelector('.frame-area');
    area.addEventListener('pointerdown', (ev) => onPointerDown(ev, id, cell, area));
    area.addEventListener('pointermove', (ev) => onPointerMove(ev, id, cell));
    area.addEventListener('pointerup', (ev) => onPointerUp(ev, id, cell, area));
    area.addEventListener('pointercancel', () => { __drag = null; __draft = null; cell.classList.remove('panning'); drawFrameAnnotations(id); });
    area.addEventListener('dblclick', (ev) => onDblClick(ev, id));
    area.addEventListener('wheel', (ev) => {
        ev.preventDefault(); const frame = getFrame(id); if (!frame) return;
        setActiveFrame(id);
        const r = area.getBoundingClientRect(), v = frame.view;
        const dx = ev.clientX - (r.left + r.width / 2), dy = ev.clientY - (r.top + r.height / 2);
        const os = v.scale, ns = clamp(os * (ev.deltaY < 0 ? 1.12 : 0.89), 0.3, 10);
        v.tx = dx - (dx - v.tx) * ns / os; v.ty = dy - (dy - v.ty) * ns / os; v.scale = ns; applyFrameView(id);
    }, { passive: false });
    attachBarHandlers(cell);
    cell.querySelector('.frame-eye').addEventListener('click', (ev) => {
        ev.stopPropagation(); __showInfo = !__showInfo; applyLayers();
    });
}

function onPointerDown(ev, id, cell, area) {
    if (ev.target.closest('.frame-eye, .anno-label, .frame-bars')) return;
    if (ev.button !== 0 && ev.button !== 1) return;
    const frame = getFrame(id); if (!frame || !frame._fit) return;
    setActiveFrame(id);
    const mid = ev.target.closest && ev.target.closest('[data-mid]');
    if (!__tool) {
        if (mid && ev.button === 0) { frame.selMark = mid.dataset.mid; drawFrameAnnotations(id); return; }
        if (frame.selMark) { frame.selMark = null; drawFrameAnnotations(id); }
    }
    const sx = ev.clientX, sy = ev.clientY;
    area.setPointerCapture(ev.pointerId);
    if (ev.shiftKey || ev.button === 1 || !__tool) {
        __drag = { type: 'pan', id, x: sx, y: sy, sx, sy }; cell.classList.add('panning'); ev.preventDefault(); return;
    }
    const n = clientToN(frame, cell, ev);
    if (__tool === 'draw') {
        const st = { id: `s${++__markSeq}`, color: __drawColor, size: __drawSize, pts: [n] };
        frame.strokes.push(st); __drag = { type: 'stroke', id, st, sx, sy }; drawFrameAnnotations(id);
    } else if (__tool === 'erase') { __drag = { type: 'erase', id, sx, sy }; eraseAt(frame, n); }
    else if (__tool === 'note') __drag = { type: 'click', id, sx, sy };
    else if (__tool === 'select') {
        __drag = { type: 'drag', id, sx, sy };
        __draft = { frameId: id, kind: __selMode === 'rect' ? 'select-rect' : 'select-free', pts: __selMode === 'rect' ? [n, n] : [n] };
    } else if (__tool === 'crop') { __drag = { type: 'drag', id, sx, sy }; __draft = { frameId: id, kind: 'crop', pts: [n, n] }; }
    else if (__tool === 'measure') {
        const spec = MT[__mtool];
        if (spec.drag) { __drag = { type: 'drag', id, sx, sy }; __draft = { frameId: id, kind: __mtool, pts: [n, n] }; }
        else if (spec.free) { __drag = { type: 'drag', id, sx, sy }; __draft = { frameId: id, kind: 'flexpoly', pts: [n] }; }
        else __drag = { type: 'click', id, sx, sy };
    }
}
function onPointerMove(ev, id, cell) {
    const frame = getFrame(id); if (!frame || !frame._fit) return;
    if (__drag && __drag.id === id) {
        const d = __drag;
        if (d.type === 'pan') { frame.view.tx += ev.clientX - d.x; frame.view.ty += ev.clientY - d.y; d.x = ev.clientX; d.y = ev.clientY; applyFrameView(id); return; }
        const n = clientToN(frame, cell, ev);
        if (d.type === 'stroke') { d.st.pts.push(n); drawFrameAnnotations(id); }
        else if (d.type === 'erase') eraseAt(frame, n);
        else if (d.type === 'drag' && __draft) {
            if (__draft.kind === 'select-free' || __draft.kind === 'flexpoly') __draft.pts.push(n); else __draft.pts[1] = n;
            drawFrameAnnotations(id);
        }
        return;
    }
    if (__draft && __draft.frameId === id && __tool === 'measure' && MT[__mtool].n) { __draft.cur = clientToN(frame, cell, ev); drawFrameAnnotations(id); }
}
function onPointerUp(ev, id, cell, area) {
    const d = __drag; if (!d || d.id !== id) return; __drag = null;
    try { area.releasePointerCapture(ev.pointerId); } catch (e) { /* noop */ }
    cell.classList.remove('panning');
    const frame = getFrame(id); if (!frame) return;
    const moved = Math.hypot(ev.clientX - d.sx, ev.clientY - d.sy);
    if (d.type === 'pan' && !__tool && moved < 5 && ev.button === 0 && typeof findingIndexAt === 'function') {
        // Klik (bukan geser) pada kotak temuan AI: buka peta opsi analisis. Ditunda sedikit agar dblclick (maksimalkan) tetap bisa.
        const hit = findingIndexAt(frame, clientToN(frame, cell, ev));
        clearTimeout(window.__insightClickTimer);
        if (hit !== -1) window.__insightClickTimer = setTimeout(() => openFindingInsight(frame.id, hit), 280);
        return;
    }
    if (d.type === 'pan' || d.type === 'erase') return;
    if (d.type === 'stroke') { if (d.st.pts.length < 2) d.st.pts.push([d.st.pts[0][0] + 1e-4, d.st.pts[0][1]]); drawFrameAnnotations(id); logLine(`Stroke added on Frame ${__frames.indexOf(frame) + 1}`); return; }
    const n = clientToN(frame, cell, ev);
    if (d.type === 'click') { if (moved < 6) { if (__tool === 'note') addNote(frame, n); else measureClick(frame, n); } return; }
    if (d.type === 'drag') commitDrag(frame, moved, n);
}
function onDblClick(ev, id) {
    clearTimeout(window.__insightClickTimer);
    if (ev.target.closest('.frame-eye, .anno-label')) return;
    const frame = getFrame(id); if (!frame) return;
    if (__draft && __draft.frameId === id && __tool === 'measure' && MT[__mtool].n === Infinity) { finishDraft(frame); return; }
    if (!__tool || __tool === 'select') toggleMaximize(id);
}

function eraseAt(frame, n) {
    const p = n2s(frame, n[0], n[1]), thr = 9 / frame.view.scale; let changed = false;
    frame.strokes = frame.strokes.filter(st => {
        for (let i = 0; i < st.pts.length; i++) {
            const a = n2s(frame, st.pts[i][0], st.pts[i][1]); const b = i ? n2s(frame, st.pts[i - 1][0], st.pts[i - 1][1]) : a;
            if (distSeg(p, a, b) < thr + st.size / 2) { changed = true; return false; }
        }
        return true;
    });
    if (changed) drawFrameAnnotations(frame.id);
}
function commitDrag(frame, moved, n) {
    const dr = __draft; __draft = null; if (!dr) return;
    if (dr.kind === 'select-rect' || dr.kind === 'select-free') {
        if (moved < 5) { frame.selection = null; tryConfirmFindingAtPoint(frame.id, n[0], n[1]); }
        else if (dr.kind === 'select-rect') frame.selection = { pts: rectPts(dr.pts[0], dr.pts[1]), invert: false };
        else if (dr.pts.length > 2) frame.selection = { pts: dr.pts, invert: false };
        updateSelectMenuState(); drawFrameAnnotations(frame.id); return;
    }
    if (moved < 5) { drawFrameAnnotations(frame.id); return; }
    if (dr.kind === 'crop') { applyCrop(frame, dr.pts[0], dr.pts[1]); return; }
    if (dr.kind === 'mask') frame.marks.push({ id: nextMarkId(), type: 'mask', pts: rectPts(dr.pts[0], dr.pts[1]) });
    else if (dr.kind === 'ellipse' || dr.kind === 'rectangle') frame.marks.push({ id: nextMarkId(), type: dr.kind, pts: [dr.pts[0], dr.pts[1]] });
    else if (dr.kind === 'flexpoly') { if (dr.pts.length < 3) { drawFrameAnnotations(frame.id); return; } frame.marks.push({ id: nextMarkId(), type: 'flexpoly', pts: dr.pts }); }
    afterMark(frame);
}
function afterMark(frame) {
    const m = frame.marks[frame.marks.length - 1];
    if (m) logLine(`Annotation added on Frame ${__frames.indexOf(frame) + 1}: ${(MEAS_ITEMS.find(i => i.k === m.type) || {}).l || m.type}`);
    if (!__continuous) setTool(null); else drawFrameAnnotations(frame.id);
}

function addNote(frame, n) {
    const m = { id: nextMarkId(), type: 'note', pts: [n], text: '' };
    frame.marks.push(m); afterMark(frame); focusMarkLabel(frame.id, m.id);
}
// Label baru langsung bisa diketik di titik yang diklik (tanpa dialog browser)
function focusMarkLabel(frameId, markId) {
    setTimeout(() => {
        const el = cellOf(frameId) && cellOf(frameId).querySelector(`.anno-label[data-mid="${markId}"]`);
        if (el) { el.focus(); }
    }, 30);
}
function commitMarkText(frame, m, text) {
    const t = (text || '').trim();
    if (m.type === 'calibration' && m.pending) {
        const mm = parseFloat(t.replace(',', '.')), px = pxLen(frame, m.pts[0], m.pts[1]);
        if (mm > 0 && px > 0) {
            frame.pxMm = mm / px; m.mm = mm; delete m.pending;
            showToast(`Calibration saved: ${frame.pxMm.toFixed(4)} mm/pixel. Ruler & measurements are now in mm/cm.`, 'success');
            relayoutFrame(frame); return;
        }
        frame.marks = frame.marks.filter(x => x !== m); drawFrameAnnotations(frame.id); return;
    }
    if (!t) { frame.marks = frame.marks.filter(x => x !== m); drawFrameAnnotations(frame.id); return; }
    m.text = t;
}
function measureClick(frame, n) {
    const spec = MT[__mtool]; if (!spec) return;
    if (!__draft || __draft.frameId !== frame.id || __draft.kind !== __mtool) __draft = { frameId: frame.id, kind: __mtool, pts: [] };
    const d = __draft;
    if (spec.closed && d.pts.length >= 3) {
        const a = n2s(frame, d.pts[0][0], d.pts[0][1]), b = n2s(frame, n[0], n[1]);
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) * frame.view.scale < 8) { finishDraft(frame); return; }
    }
    d.pts.push(n); d.cur = null;
    if (d.pts.length >= spec.n) finishDraft(frame); else drawFrameAnnotations(frame.id);
}
function finishDraft(frame) {
    const d = __draft; if (!d) return; __draft = null;
    const spec = MT[d.kind]; const pts = [];
    d.pts.forEach(p => { const l = pts[pts.length - 1]; if (!l || Math.abs(l[0] - p[0]) > 1e-6 || Math.abs(l[1] - p[1]) > 1e-6) pts.push(p); });
    if (pts.length < (spec.min || spec.n)) { drawFrameAnnotations(frame.id); return; }
    const m = { id: nextMarkId(), type: d.kind, pts };
    if (d.kind === 'calibration') {
        if (!(pxLen(frame, pts[0], pts[1]) > 0)) { drawFrameAnnotations(frame.id); return; }
        m.pending = true; m.mm = 0; frame.marks.push(m); afterMark(frame); focusMarkLabel(frame.id, m.id); return;
    }
    if (d.kind === 'text') { m.text = ''; frame.marks.push(m); afterMark(frame); focusMarkLabel(frame.id, m.id); return; }
    if (d.kind === 'spine') m.text = SPINE_LABELS[frame.marks.filter(x => x.type === 'spine').length % SPINE_LABELS.length];
    frame.marks.push(m); afterMark(frame);
}

function onKeyDown(ev) {
    if (!$id('view-scan').classList.contains('active')) return;
    const t = ev.target; if (/INPUT|TEXTAREA|SELECT/.test(t.tagName) || t.isContentEditable) return;
    const f = activeFrame(); const k = ev.key;
    if (k === 'Escape') { __draft = null; __drag = null; if (f) drawFrameAnnotations(f.id); return; }
    if (k === 'Enter' && __draft && f) { finishDraft(f); return; }
    if ((ev.ctrlKey || ev.metaKey) && k.toLowerCase() === 'a') { ev.preventDefault(); selectAll(); return; }
    if (k === 'Delete') {
        ev.preventDefault();
        if (ev.ctrlKey) return deleteAllMarks();
        if (f && f.selMark) return deleteSelectedMark();
        if (f && f.selection) return deleteSelectionContent();
        return;
    }
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
    const key = k.toLowerCase();
    if (ev.shiftKey && key === 'd') return deleteSelectedMark();
    const map = { d: 'line', a: 'angle', n: 'flexpoly', b: 'pencil', g: 'arrow', h: 'continuous', v: 'intensity', e: 'delall' };
    if (!ev.shiftKey && map[key]) { ev.preventDefault(); pickMeasure(map[key]); }
}

// ===================== Rendering anotasi =====================
function mkEl(parent, name, attrs) {
    const e = document.createElementNS(SVGNS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (!('vector-effect' in attrs)) e.setAttribute('vector-effect', 'non-scaling-stroke');
    parent.appendChild(e); return e;
}
const dotEl = (p, x, y, color, size = 6) => mkEl(p, 'line', { x1: x, y1: y, x2: x + 0.01, y2: y, stroke: color, 'stroke-width': size, 'stroke-linecap': 'round' });
const pxLen = (f, a, b) => Math.hypot((b[0] - a[0]) * f.natW, (b[1] - a[1]) * f.natH);
function fmtLen(f, px) {
    if (f.pxMm) { const mm = px * f.pxMm; return mm >= 100 ? `${(mm / 10).toFixed(2)} cm` : `${mm.toFixed(1)} mm`; }
    return `${Math.round(px)} px`;
}
function fmtArea(f, px2) {
    if (f.pxMm) { const mm2 = px2 * f.pxMm * f.pxMm; return mm2 >= 100 ? `${(mm2 / 100).toFixed(2)} cm²` : `${mm2.toFixed(1)} mm²`; }
    return `${Math.round(px2)} px²`;
}
function polyArea(f, pts) {
    let s = 0; for (let i = 0; i < pts.length; i++) {
        const a = pts[i], b = pts[(i + 1) % pts.length]; s += a[0] * f.natW * b[1] * f.natH - b[0] * f.natW * a[1] * f.natH;
    } return Math.abs(s) / 2;
}
function angleAt(f, a, v, b) {
    const ax = (a[0] - v[0]) * f.natW, ay = (a[1] - v[1]) * f.natH, bx = (b[0] - v[0]) * f.natW, by = (b[1] - v[1]) * f.natH;
    return Math.abs(Math.atan2(ax * by - ay * bx, ax * bx + ay * by)) * 180 / Math.PI;
}
function lineAngle(f, p1, p2, p3, p4) {
    const ux = (p2[0] - p1[0]) * f.natW, uy = (p2[1] - p1[1]) * f.natH, wx = (p4[0] - p3[0]) * f.natW, wy = (p4[1] - p3[1]) * f.natH;
    const a = Math.abs(Math.atan2(ux * wy - uy * wx, ux * wx + uy * wy)) * 180 / Math.PI; return Math.min(a, 180 - a);
}
const ptsStr = (S) => S.map(p => `${p[0]},${p[1]}`).join(' ');

function renderMark(frame, m, svg, labels, isDraft) {
    const S = m.pts.map(p => n2s(frame, p[0], p[1])); const sel = frame.selMark === m.id;
    const color = sel ? '#ffffff' : (isDraft ? '#fde047' : (m.type === 'note' ? '#facc15' : '#22d3ee')); const w = sel ? 2.6 : 1.8;
    const g = mkEl(svg, 'g', { 'data-mid': m.id, class: 'mk' });
    const line = (a, b, c, dash) => mkEl(g, 'line', Object.assign({ x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: c || color, 'stroke-width': w }, dash ? { 'stroke-dasharray': '5,4' } : {}));
    const lbl = (p, t, cls) => labels.push({ x: p[0], y: p[1], text: t, color: cls === 'note' ? '#facc15' : color, cls, mark: m });
    const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const closedHit = ['area', 'roi', 'closedpoly', 'flexpoly', 'ellipse', 'rectangle'].includes(m.type);
    mkEl(g, 'polyline', { points: ptsStr(closedHit && S.length > 2 ? S.concat([S[0]]) : S), fill: 'none', stroke: 'transparent', 'stroke-width': 12, class: 'hit' });
    const verts = () => S.forEach(p => dotEl(g, p[0], p[1], color, 6));
    const arcAt = (v, a, b) => {
        const a1 = Math.atan2(a[1] - v[1], a[0] - v[0]), a2 = Math.atan2(b[1] - v[1], b[0] - v[0]); let df = a2 - a1;
        while (df > Math.PI) df -= 2 * Math.PI; while (df < -Math.PI) df += 2 * Math.PI; const r = 22;
        mkEl(g, 'path', { d: `M ${v[0] + r * Math.cos(a1)} ${v[1] + r * Math.sin(a1)} A ${r} ${r} 0 0 ${df > 0 ? 1 : 0} ${v[0] + r * Math.cos(a2)} ${v[1] + r * Math.sin(a2)}`, fill: 'none', stroke: color, 'stroke-width': w });
    };
    const t = m.type, P = m.pts;
    if (t === 'line' || t === 'ruler' || t === 'calibration') {
        line(S[0], S[1], null, t === 'calibration'); verts();
        if (t === 'ruler') { const dx = S[1][0] - S[0][0], dy = S[1][1] - S[0][1], l = Math.hypot(dx, dy) || 1, nx = -dy / l * 6, ny = dx / l * 6; S.forEach(p => line([p[0] + nx, p[1] + ny], [p[0] - nx, p[1] - ny])); }
        lbl(mid(S[0], S[1]), m.pending ? '' : (t === 'calibration' && m.mm ? `Kalibrasi ${m.mm} mm` : fmtLen(frame, pxLen(frame, P[0], P[1]))));
    } else if (t === 'arrow') {
        line(S[0], S[1]); const a = Math.atan2(S[1][1] - S[0][1], S[1][0] - S[0][0]);
        [0.45, -0.45].forEach(o => line(S[1], [S[1][0] - 12 * Math.cos(a + o), S[1][1] - 12 * Math.sin(a + o)]));
    } else if (t === 'heightdiff') {
        line(S[0], S[1], null, true); line([S[0][0] - 16, S[0][1]], [S[0][0] + 16, S[0][1]]); line([S[1][0] - 16, S[1][1]], [S[1][0] + 16, S[1][1]]);
        line([S[1][0], S[0][1]], S[1]); verts();
        lbl([S[1][0], mid(S[0], S[1])[1]], `Δy ${fmtLen(frame, Math.abs(P[1][1] - P[0][1]) * frame.natH)}`);
    } else if (t === 'angle' || t === 'gonio' || t === 'flatfoot') {
        line(S[0], S[1]); line(S[1], S[2]); arcAt(S[1], S[0], S[2]); verts();
        if (__showAngles) lbl(S[1], `${t === 'flatfoot' ? 'Arch ' : ''}${angleAt(frame, P[0], P[1], P[2]).toFixed(1)}°`);
    } else if (t === 'cobb' || t === 'hto' || t === 'vertebra') {
        line(S[0], S[1]); line(S[2], S[3]); verts();
        if (__showAngles) lbl(S[3], `${t === 'cobb' ? 'Cobb ' : t === 'hto' ? 'HTO ' : ''}${lineAngle(frame, P[0], P[1], P[2], P[3]).toFixed(1)}°`);
    } else if (t === 'ctr') {
        line(S[0], S[1], '#f59e0b'); line(S[2], S[3], '#22d3ee'); verts();
        const r = pxLen(frame, P[0], P[1]) / (pxLen(frame, P[2], P[3]) || 1);
        lbl(S[3], `CTR ${r.toFixed(2)} (${(r * 100).toFixed(0)}%)${r > 0.5 ? ' ↑' : ''}`);
    } else if (t === 'polyline') {
        mkEl(g, 'polyline', { points: ptsStr(S), fill: 'none', stroke: color, 'stroke-width': w }); verts();
        let L = 0; for (let i = 1; i < P.length; i++) L += pxLen(frame, P[i - 1], P[i]);
        lbl(S[S.length - 1], fmtLen(frame, L));
    } else if (t === 'area' || t === 'roi' || t === 'closedpoly' || t === 'flexpoly') {
        mkEl(g, 'polygon', { points: ptsStr(S), fill: 'rgba(34,211,238,.12)', stroke: color, 'stroke-width': w, 'stroke-linejoin': 'round' });
        if (t !== 'flexpoly') verts();
        const cx = S.reduce((a, p) => a + p[0], 0) / S.length, cy = S.reduce((a, p) => a + p[1], 0) / S.length;
        let txt = fmtArea(frame, polyArea(frame, P));
        if (t === 'roi' && !isDraft) { const st = roiStats(frame, P); if (st) txt += ` · μ ${st.mean.toFixed(0)} σ ${st.sd.toFixed(0)}`; }
        if (t !== 'closedpoly' || true) lbl([cx, cy], txt);
    } else if (t === 'ellipse') {
        const cx = (S[0][0] + S[1][0]) / 2, cy = (S[0][1] + S[1][1]) / 2, rx = Math.abs(S[1][0] - S[0][0]) / 2, ry = Math.abs(S[1][1] - S[0][1]) / 2;
        mkEl(g, 'ellipse', { cx, cy, rx, ry, fill: 'rgba(34,211,238,.12)', stroke: color, 'stroke-width': w });
        const a = Math.abs(P[1][0] - P[0][0]) * frame.natW / 2, b = Math.abs(P[1][1] - P[0][1]) * frame.natH / 2;
        lbl([cx, cy + ry], fmtArea(frame, Math.PI * a * b));
    } else if (t === 'rectangle') {
        mkEl(g, 'rect', { x: Math.min(S[0][0], S[1][0]), y: Math.min(S[0][1], S[1][1]), width: Math.abs(S[1][0] - S[0][0]), height: Math.abs(S[1][1] - S[0][1]), fill: 'rgba(34,211,238,.12)', stroke: color, 'stroke-width': w });
        const wp = Math.abs(P[1][0] - P[0][0]) * frame.natW, hp = Math.abs(P[1][1] - P[0][1]) * frame.natH;
        lbl([Math.min(S[0][0], S[1][0]), Math.max(S[0][1], S[1][1])], `${fmtLen(frame, wp)} × ${fmtLen(frame, hp)} · ${fmtArea(frame, wp * hp)}`);
    } else if (t === 'text' || t === 'spine') {
        dotEl(g, S[0][0], S[0][1], color, t === 'spine' ? 8 : 5); lbl(S[0], m.text || (t === 'spine' ? '?' : ''));
    } else if (t === 'note') {
        dotEl(g, S[0][0], S[0][1], '#facc15', 9); lbl(S[0], m.text || '', 'note');
    } else if (t === 'intensity') {
        dotEl(g, S[0][0], S[0][1], color, 8); lbl(S[0], `I = ${grayAtN(frame, P[0][0], P[0][1])}`);
    }
}

function drawFrameAnnotations(frameId) {
    const frame = getFrame(frameId), cell = cellOf(frameId); if (!frame || !cell || !frame._fit) return;
    const svg = cell.querySelector('.frame-svg-overlay'), lo = cell.querySelector('.frame-label-overlay');
    const { W, H } = frame._fit; svg.innerHTML = ''; lo.innerHTML = ''; const labels = []; frame._aiPx = [];

    const polyPath = (S) => 'M ' + S.map(p => `${p[0]} ${p[1]}`).join(' L ') + ' Z';
    const maskPath = (pts, inv) => (inv ? `M 0 0 H ${W} V ${H} H 0 Z ` : '') + polyPath(pts.map(p => n2s(frame, p[0], p[1])));
    // masks
    frame.marks.filter(m => m.type === 'mask').forEach(m => {
        const g = mkEl(svg, 'g', { 'data-mid': m.id, class: 'mk' });
        mkEl(g, 'path', { d: maskPath(m.pts, m.invert), fill: '#000', 'fill-rule': 'evenodd', stroke: frame.selMark === m.id ? '#fff' : 'none', 'stroke-width': 2 });
    });
    // AI: Object Detection (box) + Segmentation (kontur) hasil model AI; tiap lapis bisa disembunyikan lewat menu Layer
    const aiData = (frame.result && frame.result.data) || {};
    const anomalies = aiData.anomalies || [], structures = aiData.structures || [];
    const aiG = mkEl(svg, 'g', { class: 'ai-layer' });   // kontras/hue bar hijau berlaku untuk kedua lapis
    if (!aiFilterNeutral(frame.view)) aiG.setAttribute('filter', `url(#${buildAiFilter(svg, frame, W, H)})`);
    // Empat lapis AI (masing-masing bisa disembunyikan di menu Layer): segmentasi anatomi, heatmap lesi,
    // deteksi anatomi, deteksi lesi. Urutan gambar: anatomi di bawah, lesi di atasnya.
    const zoneG = mkEl(aiG, 'g', { class: 'ai-zone' }), segAG = mkEl(aiG, 'g', { class: 'ai-seg ai-seg-anat' }), segLG = mkEl(aiG, 'g', { class: 'ai-seg ai-seg-les' });
    const detAG = mkEl(aiG, 'g', { class: 'ai-det ai-det-anat' }), detLG = mkEl(aiG, 'g', { class: 'ai-det ai-det-les' });
    const toScreen = (b) => {
        const a = n2s(frame, b.xmin, b.ymin), c = n2s(frame, b.xmax, b.ymax);
        return { x: Math.min(a[0], c[0]), y: Math.min(a[1], c[1]), w: Math.abs(c[0] - a[0]), h: Math.abs(c[1] - a[1]) };
    };
    const hexPx = (hex, n) => { const c = hexRgb(hex); for (let k = 0; k < n; k++) frame._aiPx.push(c[0], c[1], c[2]); };
    // Segmentasi anatomi (Thorax_Anatomy_Taxonomy): poligon (paru, hilus, jantung, ...) dan garis (diafragma, klavikula, fisura, ...)
    // berwarna per struktur (warna sama dengan legenda). Zona paru turunan digambar tipis di layer tersendiri.
    const anat = structures.filter(st => !st.derived), zones = structures.filter(st => st.derived);
    const sysAttr = (st) => ({ 'data-sys': st.system || '', 'data-tid': st.taxon || '' });
    zones.forEach(st => {
        if (!st.polygon || st.polygon.length < 3) return;
        const color = stColor(st);
        mkEl(zoneG, 'polygon', Object.assign({ points: ptsStr(st.polygon.map(p => n2s(frame, p[0], p[1]))), fill: hexToRgba(color, 0.05), stroke: color,
            'stroke-width': 1, 'stroke-dasharray': '2,4', 'stroke-opacity': 0.85, 'stroke-linejoin': 'round' }, sysAttr(st)));
    });
    anat.forEach(st => {
        const color = stColor(st);
        if (st.polygon && st.polygon.length >= 3) {
            const P = st.polygon.map(p => n2s(frame, p[0], p[1]));
            mkEl(segAG, 'polygon', Object.assign({ points: ptsStr(P), fill: hexToRgba(color, st.tier === 3 ? 0.1 : 0.18), stroke: color,
                'stroke-width': st.tier === 3 ? 1.2 : 1.6, 'stroke-linejoin': 'round' }, sysAttr(st)));
            hexPx(color, 12);
        }
        if (st.polyline && st.polyline.length >= 2) {
            const P = st.polyline.map(p => n2s(frame, p[0], p[1]));
            mkEl(segAG, 'polyline', Object.assign({ points: ptsStr(P), fill: 'none', stroke: color, 'stroke-width': 2.4, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, sysAttr(st)));
            hexPx(color, 8);
        }
    });
    // Segmentasi lesi = HEATMAP: tiap lesi diisi gradien radial dari skor keparahannya (biru 0 ... merah 1);
    // inti paling panas, makin ke tepi makin dingin, lalu dikaburkan agar tampak sebagai peta panas.
    const heatDefs = anomalies.some(it => it.polygon || it.box) ? mkEl(svg, 'defs', {}) : null;
    const fid = 'hb-' + String(frameId).replace(/[^A-Za-z0-9_-]/g, '');
    if (heatDefs) {
        const bf = mkEl(heatDefs, 'filter', { id: fid, filterUnits: 'userSpaceOnUse', x: 0, y: 0, width: W, height: H });
        mkEl(bf, 'feGaussianBlur', { stdDeviation: 5 });
    }
    anomalies.forEach((item, i) => {
        let P = null;
        if (item.polygon && item.polygon.length >= 3) P = item.polygon.map(p => n2s(frame, p[0], p[1]));
        else if (item.box) {                       // tanpa kontur: heatmap oval di dalam kotak (perkiraan)
            const r = toScreen(item.box), cx = r.x + r.w / 2, cy = r.y + r.h / 2;
            P = Array.from({ length: 20 }, (_, k) => [cx + (r.w / 2) * Math.cos(k * Math.PI / 10), cy + (r.h / 2) * Math.sin(k * Math.PI / 10)]);
        }
        if (!P) return;
        const sc = lesionScore(item), color = heatColor(sc);
        const cx = P.reduce((t, p) => t + p[0], 0) / P.length, cy = P.reduce((t, p) => t + p[1], 0) / P.length;
        const rad = Math.max(8, ...P.map(p => Math.hypot(p[0] - cx, p[1] - cy)));
        const gid = `hg-${fid}-${i}`;
        const gr = mkEl(heatDefs, 'radialGradient', { id: gid, gradientUnits: 'userSpaceOnUse', cx, cy, r: rad });
        [[0, 0], [0.4, 0.25], [0.75, 0.55], [1, 0.85]].forEach(([off, t]) =>
            mkEl(gr, 'stop', { offset: off, 'stop-color': heatColor(sc * (1 - 0.7 * t)), 'stop-opacity': (0.85 - 0.4 * t).toFixed(2) }));
        // Heatmap hanya di dalam segmentasi lesi: dipotong (clipPath) mengikuti kontur, dan kontur itu sendiri dipotong ke kotak lesi,
        // sehingga blur tidak merembes keluar kontur maupun kotak.
        const g = mkEl(segLG, 'g', {});
        let heatHost = g;
        if (item.box) {
            const br = toScreen(item.box), bcid = `hcb-${fid}-${i}`;
            mkEl(mkEl(heatDefs, 'clipPath', { id: bcid }), 'rect', { x: br.x, y: br.y, width: br.w, height: br.h });
            heatHost = mkEl(g, 'g', { 'clip-path': `url(#${bcid})` });
        }
        const pcid = `hcp-${fid}-${i}`;
        mkEl(mkEl(heatDefs, 'clipPath', { id: pcid }), 'polygon', { points: ptsStr(P) });
        const heatG = mkEl(heatHost, 'g', { 'clip-path': `url(#${pcid})` });
        mkEl(heatG, 'polygon', { points: ptsStr(P), fill: `url(#${gid})`, stroke: 'none', filter: `url(#${fid})` });
        mkEl(heatHost, 'polygon', { points: ptsStr(P), fill: 'none', stroke: color, 'stroke-width': 1.8, 'stroke-linejoin': 'round', 'stroke-opacity': 0.9 });
        hexPx(color, 20);
    });
    // Deteksi anatomi: kotak putus-putus berwarna per struktur; label di titik dalam struktur (bukan sudut kotak) agar tidak saling menimpa
    anat.forEach(st => {
        if (!st.box) return;
        const color = stColor(st), r = toScreen(st.box);
        mkEl(detAG, 'rect', Object.assign({ x: r.x, y: r.y, width: r.w, height: r.h, fill: 'none', stroke: color, 'stroke-width': 1.2, 'stroke-dasharray': '6,4' }, sysAttr(st)));
        hexPx(color, 4);
        const lp = labelPointOf(frame, st);
        labels.push({ x: lp[0], y: lp[1], text: st.label, color, cls: 'ai-lbl struct-lbl', sys: st.system, prio: 1 + (st.tier || 2), center: true,
            title: [st.label_en, st.description].filter(Boolean).join(' - ') });
    });
    // Deteksi lesi: kotak solid berwarna sesuai skor heatmap
    anomalies.forEach((item, i) => {
        if (!item.box) return;
        const sc = lesionScore(item), color = heatColor(sc), r = toScreen(item.box), x = r.x, y = r.y, bw = r.w, bh = r.h;
        mkEl(detLG, 'rect', { x, y, width: bw, height: bh, fill: hexToRgba(color, 0.06), stroke: color, 'stroke-width': 1.8 });
        const L = Math.min(10, bw / 3, bh / 3);
        [[x, y, 1, 1], [x + bw, y, -1, 1], [x, y + bh, 1, -1], [x + bw, y + bh, -1, -1]].forEach(c =>
            mkEl(detLG, 'polyline', { points: `${c[0] + c[2] * L},${c[1]} ${c[0]},${c[1]} ${c[0]},${c[1] + c[3] * L}`, fill: 'none', stroke: color, 'stroke-width': 3 }));
        hexPx(color, 8);
        if (typeof imIsOpen === 'function' && imIsOpen() && __im.frameId === frameId && __im.idx === i)
            mkEl(detLG, 'rect', { x: x - 5, y: y - 5, width: bw + 10, height: bh + 10, fill: 'none', stroke: '#ffffff', 'stroke-width': 1.5, 'stroke-dasharray': '6,4', class: 'im-active-box', 'vector-effect': 'non-scaling-stroke' });
        if (item.confirmed) mkEl(detLG, 'rect', { x: x - 3, y: y - 3, width: bw + 6, height: bh + 6, fill: 'none', stroke: '#22c55e', 'stroke-width': 2, 'stroke-dasharray': '3,2' });
        // Satu kartu per lesi: nama + skor, lokasi anatomi (taksonomi), dan tombol Analysis options menyatu (tidak lagi dua label bertumpuk)
        labels.push({ x, y: y + 2, text: item.label || 'Abnormality', color, score: sc.toFixed(2), ai: { item, i }, editable: !frame.readOnly,
            cls: 'ai-lbl lbl-det lbl-card', prio: 0, insightIdx: i, loc: item.lokasi_label || '', fixed: !!(item.koreksi_lateralitas || item.koreksi_zona),
            warn: item.geometry_warning || '' });
    });
    // coretan Draw
    frame.strokes.forEach(st => {
        const S = st.pts.map(p => n2s(frame, p[0], p[1]));
        mkEl(svg, 'polyline', { points: ptsStr(S), fill: 'none', stroke: st.color, 'stroke-width': st.size, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    });
    // pengukuran
    frame.marks.filter(m => m.type !== 'mask').forEach(m => renderMark(frame, m, svg, labels, false));
    // seleksi
    if (frame.selection) {
        mkEl(svg, 'path', { d: maskPath(frame.selection.pts, frame.selection.invert), 'fill-rule': 'evenodd', fill: __selTransparent ? 'none' : 'rgba(59,130,246,.22)', stroke: '#fff', 'stroke-width': 1.5, class: 'sel-shape', 'pointer-events': 'none' });
    }
    // draft
    if (__draft && __draft.frameId === frameId) renderDraft(frame, svg, labels);

    labels.forEach(l => {
        const d = document.createElement('div'); d.className = `anno-label${l.cls ? ' ' + l.cls : ''}`;
        d.dataset.ax = l.x; d.dataset.ay = l.y; d.style.borderColor = l.color;
        if (l.prio !== undefined) d.dataset.prio = l.prio;
        if (l.center) d.dataset.center = '1';
        if (l.sys) d.dataset.sys = l.sys;
        if (l.title) d.title = l.title;
        let editEl = d;                                   // elemen yang boleh diedit (teks nama); pada kartu lesi hanya span nama
        if (l.insightIdx !== undefined) {
            const t = document.createElement('span'); t.className = 'lbl-txt'; t.textContent = l.text; if (l.score) t.dataset.score = l.score;
            d.appendChild(t); editEl = t;
            if (l.loc) {
                const s2 = document.createElement('span'); s2.className = 'lbl-loc'; s2.textContent = (l.fixed ? '\u2713 ' : '') + l.loc;
                if (l.fixed) s2.title = 'Side/zone in the name was adjusted to match the lesion position on the image';
                d.appendChild(s2);
            }
            const ob = document.createElement('button'); ob.type = 'button'; ob.className = 'lbl-open'; ob.textContent = 'Analysis options';
            ob.title = 'Open the analysis options map for this finding';
            ob.addEventListener('click', (e) => { e.stopPropagation(); openFindingInsight(frameId, l.insightIdx); });
            d.appendChild(ob);
            d.title = [l.text, l.loc && ('Anatomical location: ' + l.loc), l.warn].filter(Boolean).join('\n');
        } else {
            d.textContent = l.text;
            if (l.score) d.dataset.score = l.score;
        }
        const canEdit = l.ai ? l.editable : (l.mark && (['text', 'note', 'spine'].includes(l.mark.type) || l.mark.pending));
        if (l.mark) d.dataset.mid = l.mark.id;
        if (!l.text && l.mark) d.dataset.ph = l.mark.type === 'calibration' ? 'panjang (mm)' : (l.mark.type === 'text' ? 'Type text…' : 'Type a note…');
        if (canEdit) {
            editEl.contentEditable = 'true'; editEl.title = 'Click to edit';
            editEl.addEventListener('blur', () => {
                const t = editEl.textContent.trim();
                if (l.ai) {
                    l.ai.item.label = t || l.ai.item.label;
                    const li = document.querySelector(`.aedit[data-field="label"][data-idx="${l.ai.i}"]`); if (li) li.textContent = l.ai.item.label;
                } else if (l.mark) commitMarkText(frame, l.mark, t);
            });
            editEl.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); editEl.blur(); }
                if (e.key === 'Escape') { e.preventDefault(); if (l.mark && !l.mark.text) editEl.textContent = ''; editEl.blur(); }
                e.stopPropagation();
            });
        }
        lo.appendChild(d);
    });
    positionLabels(frame, cell);
    updateColorbar(frame, cell);
    updateFrameBottom(frame, cell);
}

// Keterangan di dalam citra: legenda warna organ (kiri), diagnosis + alternatif (tengah), skala heatmap keparahan (kanan).
function updateFrameBottom(frame, cell) {
    const bt = cell.querySelector('.frame-bottom'); if (!bt) return;
    const d = (frame.result && frame.result.data) || null;
    const lg = bt.querySelector('.frame-legend'), dx = bt.querySelector('.frame-dx'), ht = bt.querySelector('.frame-heat');
    if (!d) { lg.innerHTML = dx.innerHTML = ht.innerHTML = ''; bt.classList.add('empty'); return; }
    bt.classList.remove('empty');
    // legenda anatomi: hanya struktur yang benar-benar didapat (punya kotak/kontur/garis), tanpa duplikat, dikelompokkan per sistem taksonomi
    const seen = new Set(), bySys = new Map(), SYS_LABEL = Object.fromEntries(ANAT_SYSTEMS.map(x => [x.k, x.l]));
    (d.structures || []).forEach(st => {
        if (st.derived) return;
        const k = String(st.taxon || st.label || '').trim(); if (!k || seen.has(k.toLowerCase()) || !(st.box || st.polygon || st.polyline)) return;
        seen.add(k.toLowerCase());
        const sk = st.system || 'lainnya'; if (!bySys.has(sk)) bySys.set(sk, []);
        bySys.get(sk).push({ label: st.label, color: stColor(st), seg: !!(st.polygon || st.polyline) });
    });
    const sysOrder = ANAT_SYSTEMS.map(x => x.k).concat(['lainnya']), nOrgans = [...bySys.values()].reduce((n, a) => n + a.length, 0);
    lg.innerHTML = nOrgans
        ? `<div class="fl-title">Anatomy Legend \u00B7 ${nOrgans}</div>` + sysOrder.filter(k => bySys.has(k)).map(k =>
            `<div class="fl-sys">${escapeHtml(SYS_LABEL[k] || 'Other')}</div>` + bySys.get(k).map(o =>
                `<div class="fl-row"><i class="fl-sw${o.seg ? '' : ' dashed'}" style="--c:${o.color}"></i><span>${escapeHtml(o.label)}</span></div>`).join('')).join('')
        : '';
    lg.style.display = nOrgans ? '' : 'none';
    // diagnosis di citra
    const alts = (d.diagnosis_alternatif || []).map(a => typeof a === 'string' ? a : (a.label || '')).filter(Boolean).slice(0, 3);
    const tgt = frameTarget(frame);
    dx.innerHTML = `<div class="fd-head">${tgt === 'anatomi' ? 'Anatomy Impression' : 'Diagnosis'}</div>` +
        `<div class="fd-main">${escapeHtml(d.diagnosis || 'Unidentified')}</div>` +
        (d.diagnosis_code ? `<div class="fd-code">${escapeHtml(d.diagnosis_code)}</div>` : '') +
        (alts.length ? `<div class="fd-alt"><b>Alternatives:</b> ${alts.map(escapeHtml).join(' · ')}</div>` : '') +
        ((d.needs_review || d.diagnosis_perlu_verifikasi)
            ? `<div class="fd-warn" style="color:#fbbf24;font-size:11px;margin-top:2px;">${d.needs_review ? 'Unverified result' : 'Diagnosis needs verification'}</div>` : '');
    // skala heatmap lesi
    const les = d.anomalies || [];
    ht.innerHTML = les.length
        ? `<div class="fl-title">Lesion Severity</div><div class="fh-bar" style="background:${heatGradientCss('to right')}">` +
          les.map(a => `<i class="fh-tick" style="left:${(lesionScore(a) * 100).toFixed(1)}%;--c:${heatColor(lesionScore(a))}"></i>`).join('') +
          `</div><div class="fh-scale"><span>Safe</span><span>Moderate</span><span>Severe</span></div>`
        : '';
    ht.style.display = les.length ? '' : 'none';
}

function renderDraft(frame, svg, labels) {
    const d = __draft, S = d.pts.map(p => n2s(frame, p[0], p[1]));
    const stroke = { fill: 'none', stroke: '#fde047', 'stroke-width': 1.6, 'stroke-dasharray': '5,4' };
    if (d.kind === 'select-rect' || d.kind === 'crop') {
        const r = rectPts(d.pts[0], d.pts[1]).map(p => n2s(frame, p[0], p[1]));
        mkEl(svg, 'polygon', Object.assign({ points: ptsStr(r) }, stroke, d.kind === 'crop' ? { fill: 'rgba(250,204,21,.12)' } : { stroke: '#fff' }));
    } else if (d.kind === 'select-free') mkEl(svg, 'polyline', Object.assign({ points: ptsStr(S) }, stroke, { stroke: '#fff' }));
    else if (d.kind === 'flexpoly') mkEl(svg, 'polyline', Object.assign({ points: ptsStr(S) }, stroke));
    else if (d.kind === 'ellipse' || d.kind === 'rectangle' || d.kind === 'mask') renderMark(frame, { id: '_d', type: d.kind === 'mask' ? 'rectangle' : d.kind, pts: d.pts }, svg, labels, true);
    else {
        const spec = MT[d.kind]; const pts = d.cur ? d.pts.concat([d.cur]) : d.pts;
        if (spec.n && spec.n !== Infinity && pts.length === spec.n) renderMark(frame, { id: '_d', type: d.kind, pts }, svg, labels, true);
        else {
            const P = pts.map(p => n2s(frame, p[0], p[1]));
            if (P.length > 1) mkEl(svg, 'polyline', Object.assign({ points: ptsStr(P) }, stroke));
            P.forEach(p => dotEl(svg, p[0], p[1], '#fde047', 6));
        }
    }
}

function hexToRgba(hex, alpha) {
    const h = hex.replace('#', ''); return `rgba(${parseInt(h.substring(0, 2), 16)},${parseInt(h.substring(2, 4), 16)},${parseInt(h.substring(4, 6), 16)},${alpha})`;
}
// ===================== Print Scan =====================
function printScan() {
    if (!__frames.length) { showToast('No images to print yet.', 'error'); return; }
    logLine(`Printing scan: ${__frames.length} frame(s)`);
    document.body.classList.add('printing-scan');
    setTimeout(() => { window.print(); setTimeout(() => document.body.classList.remove('printing-scan'), 500); }, 50);
}