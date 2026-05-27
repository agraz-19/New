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
