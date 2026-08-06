$(document).ready(function() {
    // Initialize Select2
    $('#projectSelect').select2({
        width: '100%',
        dropdownParent: $('#targetModal'),
        placeholder: 'Select a project'
    });

    // Load initial data
    loadProjects();
    loadTargets();
    loadActiveSessions();

    // Sidebar toggle
    $('#sidebarToggle').on('click', function() {
        $('.sidebar').toggleClass('active');
    });

    // Close sidebar when clicking outside on mobile
    $(document).on('click', function(e) {
        if ($(window).width() <= 1024) {
            if (!$(e.target).closest('.sidebar').length && !$(e.target).closest('#sidebarToggle').length) {
                $('.sidebar').removeClass('active');
            }
        }
    });

    // Navigation
    $('.nav-item').on('click', function() {
        const section = $(this).data('section');
        if (!section) return; // Skip for regular links (like Dashboard)

        $('.nav-item').removeClass('active');
        $(this).addClass('active');
        $('.content-section').removeClass('active');
        $(`#${section}`).addClass('active');

        // Update page title
        updatePageTitle(section);

        // Load section data if needed
        if (section === 'sessions') {
            loadActiveSessions();
        } else if (section === 'users') {
            loadAllUsers();
        }
    });

    // Search functionality
    $('#sessionSearch').on('input', function() {
        filterSessions($(this).val().toLowerCase());
    });

    $('#userSearch').on('input', function() {
        filterUsers($(this).val().toLowerCase());
    });

    // Refresh sessions button
    $('#refreshSessions').on('click', function() {
        const button = $(this);
        button.find('i').addClass('fa-spin');
        loadActiveSessions().always(function() {
            setTimeout(() => button.find('i').removeClass('fa-spin'), 500);
        });
    });

    // Refresh users button
    $('#refreshUsers').on('click', function() {
        const button = $(this);
        button.find('i').addClass('fa-spin');
        loadAllUsers().always(function() {
            setTimeout(() => button.find('i').removeClass('fa-spin'), 500);
        });
    });

    // Modal controls
    $('.close-btn, #cancelTargetBtn').on('click', function() {
        $('#targetModal').fadeOut(300);
    });

    // Add Target Button
    $('#addTargetBtn').on('click', function() {
        resetForm();
        $('#targetModal').fadeIn(300);
    });

    // Target Form Submit
    $('#targetForm').on('submit', function(e) {
        e.preventDefault();
        const projectSelect = $('#projectSelect');
        const selectedOption = projectSelect.find('option:selected');
        
        const data = {
            project_id: projectSelect.val(),
            project_name: selectedOption.text(),
            target: $('#targetValue').val()
        };

        if (!data.project_id || !data.target) {
            showToast('Please fill in all required fields', 'error');
            return;
        }

        saveTarget(data);
    });

    // System actions
    $('#clearCacheBtn').on('click', function() {
        if (confirm('Are you sure you want to clear the cache? This may affect application performance temporarily.')) {
            clearCache();
        }
    });

    $('#exportDataBtn').on('click', exportAllData);

    // Theme preview hover effect
    $('.theme-option').hover(
        function() { $(this).addClass('hover'); },
        function() { $(this).removeClass('hover'); }
    );

    // Font size slider
    $('#fontSize').on('input', function() {
        updateFontSizePreview($(this).val());
    });
});

// Update page title based on section
function updatePageTitle(section) {
    const titles = {
        targets: 'Project Targets',
        sessions: 'Active Sessions',
        users: 'Manage Users',
        system: 'System Settings'
    };
    $('#pageTitle').text(titles[section] || 'Settings');
}

