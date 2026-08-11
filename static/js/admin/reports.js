$(document).ready(function () {
    // Initialize summary table
    const summaryTable = $('#summaryTable').DataTable({
        dom: 't',
        ordering: false,
        columns: [
            { data: 'project_id', title: 'Project ID' },
            { data: 'project_name', title: 'Project Name' },
            { data: 'active_users', title: 'Active Users' },
            { data: 'completed_tasks', title: 'Completed Tasks' },
            { data: 'completed_work_units', title: 'Completed Work Units' },
            { data: 'avg_processtime_perunit', title: 'Avg Process Time/Unit' },
            { data: 'inprogress_tasks', title: 'In Progress Tasks' },
            { data: 'onhold_tasks', title: 'On Hold Tasks' }
        ]
    });

    // Load summary data by default
    fetchSummaryData();

    // Toggle button click handlers
    $('.summary-btn').click(function() {
        $(this).addClass('active');
        $('.report-btn').removeClass('active');
        $('.graphs-btn').removeClass('active');
        $('#summaryTableSection').show();
        $('#reportsSection').hide();
        fetchSummaryData();
    });

    $('.report-btn').click(function() {
        $(this).addClass('active');
        $('.summary-btn').removeClass('active');
        $('.graphs-btn').removeClass('active');
        $('#summaryTableSection').hide();
        $('#reportsSection').show();
        // Refresh reports data
        const startDate = $('#startDate').val();
        const endDate = $('#endDate').val();
        if (startDate && endDate) {
            fetchData(startDate, endDate);
        }
    });

    $('.graphs-btn').click(function() {
        $(this).addClass('active');
        $('.summary-btn').removeClass('active');
        $('.report-btn').removeClass('active');
        $('#summaryTableSection').hide();
        $('#reportsSection').hide();

        // Trigger the summary reports content display
        const summaryReportsLink = document.querySelector('a[href="#summaryreports"]');
        if (summaryReportsLink) {
            showContent('summaryreports');
        }
        
        // Initialize summary dashboard if not already initialized
        if (!window.projectChart) {
            // Call the initialization function from summary.js
            initializeDashboard();
        } else {
            // If already initialized, just fetch new data
            fetchSummaryData();
        }
    });

    // Function to fetch summary data using existing route
    function fetchSummaryData() {
        const today = new Date().toISOString().split('T')[0];
        const csrfToken = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
        const summaryGrid = $('.summary-grid');
        summaryGrid.html('<div class="loading" style="text-align:center; padding: 40px; font-size:16px; color:#6b7280;"><i class="fas fa-spinner fa-spin"></i> Loading projects summary...</div>');

        // Fetch master projects and report metrics in parallel
        Promise.all([
            fetch('/api/v1/masters/projects/?active=true', { credentials: 'same-origin' }).then(r => r.json()),
            fetch('/api/v1/reports/run/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ report_key: 'summary', date_from: today, date_to: today })
            }).then(r => r.json()).catch(() => ({ data: [] })),
            fetch('/api/v1/reports/run/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ report_key: 'productivity', date_from: today, date_to: today })
            }).then(r => r.json()).catch(() => ({ data: [] }))
        ])
        .then(([projRes, sumRes, prodRes]) => {
            const rawProjects = Array.isArray(projRes) ? projRes : (projRes.results || projRes.data || []);
            const summarySessions = Array.isArray(sumRes) ? sumRes : (sumRes.data || sumRes.results || []);
            const prodRows = Array.isArray(prodRes) ? prodRes : (prodRes.data || prodRes.results || []);
            window.lastDetailedData = prodRows;

            summaryGrid.empty();

            if (!rawProjects || rawProjects.length === 0) {
                summaryGrid.html(`
                    <div class="empty-state-card">
                        <i class="fas fa-folder-open"></i>
                        <h4>No Projects Found</h4>
                        <p>No active projects found in the system.</p>
                    </div>
                `);
                return;
            }

            // Adjust grid classes for single/double cards
            summaryGrid.removeClass('single-card double-card empty-state');
            if (rawProjects.length === 1) summaryGrid.addClass('single-card');
            else if (rawProjects.length === 2) summaryGrid.addClass('double-card');

            rawProjects.forEach(project => {
                const pId = project.project_id || '';
                const pName = project.project_name || pId;

                // Match sessions
                const matchingSessions = summarySessions.filter(s => 
                    (s.project && (s.project === pName || s.project === pId)) ||
                    (s.project_name && (s.project_name === pName || s.project_name === pId)) ||
                    (s.project_code && (s.project_code === pId || s.project_code === pName))
                );

                // Match productivity entries
                const matchingProd = prodRows.filter(r => 
                    (r.project && (r.project === pName || r.project === pId)) ||
                    (r.project_name && (r.project_name === pName || r.project_name === pId))
                );

                const activeUserIds = new Set();
                matchingSessions.forEach(s => { if (s.emp_id) activeUserIds.add(s.emp_id); });
                matchingProd.forEach(r => { if (r.emp_id) activeUserIds.add(r.emp_id); });
                const activeUsers = activeUserIds.size;

                let completedTasks = 0;
                let inProgressTasks = 0;
                let onHoldTasks = 0;
                let totalWorkUnits = 0;
                let totalSeconds = 0;

                if (matchingSessions.length > 0) {
                    matchingSessions.forEach(s => {
                        const units = parseInt(s.work_units || s.unit_cnt || s.total_units || 0) || 0;
                        totalWorkUnits += units;
                        
                        const status = (s.status || '').toLowerCase();
                        if (s.end_time || status === 'completed' || s.is_started === 2) {
                            completedTasks++;
                        } else if (s.is_paused || status === 'on hold' || status === 'paused') {
                            onHoldTasks++;
                        } else {
                            inProgressTasks++;
                        }
                    });
                } else if (matchingProd.length > 0) {
                    matchingProd.forEach(r => {
                        totalWorkUnits += (r.total_units || 0);
                        completedTasks += (r.session_count || 1);
                    });
                }

                const totalTasks = completedTasks + inProgressTasks + onHoldTasks;
                const completedPercent = totalTasks > 0 ? ((completedTasks / totalTasks) * 100).toFixed(1) : 0;
                const inProgressPercent = totalTasks > 0 ? ((inProgressTasks / totalTasks) * 100).toFixed(1) : 0;
                const onHoldPercent = totalTasks > 0 ? ((onHoldTasks / totalTasks) * 100).toFixed(1) : 0;

                const unitsPerUser = activeUsers > 0 ? (totalWorkUnits / activeUsers).toFixed(2) : "0.00";
                const dailyTarget = 0;
                const targetCompletion = dailyTarget > 0 ? Math.min(100, (totalWorkUnits / dailyTarget) * 100).toFixed(1) : 0;

                // Format avg time
                let avgTimePerUnit = "00:00:00";
                if (totalWorkUnits > 0 && totalSeconds > 0) {
                    const avgSec = Math.round(totalSeconds / totalWorkUnits);
                    const h = String(Math.floor(avgSec / 3600)).padStart(2, '0');
                    const m = String(Math.floor((avgSec % 3600) / 60)).padStart(2, '0');
                    const s = String(avgSec % 60).padStart(2, '0');
                    avgTimePerUnit = `${h}:${m}:${s}`;
                }

                const efficiencyRate = parseFloat(unitsPerUser) || (totalWorkUnits > 0 ? 5 : 0);
                const efficiencyClass = getEfficiencyClass(efficiencyRate);
                const efficiencyLabel = getEfficiencyLabel(efficiencyRate);

                const card = $(`
                    <div class="project-card project-card--expanded" data-project-id="${pId}" data-project-name="${pName}">
                        <div class="card-header">
                            <h3>${pName}</h3>
                            <span class="project-id">${pId}</span>
                        </div>
                        <div class="card-stats">
                            <div class="stat-group">
                                <div class="summary-stat-item">
                                    <div class="stat-value">${activeUsers}</div>
                                    <div class="stat-label">Active Users</div>
                                </div>
                                <div class="summary-stat-item">
                                    <div class="stat-value">${completedTasks}</div>
                                    <div class="stat-label">Completed Tasks</div>
                                </div>
                                <div class="summary-stat-item">
                                    <div class="stat-value">${totalWorkUnits}</div>
                                    <div class="stat-label">Work Units</div>
                                </div>
                            </div>

                            <div class="metrics-grid">
                                <div class="metric-item">
                                    <div class="metric-header">
                                        <i class="fas fa-chart-line"></i> Productivity Metrics
                                    </div>
                                    <div class="metric-content">
                                        <div class="metric-row">
                                            <span>Units/User:</span>
                                            <span class="metric-value">${unitsPerUser}</span>
                                        </div>
                                        <div class="metric-row">
                                            <span>Daily Target:</span>
                                            <span class="metric-value">${dailyTarget}</span>
                                        </div>
                                        <div class="metric-row">
                                            <span>Avg Time/Unit:</span>
                                            <span class="metric-value">${avgTimePerUnit}</span>
                                        </div>
                                    </div>
                                </div>

                                <div class="metric-item">
                                    <div class="metric-header">
                                        <i class="fas fa-tasks"></i> Task Distribution
                                    </div>
                                    <div class="task-distribution">
                                        <div class="distribution-legend">
                                            <span><i class="fas fa-circle completed"></i> Completed</span>
                                            <span><i class="fas fa-circle in-progress"></i> In Progress</span>
                                            <span><i class="fas fa-circle on-hold"></i> On Hold</span>
                                        </div>
                                        <div class="distribution-bar">
                                            <div class="completed" style="width: ${completedPercent}%"></div>
                                            <div class="in-progress" style="width: ${inProgressPercent}%"></div>
                                            <div class="on-hold" style="width: ${onHoldPercent}%"></div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="progress-section">
                                <div class="progress-info">
                                    <span>Target Completion</span>
                                    <span class="progress-percentage">${targetCompletion}%</span>
                                </div>
                                <div class="progress-bar">
                                    <div class="progress" style="width: ${Math.min(targetCompletion, 100)}%"></div>
                                </div>
                            </div>

                            <div class="task-metrics">
                                <div class="task-status">
                                    <div class="status-item">
                                        <span class="status-dot in-progress"></span>
                                        <span class="status-label">In Progress:</span>
                                        <span class="status-value">${inProgressTasks}</span>
                                    </div>
                                    <div class="status-item">
                                        <span class="status-dot on-hold"></span>
                                        <span class="status-label">On Hold:</span>
                                        <span class="status-value">${onHoldTasks}</span>
                                    </div>
                                </div>
                                <div class="efficiency-indicator ${efficiencyClass}">
                                    <i class="fas fa-tachometer-alt"></i> Efficiency: ${efficiencyLabel}
                                </div>
                            </div>
                        </div>
                    </div>
                `);

                card.click(function() {
                    const projectName = $(this).data('project-name');
                    const todayStr = new Date().toISOString().split('T')[0];
                    
                    fetch('/api/v1/reports/run/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({
                            report_key: 'productivity',
                            date_from: todayStr,
                            date_to: todayStr
                        })
                    })
                    .then(response => response.json())
                    .then(res2 => {
                        window.lastDetailedData = res2.data || res2.results || res2 || [];
                        if (typeof window.showDetailedView === 'function') {
                            window.showDetailedView(projectName);
                        }
                    });
                });

                summaryGrid.append(card);
            });
        })
        .catch(error => {
            console.error("Error fetching summary data:", error);
            summaryGrid.html('<div class="no-data" style="text-align:center; padding: 30px; color:#ef4444;">Failed to load project summary data.</div>');
        });
    }

    // Helper functions for efficiency calculations
    function getEfficiencyClass(productivityRate) {
        if (productivityRate >= 8) return 'high-efficiency';
        if (productivityRate >= 5) return 'medium-efficiency';
        return 'low-efficiency';
    }

    function getEfficiencyLabel(productivityRate) {
        if (productivityRate >= 8) return 'High';
        if (productivityRate >= 5) return 'Medium';
        return 'Low';
    }

    // Add CSS styles
    $('<style>')
        .text(`
            .summary-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                padding: 5px;
                max-width: 1600px;
                margin: 0 auto;
                justify-content: center;
            }

            .summary-grid.single-card {
                grid-template-columns: minmax(520px, 860px);
                max-width: 900px;
            }

            .summary-grid.double-card {
                grid-template-columns: repeat(2, minmax(420px, 1fr));
                max-width: 1300px;
            }

            .summary-grid.empty-state {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 260px;
            }

            .project-card {
                background: linear-gradient(360deg, #ffffff 0%, #f8f9fa 50%, #38616552  100%);
                border-radius: 10px;
                box-shadow: 0 3px 10px rgba(0,0,0,0.1);
                padding: 20px;
                transition: all 0.3s ease;
                cursor: pointer;
                min-height: 400px;
                display: flex;
                flex-direction: column;
                position: relative;
                overflow: hidden;
            }

            .project-card.project-card--expanded {
                min-height: 520px;
            }

            .summary-grid.single-card .project-card.project-card--expanded {
                width: min(860px, 95vw);
            }

            .summary-grid.double-card .project-card.project-card--expanded {
                width: min(600px, 95%);
            }

            .summary-grid.single-card .project-card.project-card--expanded .card-stats,
            .summary-grid.double-card .project-card.project-card--expanded .card-stats {
                flex: 1;
            }

            .project-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: linear-gradient(90deg, #2c3e4f 0%, #4a6785 50%, #2c3e4f 100%);
                opacity: 0.8;
            }

            .project-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 15px rgba(44, 62, 79, 0.15);
                background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 60%, #e3e6ed 100%);
            }

            .project-card:hover::before {
                opacity: 1;
                background: linear-gradient(90deg, #2c3e4f 0%, #5a7795 50%, #2c3e4f 100%);
            }

            /* Responsive grid adjustments */
            @media (max-width: 1400px) {
                .summary-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
            }

            @media (max-width: 900px) {
                .summary-grid {
                    grid-template-columns: 1fr;
                }
            }

            .empty-state-card {
                background: #ffffff;
                border-radius: 12px;
                padding: 40px 48px;
                text-align: center;
                box-shadow: 0 10px 25px rgba(15, 23, 42, 0.08);
                max-width: 420px;
            }

            .empty-state-card i {
                font-size: 32px;
                color: #f5a623;
                margin-bottom: 12px;
            }

            .empty-state-card h4 {
                margin: 0 0 8px;
                font-size: 20px;
                color: #2c3e4f;
            }

            .empty-state-card p {
                margin: 0;
                color: #6b7280;
                line-height: 1.5;
            }

            .card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }

            .card-header h3 {
                margin: 0;
                color: #2c3e4f;
                font-size: 1.2rem;
            }

            .project-id {
                color: #666;
                font-size: 0.9rem;
            }

            .card-stats {
                display: flex;
                flex-direction: column;
                gap: 15px;
            }

            .stat-group {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                text-align: center;
            }

            .summary-stat-item {
                padding: 10px;
                background: #2c3e4f;
                border-radius: 8px;
            }

            .stat-value {
                font-size: 1.5rem;
                font-weight: bold;
                color:rgb(255, 255, 255);
            }

            .stat-label {
                font-size: 0.8rem;
                color:rgb(255, 255, 255);
                margin-top: 5px;
            }

            .progress-section {
                margin: 15px 0;
            }

            .progress-info {
                display: flex;
                justify-content: space-between;
                margin-bottom: 5px;
                font-size: 0.9rem;
                color: #666;
            }

            .progress-bar {
                height: 8px;
                background: #c1c1c1;
                border-radius: 4px;
                overflow: hidden;
            }

            .progress {
                height: 100%;
                background: #2c3e4f;
                border-radius: 4px;
                transition: width 0.3s ease;
            }

            .task-status {
                display: flex;
                flex-direction: column;
                gap: 5px;
                margin-top: 15px;
            }

            .status-item {
                display: flex;
                align-items: center;
                gap: 5px;
            }

            .status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
            }

            .status-dot.in-progress {
                background: #ffc107;
            }

            .status-dot.on-hold {
                background: #dc3545;
            }

            .status-label {
                font-size: 0.9rem;
                color: #666;
            }

            .status-value {
                font-weight: bold;
                color: #2c3e4f;
            }

            .avg-time {
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #e9ecef;
                color: #666;
                font-size: 0.9rem;
                display: flex;
                align-items: center;
                gap: 5px;
            }

            /* Existing toggle button styles */
            .reports-page-title {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .reports-toggle-btn {
                display: inline-flex;
            }
            .toggle-btn {
                display: inline-flex;
                border: 1px solid #2c3e4f;
                border-radius: 4px;
                overflow: hidden;
                background: none;
                padding: 0;
            }
            .toggle-btn span {
                padding: 4px 12px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 14px;
                font-weight: 900;
                border-right: 1px solid #2c3e4f;
            }
            .toggle-btn span:last-child {
                border-right: none;
            }
            .toggle-btn span.active {
                background-color: #2c3e4f;
                color: white;
            }
            .toggle-btn span:not(.active) {
                background-color: white;
                color: #2c3e4f;
            }
            .toggle-btn span:not(.active):hover {
                background-color: #f8f9fa;
            }
            .summary-section table tbody tr {
                cursor: pointer;
            }
            .summary-section table tbody tr:hover {
                background-color: #f5f5f5;
            }
            #summaryTableSection {
                margin-top: 20px;
            }
            #reportsSection {
                display: none;
            }

            .metrics-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin: 15px 0;
            }

            .metric-item {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 12px;
            }

            .metric-header {
                display: flex;
                align-items: center;
                gap: 8px;
                color: #2c3e4f;
                font-weight: 600;
                margin-bottom: 10px;
            }

            .metric-content {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            .metric-row {
                display: flex;
                justify-content: space-between;
                color: #666;
                font-size: 0.9rem;
            }

            .task-distribution {
                margin-top: 10px;
            }

            .distribution-bar {
                height: 8px;
                background: #e9ecef;
                border-radius: 4px;
                display: flex;
                overflow: hidden;
            }

            .distribution-bar .completed {
                background: #28a745;
            }

            .distribution-bar .in-progress {
                background: #ffc107;
            }

            .distribution-bar .on-hold {
                background: #dc3545;
            }

            .distribution-legend {
                display: flex;
                justify-content: space-between;
                margin-top: 8px;
                font-size: 0.8rem;
                color: #666;
            }

            .distribution-legend i {
                font-size: 8px;
                margin-right: 4px;
            }

            .distribution-legend i.completed { color: #28a745; }
            .distribution-legend i.in-progress { color: #ffc107; }
            .distribution-legend i.on-hold { color: #dc3545; }

            .task-metrics {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #e9ecef;
            }

            .efficiency-indicator {
                padding: 4px 12px;
                border-radius: 15px;
                font-size: 0.9rem;
                display: flex;
                align-items: center;
                gap: 5px;
            }

            .efficiency-indicator.high-efficiency {
                background: #d4edda;
                color: #155724;
            }

            .efficiency-indicator.medium-efficiency {
                background: #fff3cd;
                color: #856404;
            }

            .efficiency-indicator.low-efficiency {
                background: #f8d7da;
                color: #721c24;
            }

            .progress.target-achieved {
                background: #10b981;
                box-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
            }
            .progress.target-near {
                background: #f59e0b;
            }
            .progress.target-behind {
                background: #ef4444;
            }
        `)
        .appendTo('head');

    // Header mapping configuration
    const headerMap = {
     'emp_id': 'Emp ID',
     'name': 'Emp Name',
     'date': 'Date',
     'start_time': 'Start',
     'end_time': 'End',
     'project': 'Project',
     'client_code': 'Client Code',
     'work_type': 'WorkType',
     'batch': 'Batch',
     'work_units': 'Work Units',
     'total_time': 'Total Time',
     'average_time': 'Average Time',
     'work_location': 'Location',
     'status': 'Status',
     'review': 'Review',
     'pages': 'Pages'
 };
 // Initialize DataTable with custom DOM layout
 const table = $('#reportsTable').DataTable({
     dom: 'rt<"bottom"lip><"clear">',  // Customize the layout
     lengthMenu: [10, 25, 50, 100], // Define the length menu options
     columns: [
         { data: 'emp_id' },
         { data: 'name' },
         { 
             data: 'start_time',
             render: function(data) {
                 return data ? data.split('T')[0] : '';
             }
         },
         { 
             data: 'start_time',
             render: function(data) {
                 return data ? data.split('T')[1].substring(0,8) : '';
             }
         },
         { 
             data: 'end_time',
             render: function(data) {
                 return data ? data.split('T')[1].substring(0,8) : '';
             }
         },
         { data: 'project' },
         { data: 'client_code' },
         { data: 'work_type' },
         { data: 'batch' },
         { data: 'work_units' },
         { 
             data: 'total_time',
             render: function (data) {
                 return formatTime(data);
             }
         },
         { 
             data: 'average_time',
             render: function (data) {
                 return formatTime(data);
             }
         },
         { data: 'work_location' },
         { 
             data: null,
             render: function (data) {
                 if (data.is_paused) {
                     return `Paused${data.pause_reason ? ' (' + data.pause_reason + ')' : ''}`;
                 } else if (data.end_time) {
                     return 'Completed';
                 } else {
                     return 'In Progress';
                 }
             }
         }
     ],
     createdRow: function(row, data, dataIndex) {
         if (data.is_paused) {
             $(row).addClass('paused-row');
         }
     }
 });

 // Move the length menu to the custom container
 $('#lengthMenuContainer').append($('.dataTables_length'));

 // Function to format time into hh:mm:ss without milliseconds
 function formatTime(time) {
     if (!time || isNaN(time)) return "00:00:00";
     const totalSeconds = Math.round(time); // Round to the nearest second
     const hrs = Math.floor(totalSeconds / 3600);
     const mins = Math.floor((totalSeconds % 3600) / 60);
     const secs = totalSeconds % 60;
     return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
 }

 // Set default date to today
 const today = new Date().toISOString().split('T')[0];
 $('#startDate').val(today);
 $('#endDate').val(today);

 // Fetch data for today on page load
 fetchData(today, today);

 // Fetch data when date range is changed
 $('#startDate, #endDate').on('change', function () {
     const startDate = $('#startDate').val();
     const endDate = $('#endDate').val();
     if (startDate && endDate) {
         if (startDate > endDate) {
             alert('End date cannot be before start date');
             $(this).val(today);
             return;
         }
         fetchData(startDate, endDate);
     }
 });

 // Modified download button click handler
 $('#downloadButton').on('click', function () {
     const format = $('#downloadFormat').val();
     const filteredData = table.rows({ search: 'applied' }).data().toArray(); // Get only filtered data
     const headers = Object.values(headerMap); // Use mapped headers

     if (format === 'csv') {
         downloadCSV(filteredData, headers);
     } else if (format === 'excel') {
         downloadExcel(filteredData, headers);
     }
 });

 // Modified CSV download function
 function downloadCSV(data, headers) {
     const csvRows = [];
     
     // Add headers
     csvRows.push(headers.join(','));

     // Add data rows
     data.forEach(row => {
         const values = headers.map(headerText => {
             // Find the data key for this header
             const dataKey = Object.keys(headerMap).find(k => headerMap[k] === headerText);
             let value = row[dataKey];
             
             // Handle special formatted columns
             if (dataKey === 'date') {
                 value = row.start_time ? row.start_time.split('T')[0] : '';
             } else if (dataKey === 'start_time') {
                 value = row.start_time ? row.start_time.split('T')[1].substring(0,8) : '';
             } else if (dataKey === 'end_time') {
                 value = row.end_time ? row.end_time.split('T')[1].substring(0,8) : '';
             } else if (dataKey === 'total_time' || dataKey === 'average_time') {
                 value = formatTime(value);
             } else if (dataKey === 'status') {
                 value = row.end_time ? 'Completed' : 'In Progress';
             }
             
             return `"${(value || '').toString().replace(/"/g, '""')}"`;
         });
         csvRows.push(values.join(','));
     });

     const startDate = $('#startDate').val();
     const endDate = $('#endDate').val();
     const dateRangeStr = startDate === endDate ? startDate : `${startDate}_to_${endDate}`;
     const fileName = `employee_work_data_${dateRangeStr}.csv`;

     const csvContent = "data:text/csv;charset=utf-8," + csvRows.join('\n');
     const encodedUri = encodeURI(csvContent);
     const link = document.createElement("a");
     link.setAttribute("href", encodedUri);
     link.setAttribute("download", fileName);
     document.body.appendChild(link);
     link.click();
     document.body.removeChild(link);
 }

 // Modified Excel download function
 function downloadExcel(data, headers) {
     const formattedData = data.map(row => {
         const obj = {};
         headers.forEach(headerText => {
             const dataKey = Object.keys(headerMap).find(k => headerMap[k] === headerText);
             let value = row[dataKey];
             
             // Handle special formatted columns
             if (dataKey === 'date') {
                 value = row.start_time ? row.start_time.split('T')[0] : '';
             } else if (dataKey === 'start_time') {
                 value = row.start_time ? row.start_time.split('T')[1].substring(0,8) : '';
             } else if (dataKey === 'end_time') {
                 value = row.end_time ? row.end_time.split('T')[1].substring(0,8) : '';
             } else if (dataKey === 'total_time' || dataKey === 'average_time') {
                 value = formatTime(value);
             } else if (dataKey === 'status') {
                 value = row.end_time ? 'Completed' : 'In Progress';
             }
             
             obj[headerText] = value;
         });
         return obj;
     });

     const startDate = $('#startDate').val();
     const endDate = $('#endDate').val();
     const dateRangeStr = startDate === endDate ? startDate : `${startDate}_to_${endDate}`;
     const fileName = `employee_work_data_${dateRangeStr}.xlsx`;

     const worksheet = XLSX.utils.json_to_sheet(formattedData);
     const workbook = XLSX.utils.book_new();
     XLSX.utils.book_append_sheet(workbook, worksheet, "Employee Work Data");
     XLSX.writeFile(workbook, fileName);
 }

 // Refresh button click event
 $('#refreshButton').on('click', function () {
     const startDate = $('#startDate').val();
     const endDate = $('#endDate').val();
     if (startDate && endDate) {
         fetchData(startDate, endDate);
     }
 });

 // Project filter change event
 $('#projectFilter').on('change', function () {
     const selectedProject = $(this).val();
     table.column(5).search(selectedProject).draw();
 });

 // Work Location filter change event
 $('#workLocationFilter').on('change', function () {
     const selectedWorkLocation = $(this).val();
     table.column(12).search(selectedWorkLocation).draw(); // Assuming work_location is the 13th column
 });

 // Search field keyup event
 $('#searchField').on('keyup', function () {
     const searchValue = $(this).val();
     table.search(searchValue).draw(); // Filter the table based on the search input

     // Show or hide the clear button based on whether there is text in the search field
     if (searchValue.length > 0) {
         $('#clearSearch').show();
     } else {
         $('#clearSearch').hide();
     }
 });

 // Clear search field and reset table search
 $('#clearSearch').on('click', function () {
     $('#searchField').val(''); // Clear the search field
     table.search('').draw(); // Reset the table search
     $(this).hide(); // Hide the clear button
 });

 // Auto-refresh every 5 minutes (300,000 ms)
 setInterval(function () {
     const startDate = $('#startDate').val();
     const endDate = $('#endDate').val();
     if (startDate && endDate) {
         fetchData(startDate, endDate);
     }
 }, 300000); // 5 minutes

 function fetchData(startDate, endDate) {
     $.ajax({
         url: `/api/v1/tracking/sessions/?from=${startDate}&to=${endDate}`,
         method: 'GET',
         headers: {
             'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
         },
         success: function (response) {
             const rows = response.data || response;
             table.clear();
             table.rows.add(rows).draw();

             // Populate project dropdown
             const projects = [...new Set(rows.map(item => item.project).filter(Boolean))];
             const projectFilter = $('#projectFilter');
             projectFilter.empty();
             projectFilter.append('<option value="">All Projects</option>');
             projects.forEach(project => {
                 projectFilter.append(`<option value="${project}">${project}</option>`);
             });

             // Populate work location dropdown
             const workLocations = [...new Set(rows.map(item => item.work_location || item.client_code).filter(Boolean))];
             const workLocationFilter = $('#workLocationFilter');
             workLocationFilter.empty();
             workLocationFilter.append('<option value="">All Work Locations</option>');
             workLocations.forEach(location => {
                 workLocationFilter.append(`<option value="${location}">${location}</option>`);
             });
         },
         error: function (xhr, status, error) {
             console.error("Error fetching data:", error);
             alert("An error occurred while fetching data. Please try again.");
         }
     });
 }

 // Add zoom modal to the document body
 $('body').append(`
    <div class="row-zoom-modal">
        <div class="row-zoom-content"></div>
        <div class="row-zoom-actions">
            <button class="action-btn pause-btn" title="Pause" style="display: none;">
                <i class="fas fa-pause-circle"></i>
            </button>
            <button class="action-btn delete-btn" title="Delete">
                <i class="fas fa-trash-alt"></i>
            </button>
            <button class="action-btn end-btn" title="End Work" style="display: none;">
                <i class="fas fa-check-circle"></i>
            </button>
        </div>
        <button class="close-zoom-modal">&times;</button>
    </div>
`);

 const $zoomModal = $('.row-zoom-modal');
 const $zoomContent = $('.row-zoom-content');
 let currentRowData = null;
 let currentRowIndex = null;

 // ⚡ Extend row click to toggle end button
 $('#reportsTable tbody').on('click', 'tr', function () {
    const rowData = table.row(this).data();
    currentRowData = rowData;
    currentRowIndex = table.row(this).index(); // Store the DataTables row index

    $('#reportsTable tbody tr').removeClass('selected');
    $(this).addClass('selected');

    let zoomHTML = '';
    Object.keys(headerMap).forEach(key => {
        let value = rowData[key];
        if (key === 'total_time' || key === 'average_time') value = formatTime(value);
        if (key === 'status') {
            if (rowData.is_paused) {
                value = 'Paused';
            } else {
                value = rowData.end_time ? 'Completed' : 'In Progress';
            }
        }
        zoomHTML += `
            <div class="row-zoom-label">${headerMap[key]}</div>
            <div class="row-zoom-value">${value || '-'}${key === 'status' && rowData.is_paused && rowData.pause_reason ? ` (${rowData.pause_reason})` : ''}</div>`;
    });
    $zoomContent.html(zoomHTML);

    // Show/hide pause and end buttons based on status
    const isInProgress = !rowData.end_time && !rowData.is_paused;
    const isPaused = !!rowData.is_paused;
    $('.pause-btn').toggle(isInProgress);
    $('.end-btn').toggle(isInProgress);

    // If paused, ensure pause popup cannot be triggered
    if (isPaused) {
        $('.pause-btn').prop('disabled', true);
    } else {
        $('.pause-btn').prop('disabled', false);
    }

    const top = Math.max(0, ($(window).height() - $zoomModal.outerHeight()) / 2);
    const left = Math.max(0, ($(window).width() - $zoomModal.outerWidth()) / 2);
    $zoomModal.css({ top: `${top}px`, left: `${left}px` }).fadeIn(200);
});

