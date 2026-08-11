let startTime, endTime, timerInterval, elapsedTime = 0;
let activeSessionId = null;

const startBtn = document.getElementById('start-btn');
const endPopup = document.getElementById('end-popup');
const endForm = document.getElementById('end-form');
const timerDisplay = document.getElementById('timer');
const projectSelect = document.getElementById('project-select');
const clientCodeSelect = document.getElementById('client-code-select');
const workTypeSelect = document.getElementById('work-type-select');
const batchInput = document.getElementById('batch');
// Helper to force-enable ProvenAir view and keep it active
function forceProvenAirViewActive() {
    try {
        const paTasksBtn = document.getElementById('paTasksBtn');
        const dateFilter = document.getElementById('date-filter');
        if (!paTasksBtn) return;
        // Ensure PA view is active
        if (!window.isPATodayView) {
            paTasksBtn.click();
        } else {
            // Refresh currently selected date's PA tasks
            if (dateFilter) {
                const ev = new Event('change');
                dateFilter.dispatchEvent(ev);
            }
        }
    } catch (e) {
        console.error('Failed to force ProvenAir view:', e);
    }
}

// Function to check if selections are made
function checkSelections() {
    if (projectSelect.value && clientCodeSelect.value && workTypeSelect.value) {
        startBtn.disabled = false;
    } else {
        startBtn.disabled = true;
    }
}

// Attach event listeners to dropdowns
[projectSelect, clientCodeSelect, workTypeSelect].forEach(select => {
    select.addEventListener('change', checkSelections);
});

// Format time as hh:mm:ss
function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;

    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
}

// Select the breaks content section
const breaksContent = document.querySelector('.breaks-content');

// Handle Start Button Click
startBtn.addEventListener('click', function () {
    if (startBtn.innerText === "Start") {
        // Disable the button immediately to prevent multiple clicks
        startBtn.disabled = true;
        
        startTime = new Date();

        // Hide Breaks Content Section
        breaksContent.style.display = 'none';

        // Show work session timer and update its display
        timerDisplay.style.display = 'inline-flex';
        timerDisplay.innerHTML = `
            <span class="work-status">Work In Progress</span>
            <i class="fas fa-clock" style="color: #e74c3c;"></i>
            <span class="time-value">00:00:00</span>
        `;

        // Prepare data for initial insertion
        const data = {
            project: projectSelect.value,
            client_code: clientCodeSelect.value,
            work_type: workTypeSelect.value,
            batch: batchInput.value || null,
            start_time: startTime.toISOString()
        };

        // Send initial data to server
                fetch('/api/v1/tracking/sessions/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(res => {
            const result = res.data || res;
            if (res.ok || result.id) {
                activeSessionId = result.id;
                startBtn.innerText = "End";
                startBtn.disabled = false; // Re-enable the button after successful start

                // Start the timer
                timerInterval = setInterval(function () {
                    elapsedTime = Math.floor((new Date() - startTime) / 1000);
                    timerDisplay.querySelector('.time-value').textContent = formatTime(elapsedTime);
                }, 1000);

                // Enable full screen mode
                toggleFullScreenMode(true);

                // Keep ProvenAir view active if the project is ProvenAir-AAR
                try {
                    const selectedOption = projectSelect.options[projectSelect.selectedIndex];
                    const selectedProjectName = selectedOption ? selectedOption.textContent : '';
                    if (selectedProjectName === 'ProvenAir-AAR') {
                        // Mark PA view active BEFORE any table refreshes
                        window.isPATodayView = true;
                        forceProvenAirViewActive();
                    } else {
                        // Immediately fetch and update the work data table for non-PA tasks
                        const today = new Date().toISOString().split('T')[0];
                        fetchWorkData(today);
                    }
                } catch (e) {}

                // Make sure the reports content is visible
                const reportsContent = document.querySelector('.reports-content');
                if (reportsContent) {
                    reportsContent.style.display = 'block';
                }
            } else {
                // If start failed, re-enable the button and show error
                startBtn.disabled = false;
                alert("Error: " + (res.error || "Unknown error"));
            }
        })
        .catch(error => {
            console.error("Error:", error);
            // Re-enable the button on error
            startBtn.disabled = false;
            alert("An error occurred while starting the work session. Please try again.");
        });
    } else {
        // When End is clicked
        endPopup.classList.remove('hidden');
        toggleFullScreenMode(false); // This will restore the layout
        // --- Reset the submit button to default state when end popup is shown ---
        const submitBtn = endForm.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-check"></i> Submit';
            // Focus the submit button so user can press Enter immediately
            submitBtn.focus();
        }
    }
});