// Load projects into dropdown
function loadProjects() {
    try {
    $.get('/api/v1/masters/emp_get_projects/')
            .done(function(response) {
                try {
                    // Ensure response is valid
                    if (!response || typeof response !== 'object') {
                        throw new Error('Invalid response from server');
                    }

                    const data = response.projects || (Array.isArray(response) ? response : (response.results || []));
            const select = $('#projectSelect');
            select.empty().append('<option value="">Select Project</option>');
            
            data.forEach(project => {
                        if (project && project.project_id && project.project_name) {
                            select.append(`<option value="${project.project_id}">${escapeHtml(project.project_name)}</option>`);
                        }
            });
                } catch (err) {
                    console.error('Error processing projects:', err);
                    showToast('Error loading projects: ' + err.message, 'error');
                }
        })
        .fail(function(xhr, status, error) {
                showToast('Error loading projects: ' + (error || 'Unknown error'), 'error');
        });
    } catch (err) {
        console.error('Error in loadProjects:', err);
        showToast('Error loading projects', 'error');
    }
}

// Load existing targets
function loadTargets() {
    try {
        const grid = $('.targets-grid');
        
        // Show loading state
        grid.html(`
            <div class="empty-state initial-load">
                <i class="fas fa-spinner fa-spin fa-3x"></i>
                <p>Loading targets...</p>
            </div>
        `);

        $.get('/api/v1/tracking/targets/')
            .done(function(response) {
                try {
                    // Ensure response is valid
                    if (!response || typeof response !== 'object') {
                        throw new Error('Invalid response from server');
                    }

                    const data = response.projects || (Array.isArray(response) ? response : (response.results || []));
                    grid.empty();
            
                    if (data.length === 0) {
                        grid.html(`
                            <div class="empty-state">
                                <i class="fas fa-bullseye fa-3x"></i>
                                <p>No targets set yet</p>
                            </div>
                        `);
                        return;
                    }

                    data.forEach(target => {
                        if (isValidTarget(target)) {
                            grid.append(createTargetCard(target));
                        }
                    });
                } catch (err) {
                    console.error('Error processing targets:', err);
                    showToast('Error loading targets: ' + err.message, 'error');
                    grid.html(`
                        <div class="empty-state">
                            <i class="fas fa-exclamation-circle fa-3x"></i>
                            <p>Error loading targets</p>
                        </div>
                    `);
                }
            })
            .fail(function(xhr, status, error) {
                showToast('Error loading targets: ' + (error || 'Unknown error'), 'error');
                grid.html(`
                    <div class="empty-state">
                        <i class="fas fa-exclamation-circle fa-3x"></i>
                        <p>Error loading targets</p>
                    </div>
                `);
            });
    } catch (err) {
        console.error('Error in loadTargets:', err);
        showToast('Error loading targets', 'error');
    }
}

// Validate target object
function isValidTarget(target) {
    return target && 
           typeof target === 'object' && 
           target.id && 
           typeof target.project_name === 'string' &&
           !isNaN(parseInt(target.target));
}

// Create target card HTML
function createTargetCard(target) {
    try {
        if (!isValidTarget(target)) {
            console.error('Invalid target data:', target);
            return '';
        }

        const date = target.set_at ? new Date(target.set_at).toLocaleDateString() : 'N/A';
        const targetValue = parseInt(target.target) || 0;

        return `
            <div class="project-card" data-id="${target.id}">
                <div class="project-header">
                    <div class="project-icon">
                            <i class="fas fa-bullseye"></i>
                        </div>
                    <h3 class="project-name">${escapeHtml(target.project_name)}</h3>
                                </div>
                <div class="project-info">
                    <div class="target-value">Daily Target: ${targetValue}</div>
                    <div class="target-date">
                        <i class="far fa-calendar"></i>
                        Set on ${date}
                                </div>
                            </div>
                            <div class="card-actions">
                    <button class="btn-secondary" onclick="editTarget(${target.id})">
                        <i class="fas fa-edit"></i>
                        Edit
                                </button>
                    <button class="btn-secondary" onclick="deleteTarget(${target.id})">
                        <i class="fas fa-trash"></i>
                        Delete
                                </button>
                            </div>
                        </div>
        `;
    } catch (err) {
        console.error('Error creating target card:', err);
        return '';
    }
}