// ✅ End Work click event
$('.end-btn').on('click', function () {
    if (!currentRowData) return;
    // Prevent ending if already completed
    if (currentRowData.end_time) return;
    // Prevent ending if not allowed (add any additional checks here)
    // Patch: Show/hide Pages field based on project name (ProvenAir-AAR logic)
    const projectName = currentRowData.project;
    const isProvenAirAAR = projectName === 'ProvenAir-AAR';
    // Find the label and input for Pages
    const $pagesLabel = $(".end-popup label[for='endPages']");
    const $pagesInput = $('#endPages');
    if ($pagesLabel.length && $pagesInput.length) {
        if (isProvenAirAAR) {
            $pagesLabel.show();
            $pagesInput.show().prop('required', true);
            // Optionally restore last value from localStorage
            const lastPages = localStorage.getItem('lastProvenAirPages');
            if (!$pagesInput.val() && lastPages) {
                $pagesInput.val(lastPages);
            }
        } else {
            $pagesLabel.hide();
            $pagesInput.hide().prop('required', false).val('');
        }
    }
    $('.end-popup').fadeIn(200);
    // If the work is paused, disable the end button in the modal (user should not end directly)
    if (currentRowData.is_paused) {
        $('.end-popup .end-popup-submit').prop('disabled', true).text('Resume to End Work');
    } else {
        $('.end-popup .end-popup-submit').prop('disabled', false).text('Submit');
    }
});