// End Form Submission
endForm.addEventListener('submit', function (event) {
    event.preventDefault();

    const submitBtn = endForm.querySelector('button[type="submit"]');
    const originalBtnHTML = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';

    // Default workUnits to 1 and review to empty since they are removed from the form
    const workUnits = 1;
    const review = "";

    // Check for active work session if startTime is not set
    if (!startTime) {
        const formData = new FormData(endForm);
        const empComments = formData.get("employee_comments") || "";
        
        fetch('/api/v1/tracking/sessions/current/')
            .then(response => response.json())
            .then(res => {
                const data = res.data !== undefined ? res.data : res;
                if (data && data.id) {
                    activeSessionId = data.id;
                    startTime = new Date(data.start_time);
                    submitWorkData(review);
                } else {
                    if (window.activeAllocationIdToComplete) {
                        const allocId = window.activeAllocationIdToComplete;
                        const targetStatus = window.activeAllocationTargetStatus || "completed";
                        const isQC = targetStatus === "dispatch";
                        formData.append("status", targetStatus);
                        if (isQC) {
                            formData.append("qc_comments", empComments);
                        } else {
                            formData.append("employee_comments", empComments);
                        }
                        
                        window.activeAllocationIdToComplete = null;
                        fetch(`/api/v1/allocations/${allocId}/status/`, {
                            method: 'POST',
                            headers: { 'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '' },
                            body: formData
                        })
                        .then(res => res.json())
                        .then(payload => {
                            if (!payload.ok && payload.error) {
                                alert("Error completing order: " + payload.error.message);
                                submitBtn.disabled = false;
                                submitBtn.innerHTML = originalBtnHTML;
                                return;
                            }
                            alert("Order completed successfully.");
                            endPopup.classList.add('hidden');
                            location.reload();
                        }).catch(e => {
                            alert("Network error: " + e);
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalBtnHTML;
                        });
                    } else {
                        alert("Error: Start time is not available. Please refresh the page and try again.");
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalBtnHTML;
                    }
                }
            })
            .catch(error => {
                console.error('Error checking active session:', error);
                alert("Error: Could not verify work session. Please refresh the page and try again.");
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnHTML;
            });
    } else {
        submitWorkData(review);
    }
});

// Helper function to submit work data
function submitWorkData(review) {
    endTime = new Date();
    
    // Calculate total time considering pauses
    let totalTime;
    if (typeof sessionData !== 'undefined' && sessionData && sessionData.paused_elapsed) {
        // If the session was paused, calculate total time as:
        // (end_time - start_time) - (resumed_at - paused_at)
        const startToEnd = (endTime - startTime) / 1000; // Total time in seconds
        totalTime = startToEnd - sessionData.paused_elapsed;
    } else {
        // If not paused, use regular calculation
        totalTime = (endTime - startTime) / 1000;
    }
    
    const pagesEl = document.getElementById('pages');
    const pages = pagesEl ? pagesEl.value : "";

    const data = {
        project: projectSelect.value,
        client_code: clientCodeSelect.value,
        work_type: workTypeSelect.value,
        batch: batchInput.value || null,
        review: review,
        start_time: startTime.toISOString(),
        end_time: endTime.toISOString(),
        total_time: totalTime,
        pages: pages || null
    };

    const submitBtn = endForm.querySelector('button[type="submit"]');
    const originalBtnHTML = '<i class="fas fa-check"></i> Submit';

    // Send final data to server
    const formData = new FormData(endForm);
    formData.append('work_units', 1);
    formData.append('review', review);
    if (pages) formData.append('pages', pages);

    const empComments = formData.get("employee_comments") || "";

    fetch(`/api/v1/tracking/sessions/${activeSessionId}/end/`, {
        method: 'POST',
        headers: { 
            'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
        },
        body: formData
    })
    .then(response => response.json())
    .then(res => {
        const result = res.data || res;
        if (res.ok || result.id) {
            activeSessionId = null;

            // --- Check if we need to also complete an allocated order ---
            if (window.activeAllocationIdToComplete) {
                const allocId = window.activeAllocationIdToComplete;
                const targetStatus = window.activeAllocationTargetStatus || "completed";
                const isQC = targetStatus === "dispatch";
                
                // We reuse formData which already contains the files
                formData.append("status", targetStatus);
                if (isQC) {
                    formData.append("qc_comments", empComments || review);
                } else {
                    formData.append("employee_comments", empComments || review);
                }
                
                window.activeAllocationIdToComplete = null;
                fetch(`/api/v1/allocations/${allocId}/status/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '' },
                    body: formData
                })
                .then(res => res.json())
                .then(payload => {
                    if (!payload.ok && payload.error) {
                        alert("Warning: Tracking session saved, but failed to complete order: " + payload.error.message);
                    }
                    if (window.loadAllocatedOrders) window.loadAllocatedOrders();
                }).catch(e => console.error("Failed to complete allocation:", e));
            }

            alert("Work data submitted successfully.");
            
            // Reset form fields and enable them
            batchInput.value = '';
            // Fields removed: review, pages
            
            // Also reset file inputs and comments
            document.getElementById('chain-sheet').value = '';
            document.getElementById('search-package').value = '';
            document.getElementById('report').value = '';
            document.getElementById('employee-comments').value = '';
            // Enable all form fields
            projectSelect.disabled = false;
            clientCodeSelect.disabled = false;
            workTypeSelect.disabled = false;
            batchInput.disabled = false;
            
            // Reset timer and button states
            startTime = null;
            elapsedTime = 0;
            startBtn.innerText = "Start";
            startBtn.disabled = false;
            endPopup.classList.add('hidden');
            clearInterval(timerInterval);
            timerDisplay.style.display = 'none';

            // Show Breaks Content Section Again
            breaksContent.style.display = 'block';

            // Disable full screen mode
            toggleFullScreenMode(false);

            // Keep ProvenAir view active by default after submission and refresh PA list immediately
            try {
                // Determine selected project name at time of submission
                const selectedProjectOption = Array.from(projectSelect.options).find(opt => opt.value === data.project);
                const selectedProjectName = selectedProjectOption ? selectedProjectOption.textContent : '';
                if (selectedProjectName === 'ProvenAir-AAR' || window.isPATodayView) {
                    window.isPATodayView = true;
                    if (typeof window.refreshProvenAirTasksView === 'function') {
                        window.refreshProvenAirTasksView();
                    } else {
                        forceProvenAirViewActive();
                    }
                } else {
                    const today = new Date().toISOString().split('T')[0];
                    fetchWorkData(today);
                }
            } catch (e) {
                const today = new Date().toISOString().split('T')[0];
                fetchWorkData(today);
            }
        } else {
            alert("Error: " + (res.error || "Unknown error"));
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnHTML;
        }
    })
    .catch(error => {
        console.error("Error:", error);
        alert("An error occurred while submitting the work data. Please try again.");
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalBtnHTML;
    });
}

// Disable Start button on load
startBtn.disabled = true;

// Add new function to handle layout changes
function toggleFullScreenMode(isFullScreen) {
    const leftSection = document.querySelector('.left-section');
    const reportsContent = document.querySelector('.reports-content');
    const sideNav = document.querySelector('.side-nav ul');
    
    if (isFullScreen) {
        leftSection.style.display = 'none';
        reportsContent.style.width = '100%';
        
        // Add end button to side nav
        const endButton = document.createElement('li');
        endButton.innerHTML = `
            <a href="#" id="side-nav-end-btn" title="End Work Session">
                <i class="fas fa-stop"></i>
                <span class="nav-text">End Session</span>
            </a>
        `;
        sideNav.appendChild(endButton);
        
        // Add click handler for the side nav end button
        document.getElementById('side-nav-end-btn').addEventListener('click', (e) => {
            e.preventDefault();
            // Trigger the main start/end button click
            if (startBtn.innerText === "End") {
                startBtn.click();
            }
        });
    } else {
        const feedbackSection = document.getElementById('feedback-section');
        const isFeedbackActive = feedbackSection && feedbackSection.style.display === 'block';
        if (!isFeedbackActive) {
            leftSection.style.display = 'flex';
            reportsContent.style.width = '78%';
            reportsContent.style.display = 'block';
        }
        
        // Remove end button from side nav
        const endButton = document.getElementById('side-nav-end-btn');
        if (endButton) {
            endButton.parentElement.remove();
        }
    }
}

// Fetch work data for the logged-in user based on selected date
document.getElementById('date-filter').addEventListener('change', function () {
    const selectedDate = this.value;
    fetchWorkData(selectedDate);
});

// Function to fetch work data from the server
function fetchWorkData(date) {
    // Only suppress My Tasks updates while the ProvenAir view is actively selected
    const paBtn = document.getElementById('paTasksBtn');
    if (window.isPATodayView && paBtn && paBtn.classList.contains('active')) {
        return;
    }
    const userId = sessionStorage.getItem('emp_id');
    if (!userId) {
        // emp_id is embedded in the page via bootstrap-data — read it directly.
        try {
            const bootstrap = JSON.parse(document.getElementById('bootstrap-data')?.textContent || '{}');
            const empId = bootstrap?.user?.emp_id;
            if (empId) {
                sessionStorage.setItem('emp_id', empId);
                fetchWorkData(date);
            }
        } catch (e) { console.error('Could not read emp_id from bootstrap-data', e); }
        return;
    }

    // Update button text based on current view
    const pendingTasksBtn = document.getElementById('pendingTasksBtn');
    pendingTasksBtn.innerHTML = isPendingView ? 
        '<i class="fas fa-calendar-day"></i> Today\'s Tasks' : 
        `<i class="fas fa-tasks"></i> OverDue Tasks <span id="pendingCount" class="badge badge-light" style="display: none;">0</span>`;

        fetch(`/api/v1/tracking/sessions/?emp_id=${userId}&${isPendingView ? 'open=true' : 'today=true'}`)
        .then(response => response.json())
        .then(res => {
            const data = res.data || res;
            const tableBody = isPendingView ? document.getElementById('pending-work-data-body') : document.getElementById('work-data-body');
            
            if (tableBody) tableBody.innerHTML = ''; // Clear existing rows
            else return; // Don't proceed if table body not found
            
            if (!Array.isArray(data)) {
                console.error("Expected array from API, got:", typeof data);
                return;
            }
            
            data.forEach(row => {
                const tr = document.createElement('tr');
                
                // Format times
                const startTimeStr = row.start_time ? new Date(row.start_time).toLocaleTimeString('en-IN', { hour12: true }) : '';
                const endTimeStr = row.end_time ? new Date(row.end_time).toLocaleTimeString('en-IN', { hour12: true }) : (row.is_open ? (row.is_paused ? 'Paused' : 'In Progress') : 'Completed');
                const dateStr = row.start_time ? row.start_time.substring(0, 10) : '';

                let statusBadge = '';
                if (row.is_open) {
                    if (row.is_paused) {
                        statusBadge = `<span class="status-badge status-paused" title="Paused by ${row.paused_by || 'Unknown'} at ${row.paused_at ? new Date(row.paused_at).toLocaleString('en-IN') : 'Unknown'}">Paused</span>`;
                    } else {
                        statusBadge = '<span class="status-badge status-inprogress">In Progress</span>';
                    }
                } else {
                    statusBadge = '<span class="status-badge status-completed">Completed</span>';
                }

                let resumeBtn = '';
                if (isPendingView && row.is_open && row.is_paused) {
                    const st = row.start_time ? row.start_time.replace('T', ' ').replace('Z', '') : '';
                    resumeBtn = `
                        <button class="resume-btn" onclick="resumeWork('${st}', '${row.id}')" title="Resume Work">
                            <i class="fas fa-play"></i> Resume
                        </button>`;
                }

                const totalTimeFormatted = row.total_time ? new Date(row.total_time * 1000).toISOString().substr(11, 8) : '00:00:00';

                tr.innerHTML = `
                    <td>${dateStr}</td>
                    <td>${row.project || ''}</td>
                    <td>${row.client_name || row.client_code || ''}</td>
                    <td>${row.work_type || ''}</td>
                    <td>${row.batch || '-'}</td>
                    <td>${row.order_type || '-'}</td>
                    <td>${startTimeStr}</td>
                    <td>${endTimeStr}</td>
                    <td>${totalTimeFormatted}</td>
                    <td>${row.review || '-'}</td>
                    <td>${row.pages || '-'}</td>
                    <td>${statusBadge}</td>
                    ${isPendingView ? `<td>${resumeBtn}</td>` : ''}
                `;
                tableBody.appendChild(tr);
            });
        })
        .catch(error => console.error('Error fetching work data:', error));
}

// Attach click listener to "View" span
document.querySelectorAll('.status-badge.allocated.view-btn').forEach(viewBtn => {
    viewBtn.addEventListener('click', function (event) {
        event.stopPropagation(); // Prevent row click, if any
        const row = this.closest('tr');
        const allocationId = row.querySelector('td:last-child').textContent.trim();

        if (allocationId) {
            fetch(`/api/v1/allocations/${allocationId}/`)
                .then(response => response.json())
                .then(orderData => {
                    // Show in popup modal
                    displayOrderDetails(orderData);
                })
                .catch(error => {
                    console.error('Error fetching order allocation data:', error);
                });
        }
    });
});

// Fetch today's work data by default on page load
document.addEventListener('DOMContentLoaded', function () {
    const today = new Date().toISOString().split('T')[0];  // Get today's date in YYYY-MM-DD format
    document.getElementById('date-filter').value = today;
    fetchWorkData(today);  // Fetch today's data

});


// Add event listener for cancel button in end popup
document.getElementById('end-popup-cancel').addEventListener('click', function() {
    const endPopup = document.getElementById('end-popup');
    endPopup.classList.add('hidden');
    const pagesInput = document.getElementById('pages');
    if (pagesInput) pagesInput.value = '';
    // --- Also reset the submit button on cancel for extra safety ---
    const submitBtn = endForm.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-check"></i> Submit';
    }
});

// Add this function to show pause notification
function showPauseNotification(pauserName) {
    // Remove any existing notification
    const existingModal = document.querySelector('.pause-notification-modal');
    if (existingModal) {
        existingModal.remove();
    }

    const modal = document.createElement('div');
    modal.className = 'pause-notification-modal';
    modal.innerHTML = `
        <div class="pause-notification-content">
            <h3>
                <i class="fas fa-pause-circle"></i>
                Work Session Paused
            </h3>
            <p>Your work session has been paused by <strong>${pauserName}</strong></p>
            <button class="btn btn-primary">
                <i class="fas fa-check"></i>
                Acknowledge
            </button>
        </div>
    `;
    document.body.appendChild(modal);

    // Add fade out effect before removing
    const okButton = modal.querySelector('button');
    okButton.addEventListener('click', function() {
        modal.style.opacity = '0';
        modal.style.transition = 'opacity 0.3s ease-out';
        setTimeout(() => {
            modal.remove();
        }, 300);
    });

    // Add click outside to close
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.style.opacity = '0';
            modal.style.transition = 'opacity 0.3s ease-out';
            setTimeout(() => {
                modal.remove();
            }, 300);
        }
    });

    // Add escape key to close
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && document.querySelector('.pause-notification-modal')) {
            modal.style.opacity = '0';
            modal.style.transition = 'opacity 0.3s ease-out';
            setTimeout(() => {
                modal.remove();
            }, 300);
        }
    });
}

// Add function to resume work session
function resumeWorkSession(startTime) {
    // The startTime is coming in HH:MM:SS format, we need to add the date part
    const [hours, minutes, seconds] = startTime.split(':');
    const today = new Date().toISOString().split('T')[0]; // Get current date in YYYY-MM-DD format
    const formattedStartTime = `${today} ${hours}:${minutes}:${seconds}`;
    
    fetch(`/resume_work_entry/${sessionStorage.getItem('emp_id')}/${encodeURIComponent(formattedStartTime)}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            sessionData = data.data; // Store session data globally
            
            // Set project and form fields
            projectSelect.value = sessionData.project;
            
            // First fetch and set client codes
            fetch(`/get_client_codes_for_project?project=${sessionData.project}`)
                .then(response => response.json())
                .then(clientData => {
                    // Clear existing options
                    clientCodeSelect.innerHTML = '<option value="">Select Client Code</option>';
                    
                    // Add new options
                    clientData.client_codes.forEach(code => {
                        const option = document.createElement('option');
                        option.value = code;
                        option.textContent = code;
                        clientCodeSelect.appendChild(option);
                    });
                    
                    // Set the client code
                    clientCodeSelect.value = sessionData.client_code;
                    
                    // Now fetch and set work types
                    return fetch(`/get_work_types_for_client_code?client_code=${sessionData.client_code}`);
                })
                .then(response => response.json())
                .then(workTypeData => {
                    // Clear existing options
                    workTypeSelect.innerHTML = '<option value="">Select Work Type</option>';
                    
                    // Add new options
                    workTypeData.work_types.forEach(type => {
                        const option = document.createElement('option');
                        option.value = type;
                        option.textContent = type;
                        workTypeSelect.appendChild(option);
                    });
                    
                    // Set the work type
                    workTypeSelect.value = sessionData.work_type;
                    
                    // Set batch value
                    batchInput.value = sessionData.batch || '';
                    
                    // Disable form fields
                    projectSelect.disabled = true;
                    clientCodeSelect.disabled = true;
                    workTypeSelect.disabled = true;
                    batchInput.disabled = true;
                    
                    // Update button state
                    startBtn.innerText = "End";
                    startBtn.disabled = false;
                    
                    // Show timer
                    timerDisplay.style.display = 'inline-flex';
                    timerDisplay.innerHTML = `
                        <span class="work-status">Work In Progress</span>
                        <i class="fas fa-clock" style="color: #e74c3c;"></i>
                        <span class="time-value">${formatTime(sessionData.paused_elapsed)}</span>
                    `;

                    // Start timer considering the elapsed time before pause
                    activeSessionId = sessionData.id;
                    startTime = new Date(sessionData.start_time);
                    const pausedElapsed = sessionData.paused_elapsed || 0;
                    
                    // Clear any existing interval
                    if (timerInterval) {
                        clearInterval(timerInterval);
                    }

                    // Start new timer
                    timerInterval = setInterval(function () {
                        const currentTime = new Date();
                        const resumedAt = new Date(sessionData.resumed_at);
                        const timeSinceResume = Math.floor((currentTime - resumedAt) / 1000);
                        const totalElapsed = pausedElapsed + timeSinceResume;
                        timerDisplay.querySelector('.time-value').textContent = formatTime(totalElapsed);
                    }, 1000);

                    // Hide breaks content
                    breaksContent.style.display = 'none';

                    // Enable full screen mode
                    toggleFullScreenMode(true);

                    // Keep ProvenAir view active for ProvenAir-AAR, otherwise refresh My Tasks
                    try {
                        const selectedOption = projectSelect.options[projectSelect.selectedIndex];
                        const selectedProjectName = selectedOption ? selectedOption.textContent : '';
                        if (selectedProjectName === 'ProvenAir-AAR') {
                            window.isPATodayView = true;
                            forceProvenAirViewActive();
                        } else {
                            const today = new Date().toISOString().split('T')[0];
                            fetchWorkData(today);
                        }
                    } catch (e) {
                        const today = new Date().toISOString().split('T')[0];
                        fetchWorkData(today);
                    }
                });
        } else {
            alert('Failed to resume work session: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while resuming the work session');
    });
}

// Add this function near the top of userdashboard.js
function resetDashboard() {
    // Reset form fields and enable them
    projectSelect.disabled = false;
    clientCodeSelect.disabled = false;
    workTypeSelect.disabled = false;
    batchInput.disabled = false;
    batchInput.value = '';
    
    // Reset selections
    projectSelect.value = '';
    clientCodeSelect.innerHTML = '<option value="">Select Client Code</option>';
    workTypeSelect.innerHTML = '<option value="">Select Work Type</option>';
    
    // Reset timer and button states
    startTime = null;
    elapsedTime = 0;
    startBtn.innerText = "Start";
    startBtn.disabled = true; // Disabled until selections are made
    if (timerInterval) {
        clearInterval(timerInterval);
    }
    timerDisplay.style.display = 'none';

    // Ensure normal layout
    const feedbackSection = document.getElementById('feedback-section');
    const isFeedbackActive = feedbackSection && feedbackSection.style.display === 'block';
    if (!isFeedbackActive) {
        document.querySelector('.left-section').style.display = 'flex';
        document.querySelector('.reports-content').style.width = '78%';
        document.querySelector('.reports-content').style.display = 'block';
    }
    
    // Remove end button if it exists
    const endButton = document.getElementById('side-nav-end-btn');
    if (endButton && endButton.parentElement) {
        endButton.parentElement.remove();
    }

    // Show Breaks Content Section
    breaksContent.style.display = 'block';

    // Refresh the work data table
    const today = new Date().toISOString().split('T')[0];
    fetchWorkData(today);
}

// Add this at the beginning of the file, after DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // Seed emp_id from the page's bootstrap blob immediately (replaces /get_current_user)
    if (!sessionStorage.getItem('emp_id')) {
        try {
            const bootstrap = JSON.parse(document.getElementById('bootstrap-data')?.textContent || '{}');
            const empId = bootstrap?.user?.emp_id;
            if (empId) sessionStorage.setItem('emp_id', empId);
        } catch (e) {}
    }

    // Check for active work session on page load using the correct API endpoint.
    fetch('/api/v1/tracking/sessions/current/')
        .then(response => response.json())
        .then(payload => {
            const data = payload.data !== undefined ? payload.data : payload;
            if (data && data.start_time) {
                activeSessionId = data.id;
                startTime = new Date(data.start_time);
                if (timerDisplay.style.display !== 'none') {
                    timerInterval = setInterval(function () {
                        elapsedTime = Math.floor((new Date() - startTime) / 1000);
                        timerDisplay.querySelector('.time-value').textContent = formatTime(elapsedTime);
                    }, 1000);
                }
            }
        })
        .catch(error => console.error('Error checking active session:', error));
});

// Add cleanup when page unloads
window.addEventListener('beforeunload', function() {
    // any previous cleanup
});

// Add this function after the existing variable declarations
function isBreakActive() {
    const savedBreak = localStorage.getItem("break_state");
    return savedBreak !== null;
}

// Add this function after the existing variable declarations
function isWorkSessionActive() {
    return startBtn.innerText === "End";
}

// --- Auto-start Work Sessions for Allocated Orders ---
window.startAllocatedWorkSession = async function(allocData) {
    // End any existing session first
    if (startBtn.innerText === "End") {
        toast.show("Please end your current work session first.", {type: "warning"});
        return false;
    }

    const data = {
        project: allocData.project,
        client_code: allocData.client_code,
        work_type: allocData.work_type,
        batch: allocData.batch,
        allocation_id: allocData.allocation_id,
        start_time: new Date().toISOString()
    };

    try {
        const res = await fetch('/api/v1/tracking/sessions/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
            },
            body: JSON.stringify(data)
        });
        const payload = await res.json();
        const result = payload.data || payload;
        
        if (payload.ok || result.id) {
            activeSessionId = result.id;
            window.activeAllocationId = allocData.allocation_id;
            
            startTime = new Date();
            startBtn.innerText = "End";
            startBtn.disabled = false;
            
            timerInterval = setInterval(function () {
                elapsedTime = Math.floor((new Date() - startTime) / 1000);
                timerDisplay.querySelector('.time-value').textContent = formatTime(elapsedTime);
            }, 1000);
            toggleFullScreenMode(true);
            return true;
        } else {
            alert("Error: " + (payload.error || "Unknown error"));
            return false;
        }
    } catch (e) {
        console.error("Failed to start session", e);
        return false;
    }
};

window.completeAllocatedOrder = function(allocationId, targetStatus = "completed") {
    window.activeAllocationIdToComplete = allocationId;
    window.activeAllocationTargetStatus = targetStatus;
    
    const endPopup = document.getElementById('end-popup');
    if (endPopup) {
        endPopup.classList.remove('hidden');
        
        const endForm = document.getElementById('end-form');
        if (endForm) {
            const submitBtn = endForm.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-check"></i> Submit';
                submitBtn.focus();
            }
        }
    }
};
