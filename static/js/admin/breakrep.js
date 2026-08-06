document.addEventListener('DOMContentLoaded', function() {
    let currentPage = 1;
    let entriesPerPage = 10;
    let filteredData = [];
    let sortColumn = '';
    let sortDirection = 'asc';
    let currentSummaryType = null;
    let currentSummaryDetails = null;

    // Initialize components
    const searchField = document.querySelector('.break-search-field');
    const clearSearch = document.querySelector('.break-clear-search');
    const entriesDropdown = document.querySelector('.break-entries-dropdown');
    const dateFilter = document.getElementById('breakReportDate');
    const tbody = document.querySelector('.break-table tbody');

    // Set default date to today
    const today = new Date().toISOString().split('T')[0];
    if (dateFilter) {
        dateFilter.value = today;
    }

    // --- Mini Card Details Data ---
    let breakSummaryDetailsData = {
        idle: [],
        working: [],
        break: [],
        loggedIn: [], // Users currently logged in today (not logged out)
        loggedOut: [] // Users who have logged out today
    };

    // Function to fetch break reports
    window.fetchBreakReports = function() {
        const selectedDate = dateFilter.value;
        if (!selectedDate) {
            console.error("Date filter is not available or has no value.");
            return;
        }

                return fetch('/api/v1/reports/run/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
            },
            body: JSON.stringify({
                report_key: 'breaks',
                date_from: selectedDate,
                date_to: selectedDate
            })
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(res => {
                const data = res.data || res;
                filteredData = data;
                updateTable();
                return data; // Return the data for chaining
            })
            .catch(error => {
                console.error('Error fetching break reports:', error);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="12" class="break-error-message">Error loading data. Please try again.</td></tr>`;
                }
                throw error; // Re-throw for other handlers
            });
    };

    // Add auto-refresh timer
    let autoRefreshTimer;
    
    function startAutoRefresh() {
        if (autoRefreshTimer) {
            clearInterval(autoRefreshTimer);
        }
        autoRefreshTimer = setInterval(() => {
            // Only auto-refresh if viewing today's date
            const todayStr = new Date().toISOString().split('T')[0];
            if (dateFilter.value === todayStr) {
                fetchBreakReports().catch(error => {
                    console.error('Auto-refresh error:', error);
                });
            }
        }, 60000); // 1 minute
    }

    // Add refresh button click handler
    document.querySelector('.break-refresh-button').addEventListener('click', function() {
        const button = this;
        const icon = button.querySelector('i');
        
        button.classList.add('loading');
        button.disabled = true;
        icon.classList.add('fa-spin');
        
        fetchBreakReports()
            .finally(() => {
                button.classList.remove('loading');
                button.disabled = false;
                icon.classList.remove('fa-spin');
            });
        
        startAutoRefresh();
    });

    // Update headerMap to include new fields
        const headerMap = {
        'emp_id': 'Emp ID',
        'name': 'Emp Name',
        'break_type': 'Break Type',
        'count': 'Times Taken',
        'total_minutes': 'Total Minutes',
        'allotted_minutes': 'Allowed Minutes',
        'overruns': 'Overruns'
    };

    // Update the status formatting function
    function formatDuration(status) {
        const match = status.match(/\(([^)]+)\)/);
        if (!match) return status;

        const durationPart = match[1];
        const mainStatus = status.split('(')[0].trim();
        
        let icon, statusColor;
        switch (mainStatus.toLowerCase()) {
            case 'working':
                icon = '💻';
                statusColor = '#28a745';
                break;
            case 'idle':
                icon = '⏸️';
                statusColor = '#ffc107';
                break;
            case 'on break':
                icon = '☕';
                statusColor = '#17a2b8';
                break;
            case 'logged out':
                icon = '🚪';
                statusColor = '#dc3545';
                break;
            default:
                icon = '❓';
                statusColor = '#6c757d';
        }

        return mainStatus; // Return only the status text initially
    }

    function updateTable() {
        if (!tbody) return;

        const searchTerm = searchField ? searchField.value.toLowerCase() : '';
        let filtered = filteredData;

        // Apply search filter
        if (searchTerm) {
            filtered = filtered.filter(report => {
                // Include projects string in search explicitly
                const values = Object.values(report).concat([report.projects || '']);
                return values.some(value => String(value).toLowerCase().includes(searchTerm));
            });
        }

        // Apply sorting
        if (sortColumn) {
            filtered.sort((a, b) => {
                let valueA = a[sortColumn] || '';
                let valueB = b[sortColumn] || '';
                return sortDirection === 'asc' ? 
                    String(valueA).localeCompare(String(valueB)) : 
                    String(valueB).localeCompare(String(valueA));
            });
        }

        // Calculate pagination
        const startIndex = (currentPage - 1) * entriesPerPage;
        const endIndex = startIndex + entriesPerPage;
        const paginatedData = filtered.slice(startIndex, endIndex);

        // Update table body with all columns
        tbody.innerHTML = paginatedData.length ? 
            paginatedData.map(report => {
                // Get current idle time for tooltip if status is idle
                let currentIdleTime = '';
                if (report.current_status?.toLowerCase().startsWith('idle')) {
                    currentIdleTime = report.current_status.match(/\(([^)]+)\)/)?.[1] || '';
                }

                                return `
                    <tr>
                        <td>${report.emp_id || ''}</td>
                        <td>${report.name || ''}</td>
                        <td>${report.break_type || ''}</td>
                        <td>${report.count || 0}</td>
                        <td>${report.total_minutes || 0}</td>
                        <td>${report.allotted_minutes || 0}</td>
                        <td>${report.overruns || 0}</td>
                    </tr>
                `;
            }).join('') :
            '<tr><td colspan="7" class="break-no-data">No data available</td></tr>';

        // Add click handler for status cells
        document.querySelectorAll('.break-status-cell').forEach(cell => {
            cell.addEventListener('click', (e) => {
                // Remove any existing tooltips
                document.querySelectorAll('.status-tooltip').forEach(tooltip => tooltip.remove());
                
                const status = cell.dataset.status;
                if (!status) return;

                const mainStatus = status.split('(')[0].trim();
                let durationText = '';

                // For idle status, use current idle time instead of total
                if (mainStatus.toLowerCase() === 'idle') {
                    const currentIdleTime = cell.dataset.currentIdle;
                    durationText = currentIdleTime ? `Current Idle: ${currentIdleTime}` : '';
                } else {
                    const match = status.match(/\(([^)]+)\)/);
                    durationText = match ? match[1] : '';
                }
                
                let icon, statusColor;
                switch (mainStatus.toLowerCase()) {
                    case 'working':
                        icon = '💻';
                        statusColor = '#28a745';
                        break;
                    case 'idle':
                        icon = '⏸️';
                        statusColor = '#ffc107';
                        break;
                    case 'on break':
                        icon = '☕';
                        statusColor = '#17a2b8';
                        break;
                    case 'logged out':
                        icon = '🚪';
                        statusColor = '#dc3545';
                        break;
                    default:
                        icon = '❓';
                        statusColor = '#6c757d';
                }

                // Create tooltip with current idle time for idle status
                const tooltip = document.createElement('div');
                tooltip.className = 'status-tooltip';
                tooltip.style.cssText = `
                    position: fixed;
                    z-index: 1000;
                    padding: 10px 15px;
                    background: #1a1a1a;
                    color: white;
                    border-radius: 6px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
                    font-family: Arial, sans-serif;
                    min-width: 150px;
                    animation: tooltipFadeIn 0.2s ease-out;
                `;
                tooltip.innerHTML = `
                    <div style="
                        font-weight: bold;
                        margin-bottom: 6px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        font-size: 14px;
                        color: ${statusColor};
                    ">
                        <span>${icon}</span>
                        <span>${mainStatus}</span>
                    </div>
                    ${durationText ? `
                        <div style="
                            color: #cccccc;
                            font-size: 13px;
                            display: flex;
                            align-items: center;
                            gap: 4px;
                        ">
                            <span>⏱️</span>
                            <span>${durationText}</span>
                        </div>
                    ` : ''}
                    <div class="tooltip-arrow"></div>
                `;

                // Position the tooltip
                const cellRect = cell.getBoundingClientRect();
                const tooltipWidth = 200; // Approximate width of tooltip

                // Calculate position
                let left = cellRect.right + 10;
                let top = cellRect.top + (cellRect.height / 2);

                // Adjust if tooltip would go off screen
                if (left + tooltipWidth > window.innerWidth) {
                    left = cellRect.left - tooltipWidth - 10;
                    tooltip.querySelector('.tooltip-arrow').style.cssText = `
                        left: auto;
                        right: -6px;
                        border-right: none;
                        border-left: 6px solid #1a1a1a;
                    `;
                }

                // Apply position
                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
                tooltip.style.transform = 'translateY(-50%)';

                // Add to document
                cell.appendChild(tooltip);

                // Close tooltip when clicking outside
                document.addEventListener('click', function(e) {
                    if (!e.target.closest('.status-tooltip, .break-status-cell')) {
                        tooltip.remove();
                    }
                });
            });
        });

        // Update pagination info
        updatePaginationInfo(filtered.length);
    }

    function updatePaginationInfo(totalItems) {
        const startEntry = document.getElementById('breakStartEntry');
        const endEntry = document.getElementById('breakEndEntry');
        const totalEntries = document.getElementById('breakTotalEntries');
        const currentPageSpan = document.getElementById('breakCurrentPage');

        if (startEntry && endEntry && totalEntries && currentPageSpan) {
            const start = totalItems === 0 ? 0 : (currentPage - 1) * entriesPerPage + 1;
            const end = Math.min(start + entriesPerPage - 1, totalItems);
            
            startEntry.textContent = start;
            endEntry.textContent = end;
            totalEntries.textContent = totalItems;
            currentPageSpan.textContent = currentPage;
        }
    }

    // Event Listeners
    if (searchField) {
        searchField.addEventListener('input', function() {
            currentPage = 1;
            if (clearSearch) {
                clearSearch.style.display = this.value ? 'block' : 'none';
            }
            updateTable();
        });
    }

    if (clearSearch) {
        clearSearch.addEventListener('click', function() {
            if (searchField) {
                searchField.value = '';
                this.style.display = 'none';
                updateTable();
            }
        });
    }

    if (entriesDropdown) {
        entriesDropdown.addEventListener('change', function() {
            entriesPerPage = parseInt(this.value);
            currentPage = 1;
            updateTable();
        });
    }

    if (dateFilter) {
        // Set default date to today and add change listener
        dateFilter.value = new Date().toISOString().split('T')[0];
        dateFilter.addEventListener('change', () => {
            fetchBreakReports();
            startAutoRefresh(); // Restart timer logic on date change
        });
    }

    // Pagination event listeners
    document.getElementById('breakPrevPage')?.addEventListener('click', function() {
        if (currentPage > 1) {
            currentPage--;
            updateTable();
        }
    });

    document.getElementById('breakNextPage')?.addEventListener('click', function() {
        const maxPage = Math.ceil(filteredData.length / entriesPerPage);
        if (currentPage < maxPage) {
            currentPage++;
            updateTable();
        }
    });

    // Add sorting functionality
    document.querySelectorAll('.break-sortable').forEach(header => {
        header.addEventListener('click', function() {
            const column = this.textContent.trim().toLowerCase().replace(/ /g, '_');
            if (sortColumn === column) {
                sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                sortColumn = column;
                sortDirection = 'asc';
            }
            updateTable();
        });
    });

    // Column resize functionality for break-table (with persistence)
    function makeBreakTableHeadersResizable() {
        const table = document.querySelector('.break-table');
        if (!table) return;
        const headers = table.querySelectorAll('th');

        // Utilities: load/apply/save widths to localStorage
        const STORAGE_KEY = 'breakTableColWidths';
        const loadWidths = () => {
            try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch (_) { return []; }
        };
        const applyWidths = (widths) => {
            if (!Array.isArray(widths) || !widths.length) return;
            headers.forEach((th, idx) => {
                const w = widths[idx];
                if (!w) return;
                th.style.width = w + 'px';
                th.style.minWidth = w + 'px';
                th.style.maxWidth = w + 'px';
                table.querySelectorAll(`tr td:nth-child(${idx + 1})`).forEach(td => {
                    td.style.width = w + 'px';
                    td.style.minWidth = w + 'px';
                    td.style.maxWidth = w + 'px';
                });
            });
        };
        const saveWidths = () => {
            const widths = Array.from(headers).map(th => th.offsetWidth);
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(widths)); } catch (_) {}
        };

        // Apply saved widths once at start
        applyWidths(loadWidths());

        headers.forEach((th, index) => {
            // Add resizer handle
            const resizer = document.createElement('div');
            resizer.className = 'break-col-resizer';
            th.appendChild(resizer);

            let startX = 0;
            let startWidth = 0;

            const onMouseMove = (e) => {
                const dx = e.clientX - startX;
                const newWidth = Math.max(80, startWidth + dx); // minimum width slightly larger to avoid overlap
                th.style.width = newWidth + 'px';
                th.style.minWidth = newWidth + 'px';
                th.style.maxWidth = newWidth + 'px';
                // Apply width to all cells in this column
                table.querySelectorAll(`tr td:nth-child(${index + 1})`).forEach(td => {
                    td.style.width = newWidth + 'px';
                    td.style.minWidth = newWidth + 'px';
                    td.style.maxWidth = newWidth + 'px';
                    td.style.overflow = 'hidden';
                    td.style.textOverflow = 'ellipsis';
                    td.style.whiteSpace = 'nowrap';
                });
            };

            const onMouseUp = () => {
                document.body.classList.remove('break-resizing');
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                saveWidths();
            };

            resizer.addEventListener('mousedown', (e) => {
                e.preventDefault();
                startX = e.clientX;
                startWidth = th.offsetWidth;
                document.body.classList.add('break-resizing');
                document.addEventListener('mousemove', onMouseMove);
                document.addEventListener('mouseup', onMouseUp);
            });
        });
    }

    // Initialize resizers after first render
    makeBreakTableHeadersResizable();

    // Export logic
    function exportToCSV(rows) {
        const headers = ['Emp ID','Emp Name','Location','Project','Login Time','Logout Time','Current Status','Working Time','Total Idle Time','Break 1','Break 2','Meal Break','Total Break Time'];
        const csvRows = [headers.join(',')];
        rows.forEach(r => {
            const values = [
                r.emp_id || '', r.name || '', r.location || '', r.projects || '', r.login_time || '', r.logout_time || '',
                (r.current_status || '').split('\n').join(' '), r.actual_working_time || '00:00:00', r.total_idle_time || '00:00:00',
                r.break_1 || '00:00:00', r.break_2 || '00:00:00', r.meal_break || '00:00:00', r.total_break_time || '00:00:00'
            ];
            const escaped = values.map(v => {
                const s = String(v).replace(/"/g, '""');
                return /[",\n]/.test(s) ? `"${s}"` : s;
            });
            csvRows.push(escaped.join(','));
        });
        const BOM = '\uFEFF';
        const dateStr = (document.getElementById('breakReportDate')?.value || new Date().toISOString().split('T')[0]);
        const blob = new Blob([BOM + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `break_reports_${dateStr}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    function exportToExcel(rows) {
        if (!window.XLSX) {
            console.error('XLSX library not loaded');
            exportToCSV(rows);
            return;
        }
        const headers = ['Emp ID','Emp Name','Location','Project','Login Time','Logout Time','Current Status','Working Time','Total Idle Time','Break 1','Break 2','Meal Break','Total Break Time'];
        const data = [headers].concat(rows.map(r => [
            r.emp_id || '', r.name || '', r.location || '', r.projects || '', r.login_time || '', r.logout_time || '',
            (r.current_status || '').split('\n').join(' '), r.actual_working_time || '00:00:00', r.total_idle_time || '00:00:00',
            r.break_1 || '00:00:00', r.break_2 || '00:00:00', r.meal_break || '00:00:00', r.total_break_time || '00:00:00'
        ]));

        const wb = XLSX.utils.book_new();
        const ws = XLSX.utils.aoa_to_sheet(data);
        ws['!cols'] = [
            { wch: 10 },
            { wch: 20 },
            { wch: 14 },
            { wch: 30 },
            { wch: 12 },
            { wch: 12 },
            { wch: 18 },
            { wch: 12 },
            { wch: 14 },
            { wch: 10 },
            { wch: 10 },
            { wch: 12 },
            { wch: 16 }
        ];
        XLSX.utils.book_append_sheet(wb, ws, 'Break Reports');
        const dateStr = (document.getElementById('breakReportDate')?.value || new Date().toISOString().split('T')[0]);
        XLSX.writeFile(wb, `break_reports_${dateStr}.xlsx`, { bookType: 'xlsx' });
    }

    function getCurrentlyFilteredRows() {
        // Reapply same filtering and sorting used in updateTable to get the filtered array
        const searchTerm = searchField ? searchField.value.toLowerCase() : '';
        let filtered = filteredData;
        if (searchTerm) {
            filtered = filtered.filter(report => 
                Object.values(report).some(value => 
                    String(value).toLowerCase().includes(searchTerm)
                )
            );
        }
        if (sortColumn) {
            filtered.sort((a, b) => {
                let valueA = a[sortColumn] || '';
                let valueB = b[sortColumn] || '';
                return sortDirection === 'asc' ? 
                    String(valueA).localeCompare(String(valueB)) : 
                    String(valueB).localeCompare(String(valueA));
            });
        }
        return filtered;
    }

    const exportButton = document.querySelector('.break-export-button');
    const exportFormat = document.querySelector('.break-export-format');
    if (exportButton && exportFormat) {
        exportButton.addEventListener('click', () => {
            const rows = getCurrentlyFilteredRows();
            const fmt = exportFormat.value;
            if (fmt === 'csv') exportToCSV(rows);
            else exportToExcel(rows);
        });
    }

    // Dynamically render summary cards as an inline grid
    function renderSummaryCards({idleCount, workingCount, breakCount, loggedInCount, loggedOutCount}) {
        const cardData = [
            {
                id: 'idle',
                icon: 'fa-pause-circle',
                label: 'Idle Employees',
                count: idleCount,
                cardId: 'idleEmployeesMiniCard',
                color: '#ffc107'
            },
            {
                id: 'working',
                icon: 'fa-laptop-code',
                label: 'Working Employees',
                count: workingCount,
                cardId: 'workingEmployeesMiniCard',
                color: '#28a745'
            },
            {
                id: 'break',
                icon: 'fa-coffee',
                label: 'On Break',
                count: breakCount,
                cardId: 'breakEmployeesMiniCard',
                color: '#17a2b8'
            },
            {
                id: 'loggedIn',
                icon: 'fa-sign-in-alt',
                label: 'Logged In Today',
                count: loggedInCount,
                cardId: 'loggedInEmployeesMiniCard',
                color: '#6c757d'
            },
            {
                id: 'loggedOut',
                icon: 'fa-sign-out-alt',
                label: 'Logged Out Today',
                count: loggedOutCount,
                cardId: 'loggedOutEmployeesMiniCard',
                color: '#dc3545'
            }
        ];
        const group = document.querySelector('.break-summary-card-group');
        if (!group) return;
        group.innerHTML = cardData.map(card => `
            <div class="mini-summary-card" id="${card.cardId}" style="border-top: 3px solid ${card.color};">
                <div class="mini-label" style="margin-bottom: 4px;">${card.label}</div>
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 80%;">
                    <div class="mini-card-header" style="color: ${card.color}; font-size: 1.3rem;"><i class="fas ${card.icon}"></i></div>
                    <div class="mini-count" style="font-size: 1.3rem; font-weight: 700; color: ${card.color};">${card.count}</div>
                </div>
            </div>
        `).join('');
        // Add click handlers for modal details
        document.getElementById('idleEmployeesMiniCard').onclick = function() { showDetailsModal('idle', breakSummaryDetailsData.idle); };
        document.getElementById('workingEmployeesMiniCard').onclick = function() { showDetailsModal('working', breakSummaryDetailsData.working); };
        document.getElementById('breakEmployeesMiniCard').onclick = function() { showDetailsModal('break', breakSummaryDetailsData.break); };
        document.getElementById('loggedInEmployeesMiniCard').onclick = function() { showDetailsModal('loggedIn', breakSummaryDetailsData.loggedIn); };
        document.getElementById('loggedOutEmployeesMiniCard').onclick = function() { showDetailsModal('loggedOut', breakSummaryDetailsData.loggedOut); };
    }

    function updateSummaryCards(data) {
        let idleCount = 0, workingCount = 0, breakCount = 0, loggedInCount = 0, loggedOutCount = 0;
        let idleDetails = [], workingDetails = [], breakDetails = [], loggedInDetails = [], loggedOutDetails = [];
        let loggedInEmpIds = new Set(), loggedOutEmpIds = new Set();

        data.forEach(employee => {
            const status = (employee.current_status || '').toLowerCase();
            if (status === 'idle' || status === 'ideal') {
                idleCount++;
                idleDetails.push({
                    name: employee.name,
                    time: employee.total_idle_time
                });
            } else if (status.includes('working')) {
                workingCount++;
                workingDetails.push({
                    name: employee.name,
                    time: employee.actual_working_time
                });
            } else if (status.includes('on break')) {
                breakCount++;
                // Extract break type from current_status, e.g. "On Break (Tea break 1 - 5 min)"
                let breakType = '';
                const match = employee.current_status && employee.current_status.match(/On Break \(([^-]+)-/i);
                breakType = match ? match[1].trim() : '';
                breakDetails.push({
                    name: employee.name,
                    breakType: breakType,
                    time: employee.total_break_time
                });
            }
            // Determine logged in/out status
            if (employee.login_time) {
                // If logout_time is present, user has logged out today
                if (employee.logout_time && employee.logout_time !== '00:00:00') {
                    loggedOutCount++;
                    loggedOutDetails.push({
                        name: employee.name,
                        login: employee.login_time,
                        logout: employee.logout_time
                    });
                    loggedOutEmpIds.add(employee.emp_id);
                } else {
                    // User is currently logged in (no logout_time)
                    loggedInCount++;
                    loggedInDetails.push({
                        name: employee.name,
                        login: employee.login_time,
                        logout: employee.logout_time || 'Ongoing'
                    });
                    loggedInEmpIds.add(employee.emp_id);
                }
            }
        });
        renderSummaryCards({idleCount, workingCount, breakCount, loggedInCount, loggedOutCount});
        // Store details for modal
        breakSummaryDetailsData.idle = idleDetails;
        breakSummaryDetailsData.working = workingDetails;
        breakSummaryDetailsData.break = breakDetails;
        breakSummaryDetailsData.loggedIn = loggedInDetails;
        breakSummaryDetailsData.loggedOut = loggedOutDetails;
    }

    // --- Modal Logic ---
    const modal = document.getElementById('breakSummaryDetailsModal');
    const modalTitle = document.getElementById('breakSummaryDetailsTitle');
    const modalTableContainer = document.getElementById('breakSummaryDetailsTableContainer');
    const closeModalBtn = document.querySelector('.close-details-modal');

    function showDetailsModal(type, details) {
        currentSummaryType = type;
        currentSummaryDetails = details;
        let title = '', tableHtml = '';
        if (type === 'idle') {
            title = 'Idle Employees';
            tableHtml = `<table class="break-summary-details-table"><thead><tr><th>Name</th><th>Total Idle Time</th></tr></thead><tbody>` +
                details.map(d => `<tr><td>${d.name}</td><td>${d.time}</td></tr>`).join('') +
                '</tbody></table>';
        } else if (type === 'working') {
            title = 'Working Employees';
            tableHtml = `<table class="break-summary-details-table"><thead><tr><th>Name</th><th>Working Time</th></tr></thead><tbody>` +
                details.map(d => `<tr><td>${d.name}</td><td>${d.time}</td></tr>`).join('') +
                '</tbody></table>';
        } else if (type === 'break') {
            title = 'Employees On Break';
            tableHtml = `<table class="break-summary-details-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Break Type</th>
                        <th>Break Time</th>
                    </tr>
                </thead>
                <tbody>` +
                details.map(d => `<tr>
                    <td>${d.name}</td>
                    <td>${d.breakType || '-'}</td>
                    <td>${d.time}</td>
                </tr>`).join('') +
                '</tbody></table>';
        } else if (type === 'loggedIn') {
            title = "Today's Logged In Employees (Currently Logged In)";
            tableHtml = `<table class="break-summary-details-table"><thead><tr><th>Name</th><th>Login Time</th><th>Logout Time</th></tr></thead><tbody>` +
                details.map(d => `<tr><td>${d.name}</td><td>${d.login}</td><td>${d.logout}</td></tr>`).join('') +
                '</tbody></table>';
        } else if (type === 'loggedOut') {
            title = "Today's Logged Out Employees";
            tableHtml = `<table class="break-summary-details-table"><thead><tr><th>Name</th><th>Login Time</th><th>Logout Time</th></tr></thead><tbody>` +
                details.map(d => `<tr><td>${d.name}</td><td>${d.login}</td><td>${d.logout}</td></tr>`).join('') +
                '</tbody></table>';
        }
        modalTitle.textContent = title;
        modalTableContainer.innerHTML = tableHtml;
        modal.classList.add('active');
        document.querySelector('.refresh-details-modal').onclick = function() {
            refreshSummaryDetails();
        };
    }
    function closeDetailsModal() {
        modal.classList.remove('active');
    }
    closeModalBtn.addEventListener('click', closeDetailsModal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeDetailsModal();
    });

    // Initial fetch for today's data
    fetchBreakReports();
    startAutoRefresh();


    function refreshSummaryDetails() {
        if (currentSummaryType) {
            const refreshButton = document.querySelector('.refresh-details-modal');
            const refreshIcon = refreshButton.querySelector('i');
            
            // Add loading animation and disable button
            refreshIcon.classList.add('fa-spin');
            refreshButton.style.pointerEvents = 'none';
            
            fetchBreakReports()
                .then(() => {
                    let details = breakSummaryDetailsData[currentSummaryType];
                    showDetailsModal(currentSummaryType, details);
                })
                .catch(error => {
                    console.error('Error refreshing details:', error);
                })
                .finally(() => {
                    // Remove loading animation and re-enable button
                    refreshIcon.classList.remove('fa-spin');
                    refreshButton.style.pointerEvents = 'auto';
                });
        }
    }

    function extractBreakType(status) {
        if (!status.startsWith('On Break')) return '';
        const match = status.match(/On Break \(([^-]+)-/);
        return match ? match[1].trim() : '';
    }
});

    function toggleBreakReport(event) {
        event.preventDefault(); // Prevent the default link behavior
        const breakReportTable = document.getElementById('breakReportTable');

        // Toggle visibility of the table
        if (breakReportTable.style.display === 'none' || breakReportTable.style.display === '') {
            breakReportTable.style.display = 'block'; // Show the table
        } else {
            breakReportTable.style.display = 'none'; // Hide the table
        }
    }