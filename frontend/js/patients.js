let __patientsCache = [];
let __searchDebounce = null;

async function loadPatients() {
    const q = document.getElementById('patient-search').value.trim();
    logLine(q ? `Loading patient list with search: ${q}` : 'Loading patient list');
    try {
        const path = q ? `/api/patients?q=${encodeURIComponent(q)}` : '/api/patients';
        const patients = await apiFetch(path);
        __patientsCache = patients;
        renderPatientsTable(patients);
        logLine(`Patient list loaded: ${patients.length} patients${q ? ' matching the search' : ''}`, 'ok');
        if (typeof loadPatientOptionsForScan === 'function') loadPatientOptionsForScan(); // sidebar ikut diperbarui
    } catch (e) {
        showToast(`Failed to load patient data: ${e.message}`, 'error');
    }
}

function renderPatientsTable(patients) {
    const tbody = document.getElementById('patients-tbody');
    const emptyState = document.getElementById('patients-empty');

    if (!patients || patients.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }
    emptyState.style.display = 'none';

    tbody.innerHTML = patients.map(p => `
        <tr>
            <td>${escapeHtml(p.mrn)}</td>
            <td>${escapeHtml(p.name)}</td>
            <td>${p.gender === 'L' ? 'Male' : p.gender === 'P' ? 'Female' : '-'}</td>
            <td>${p.birth_date || '-'}</td>
            <td>${p.phone || '-'}</td>
            <td>${p.total_scans}</td>
            <td>
                <div class="row-actions">
                    <button type="button" class="btn-secondary btn-sm" onclick="openPatientModal(${p.id})">Edit</button>
                    <button type="button" class="btn-danger btn-sm" onclick="deletePatient(${p.id}, '${escapeHtml(p.name).replace(/'/g, "\\'")}')">Delete</button>
                </div>
            </td>
        </tr>
    `).join('');
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('patient-search').addEventListener('input', () => {
        clearTimeout(__searchDebounce);
        __searchDebounce = setTimeout(loadPatients, 350);
    });

    document.getElementById('btn-add-patient').addEventListener('click', () => openPatientModal(null));
    document.getElementById('btn-cancel-patient').addEventListener('click', closePatientModal);
    document.getElementById('btn-save-patient').addEventListener('click', savePatient);
});

function openPatientModal(patientId) {
    const modal = document.getElementById('patient-modal');
    const title = document.getElementById('patient-modal-title');

    document.getElementById('patient-id').value = '';
    document.getElementById('patient-mrn').value = '';
    document.getElementById('patient-name').value = '';
    document.getElementById('patient-gender').value = '';
    document.getElementById('patient-birthdate').value = '';
    document.getElementById('patient-phone').value = '';
    document.getElementById('patient-address').value = '';
    document.getElementById('patient-notes').value = '';

    if (patientId) {
        const p = __patientsCache.find(x => x.id === patientId);
        if (p) {
            logLine(`Opening edit patient form: ${p.name} (${p.mrn})`);
            title.textContent = 'Edit Patient';
            document.getElementById('patient-id').value = p.id;
            document.getElementById('patient-mrn').value = p.mrn;
            document.getElementById('patient-name').value = p.name;
            document.getElementById('patient-gender').value = p.gender || '';
            document.getElementById('patient-birthdate').value = p.birth_date || '';
            document.getElementById('patient-phone').value = p.phone || '';
            document.getElementById('patient-address').value = p.address || '';
            document.getElementById('patient-notes').value = p.notes || '';
        }
    } else {
        logLine('Opening add patient form');
        title.textContent = 'Add New Patient';
    }

    modal.classList.add('active');
}

function closePatientModal() {
    if (document.getElementById('patient-modal').classList.contains('active')) logLine('Patient form closed');
    document.getElementById('patient-modal').classList.remove('active');
}

async function savePatient() {
    const id = document.getElementById('patient-id').value;
    const payload = {
        mrn: document.getElementById('patient-mrn').value.trim(),
        name: document.getElementById('patient-name').value.trim(),
        gender: document.getElementById('patient-gender').value,
        birth_date: document.getElementById('patient-birthdate').value,
        phone: document.getElementById('patient-phone').value.trim(),
        address: document.getElementById('patient-address').value.trim(),
        notes: document.getElementById('patient-notes').value.trim(),
    };

    if (!payload.mrn || !payload.name) {
        showToast('Medical Record No. and Name are required.', 'error');
        return;
    }

    try {
        logLine(`${id ? 'Saving changes' : 'Saving new patient'}: ${payload.name} (${payload.mrn})`);
        if (id) {
            await apiFetch(`/api/patients/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
            showToast(`Patient ${payload.name} updated successfully.`, 'success');
        } else {
            await apiFetch('/api/patients', { method: 'POST', body: JSON.stringify(payload) });
            showToast(`New patient ${payload.name} added successfully.`, 'success');
        }
        closePatientModal();
        loadPatients();
    } catch (e) {
        showToast(`Failed to save: ${e.message}`, 'error');
    }
}

async function deletePatient(id, name) {
    if (!confirm(`Delete patient "${name}"? All related scan history will also be deleted.`)) { logLine(`Patient deletion cancelled: ${name}`); return; }
    try {
        logLine(`Deleting patient: ${name}`);
        await apiFetch(`/api/patients/${id}`, { method: 'DELETE' });
        showToast(`Patient ${name} deleted successfully.`, 'success');
        loadPatients();
    } catch (e) {
        showToast(`Failed to delete: ${e.message}`, 'error');
    }
}
