document.addEventListener("DOMContentLoaded", function () {

    /* =============================
       THEME TOGGLE
    ============================== */
    const themeToggle = document.getElementById('themeToggle');
    const htmlElement = document.documentElement;
    const themeIcon = document.getElementById('themeIcon');

    function updateIcon(theme) {
        if (themeIcon) themeIcon.innerText = theme === 'light' ? '🌑' : '☀️';
    }

    const savedTheme = localStorage.getItem('theme') || 'light';
    htmlElement.setAttribute('data-bs-theme', savedTheme);
    updateIcon(savedTheme);

    themeToggle?.addEventListener('click', () => {
        const newTheme = htmlElement.getAttribute('data-bs-theme') === 'light' ? 'dark' : 'light';
        htmlElement.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateIcon(newTheme);
    });

    /* =============================
       FONT SIZE
    ============================== */
    function applyFont(size) {
        document.body.classList.remove('font-medium', 'font-large');
        if (size !== 'normal') document.body.classList.add('font-' + size);
    }

    const savedFontSize = localStorage.getItem('user-font-size') || 'normal';
    applyFont(savedFontSize);

    const fontSelector = document.getElementById('fontSelector');
    if (fontSelector) {
        fontSelector.value = savedFontSize;
        fontSelector.addEventListener('change', (e) => {
            localStorage.setItem('user-font-size', e.target.value);
            applyFont(e.target.value);
        });
    }

    /* =============================
       AUTO HIDE ALERTS
    ============================== */
    const alerts = document.querySelectorAll('.auto-alert');
    if (alerts.length > 0) {
        setTimeout(() => {
            alerts.forEach(alert => {
                alert.classList.remove('show');
                alert.style.opacity = "0";
                setTimeout(() => alert.remove(), 500);
            });
        }, 3000);
    }

});
/*qpr-specific code*/
const API_URL = "/qpr/api/records/";
let records = []; // Store data globally

// Function to mask sensitive fields
function maskSensitiveData(value) {
    if (!value || value === '-') return '-';
    const valueStr = String(value);
    if (valueStr.length <= 2) return valueStr;
    return valueStr.charAt(0) + '*'.repeat(valueStr.length - 2) + valueStr.charAt(valueStr.length - 1);
}

// Fields to mask when in draft mode
const SENSITIVE_FIELDS = ['officeCode', 'phone', 'email'];

// --- 1. Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    // Check if user is authenticated
    checkAuthentication();
    populateYearDropdown();
    loadData();
    initHindiKeyboard();
    bindHindiFocusHandlers();
});

// Check if user is authenticated
function checkAuthentication() {
    const userDisplay = document.getElementById('userDisplay');
    if (!userDisplay) return;
    
    fetch('/qpr/api/records/')
        .then(res => {
            if (res.status === 401) {
                // Not authenticated, redirect to login
                window.location.href = '/login/';
            }
        })
        .catch(err => console.error(err));
}

// Hindi Keyboard - Track focused input
let currentHindiTarget = null;

function bindHindiFocusHandlers() {
    const selector = 'input[type=text], input[type=email], textarea';
    document.querySelectorAll(selector).forEach(el => {
        el.addEventListener('focus', () => { currentHindiTarget = el; });
        el.addEventListener('blur', () => { currentHindiTarget = null; });
    });
}

function initHindiKeyboard() {
    const toggle = document.getElementById('hindiToggle');
    const kb = document.getElementById('hindiKeyboard');
    if (!toggle || !kb) return;

    toggle.addEventListener('click', () => {
        kb.style.display = kb.style.display === 'block' ? 'none' : 'block';
    });

    // Hindi characters organized by category
    const rows = [
        ['अ','आ','इ','ई','उ','ऊ','ए','ऐ','ओ','औ'],
        ['क','ख','ग','घ','ङ','च','छ','ज','झ','ञ'],
        ['ट','ठ','ड','ढ','ण','त','थ','द','ध','न'],
        ['प','फ','ब','भ','म','य','र','ल','व','श'],
        ['ष','स','ह','ा','ि','ी','ु','ू','ृ','ॉ'],
        ['्','ं','ः','ँ','Space','Delete']
    ];

    kb.innerHTML = '';
    rows.forEach(r => {
        const row = document.createElement('div');
        row.className = 'hk-row';
        r.forEach(key => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = key === 'Space' ? '␣' : (key === 'Delete' ? '⌫' : key);
            btn.setAttribute('tabindex', '-1'); // Prevent focus on button
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault(); // Prevent focus steal
            });
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                if (!currentHindiTarget) return;

                if (key === 'Delete') {
                    const el = currentHindiTarget;
                    const start = el.selectionStart || 0;
                    if (start > 0) {
                        el.value = el.value.slice(0, start - 1) + el.value.slice(start);
                        el.selectionStart = el.selectionEnd = start - 1;
                    }
                } else if (key === 'Space') {
                    const el = currentHindiTarget;
                    const start = el.selectionStart || 0;
                    const end = el.selectionEnd || 0;
                    el.value = el.value.slice(0, start) + ' ' + el.value.slice(end);
                    el.selectionStart = el.selectionEnd = start + 1;
                } else {
                    const el = currentHindiTarget;
                    const start = el.selectionStart || 0;
                    const end = el.selectionEnd || 0;
                    el.value = el.value.slice(0, start) + key + el.value.slice(end);
                    el.selectionStart = el.selectionEnd = start + key.length;
                }
                // Keep focus on the input field
                currentHindiTarget.focus();
            });
            row.appendChild(btn);
        });
        kb.appendChild(row);
    });
}

