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
// Ensure server globals are available before any QPR logic
document.addEventListener('DOMContentLoaded', function () {
    try { console.log("SERVER:", window.SERVER_MONTH, window.SERVER_YEAR); } catch(e) {}
    try { if (typeof populateYearDropdown === 'function') populateYearDropdown(); } catch(e) {}
    try { if (typeof populateQuarterDropdown === 'function') populateQuarterDropdown(); } catch(e) {}
    try { if (typeof populateMonthDropdown === 'function') populateMonthDropdown(); } catch(e) {}
});

function populateYearDropdown() {
    // Year options are server-rendered; this function is a safe hook for future logic.
    const yearEl = document.getElementById('year');
    if (!yearEl) return;
}

function populateMonthDropdown() {
    // placeholder for month-level dropdown if required by UI
    return;
}

// API URL is removed for client-side fetch. When present, templates may define
// `PRELOADED_RECORDS` or `window.QPR_API_URL`. Default to null to avoid calls.
let API_URL = window.QPR_API_URL || null;
let records = []; // Store data globally

function unlockQprFillControls() {
    const frequencyEl = document.getElementById('frequency');
    if (frequencyEl) {
        frequencyEl.disabled = false;
        Array.from(frequencyEl.options).forEach(opt => {
            opt.disabled = false;
        });
    }

    const selectedDateEl = document.getElementById('selectedDate');
    if (selectedDateEl) {
        selectedDateEl.disabled = false;
        selectedDateEl.readOnly = false;
        selectedDateEl.removeAttribute('min');
        selectedDateEl.setCustomValidity('');
        selectedDateEl.classList.remove('text-muted');
    }
}

// Function to mask sensitive fields
function maskSensitiveData(value) {
    if (!value || value === '-') return '-';
    const valueStr = String(value);
    if (valueStr.length <= 2) return valueStr;
    return valueStr.charAt(0) + '*'.repeat(valueStr.length - 2) + valueStr.charAt(valueStr.length - 1);
}

// Fields to mask when in draft mode (don't mask officeCode anymore)
const SENSITIVE_FIELDS = [];