$('.end-popup-cancel').on('click', function () {
    $('.end-popup').fadeOut(200);
    $('#endWorkUnits').val('');
    $('#endPages').val('');
    $('#endReview').val('');
});

$('.end-popup-submit').off('click').on('click', function () {
    if (!currentRowData) return;
    if (currentRowData.is_paused) {
        alert('You must resume the paused work before ending it.');
        return;
    }
    const work_units = parseInt($('#endWorkUnits').val());
    const pages = parseInt($('#endPages').val());
    const review = $('#endReview').val().trim();
    const emp_id = currentRowData.emp_id;
    // Combine date and time in the format 'YYYY-MM-DD HH:MM:SS' to match DB
    const start_time = `${currentRowData.date} ${currentRowData.start_time}`;
    const end_time = new Date().toISOString();

    if (!work_units || work_units <= 0) {
        alert('Work units must be greater than 0.');
        return;
    }

        const session_id = currentRowData.id;
    if (!session_id) {
        alert('Cannot end session without ID.');
        return;
    }

    $.ajax({
        url: `/api/v1/tracking/sessions/${session_id}/end/`,
        method: 'POST',
        headers: {
            'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
        },
        contentType: 'application/json',
        data: JSON.stringify({
            work_units,
            review,
            pages
        }),
        success: function (res) {
            const result = res.data || res;
            if (res.ok || result.id) {
                $('.end-popup').fadeOut(200);
                alert('Work ended successfully.');
                $zoomModal.fadeOut(200);
                fetchData($('#startDate').val(), $('#endDate').val());
                // Notify userdashboard for instant update
                try {
                    localStorage.setItem('work-ended-notify', JSON.stringify({
                        emp_id: currentRowData.emp_id,
                        project: currentRowData.project,
                        ts: Date.now()
                    }));
                } catch (e) {}
                // Update the row status to Completed immediately in the table
                if (currentRowIndex !== null) {
                    currentRowData.end_time = 'Completed'; // Set status to Completed for immediate UI update
                    currentRowData.is_paused = false;
                    currentRowData.pause_reason = null;
                    table.row(currentRowIndex).data(currentRowData).invalidate().draw(false);
                    // Remove yellow highlight if present
                    const rowNode = table.row(currentRowIndex).node();
                    if (rowNode) {
                        $(rowNode).removeClass('paused-row');
                    }
                }
            } else {
                alert('Error: ' + (res.error || 'Unknown error'));
            }
        },
        error: function () {
            alert('Something went wrong while submitting work data.');
        }
    });
});

 // Handle row click events
 $('#reportsTable tbody').on('click', 'tr', function(e) {
     const rowData = table.row(this).data();
     currentRowData = rowData;
     
     // Remove selected class from all rows and add to clicked row
     $('#reportsTable tbody tr').removeClass('selected');
     $(this).addClass('selected');
     
     // Build zoom content
     let zoomHTML = '';
     Object.keys(headerMap).forEach(key => {
         let value = rowData[key];
         
         // Format special values
         if (key === 'date') {
             value = rowData.start_time ? rowData.start_time.split('T')[0] : '';
         } else if (key === 'start_time') {
             value = rowData.start_time ? rowData.start_time.split('T')[1].substring(0,8) : '';
         } else if (key === 'end_time') {
             value = rowData.end_time ? rowData.end_time.split('T')[1].substring(0,8) : '';
         } else if (key === 'total_time' || key === 'average_time') {
             value = formatTime(value);
         } else if (key === 'status') {
             value = rowData.end_time ? 'Completed' : 'In Progress';
         }

         zoomHTML += `
             <div class="row-zoom-label">${headerMap[key]}</div>
             <div class="row-zoom-value">${value || '-'}</div>
         `;
     });

     $zoomContent.html(zoomHTML);

     // Show/hide pause button based on status
     const isInProgress = !rowData.end_time;
     $('.pause-btn').toggle(isInProgress);
     $('.end-btn').toggle(isInProgress);

     // Position the modal in the center of the screen
     const windowHeight = $(window).height();
     const windowWidth = $(window).width();
     const modalWidth = $zoomModal.outerWidth();
     const modalHeight = $zoomModal.outerHeight();

     const top = Math.max(0, (windowHeight - modalHeight) / 2);
     const left = Math.max(0, (windowWidth - modalWidth) / 2);

     // Show the modal with animation
     $zoomModal.css({
         top: top + 'px',
         left: left + 'px'
     }).fadeIn(200);
 });

 // Handle delete button click
 $('.delete-btn').on('click', function() {
     if (!currentRowData) return;
     
     if (confirm('Are you sure you want to delete this entry?')) {
         // Combine the date and time to create full datetime
         const fullDateTime = `${currentRowData.date} ${currentRowData.start_time}`;
         
         $.ajax({
             url: `/delete_work_entry/${currentRowData.emp_id}/${encodeURIComponent(fullDateTime)}`,
             method: 'DELETE',
             success: function(response) {
                 if (response.success) {
                     // Remove the row from the table
                     table.row('.selected').remove().draw();
                     // Close the modal
                     $zoomModal.fadeOut(200);
                     // Show success message
                     alert('Entry deleted successfully');
                 } else {
                     alert('Failed to delete entry: ' + (response.error || 'Unknown error'));
                 }
             },
             error: function(xhr, status, error) {
                 console.error('Delete error:', error);
                 alert('An error occurred while deleting the entry');
             }
         });
     }
 });

 // Add pause reason popup to the document body
 $('body').append(`
     <div class="pause-reason-popup">
         <div class="pause-reason-content">
             <h3>Enter Reason for Pausing Work Session</h3>
             <textarea id="pauseReasonText" placeholder="Please provide a reason for pausing this work session..."></textarea>
             <div class="pause-reason-buttons">
                 <button class="pause-reason-cancel">Cancel</button>
                 <button class="pause-reason-submit">Submit</button>
             </div>
         </div>
     </div>
 `);

 // Update the pause button click handler
 $('.pause-btn').on('click', function() {
     if (!currentRowData || currentRowData.is_paused) return; // Prevent pause if already paused
     
     let pauserId = sessionStorage.getItem('emp_id');
     
     // If emp_id is not in sessionStorage, get it from the server
     if (!pauserId) {
         $.ajax({
             url: '/get_current_user',
             method: 'GET',
             async: false, // We need this synchronously
             success: function(response) {
                 if (response.employee_id) {
                     pauserId = response.employee_id;
                     sessionStorage.setItem('emp_id', pauserId);
                 }
             },
             error: function(xhr, status, error) {
                 console.error('Error getting user info:', error);
                 alert('Session information not found. Please refresh the page or log in again.');
                 return;
             }
         });
     }
     
     if (!pauserId) {
         alert('Session information not found. Please refresh the page or log in again.');
         return;
     }

     // Show the pause reason popup
     $('.pause-reason-popup').fadeIn(300);
     $('#pauseReasonText').focus();

     // Handle submit button click
     $('.pause-reason-submit').one('click', function() {
         const pauseReason = $('#pauseReasonText').val().trim();
         
         if (!pauseReason) {
             $('#pauseReasonText').css('border-color', '#dc3545');
             return;
         }

         // Combine the date and time to create full datetime
         const fullDateTime = `${currentRowData.date} ${currentRowData.start_time}`;
         
         $.ajax({
             url: `/pause_work_entry/${currentRowData.emp_id}/${encodeURIComponent(fullDateTime)}`,
             method: 'POST',
             data: JSON.stringify({
                 paused_by: pauserId,
                 pause_reason: pauseReason
             }),
             contentType: 'application/json',
             success: function(response) {
                 if (response.success) {
                     // Update the row data to reflect paused state
                     currentRowData.is_paused = true;
                     currentRowData.pause_reason = pauseReason;
                     // Redraw the table to update row color using stored index
                     if (currentRowIndex !== null) {
                         table.row(currentRowIndex).data(currentRowData).invalidate().draw(false);
                         // Ensure yellow highlight is applied immediately
                         const rowNode = table.row(currentRowIndex).node();
                         if (rowNode && currentRowData.is_paused) {
                             $(rowNode).addClass('paused-row');
                         }
                     }
                     // Close both modals
                     $('.row-zoom-modal').fadeOut(200);
                     $('.pause-reason-popup').fadeOut(200);
                     // Clear the textarea
                     $('#pauseReasonText').val('');
                     // Notify the paused user immediately (for userdashboard.js)
                     try {
                         localStorage.setItem('work-paused-notify', JSON.stringify({
                             emp_id: currentRowData.emp_id,
                             project: currentRowData.project,
                             ts: Date.now(),
                             pauser: pauserId
                         }));
                     } catch (e) {}
                 } else {
                     alert('Failed to pause work session: ' + (response.error || 'Unknown error'));
                 }
             },
             error: function(xhr, status, error) {
                 console.error('Pause error:', error);
                 let errorMessage = 'An error occurred while pausing the work session';
                 try {
                     const response = JSON.parse(xhr.responseText);
                     if (response.error) {
                         errorMessage = response.error;
                     }
                 } catch (e) {
                     // Use default error message
                 }
                 alert(errorMessage);
             }
         });
     });

     // Handle cancel button click
     $('.pause-reason-cancel').one('click', function() {
         $('.pause-reason-popup').fadeOut(200);
         $('#pauseReasonText').val('').css('border-color', '#ddd');
     });

     // Handle Enter key in textarea
     $('#pauseReasonText').on('keydown', function(e) {
         if (e.key === 'Enter' && !e.shiftKey) {
             e.preventDefault();
             $('.pause-reason-submit').click();
         }
     });
 });

 // Close modal when clicking the close button
 $('.close-zoom-modal').on('click', function() {
     $zoomModal.fadeOut(200);
     $('#reportsTable tbody tr').removeClass('selected');
 });

 // Close modal when clicking outside
 $(document).on('click', function(e) {
     if (!$(e.target).closest('#reportsTable tbody tr, .row-zoom-modal').length) {
         $zoomModal.fadeOut(200);
         $('#reportsTable tbody tr').removeClass('selected');
     }
 });

 // Prevent modal from closing when clicking inside it
 $('.row-zoom-modal').on('click', function(e) {
     e.stopPropagation();
 });
}); 