// Save target
function saveTarget(data) {
    try {
        if (!isValidTargetData(data)) {
            showToast('Invalid target data', 'error');
            return;
        }

    $.ajax({
        url: '/api/v1/tracking/targets/',
        method: 'POST',
        contentType: 'application/json',
            data: JSON.stringify(data),
        success: function(response) {
            $('#targetModal').fadeOut(300);
            showToast('Target saved successfully');
            loadTargets();
            resetForm();
        },
        error: function(xhr, status, error) {
                showToast('Error saving target: ' + (xhr.responseJSON?.error || error || 'Unknown error'), 'error');
            }
        });
    } catch (err) {
        console.error('Error saving target:', err);
        showToast('Error saving target', 'error');
        }
}

// Validate target data for saving
function isValidTargetData(data) {
    return data && 
           typeof data === 'object' &&
           data.project_id &&
           typeof data.project_name === 'string' &&
           !isNaN(parseInt(data.target));
}

// Edit target
function editTarget(targetId) {
    try {
        if (!targetId) {
            showToast('Invalid target ID', 'error');
            return;
        }

    $.get(`/api/v1/tracking/targets/${targetId}/`)
        .done(function(target) {
                try {
                    if (!isValidTarget(target)) {
                        throw new Error('Invalid target data received');
                    }

            $('#projectSelect').val(target.project_id).trigger('change');
                    $('#targetValue').val(target.target || '');
            $('#targetForm').data('edit-id', targetId);
            $('#targetModal').fadeIn(300);
                } catch (err) {
                    console.error('Error processing target data:', err);
                    showToast(err.message, 'error');
                }
        })
        .fail(function(xhr, status, error) {
                showToast('Error loading target details: ' + (error || 'Unknown error'), 'error');
        });
    } catch (err) {
        console.error('Error editing target:', err);
        showToast('Error editing target', 'error');
    }
}

// Delete target
function deleteTarget(targetId) {
    try {
        if (!targetId) {
            showToast('Invalid target ID', 'error');
            return;
        }

    if (confirm('Are you sure you want to delete this target?')) {
        $.ajax({
            url: `/api/v1/tracking/targets/${targetId}/`,
            method: 'DELETE',
            success: function() {
                showToast('Target deleted successfully');
                loadTargets();
            },
            error: function(xhr, status, error) {
                    showToast('Error deleting target: ' + (error || 'Unknown error'), 'error');
            }
        });
        }
    } catch (err) {
        console.error('Error deleting target:', err);
        showToast('Error deleting target', 'error');
    }
}

// Reset form
function resetForm() {
    try {
    $('#targetForm')[0].reset();
    $('#projectSelect').val('').trigger('change');
    $('#targetForm').removeData('edit-id');
    } catch (err) {
        console.error('Error resetting form:', err);
    }
}

// Save email settings
function saveEmailSettings(data) {
    $.post('/api/settings/notifications', data, function(response) {
        showToast('Notification settings saved successfully');
    }).fail(function(error) {
        showToast('Error saving notification settings', true);
    });
}

// Save display settings
function saveDisplaySettings(data) {
    $.post('/api/settings/display', data, function(response) {
        showToast('Display settings saved successfully');
        applyDisplaySettings(data);
    }).fail(function(error) {
        showToast('Error saving display settings', true);
    });
}

// System functions
function resetLoginStatus() {
    $.post('/api/settings/reset-login', function(response) {
        showToast('Login status reset successfully');
    }).fail(function(error) {
        showToast('Error resetting login status', true);
    });
}

function forceLogoutAllUsers() {
    $.post('/api/settings/force-logout', function(response) {
        showToast('All users have been logged out');
    }).fail(function(error) {
        showToast('Error logging out users', true);
    });
}

function exportAllData() {
    window.location.href = '/api/settings/export-data';
}

function clearCache() {
    $.post('/api/settings/clear-cache', function(response) {
        showToast('Cache cleared successfully');
    }).fail(function(error) {
        showToast('Error clearing cache', true);
    });
}

// UI Helpers
function showToast(message, type = 'success') {
    try {
    const toast = $('#toast');
        toast.removeClass('error success').addClass(type);
        $('#toastMessage').text(message || 'An error occurred');
    
    toast.fadeIn(300);
    setTimeout(() => toast.fadeOut(300), 3000);
    } catch (err) {
        console.error('Error showing toast:', err);
    }
}

function updateFontSizePreview(size) {
    const preview = $('.font-size-preview');
    preview.css('font-size', `${size}px`);
}