// Function to populate year dropdown with fiscal years
function populateYearDropdown() {
    const yearSelect = document.getElementById('year');
    
    if (!yearSelect) {
        console.error('Year select element not found');
        return;
    }
    
    const currentDate = new Date();
    const currentMonth = currentDate.getMonth();
    const currentYear = currentDate.getFullYear();
    
    // Fiscal year in India runs from April to March
    // If current month is March or earlier, fiscal year starts from previous year
    let fiscalYearStart = currentMonth < 3 ? currentYear - 1 : currentYear;
    let fiscalYearEnd = fiscalYearStart + 1;
    
    yearSelect.innerHTML = ''; // Clear existing options
    
    const startYear = 2000;
    const endYear = new Date().getFullYear() + 50; // Current year + 50 years ahead
    
    for (let year = startYear; year <= endYear; year++) {
        const option = document.createElement('option');
        option.value = `${year}-${year + 1}`;
        option.textContent = `${year}-${year + 1}`;
        yearSelect.appendChild(option);
    }
    
    // Set the current fiscal year as selected
    yearSelect.value = `${fiscalYearStart}-${fiscalYearEnd}`;
    console.log('Year dropdown populated with current fiscal year:', `${fiscalYearStart}-${fiscalYearEnd}`);
}

// --- 2. Load Data (GET) ---
async function loadData() {
    try {
        const response = await fetch(API_URL);
        const data = await response.json();

        // *** FIX 1: Update the global variable so editRecord finds the data ***
        records = data;
        
        // If tableBody exists on this page, populate the table (report list or main view)
        const tableBody = document.getElementById('tableBody');
        if (tableBody && tableBody !== null) {
            try {
                tableBody.innerHTML = ''; // Clear existing rows

                if (records.length === 0) {
                    tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No records found</td></tr>';
                } else {
                    records.forEach(record => {
                    let actionButtons = '';
                    let statusBadge = '';

                    if (record.status === 'Draft') {
                        statusBadge = '<span class="badge bg-primary">Draft</span>';
                        actionButtons = `
                            <button class="btn btn-sm btn-outline-warning fw-bold" onclick="event.stopPropagation(); editRecord(${record.id})">
                                ✏️ Edit
                            </button>
                        `;
                    } else {
                        statusBadge = '<span class="badge bg-success">Submitted</span>';
                        actionButtons = `
                            <button class="btn btn-sm btn-outline-danger fw-bold" onclick="event.stopPropagation(); deleteRecord(${record.id})">
                                ✘ Delete
                            </button>
                        `;
                    }

                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${record.officeName || '-'}</td>
                        <td>${record.officeCode || '-'}</td>
                        <td>${record.region || '-'}</td>
                        <td>${record.quarter || '-'}</td>
                        <td>${statusBadge}</td>
                        <td>${actionButtons}</td>
                    `;
                    tableBody.appendChild(row);

                    if (record.status === 'Submitted') {
                        row.style.cursor = 'pointer';
                        row.addEventListener('click', () => toggleDetailsRow(row, record));
                    }
                });
            }
            } catch(err) {
                console.error('Error populating tableBody:', err);
            }
        }

        // Check if we're coming from edit action in report list
        const editId = localStorage.getItem('editRecordId');
        console.log("After loadData - editId from localStorage:", editId);
        console.log("Total records loaded:", records.length);
        
        if (editId) {
            localStorage.removeItem('editRecordId');
            const rid = parseInt(editId, 10);
            console.log("Attempting to edit record ID:", rid);
            if (!isNaN(rid)) {
                const rec = records.find(r => r.id === rid);
                console.log("Found record in array:", rec);
                if (rec) {
                    editRecord(rid);
                }
            }
        } else {
            // Only show Tab 1 if not editing
            if (!document.getElementById('tableBody')) {
                showTab(1);
            }
        }

    } catch (error) {
        console.error('Error loading data:', error);
    }
}

// --- 3. Save Data (Smart Version) ---
async function saveData(status) {
    const idInput = document.getElementById('recordId');
    const id = idInput ? idInput.value : null;
    
    console.log("saveData called with status:", status);
    console.log("recordId input element:", idInput);
    console.log("recordId value:", id);
    
    const mainFields = ['officeName', 'officeCode', 'region', 'quarter', 'recordId'];
    
    const payload = {
        id: id ? id : null,
        status: status,
        officeName: document.getElementById('officeName').value,
        officeCode: document.getElementById('officeCode').value,
        region: document.getElementById('region').value,
        quarter: document.getElementById('quarter').value,
        details: {} 
    };

    console.log("Payload being sent:", payload);

    const form = document.getElementById('qprForm');
    const elements = form.elements; 

    for (let i = 0; i < elements.length; i++) {
        const el = elements[i];
        if (el.id && !mainFields.includes(el.id)) {
            payload.details[el.id] = el.value;
        }
    }

    try {
        const res = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            alert(status === 'Draft' ? "Draft Saved Successfully!" : "Report Submitted Successfully!");
            clearForm();
            loadData(); 
        } else {
            alert("Server Error: " + res.statusText);
        }
    } catch (err) {
        console.error("Save Error:", err);
        alert("Failed to save.");
    }
}

// --- 4. Edit Data (Now working!) ---
function editRecord(id) {
    // This finds the record because we updated 'records' in loadData()
    const record = records.find(r => r.id === id);
    
    console.log("editRecord called with id:", id);
    console.log("Available records:", records);
    console.log("Found record:", record);
    
    if (!record) {
        console.error("Record not found for ID:", id);
        return;
    }

    // Fill Main Fields - Apply masking to all records
    console.log("Filling form with record:", record);
    document.getElementById('recordId').value = record.id;
    document.getElementById('officeName').value = record.officeName;
    document.getElementById('officeCode').value = maskSensitiveData(record.officeCode);
    document.getElementById('region').value = record.region;
    document.getElementById('quarter').value = record.quarter;
    
    // Handle phone field if it exists in details
    if (record.details && record.details.phone) {
        const phoneEl = document.getElementById('phone');
        if (phoneEl) {
            phoneEl.value = maskSensitiveData(record.details.phone);
        }
    }
    
    // Handle email field if it exists in details
    if (record.details && record.details.email) {
        const emailEl = document.getElementById('email');
        if (emailEl) {
            emailEl.value = maskSensitiveData(record.details.email);
        }
    }

    // Fill Details - Apply masking to all records
    if (record.details) {
        for (const [key, value] of Object.entries(record.details)) {
            const el = document.getElementById(key);
            if (el) {
                if (SENSITIVE_FIELDS.includes(key)) {
                    el.value = maskSensitiveData(value);
                } else {
                    el.value = value;
                }
                console.log("Set field", key, "to", el.value);
            }
        }
    }
    
    // Disable/Enable form based on edit permission
    setFormEditability(record.can_edit, record.edit_approved);

    showTab(1);
}

// Helper function to disable/enable form fields based on edit permission
function setFormEditability(canEdit, editApproved) {
    const form = document.getElementById('qprForm');
    const allInputs = form.querySelectorAll('input, textarea, select');
    
    // Get all save buttons (both Draft and Submit buttons)
    const saveBtns = document.querySelectorAll('button[onclick*="saveData"]');
    
    if (canEdit) {
        // Enable all fields
        allInputs.forEach(input => {
            input.disabled = false;
        });
        saveBtns.forEach(btn => btn.disabled = false);
        
        if (editApproved) {
            // Show info message
            showEditApprovedMessage();
        }
    } else {
        // Disable all fields (read-only mode)
        allInputs.forEach(input => {
            input.disabled = true;
        });
        saveBtns.forEach(btn => btn.disabled = true);
        
        // Show message
        showEditDisabledMessage();
    }
}

// Show message when edit is approved
function showEditApprovedMessage() {
    const existingMsg = document.getElementById('editApprovedMsg');
    if (existingMsg) existingMsg.remove();
    
    const msgDiv = document.createElement('div');
    msgDiv.id = 'editApprovedMsg';
    msgDiv.className = 'alert alert-success alert-dismissible fade show mb-3';
    msgDiv.innerHTML = `
        <i class="fas fa-check-circle"></i> <strong>Edit Approved!</strong> 
        Admin has approved your edit request. You can now modify this QPR.
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const form = document.getElementById('qprForm');
    form.parentNode.insertBefore(msgDiv, form);
}

// Show message when edit is not allowed
function showEditDisabledMessage() {
    const existingMsg = document.getElementById('editDisabledMsg');
    if (existingMsg) existingMsg.remove();
    
    const msgDiv = document.createElement('div');
    msgDiv.id = 'editDisabledMsg';
    msgDiv.className = 'alert alert-warning alert-dismissible fade show mb-3';
    msgDiv.innerHTML = `
        <i class="fas fa-lock"></i> <strong>Read-Only Mode</strong> 
        This submitted QPR cannot be edited. If you need to make changes, 
        please request permission using the "Request to Edit" option.
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const form = document.getElementById('qprForm');
    form.parentNode.insertBefore(msgDiv, form);
}

// --- 5. Delete Data ---
async function deleteRecord(id) {
    if (!confirm("Are you sure you want to permanently delete this record?")) return;

    try {
        await fetch(`${API_URL}?id=${id}`, { method: 'DELETE' });
        loadData();
    } catch (error) {
        console.error("Error deleting:", error);
        alert("Failed to delete.");
    }
}

// --- 6. Tab Navigation ---
function showTab(n) {
    document.getElementById('tab1').classList.add('d-none');
    document.getElementById('tab2').classList.add('d-none');
    document.getElementById('tab3').classList.add('d-none');

    const selectedTab = document.getElementById('tab' + n);
    if (selectedTab) selectedTab.classList.remove('d-none');

    // Update part badge to reflect current tab number (Part-1, Part-2, Part-3...)
    const partEl = document.getElementById('partBadge');
    if (partEl) {
        partEl.textContent = `Part-${n}`;
    }

    document.querySelector('.card').scrollIntoView({ behavior: 'smooth' });
}

// --- 7. Helper: Clear Form ---
function clearForm() {
    const form = document.getElementById('qprForm');
    if (form) form.reset();
    
    const idInput = document.getElementById('recordId');
    if (idInput) idInput.value = '';
    
    showTab(1);
}

// --- 8. Details view for submitted records ---
function getLabelForInput(id) {
    const el = document.getElementById(id);
    if (!el) return id;

    // Try to find a nearby .lbl-text
    const lblRow = el.closest('.lbl-row');
    if (lblRow) {
        const labelEl = lblRow.querySelector('.lbl-text');
        if (labelEl) return labelEl.innerText.trim();
    }

    // For textareas, use placeholder
    if (el.placeholder) return el.placeholder;

    // Fallback to id
    return id;
}

function toggleDetailsRow(row, record) {
    // If next sibling is already the details row for this record, remove it
    const next = row.nextElementSibling;
    if (next && next.classList.contains('details-row') && next.dataset.id == record.id) {
        next.remove();
        return;
    }

    // Remove any other details rows
    const existing = document.querySelectorAll('.details-row');
    existing.forEach(r => r.remove());

    // Build headings and values arrays
    const headings = ['Office Name', 'Office Code', 'Region', 'Quarter', 'Status'];
    const values = [record.officeName || '-', record.officeCode || '-', record.region || '-', record.quarter || '-', record.status || '-'];

    // Add details fields (order as stored)
    if (record.details) {
        for (const [key, val] of Object.entries(record.details)) {
            headings.push(getLabelForInput(key));
            values.push(val === undefined || val === null || val === '' ? '-' : val);
        }
    }

    // Create details row
    const detailsRow = document.createElement('tr');
    detailsRow.className = 'details-row';
    detailsRow.dataset.id = record.id;
    const td = document.createElement('td');
    td.colSpan = 6;

    // Build an inner table with headings on top and values bottom
    let inner = '<div class="table-responsive"><table class="table table-sm table-bordered mb-0">';
    inner += '<thead class="table-light"><tr>';
    headings.forEach(h => { inner += `<th scope="col">${h}</th>`; });
    inner += '</tr></thead>';
    inner += '<tbody><tr>';
    values.forEach(v => { inner += `<td>${v}</td>`; });
    inner += '</tr></tbody></table></div>';

    td.innerHTML = inner;
    detailsRow.appendChild(td);

    // Insert after the clicked row
    row.parentNode.insertBefore(detailsRow, row.nextSibling);
    detailsRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
