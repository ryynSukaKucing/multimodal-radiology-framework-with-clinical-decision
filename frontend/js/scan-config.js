// =====================================================================
//  Konfigurasi pemindaian tetap (menggantikan Scan Settings yang sudah dihapus).
//  - Area anatomi dikunci ke Thorax / Chest (fokus toraks).
//  - Jenis pencitraan, objek pindai (anatomi / lesi / anatomi+lesi), dan kode diagnosis dipilih di panel pengaturan (scan.js).
//  - Object Detection + Segmentation dibuat otomatis oleh Model AI (lihat menu Layer untuk menyembunyikan).
//  - Sintesis SOAP + ICD-11 aktif secara bawaan.
// =====================================================================
window.__llmSynth = true;

document.addEventListener('DOMContentLoaded', () => {
    const area = document.getElementById('anatomical-area-select');
    if (area) area.value = 'Thorax / Chest';
    const model = document.getElementById('model-select');
    if (model) model.addEventListener('change', () => {
        logLine(`AI Model: ${model.value}`, '', 'scan');
        if (typeof refreshAllFrameInfo === 'function') refreshAllFrameInfo();
    });
});
