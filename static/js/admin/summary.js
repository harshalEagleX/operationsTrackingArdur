document.addEventListener('DOMContentLoaded', function() {
    let projectChart, locationChart, productivityChart;

    // Add this at the beginning of your script
    const projectColorMap = new Map();

    function getProjectColor(projectName) {
        if (projectColorMap.has(projectName)) {
            return projectColorMap.get(projectName);
        }

        const baseColors = [
            '#4CAF50', '#2196F3', '#FFC107', '#E91E63', '#9C27B0',
            '#FF5722', '#795548', '#607D8B', '#3F51B5', '#009688'
        ];
        
        const newColor = baseColors[projectColorMap.size % baseColors.length];
        projectColorMap.set(projectName, newColor);
        return newColor;
    }

    function initializeCharts() {
        // Project Chart as doughnut with data labels
        projectChart = new Chart(document.getElementById('projectChart'), {
            type: 'doughnut',
            data: {
                labels: [],
                datasets: [{
                    label: 'Number of Employees',
                    data: [],
                    backgroundColor: [],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        align: 'center',
                        labels: {
                            padding: 20
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `${context.label}: ${context.parsed} employees`;
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: 'Project-wise Employees Count',
                        font: { size: 16 }
                    },
                    datalabels: {
                        color: '#fff',
                        font: {
                            weight: 'bold',
                            size: 14
                        },
                        formatter: function(value, context) {
                            return value;
                        }
                    }
                }
            },
            plugins: [ChartDataLabels, {
                id: 'centerText',
                afterDraw: function(chart) {
                    const ctx = chart.ctx;
                    const width = chart.width;
                    const height = chart.height;
                    
                    // Get total from the data
                    const total = chart.data.datasets[0].data.reduce((sum, value) => sum + value, 0);
                    
                    ctx.save();
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.font = 'bold 28px Arial';
                    ctx.fillStyle = '#2c3e50';
                    ctx.fillText(total, width / 2, height / 2);
                    ctx.restore();
                }
            }]
        });

        // Update location chart controls to only show navigation
        const locationChartControls = ''; // Empty string instead of the controls HTML

        // Initialize location line chart (empty initially)
        locationChart = new Chart(document.getElementById('locationChart'), {
            type: 'line',
            data: { 
                labels: [], 
                datasets: []
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'top',
                        align: 'start',
                        labels: {
                            padding: 20,  // Increase padding between legend items
                            boxWidth: 40, // Increase color box width
                            font: {
                                size: 12
                            },
                            usePointStyle: true,  // Use point style instead of boxes
                            pointStyle: 'circle'  // Make legend markers circular
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `${context.dataset.label}: ${context.parsed.y} users`;
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: 'Location-wise Active Users Attendance',
                        font: { size: 16 }
                    },
                    datalabels: {
                        align: 'top',
                        anchor: 'end',
                        offset: 4,
                        color: function(context) {
                            return context.dataset.borderColor;
                        },
                        font: {
                            weight: 'bold',
                            size: 11
                        },
                        formatter: function(value) {
                            // Format numbers over 1000 as 1k, 1.1k etc.
                            if (value >= 1000) {
                                return (value / 1000).toFixed(1) + 'k';
                            }
                            return value;
                        },
                        display: function(context) {
                            return context.dataset.data[context.dataIndex] !== 0; // Only show if value is not zero
                        },
                        padding: {
                            top: 4,
                            bottom: 4,
                            left: 6,
                            right: 6
                        },
                        borderRadius: 4
                    }
                },
                scales: { 
                    y: { 
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Number of Active Users'
                        },
                        ticks: {
                            callback: function(value) {
                                // Format y-axis labels for better readability
                                if (value >= 1000) {
                                    return (value / 1000).toFixed(1) + 'k';
                                }
                                return value;
                            }
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Date'
                        },
                        ticks: {
                            maxRotation: 45,  // Rotate labels for better fit
                            minRotation: 45   // Ensure consistent rotation
                        }
                    }
                },
                layout: {
                    padding: {
                        top: 0,    // Add padding to prevent label cutoff
                        right: 20,
                        bottom: 10,
                        left: 0
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                }
            },
            plugins: [ChartDataLabels]
        });

        // Productivity Chart (vertical bars)
        productivityChart = new Chart(document.getElementById('productivityChart'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: []
            },
            options: {
                responsive: true,
                indexAxis: 'x',
                plugins: {
                    legend: {
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `Total Units: ${context.parsed.y}`;
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: function() {
                            const startDate = document.getElementById('summaryStartDate').value;
                            const endDate = document.getElementById('summaryEndDate').value;
                            
                            const formatDate = (dateStr) => {
                                return new Date(dateStr).toLocaleDateString('en-US', {
                                    day: 'numeric',
                                    month: 'short',
                                    year: 'numeric'
                                });
                            };

                            if (startDate === endDate) {
                                return `Project Productivity Summary - ${formatDate(startDate)}`;
                            } else {
                                return `Project Productivity Summary - ${formatDate(startDate)} To ${formatDate(endDate)}`;
                            }
                        },
                        font: { size: 16 }
                    },
                    datalabels: {
                        anchor: 'end',
                        align: 'top',
                        formatter: function(value) {
                            return value;
                        },
                        color: '#000',
                        font: {
                            weight: 'bold'
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Projects'
                        }
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Total Work Units'
                        }
                    }
                },
                onClick: function(event, elements) {
                    if (elements.length > 0 && document.getElementById('projectSelect').value === 'all') {
                        const index = elements[0].index;
                        const projectName = this.data.labels[index];
                        showDetailedView(projectName);
                    }
                }
            },
            plugins: [ChartDataLabels]
        });
    }

        function updateCharts(data, selectedProject) {
        if (!data || !Array.isArray(data)) {
            data = [];
        }

        // Hide location chart completely since we don't have location data in productivity report
        const locChartElement = document.getElementById('locationChart');
        if (locChartElement && locChartElement.parentElement && locChartElement.parentElement.parentElement) {
            locChartElement.parentElement.parentElement.style.display = 'none';
        }

        // Filter by project if needed
        let filteredData = data;
        if (selectedProject && selectedProject !== 'all') {
            filteredData = data.filter(d => String(d.project) === selectedProject);
        }

        // Aggregate project data (Count unique employees per project)
        const projectEmps = {};
        filteredData.forEach(row => {
            const proj = row.project || 'Unknown';
            if (!projectEmps[proj]) projectEmps[proj] = new Set();
            projectEmps[proj].add(row.emp_id);
        });

        const projectNames = Object.keys(projectEmps);
        const projectCounts = projectNames.map(p => projectEmps[p].size);
        const totalEmps = projectCounts.reduce((a, b) => a + b, 0);

        if (projectChart) {
            projectChart.data.labels = projectNames;
            projectChart.data.datasets[0].data = projectCounts;
            projectChart.data.datasets[0].backgroundColor = projectNames.map(getProjectColor);
            projectChart.update();
        }

        // Aggregate productivity data (Sum of units per project or per employee)
        if (productivityChart) {
            if (selectedProject === 'all') {
                // Show project totals
                const projectUnits = {};
                filteredData.forEach(row => {
                    const proj = row.project || 'Unknown';
                    projectUnits[proj] = (projectUnits[proj] || 0) + (row.total_units || 0);
                });
                const projs = Object.keys(projectUnits);
                productivityChart.data.labels = projs;
                productivityChart.data.datasets = [{
                    label: 'All Projects',
                    data: projs.map(p => projectUnits[p]),
                    backgroundColor: projs.map(getProjectColor),
                    borderWidth: 1
                }];
            } else {
                // Show individual employee units for the selected project
                productivityChart.data.labels = filteredData.map(d => d.name || d.emp_id);
                productivityChart.data.datasets = [{
                    label: selectedProject,
                    data: filteredData.map(d => d.total_units || 0),
                    backgroundColor: getProjectColor(selectedProject),
                    borderWidth: 1
                }];
            }
            productivityChart.update();
        }

        // Update stats
        const totalUnits = filteredData.reduce((sum, d) => sum + (d.total_units || 0), 0);
        const avgUnits = totalEmps > 0 ? (totalUnits / totalEmps).toFixed(2) : 0;
        
        const statsHtml = `
            <div class="summary-stats">
                <div class="stat-item">
                    <h5>Total Employees</h5>
                    <p>${totalEmps}</p>
                </div>
                <div class="stat-item">
                    <h5>Total Work Units</h5>
                    <p>${totalUnits}</p>
                </div>
                <div class="stat-item">
                    <h5>Avg. Work Units</h5>
                    <p>${avgUnits}</p>
                </div>
            </div>
        `;
        let statsContainer = document.querySelector('.summary-stats');
        if (!statsContainer) {
            const chartSec = document.querySelector('.chart-section');
            if (chartSec) chartSec.insertAdjacentHTML('beforebegin', statsHtml);
        } else {
            statsContainer.outerHTML = statsHtml;
        }

        window.lastDetailedData = filteredData; // For drilldowns if they exist
    }

    // Better color palette generator
    function generateColorPalette(count) {
        const baseColors = [
            '#4CAF50', '#2196F3', '#FFC107', '#E91E63', '#9C27B0',
            '#FF5722', '#795548', '#607D8B', '#3F51B5', '#009688'
        ];
        
        const colors = [];
        for (let i = 0; i < count; i++) {
            colors.push(baseColors[i % baseColors.length]);
        }
        return colors;
    }

    // Add loading overlay function
    function showLoadingOverlay() {
        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content">
                <div class="loading-bars">
                    <div class="bar"></div>
                    <div class="bar"></div>
                    <div class="bar"></div>
                    <div class="bar"></div>
                    <div class="bar"></div>
                </div>
                <div class="loading-text">Please wait...</div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    function hideLoadingOverlay() {
        const overlay = document.querySelector('.loading-overlay');
        if (overlay) {
            overlay.classList.add('fade-out');
            setTimeout(() => overlay.remove(), 300);
        }
    }

    // Modify fetchSummaryData to use the loading overlay
        function fetchSummaryData() {
        showLoadingOverlay();
        
        const startDate = document.getElementById('summaryStartDate').value;
        const endDate = document.getElementById('summaryEndDate').value;
        const projectId = document.getElementById('projectSelect').value || 'all';

        return fetch('/api/v1/reports/run/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
            },
            body: JSON.stringify({
                report_key: 'productivity',
                date_from: startDate,
                date_to: endDate
            })
        })
            .then(response => response.json())
            .then(res => {
                const data = res.data || res;
                updateCharts(data, projectId);
            })
            .catch(error => console.error('Error fetching summary data:', error))
            .finally(() => {
                hideLoadingOverlay();
            });
    }

    // Initialize the dashboard
    function initializeDashboard() {
        initializeCharts();
        loadProjects().then(() => {
            // Set default date to today only on initial load
            const today = new Date().toISOString().split('T')[0];
            if (!document.getElementById('summaryStartDate').value) {
                document.getElementById('summaryStartDate').value = today;
            }
            if (!document.getElementById('summaryEndDate').value) {
                document.getElementById('summaryEndDate').value = today;
            }
            
            // Ensure 'all' is selected for projects
            document.getElementById('projectSelect').value = 'all';
            
            // Fetch initial data
            fetchSummaryData();
        });
    }

    // Update the summary tab click handler
    document.querySelector('a[href="#summaryreports"]').addEventListener('click', function() {
        if (!projectChart) {
            initializeDashboard();
        }
    });

    // Update loadProjects to return a promise with caching
    function loadProjects() {
        return MasterDataCache.getOrFetch('master_projects', '/api/v1/masters/emp_get_projects/')
            .then(projects => {
                const projectSelect = document.getElementById('projectSelect');
                projectSelect.innerHTML = ''; // Clear existing options
                
                // Add "All Projects" option
                const allProjectsOption = document.createElement('option');
                allProjectsOption.value = 'all';
                allProjectsOption.textContent = 'All Projects';
                projectSelect.appendChild(allProjectsOption);
                
                // Add individual projects
                projects.forEach(project => {
                    const option = document.createElement('option');
                    option.value = project.project_id;
                    option.textContent = project.project_name;
                    projectSelect.appendChild(option);
                });
                
                // Set default value to 'all'
                projectSelect.value = 'all';
            })
            .catch(error => console.error('Error loading projects:', error));
    }

    // Update the project select event listener
    document.getElementById('projectSelect').addEventListener('change', function() {
        fetchSummaryData();
    });

    // Update date input event listeners
    document.getElementById('summaryStartDate').addEventListener('change', function() {
        const startDate = this.value;
        const endDate = document.getElementById('summaryEndDate').value;
        if (endDate && startDate > endDate) {
            document.getElementById('summaryEndDate').value = startDate;
        }
        fetchSummaryData();
    });

    document.getElementById('summaryEndDate').addEventListener('change', function() {
        const endDate = this.value;
        const startDate = document.getElementById('summaryStartDate').value;
        if (startDate && endDate < startDate) {
            document.getElementById('summaryStartDate').value = endDate;
        }
        fetchSummaryData();
    });

    // Add this function to format dates
    function formatDate(dateString) {
        const date = new Date(dateString);
        const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        return `${days[date.getDay()]}, ${date.getDate()}/${date.getMonth() + 1}`;
    }

    // Add week navigation functionality
    let currentWeekStart = new Date();
    currentWeekStart.setDate(currentWeekStart.getDate() - 6);

    document.addEventListener('click', function(e) {
        if (e.target.id === 'prevWeekBtn' || e.target.closest('#prevWeekBtn')) {
            currentWeekStart.setDate(currentWeekStart.getDate() - 7);
            fetchSummaryData();
        } else if (e.target.id === 'nextWeekBtn' || e.target.closest('#nextWeekBtn')) {
            currentWeekStart.setDate(currentWeekStart.getDate() + 7);
            const today = new Date();
            if (currentWeekStart > today) {
                currentWeekStart.setDate(today.getDate() - 6);
                return;
            }
            fetchSummaryData();
        }
    });

    function showDetailedView(projectName) {
        const modal = document.createElement('div');
        modal.className = 'detailed-chart-modal';
        
        // Calculate project statistics
        const projectData = window.lastDetailedData.filter(item => item.project_name === projectName);
        const totalEmployees = projectData.length;
        const totalUnits = projectData.reduce((sum, item) => sum + parseInt(item.unit_cnt), 0);
        
        // Calculate dynamic height based on number of employees (minimum 400px, 30px per employee)
        const chartHeight = Math.max(400, totalEmployees * 30);
        
        modal.innerHTML = `
            <div class="detailed-chart-content">
                <div class="detailed-header">
                    <h3>${projectName.toUpperCase()} - EMPLOYEE DETAILS</h3>
                    <div class="detailed-actions">
                        <button class="refresh-detailed-btn" title="Refresh Data">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                        <span class="close-modal">&times;</span>
                    </div>
                </div>
                <div class="project-stats">
                    <div class="stat-item">
                        <h5>Total Employees</h5>
                        <p>${formatNumber(totalEmployees)}</p>
                    </div>
                    <div class="stat-item">
                        <h5>Total Work Units</h5>
                        <p>${formatNumber(totalUnits)}</p>
                    </div>
                </div>
                <div class="detailed-chart-container" style="height: ${chartHeight}px;">
                    <canvas id="detailedChart"></canvas>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        const closeBtn = modal.querySelector('.close-modal');
        closeBtn.onclick = () => modal.remove();

        // Add refresh functionality
        const refreshBtn = modal.querySelector('.refresh-detailed-btn');
        refreshBtn.onclick = () => {
            const spinner = refreshBtn.querySelector('i');
            spinner.classList.add('fa-spin');
            
            fetchSummaryData()
                .then(() => {
                    // Get fresh data for this project only
                    const updatedProjectData = window.lastDetailedData.filter(item => item.project_name === projectName);
                    updatedProjectData.sort((a, b) => b.unit_cnt - a.unit_cnt);

                    // Update statistics
                    const updatedTotalEmployees = updatedProjectData.length;
                    const updatedTotalUnits = updatedProjectData.reduce((sum, item) => sum + parseInt(item.unit_cnt), 0);

                    // Update statistics display
                    modal.querySelector('.stat-item:first-child p').textContent = formatNumber(updatedTotalEmployees);
                    modal.querySelector('.stat-item:last-child p').textContent = formatNumber(updatedTotalUnits);

                    // Update chart height
                    const newChartHeight = Math.max(400, updatedTotalEmployees * 30);
                    modal.querySelector('.detailed-chart-container').style.height = `${newChartHeight}px`;

                    // Update chart
                    detailedChart.data.labels = updatedProjectData.map(item => item.name.toUpperCase());
                    detailedChart.data.datasets[0].data = updatedProjectData.map(item => item.unit_cnt);
                    detailedChart.update();
                })
                .finally(() => {
                    spinner.classList.remove('fa-spin');
                });
        };

        // Create detailed chart with configuration
        const detailedChart = new Chart(document.getElementById('detailedChart'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Work Units',
                    data: [],
                    backgroundColor: '#4CAF50',
                    borderColor: '#4CAF50',
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    datalabels: {
                        anchor: 'end',
                        align: 'right',
                        offset: 2,
                        clamp: true,
                        formatter: function(value) {
                            return value;
                        },
                        font: {
                            weight: 'bold',
                            size: 12
                        },
                        padding: {
                            left: 5,
                            right: 5
                        },
                        borderRadius: 4
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'WORK UNITS',
                            font: {
                                weight: 'bold',
                                size: 14
                            }
                        },
                        ticks: {
                            font: {
                                weight: 'bold'
                            }
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'EMPLOYEES',
                            font: {
                                weight: 'bold',
                                size: 14
                            }
                        },
                        ticks: {
                            font: {
                                weight: 'bold'
                            },
                            callback: function(value) {
                                // Convert employee names to uppercase
                                return this.getLabelForValue(value).toUpperCase();
                            },
                            maxRotation: 0,
                            minRotation: 0
                        }
                    }
                },
                layout: {
                    padding: {
                        right: 30,
                        left: 20
                    }
                },
                onClick: (event, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const employeeName = detailedChart.data.labels[index];
                        const employeeData = projectData.find(item => item.name.toUpperCase() === employeeName);
                        
                        if (employeeData) {
                            showEmployeeWorkData(employeeData.emp_id, employeeName);
                        }
                    }
                }
            },
            plugins: [ChartDataLabels]
        });

        // Initial chart population
        projectData.sort((a, b) => b.unit_cnt - a.unit_cnt);
        detailedChart.data.labels = projectData.map(item => item.name.toUpperCase());
        detailedChart.data.datasets[0].data = projectData.map(item => item.unit_cnt);
        detailedChart.update();
    }

    function formatTimeToHHMMSS(seconds) {
        if (!seconds || isNaN(seconds)) return '-';
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        
        return [
            hours.toString().padStart(2, '0'),
            minutes.toString().padStart(2, '0'),
            remainingSeconds.toString().padStart(2, '0')
        ].join(':');
    }

    function showEmployeeWorkData(empId, empName) {
        const startDate = document.getElementById('summaryStartDate').value;
        const endDate = document.getElementById('summaryEndDate').value;
        
        // Create work data modal
        const workDataModal = document.createElement('div');
        workDataModal.className = 'work-data-modal';
        
        workDataModal.innerHTML = `
            <div class="work-data-content">
                <div class="work-data-header">
                    <h3>${empName}'s Work Details (${startDate} to ${endDate})</h3>
                    <span class="close-work-data">&times;</span>
                </div>
                <div class="work-data-table-container">
                    <table class="work-data-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Start Time</th>
                                <th>End Time</th>
                                <th>Project</th>
                                <th>Client Code</th>
                                <th>Work Type</th>
                                <th>Batch</th>
                                <th>Work Units</th>
                                <th>Total Time</th>
                                <th>Average Time</th>
                                <th>Review</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td colspan="11" class="loading-data">Loading...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        
        document.body.appendChild(workDataModal);

        // Add close functionality
        const closeBtn = workDataModal.querySelector('.close-work-data');
        closeBtn.onclick = () => workDataModal.remove();

        // Fetch and populate work data using the new route
        fetch('/api/v1/reports/run/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
            },
            body: JSON.stringify({
                report_key: 'summary',
                date_from: startDate,
                date_to: endDate,
                emp_id: empId
            })
        })
            .then(response => response.json())
            .then(res => {
                const data = res.data || res;
                const tbody = workDataModal.querySelector('tbody');
                if (!data || data.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="11">No data available</td></tr>';
                    return;
                }

                tbody.innerHTML = data.map(record => `
                    <tr>
                        <td>${record.date}</td>
                        <td>${record.start_time || '-'}</td>
                        <td>${record.end_time || '-'}</td>
                        <td>${record.project || '-'}</td>
                        <td>${record.client_code || '-'}</td>
                        <td>${record.work_type || '-'}</td>
                        <td>${record.batch || '-'}</td>
                        <td>${record.work_units || '0'}</td>
                        <td>${formatTimeToHHMMSS(record.total_time)}</td>
                        <td>${formatTimeToHHMMSS(record.average_time)}</td>
                        <td>${record.review || '-'}</td>
                    </tr>
                `).join('');
            })
            .catch(error => {
                console.error('Error fetching work data:', error);
                const tbody = workDataModal.querySelector('tbody');
                tbody.innerHTML = '<tr><td colspan="11">Error loading data</td></tr>';
            });
    }

    // Add this helper function at the top of your file
    function formatNumber(num) {
        return new Intl.NumberFormat('en-US').format(num);
    }


    window.showDetailedView = showDetailedView;  // Make the function globally accessible
    window.initializeDashboard = initializeDashboard;
    window.fetchSummaryData = fetchSummaryData;
    window.projectChart = null;  // Initialize global variable
});