// Apply display settings
function applyDisplaySettings(settings) {
    document.documentElement.setAttribute('data-theme', settings.theme);
    document.documentElement.style.fontSize = `${settings.fontSize}px`;
}

// Filter sessions
function filterSessions(searchText = '') {
    try {
        const items = $('.session-item');
        
        items.each(function() {
            const item = $(this);
            const nameElement = item.find('h4');
            const name = nameElement.length ? nameElement.text() : '';
            
            // Safely convert searchText to lowercase, defaulting to empty string if undefined
            const searchLower = (searchText || '').toLowerCase();
            const nameLower = name.toLowerCase();
            
            const matchesSearch = !searchLower || nameLower.includes(searchLower);
            
            item.toggle(matchesSearch);
        });

        // Show/hide empty state
        const visibleItems = items.filter(':visible').length;
        if (visibleItems === 0) {
            if (!$('.empty-state').length) {
                $('.sessions-list').append(`
                    <div class="empty-state">
                        <i class="fas fa-search fa-3x"></i>
                        <p>No matching sessions found</p>
                    </div>
                `);
            }
        } else {
            $('.empty-state').remove();
        }
    } catch (err) {
        console.error('Error filtering sessions:', err);
        showToast('Error filtering sessions', 'error');
    }
}

// Load active sessions
function loadActiveSessions() {
    return $.get('/api/v1/tracking/sessions/active/')
        .done(function(data) {
            const sessionsList = $('.sessions-list');
            sessionsList.empty();
            
            if (!Array.isArray(data) || data.length === 0) {
                sessionsList.append(`
                    <div class="empty-state">
                        <i class="fas fa-users fa-3x"></i>
                        <p>No active sessions found</p>
                    </div>
                `);
                return;
            }

            data.forEach(user => {
                if (!user || !user.emp_id || !user.name) return;
                
                const name = escapeHtml(user.name);
                const empId = escapeHtml(user.emp_id);
                const role = escapeHtml(user.role || 'Employee');
                
                sessionsList.append(`
                    <div class="session-item" data-emp-id="${empId}">
                        <div class="session-info">
                            <div class="session-avatar">
                                ${name.charAt(0).toUpperCase()}
                            </div>
                            <div class="session-details">
                                <h4>${name}</h4>
                                <div class="session-meta">
                                    <span>${empId}</span>
                                    <span>${role}</span>
                                </div>
                            </div>
                        </div>
                        <div class="session-actions">
                            <span class="session-badge active">
                                <i class="fas fa-circle"></i>
                                Active
                            </span>
                            <button class="btn-danger btn-sm" onclick="showResetConfirmation('${empId}', '${name}')">
                                <i class="fas fa-power-off"></i>
                                Reset
                            </button>
                        </div>
                    </div>
                `);
            });

            // Reapply current filters
            const searchValue = $('#sessionSearch').val();
            const searchText = searchValue ? searchValue.toLowerCase() : '';
            filterSessions(searchText);
        })
        .fail(function(xhr, status, error) {
            showToast('Error loading active sessions: ' + (error || 'Unknown error'), 'error');
        });
}

// Show reset confirmation modal
function showResetConfirmation(empId, name) {
    if (!empId || !name) {
        showToast('Invalid session data', 'error');
        return;
    }

    const modal = $('#resetSessionModal');
    modal.find('.modal-message').text(`Are you sure you want to reset the session for ${name}?`);
    
    // Update confirm button click handler
    $('#confirmResetBtn').off('click').on('click', function() {
        resetUserSession(empId);
        modal.fadeOut(300);
    });
    
    modal.fadeIn(300);
}

// Reset user session
function resetUserSession(empId) {
    if (!empId) {
        showToast('Invalid employee ID', 'error');
        return;
    }

    $.ajax({
        url: `/api/reset-login/${empId}`,
        method: 'POST',
        success: function(response) {
            showToast('Session reset successfully');
            loadActiveSessions(); // Reload the sessions list
        },
        error: function(xhr, status, error) {
            showToast('Error resetting session: ' + (xhr.responseJSON?.error || error || 'Unknown error'), 'error');
        }
    });
}