// --- 1. Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    // Initialize only on QPR form/page to avoid errors on other pages
    const isQPRPage = !!document.getElementById('qprForm');
    if (isQPRPage) {
        initHindiKeyboard();
        bindHindiFocusHandlers();
        checkAuthentication();
            loadData();
            // Attach live totals listeners (no API) for client-side immediate sums
            try { attachLiveTotalsListeners(); } catch(e) { console.error('live totals init error', e); }

        // Prefill quarter/year from server (exposed as window globals in template)
        try {
            const serverQuarter = window.QPR_SERVER_QUARTER || '';
            const serverYear = window.QPR_SERVER_YEAR || '';
            const quarterEl = document.getElementById('quarter');
            const yearEl = document.getElementById('year');
            if (quarterEl && serverQuarter) quarterEl.value = serverQuarter;

            // Populate quarter options based on selected year and today's date
            try { populateQuarterDropdown(); } catch(e) { console.error(e); }
            try { updateQuarterAvailability(); } catch(e) { console.error(e); }

            // Recompute quarter options & availability when year changes
            if (yearEl) yearEl.addEventListener('change', () => {
                try { populateQuarterDropdown(); } catch(e) { console.error(e); }
                try { updateQuarterAvailability(); } catch(e) { console.error(e); }
            });

            // Selected date behavior: default to today, set min/max and query availability
            const selectedDateEl = document.getElementById('selectedDate');
            const frequencyEl = document.getElementById('frequency');
            
            // Ensure frequency defaults to 'daily' (should not be empty)
            if (frequencyEl && (!frequencyEl.value || frequencyEl.value === '')) {
                frequencyEl.value = 'daily';
            }
            
            const availabilityBoxId = 'qprAvailabilityBox';
            function isScopedSnapshotEditMode() {
                const params = new URLSearchParams(window.location.search || '');
                const urlScope = (params.get('edit_scope') || '').toLowerCase();
                const hiddenScope = (document.getElementById('snapshotEditScope')?.value || '').toLowerCase();
                return ['weekly', 'monthly', 'quarterly'].includes(urlScope || hiddenScope);
            }
            function showAvailabilityBox(html) {
                let box = document.getElementById(availabilityBoxId);
                if (!box) {
                    box = document.createElement('div');
                    box.id = availabilityBoxId;
                    box.className = 'mt-2';
                    const form = document.getElementById('qprForm');
                    form.parentNode.insertBefore(box, form.nextSibling);
                }
                box.innerHTML = html;
            }

            function parseLocalDate(dateStr) {
                if (!dateStr) return null;
                const parts = String(dateStr).split('-').map(Number);
                if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
                return new Date(parts[0], parts[1] - 1, parts[2]);
            }

            function toIsoDate(dateObj) {
                const y = dateObj.getFullYear();
                const m = String(dateObj.getMonth() + 1).padStart(2, '0');
                const d = String(dateObj.getDate()).padStart(2, '0');
                return `${y}-${m}-${d}`;
            }

            function addDays(dateObj, days) {
                const d = new Date(dateObj.getFullYear(), dateObj.getMonth(), dateObj.getDate());
                d.setDate(d.getDate() + days);
                return d;
            }

            function quarterBounds(dateObj) {
                const y = dateObj.getFullYear();
                const m = dateObj.getMonth();
                if (m >= 3 && m <= 5) return [new Date(y, 3, 1), new Date(y, 5, 30)];
                if (m >= 6 && m <= 8) return [new Date(y, 6, 1), new Date(y, 8, 30)];
                if (m >= 9 && m <= 11) return [new Date(y, 9, 1), new Date(y, 11, 31)];
                return [new Date(y, 0, 1), new Date(y, 2, 31)];
            }

            function periodBounds(freq, dateObj) {
                const [qStart, qEnd] = quarterBounds(dateObj);
                if (freq === 'weekly') {
                    const mondayBasedDay = (dateObj.getDay() + 6) % 7;
                    let start = addDays(dateObj, -mondayBasedDay);
                    let end = addDays(start, 5);
                    if (start < qStart) start = qStart;
                    if (end > qEnd) end = qEnd;
                    return [start, end];
                }
                if (freq === 'monthly') {
                    let start = new Date(dateObj.getFullYear(), dateObj.getMonth(), 1);
                    let end = new Date(dateObj.getFullYear(), dateObj.getMonth() + 1, 0);
                    if (start < qStart) start = qStart;
                    if (end > qEnd) end = qEnd;
                    return [start, end];
                }
                if (freq === 'quarterly') return [qStart, qEnd];
                return [dateObj, dateObj];
            }

            function fillForPeriod(freq, startIso, endIso) {
                const source = window.QPR_MISSING_DAYS_SOURCE || {};
                const fills = source.fills && source.fills[freq] ? source.fills[freq] : [];
                return fills.find(fill => fill.period_start === startIso && fill.period_end === endIso) || null;
            }

            function missingInfoFor(freq, dateStr) {
                const selected = parseLocalDate(dateStr);
                if (!selected || !['weekly', 'monthly', 'quarterly'].includes(freq)) return null;
                const [start, end] = periodBounds(freq, selected);
                const submitted = new Set((window.QPR_MISSING_DAYS_SOURCE || {}).submitted_daily_dates || []);
                const missingDays = [];
                for (let day = new Date(start); day <= end; day = addDays(day, 1)) {
                    if (day.getDay() === 0) continue;
                    const iso = toIsoDate(day);
                    if (!submitted.has(iso)) missingDays.push(iso);
                }

                const startIso = toIsoDate(start);
                const endIso = toIsoDate(end);
                const existingFill = fillForPeriod(freq, startIso, endIso);
                const dayNames = missingDays.map(d => parseLocalDate(d).toLocaleDateString('en-IN', { weekday: 'short' }));
                const message = missingDays.length
                    ? `Filling ${missingDays.length} missing day${missingDays.length === 1 ? '' : 's'} (${dayNames.join(', ')}) for ${freq} of ${start.toLocaleDateString('en-GB')}`
                    : `All days covered for this ${freq}. No missing days to fill.`;

                return {
                    missing_days: missingDays,
                    has_fill: !!existingFill,
                    fill_fields_count: existingFill ? (existingFill.fill_fields_count || 0) : 0,
                    message,
                    period_start: startIso,
                    period_end: endIso,
                };
            }

            function updateMissingDaysAlert() {
                const missingDaysAlert = document.getElementById('missingDaysAlert');
                if (!missingDaysAlert || !frequencyEl || !selectedDateEl) return;
                const freq = frequencyEl.value;
                const missingInfo = missingInfoFor(freq, selectedDateEl.value);
                if (!missingInfo) {
                    missingDaysAlert.classList.add('d-none');
                    return;
                }

                document.getElementById('missingDaysTitle').textContent = `${freq.charAt(0).toUpperCase() + freq.slice(1)} - Missing Days Info`;
                document.getElementById('missingDaysMessage').textContent = missingInfo.message;
                if (missingInfo.missing_days && missingInfo.missing_days.length) {
                    const daysList = missingInfo.missing_days.map(d => parseLocalDate(d).toLocaleDateString('en-IN', {weekday: 'short', month: 'short', day: 'numeric'})).join(', ');
                    document.getElementById('missingDaysList').textContent = `Missing dates: ${daysList}`;
                } else {
                    document.getElementById('missingDaysList').textContent = 'No missing days - all days are covered.';
                }
                document.getElementById('existingFillInfo').textContent = missingInfo.has_fill
                    ? `You have already filled ${missingInfo.fill_fields_count} field(s) for this ${freq}. Submitting will update these values.`
                    : '';
                missingDaysAlert.classList.remove('d-none');
            }

            function updateAvailabilitySummary() {
                if (!selectedDateEl) return;
                const week = missingInfoFor('weekly', selectedDateEl.value);
                const month = missingInfoFor('monthly', selectedDateEl.value);
                const quarter = missingInfoFor('quarterly', selectedDateEl.value);
                const lines = [];
                if (week) lines.push(`<strong>Missing (week):</strong> ${week.missing_days.length ? week.missing_days.join(', ') : '0 days'}`);
                if (month) lines.push(`<strong>Missing (month):</strong> ${month.missing_days.length} days`);
                if (quarter) lines.push(`<strong>Missing (quarter):</strong> ${quarter.missing_days.length} days`);
                showAvailabilityBox(lines.length ? '<div class="alert alert-info">' + lines.join('<br>') + '</div>' : '<div class="text-muted small">No missing days for selected date</div>');
            }

            if (selectedDateEl) {
                // initialize and update missing-day info locally from preloaded data
                if (!selectedDateEl.value) selectedDateEl.value = (new Date()).toISOString().slice(0,10);
                unlockQprFillControls();
                updateAvailabilitySummary();
                updateMissingDaysAlert();
                selectedDateEl.addEventListener('change', (e) => {
                    unlockQprFillControls();
                    updateAvailabilitySummary();
                    updateMissingDaysAlert();
                });
            }

            if (frequencyEl) {
                frequencyEl.addEventListener('change', () => {
                    updateMissingDaysAlert();
                    
                    unlockQprFillControls();
                    // Draft is valid for normal QPR entry flows, including weekly/monthly/quarterly
                    // entries used to fill missed daily periods. Hide it only for snapshot overwrites.
                    try {
                        const saveDraftBtn = document.getElementById('saveDraftBtn');
                        if (saveDraftBtn) {
                            if (isScopedSnapshotEditMode()) {
                                saveDraftBtn.disabled = true;
                                saveDraftBtn.classList.add('d-none');
                            } else {
                                saveDraftBtn.disabled = false;
                                saveDraftBtn.classList.remove('d-none');
                            }
                        }
                    } catch(e) {}
                });
                // initialize draft button state based on current edit mode
                try {
                    const saveDraftBtn = document.getElementById('saveDraftBtn');
                    if (saveDraftBtn) {
                        if (isScopedSnapshotEditMode()) {
                            saveDraftBtn.disabled = true;
                            saveDraftBtn.classList.add('d-none');
                        } else {
                            saveDraftBtn.disabled = false;
                            saveDraftBtn.classList.remove('d-none');
                        }
                        // prevent accidental usage during snapshot overwrite edits
                        try {
                            saveDraftBtn.addEventListener('click', function(ev){
                                if (isScopedSnapshotEditMode()) {
                                    ev.preventDefault();
                                    alert('Draft is not available for snapshot overwrites. Please submit the snapshot changes.');
                                    return false;
                                }
                            });
                        } catch(e) {}
                    }
                } catch(e) {}

                // Prevent form submitting a draft during snapshot overwrite edits (covers hidden inputs)
                try {
                    const qprForm = document.getElementById('qprForm');
                    if (qprForm) {
                        qprForm.addEventListener('submit', function(ev){
                            try {
                                const statusInput = qprForm.querySelector('input[name="status"]');
                                const statusVal = statusInput ? String(statusInput.value).toLowerCase() : null;
                                if (isScopedSnapshotEditMode() && statusVal === 'draft') {
                                    ev.preventDefault();
                                    alert('Draft is not available for snapshot overwrites. Please submit the snapshot changes.');
                                    return false;
                                }
                            } catch(e) { /* ignore */ }
                        });
                    }
                } catch(e) {}
            }

            // Also recompute when recordId is set by edit action
            const rid = document.getElementById('recordId');
            if (rid) {
                const observer = new MutationObserver(() => updateQuarterAvailability());
                observer.observe(rid, { attributes: true, childList: true, subtree: false });
            }
        } catch (e) { console.error(e); }

        return;
    }

    // For non-QPR pages, still bind lightweight helpers
    bindHindiFocusHandlers();
});