// Load all users
function loadAllUsers() {
    return $.get('/api/v1/auth/employees/')
        .done(function(data) {
            const usersList = $('.users-list');
            usersList.empty();
            
            if (!Array.isArray(data) || data.length === 0) {
                usersList.append(`
                    <div class="empty-state">
                        <i class="fas fa-users fa-3x"></i>
                        <p>No users found</p>
                    </div>
                `);
                return;
            }

            data.forEach(user => {
                if (!user || !user.emp_id || !user.name) return;
                
                const name = escapeHtml(user.name);
                const empId = escapeHtml(user.emp_id);
                const role = escapeHtml(user.role || 'Employee');
                const status = escapeHtml(user.status || 'Active');
                
                usersList.append(`
                    <div class="session-item user-item" data-emp-id="${empId}">
                        <div class="session-info">
                            <div class="session-avatar">
                                ${name.charAt(0).toUpperCase()}
                            </div>
                            <div class="session-details">
                                <h4>${name}</h4>
                                <div class="session-meta">
                                    <span>${empId}</span>
                                    <span>${role}</span>
                                </div>
                            </div>
                        </div>
                        <div class="session-actions">
                            <span class="status-badge ${status.toLowerCase()}">${status}</span>
                            <button class="btn-danger btn-sm" onclick="showResetPasswordConfirmation('${empId}', '${name}')">
                                <i class="fas fa-key"></i>
                                Reset Password
                            </button>
                        </div>
                    </div>
                `);
            });

            // Reapply current filters
            const searchValue = $('#userSearch').val();
            const searchText = searchValue ? searchValue.toLowerCase() : '';
            filterUsers(searchText);
        })
        .fail(function(xhr, status, error) {
            showToast('Error loading users: ' + (error || 'Unknown error'), 'error');
        });
}

// Filter users
function filterUsers(searchText = '') {
    try {
        const items = $('.user-item');
        
        items.each(function() {
            const item = $(this);
            const nameElement = item.find('h4');
            const name = nameElement.length ? nameElement.text() : '';
            
            // Safely convert searchText to lowercase, defaulting to empty string if undefined
            const searchLower = (searchText || '').toLowerCase();
            const nameLower = name.toLowerCase();
            
            const matchesSearch = !searchLower || nameLower.includes(searchLower);
            
            item.toggle(matchesSearch);
        });

        // Show/hide empty state
        const visibleItems = items.filter(':visible').length;
        if (visibleItems === 0 && items.length > 0) {
            if (!$('.users-list .empty-state').length) {
                $('.users-list').append(`
                    <div class="empty-state">
                        <i class="fas fa-search fa-3x"></i>
                        <p>No matching users found</p>
                    </div>
                `);
            }
        } else {
            $('.users-list .empty-state').remove();
        }
    } catch (err) {
        console.error('Error filtering users:', err);
        showToast('Error filtering users', 'error');
    }
}

// Show reset password confirmation modal
function showResetPasswordConfirmation(empId, name) {
    if (!empId || !name) {
        showToast('Invalid user data', 'error');
        return;
    }

    const modal = $('#resetPasswordModal');
    modal.find('.modal-message').text(`Are you sure you want to reset the password for ${name} to 1122?`);
    
    // Update confirm button click handler
    $('#confirmResetPasswordBtn').off('click').on('click', function() {
        resetUserPassword(empId);
        modal.fadeOut(300);
    });
    
    modal.fadeIn(300);
}

// Reset user password
function resetUserPassword(empId) {
    if (!empId) {
        showToast('Invalid employee ID', 'error');
        return;
    }

    $.ajax({
        url: `/api/reset-user-password/${empId}`,
        method: 'POST',
        success: function(response) {
            showToast('Password reset successfully to 1122');
            loadAllUsers(); // Reload the users list
        },
        error: function(xhr, status, error) {
            showToast('Error resetting password: ' + (xhr.responseJSON?.error || error || 'Unknown error'), 'error');
        }
    });
}

// Escape HTML to prevent XSS
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return '';
    try {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    } catch (err) {
        console.error('Error escaping HTML:', err);
        return '';
    }
} 