// Check if user is authenticated
function checkAuthentication() {
    const userDisplay = document.getElementById('userDisplay');
    if (!userDisplay) return;
    // Authentication checks are handled server-side. Avoid calling removed API.
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

// Populate quarter dropdown based on selected year and current date
function populateQuarterDropdown() {
    const quarterSelect = document.getElementById("quarter");
    const yearEl = document.getElementById("year");
    if (!quarterSelect || !yearEl) return;

    const yearValue = yearEl.value;
    if (!yearValue) return;

    const selectedYearStart = parseInt(yearValue.split("-")[0], 10);
    if (isNaN(selectedYearStart)) return;

    const currentMonth = parseInt(window.SERVER_MONTH || (new Date()).getMonth() + 1, 10);
    const currentYear = parseInt(window.SERVER_YEAR || (new Date()).getFullYear(), 10);

    // Map month -> fiscal quarter number (Q1: Apr-Jun, Q2: Jul-Sep, Q3: Oct-Dec, Q4: Jan-Mar)
    let currentQuarter;
    if (currentMonth <= 3) currentQuarter = 4;
    else if (currentMonth <= 6) currentQuarter = 1;
    else if (currentMonth <= 9) currentQuarter = 2;
    else currentQuarter = 3;

    quarterSelect.innerHTML = "";

    const quarters = [
        { value: "Q1", label: "Apr-Jun", backendLabel: "30 जून / Jun 30" },
        { value: "Q2", label: "Jul-Sep", backendLabel: "30 सितंबर / Sep 30" },
        { value: "Q3", label: "Oct-Dec", backendLabel: "31 दिसंबर / Dec 31" },
        { value: "Q4", label: "Jan-Mar", backendLabel: "31 मार्च / Mar 31" }
    ];

    // Determine fiscal-year start for server/current and for selected year
    const currentFiscalStart = (currentMonth >= 4) ? currentYear : (currentYear - 1);
    const selectedFiscalStart = selectedYearStart;

    // Always show all quarters (Q1..Q4) regardless of selected year
    let includeIndices = [0, 1, 2, 3];

    includeIndices.forEach(idx => {
        const q = quarters[idx];
        const opt = document.createElement('option');
        opt.value = q.backendLabel;
        opt.textContent = `${q.value} (${q.label})`;
        quarterSelect.appendChild(opt);
    });

    // Preserve server-provided selection when present
    try {
        const serverQuarter = window.QPR_SERVER_QUARTER || '';
        if (serverQuarter) {
            const found = Array.from(quarterSelect.options).some(o => o.value === serverQuarter);
            if (found) quarterSelect.value = serverQuarter;
        }
    } catch (e) { /* ignore */ }
}

// Disable quarter options that already have a report for the selected year
function updateQuarterAvailability() {
    const yearSelect = document.getElementById('year');
    const quarterSelect = document.getElementById('quarter');
    if (!yearSelect || !quarterSelect) return;

    const selectedYear = yearSelect.value;
    // Build a set of quarters used in this selected year (excluding the currently editing record)
    const editingId = document.getElementById('recordId') ? document.getElementById('recordId').value : '';
    const usedQuarters = window.QPR_USED_QUARTERS || [];
    const usedForYear = new Set(usedQuarters.filter(u => (u.year||u.year_string||'') === selectedYear && String(u.record_id || u.recordId || u.id || '') !== String(editingId)).map(u => (u.quarter || '').trim()));

    Array.from(quarterSelect.options).forEach(opt => {
        const txt = opt.textContent.trim();
        if (usedForYear.has(txt)) {
            opt.disabled = true;
            opt.title = 'A report for this quarter already exists';
        } else {
            opt.disabled = false;
            opt.title = '';
        }
    });
}

// --- 2. Load Data (GET) ---
async function loadData() {
    try {
        let data = [];
        // Prefer server-preloaded records when available (template provides PRELOADED_RECORDS)
        if (typeof PRELOADED_RECORDS !== 'undefined') {
            data = Array.isArray(PRELOADED_RECORDS) ? PRELOADED_RECORDS : [];
        } else if (API_URL) {
            const response = await fetch(API_URL);
            data = await response.json();
        } else {
            data = [];
        }

        // Update the global variable so editRecord finds the data
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
                    } else {
                        statusBadge = '<span class="badge bg-success">Submitted</span>';
                    }

                    // Show Edit only when server explicitly allows it for this record
                    if (record.can_edit) {
                        actionButtons = `
                            <button class="btn btn-sm btn-outline-warning fw-bold" onclick="event.stopPropagation(); editRecord(${record.id})">
                                Edit
                            </button>
                        `;
                    } else {
                        // For submitted records that are not editable, offer request-to-edit or show pending
                        if (record.status === 'Submitted' || record.is_submitted) {
                            if (record.has_pending_edit_request) {
                                actionButtons = `
                                    <button class="btn btn-sm btn-outline-secondary fw-bold" disabled>
                                        Pending
                                    </button>
                                `;
                            } else {
                                actionButtons = `
                                    <button class="btn btn-sm btn-outline-primary fw-bold" onclick="event.stopPropagation(); try { requestEdit(${record.id}); } catch(e){ window.location.href='/qpr/reports/${record.id}/request-edit/'; }">
                                        Request to Edit
                                    </button>
                                `;
                            }
                        } else {
                            // Non-submitted and not editable (rare) — show disabled edit
                            actionButtons = `
                                <button class="btn btn-sm btn-outline-secondary fw-bold" disabled>
                                    Edit
                                </button>
                            `;
                        }
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
        const editParams = new URLSearchParams(window.location.search || '');
        const editId = editParams.get('edit_record') || localStorage.getItem('editRecordId');
        const editScopeFromUrl = (editParams.get('edit_scope') || '').toLowerCase();
        if (editScopeFromUrl) localStorage.setItem('editSnapshotScope', editScopeFromUrl);
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
    
    const mainFields = ['officeName', 'officeCode', 'region', 'quarter', 'recordId', 'phone', 'email', 'year'];
    
    const payload = {
        id: id ? id : null,
        status: status,
        officeName: document.getElementById('officeName').value,
        officeCode: document.getElementById('officeCode').value,
        region: document.getElementById('region').value,
        quarter: document.getElementById('quarter').value,
        year: document.getElementById('year').value,
        frequency: document.getElementById('frequency') ? document.getElementById('frequency').value : '',
        selected_date: document.getElementById('selectedDate') ? document.getElementById('selectedDate').value : '',
        // frequency is determined by server; do not send from client
        phone: document.getElementById('phone')?.value || '',
        email: document.getElementById('email')?.value || '',
        details: {} 
    };

    // Safety check: ensure frequency is not empty before submission
    if (!payload.frequency || payload.frequency === '') {
        payload.frequency = 'daily';
        document.getElementById('frequency').value = 'daily';
    }
    unlockQprFillControls();

    console.log("Payload being sent:", payload);

    const form = document.getElementById('qprForm');
    const elements = form.elements; 

    for (let i = 0; i < elements.length; i++) {
        const el = elements[i];
        if (el.id && !mainFields.includes(el.id)) {
            payload.details[el.id] = el.value;
        }
    }

    // If client-side API URL is not present, submit the server-rendered form instead
    if (!API_URL) {
        const form = document.getElementById('qprForm');
        if (!form) { alert('Form element not found.'); return; }

        // ensure hidden details field exists and set its value
        let detailsField = document.getElementById('detailsField') || form.querySelector('input[name="details"]');
        if (!detailsField) {
            detailsField = document.createElement('input');
            detailsField.type = 'hidden';
            detailsField.name = 'details';
            detailsField.id = 'detailsField';
            form.appendChild(detailsField);
        }
        detailsField.value = JSON.stringify(payload.details || {});

        // ensure status field exists and set it
        let statusInput = form.querySelector('input[name="status"]');
        if (!statusInput) {
            statusInput = document.createElement('input');
            statusInput.type = 'hidden';
            statusInput.name = 'status';
            form.appendChild(statusInput);
        }
        statusInput.value = status;

        let frequencyInput = form.querySelector('input[name="frequency"][type="hidden"]');
        if (!frequencyInput) {
            frequencyInput = document.createElement('input');
            frequencyInput.type = 'hidden';
            frequencyInput.name = 'frequency';
            form.appendChild(frequencyInput);
        }
        frequencyInput.value = payload.frequency;

        let selectedDateInput = form.querySelector('input[name="selected_date"][type="hidden"]');
        if (!selectedDateInput) {
            selectedDateInput = document.createElement('input');
            selectedDateInput.type = 'hidden';
            selectedDateInput.name = 'selected_date';
            form.appendChild(selectedDateInput);
        }
        selectedDateInput.value = payload.selected_date;

        form.submit();
        return;
    }

    try {
        const res = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        console.log("Response status:", res.status, "ok:", res.ok);
        
        if (res.ok) {
            alert(status === 'Draft' ? "Draft Saved Successfully!" : "Report Submitted Successfully!");
            
            console.log("Alert shown. Status is:", status);
            
            // If submitted, redirect to report list; if draft, reload form
            if (status === 'Submitted') {
                console.log("Redirecting to /qpr/reports/");
                window.location.href = "/qpr/reports/";
            } else {
                console.log("Not submitted, reloading form");
                clearForm();
                loadData();
            }
        } else {
            const errorData = await res.json().catch(() => ({}));
            console.error("Response error:", errorData);
            alert("Server Error: " + (errorData.error || res.statusText));
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
    
    if (!record) {
        console.error("Record not found for ID:", id);
        return;
    }

    const editParams = new URLSearchParams(window.location.search || '');
    const requestedSnapshotScope = (
        editParams.get('edit_scope') ||
        localStorage.getItem('editSnapshotScope') ||
        record.edit_approved_scope ||
        ''
    ).toLowerCase();
    const scopedEditRequested = ['weekly', 'monthly', 'quarterly'].includes(requestedSnapshotScope);
    const snapshotEdit = (record.snapshot_edit && record.snapshot_edit.scope === requestedSnapshotScope) ? record.snapshot_edit : null;
    const editFrequency = snapshotEdit ? snapshotEdit.scope : (scopedEditRequested ? requestedSnapshotScope : (record.frequency || 'daily'));
    const canUseCurrentApproval = !(record.edit_approved_scope) || !!snapshotEdit || scopedEditRequested;
    const canEditCurrentRecord = !!record.can_edit || (!!record.snapshot_can_edit && (!!snapshotEdit || scopedEditRequested)) || scopedEditRequested;
    if (record.edit_approved_scope && record.edit_approved_scope !== requestedSnapshotScope && !snapshotEdit) {
        alert('This approval is only for the ' + record.edit_approved_scope + ' cumulative QPR. Please open the matching ' + record.edit_approved_scope + ' row from the report list.');
        window.location.href = '/qpr/reports/';
        return;
    }

    // Fill Main Fields - Apply masking to all records
    document.getElementById('recordId').value = record.id;
    const officeNameEl = document.getElementById('officeName');
    if (officeNameEl && String(officeNameEl.dataset.protected) !== '1') officeNameEl.value = record.officeName || '';
    // Do not mask office code — show the full code so it is saved unchanged
    const officeCodeEl = document.getElementById('officeCode');
    if (officeCodeEl && String(officeCodeEl.dataset.protected) !== '1') officeCodeEl.value = record.officeCode || '';
    const regionEl = document.getElementById('region');
    if (regionEl && String(regionEl.dataset.protected) !== '1') regionEl.value = record.region || '';
    const quarterEl = document.getElementById('quarter');
    if (quarterEl) quarterEl.value = record.quarter || '';
    const yearEl = document.getElementById('year');
    if (yearEl && record.year) yearEl.value = record.year;
    const selectedDateEl = document.getElementById('selectedDate');
    if (selectedDateEl) {
        const editPeriodStart = snapshotEdit ? snapshotEdit.period_start : record.period_start;
        if (editPeriodStart) selectedDateEl.value = String(editPeriodStart).slice(0, 10);
        if (scopedEditRequested) {
            selectedDateEl.removeAttribute('min');
            selectedDateEl.removeAttribute('max');
            selectedDateEl.setCustomValidity('');
        }
    }
    const snapshotScopeEl = document.getElementById('snapshotEditScope');
    if (snapshotScopeEl) snapshotScopeEl.value = snapshotEdit ? snapshotEdit.scope : (scopedEditRequested ? requestedSnapshotScope : '');
    
    // Handle phone field if it exists in details
    const phoneEl = document.getElementById('phone');
    if (phoneEl && String(phoneEl.dataset.protected) !== '1') {
        phoneEl.value = record.phone || '';
    }
    
    // Handle email field if it exists in details
    const emailEl = document.getElementById('email');
    if (emailEl && String(emailEl.dataset.protected) !== '1') {
        emailEl.value = record.email || '';
    }
    // Edit mode must use the record's original entry type, not today's default.
    const freqEl = document.getElementById('frequency');
    if (freqEl) {
        if (scopedEditRequested) {
            Array.from(freqEl.options).forEach(opt => {
                if (opt.value === requestedSnapshotScope) opt.disabled = false;
            });
        }
        freqEl.value = editFrequency;
        freqEl.dispatchEvent(new Event('change'));
        if (scopedEditRequested) {
            Array.from(freqEl.options).forEach(opt => {
                if (opt.value === requestedSnapshotScope) opt.disabled = false;
            });
            freqEl.value = editFrequency;
        }
    }

    // Fill Details after frequency handlers run so scoped snapshot values win.
    const cumulativeDetails = (scopedEditRequested && record.cumulative && record.cumulative[requestedSnapshotScope])
        ? record.cumulative[requestedSnapshotScope]
        : null;
    const detailSource = snapshotEdit ? snapshotEdit.details : (cumulativeDetails || record.details);
    if (detailSource) {
        for (const [key, value] of Object.entries(detailSource)) {
            const el = document.getElementById(key);
            if (el) {
                el.value = value;
            }
        }
    }
    localStorage.removeItem('editSnapshotScope');
    
    // Disable/Enable form based on edit permission
    setFormEditability(canEditCurrentRecord && canUseCurrentApproval, (record.edit_approved || scopedEditRequested) && canUseCurrentApproval);

    showTab(1);
}

// Helper function to disable/enable form fields based on edit permission
function setFormEditability(canEdit, editApproved) {
    const form = document.getElementById('qprForm');
    const allInputs = form.querySelectorAll('input, textarea, select');
    
    // Get all save buttons (both Draft and Submit buttons)
    const saveBtns = document.querySelectorAll('button[onclick*="saveData"]');
    
    if (canEdit) {
        // Enable fields except those protected by profile data
        allInputs.forEach(input => {
            const isProtected = String(input.dataset.protected) === '1';
            if (!isProtected) input.disabled = false;
        });
        saveBtns.forEach(btn => btn.disabled = false);

        if (editApproved) {
            showEditApprovedMessage();
        }
    } else {
        // Disable all fields (read-only mode)
        allInputs.forEach(input => { input.disabled = true; });
        saveBtns.forEach(btn => btn.disabled = true);
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
        // Submit server-side delete POST form to the configured endpoint.
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/qpr/records/delete/${id}/`;

        // Attach CSRF token from cookie if available
        const csrf = getCookie('csrftoken');
        if (csrf) {
            const inpt = document.createElement('input');
            inpt.type = 'hidden'; inpt.name = 'csrfmiddlewaretoken'; inpt.value = csrf;
            form.appendChild(inpt);
        }

        document.body.appendChild(form);
        form.submit();
    } catch (error) {
        console.error("Error deleting:", error);
        alert("Failed to delete.");
    }
}

// Utility: read cookie value (used for CSRF token)
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
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

// -----------------------
// Live totals & constraints
// -----------------------
function isEditingMode() {
    try {
        var rid = document.getElementById('recordId');
        return !!(rid && String(rid.value || '').trim());
    } catch (e) { return false; }
}

function toIntSafe(v) {
    var n = parseInt(String(v || '').replace(/[^0-9]/g, ''), 10);
    return isNaN(n) ? 0 : n;
}

function updateSection6Totals() {
    if (isEditingMode()) return; // do not auto-update totals when editing existing record
    ['a','b','c'].forEach(function(region){
        try {
            var h = document.getElementById('s6_' + region + '_hindi');
            var e = document.getElementById('s6_' + region + '_eng');
            var t = document.getElementById('s6_' + region + '_total');
            if (!t) return;
            var sum = toIntSafe(h && h.value) + toIntSafe(e && e.value);
            t.value = String(sum);
        } catch(err) { /* ignore individual region errors */ }
    });
}

function enforceSection1Constraint() {
    try {
        var totalEl = document.getElementById('s1_total');
        var hindiEl = document.getElementById('s1_hindi');
        if (!totalEl || !hindiEl) return;
        var total = toIntSafe(totalEl.value);
        if (!isEditingMode()) {
            // set max and clamp
            try { hindiEl.max = String(total); } catch(e) {}
            if (toIntSafe(hindiEl.value) > total) hindiEl.value = String(total);
        } else {
            // when editing, don't interfere with values
            try { hindiEl.removeAttribute('max'); } catch(e) {}
        }
    } catch(e) {}
}

function attachLiveTotalsListeners() {
    // Attach listeners for section 6 totals and section 1 constraint
    var fields = [];
    ['a','b','c'].forEach(function(region){
        var h = document.getElementById('s6_' + region + '_hindi');
        var e = document.getElementById('s6_' + region + '_eng');
        if (h) { h.addEventListener('input', updateSection6Totals); fields.push(h); }
        if (e) { e.addEventListener('input', updateSection6Totals); fields.push(e); }
    });

    var s1Total = document.getElementById('s1_total');
    var s1Hindi = document.getElementById('s1_hindi');
    if (s1Total) s1Total.addEventListener('input', enforceSection1Constraint);
    if (s1Hindi) {
        s1Hindi.addEventListener('input', function(){
            if (isEditingMode()) return; // do not clamp on edit
            var tot = toIntSafe(document.getElementById('s1_total')?.value);
            if (toIntSafe(s1Hindi.value) > tot) s1Hindi.value = String(tot);
        });
    }

    // Run once to initialize totals/constraints on fresh form load
    try { updateSection6Totals(); } catch(e) {}
    try { enforceSection1Constraint(); } catch(e) {}
}
