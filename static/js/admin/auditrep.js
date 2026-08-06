// Global state variables
window.isGraphMode = false;
window.feedbackChart = null;
window.productivityChart = null;

// Global variables
let currentPage = 1;
let entriesPerPage = 10;
let totalEntries = 0;
let sortColumn = 'processed_date';
let sortOrder = 'desc';
let currentData = [];
let searchTerm = '';
let selectedProject = '';
let selectedWorkType = '';
let isProjectView = false;
let selectedFeedbackRecorded = '';
let currentImageIndex = 0;
let imagesList = [];

// Default date ranges
let defaultDateRange = {
    graph: {
        start: null,
        end: null
    },
    table: {
        start: null,
        end: null
    }
};

// Get DOM elements
const auditTable = document.querySelector('.audit-table tbody');
const entriesDropdown = document.querySelector('.audit-entries-dropdown');
const searchField = document.querySelector('.audit-search-field');
const clearSearch = document.querySelector('.audit-clear-search');
const refreshButton = document.querySelector('.audit-refresh-button');
const datePicker = document.getElementById('auditDate');
const modal = document.getElementById('auditDetailModal');
const closeBtn = document.querySelector('.auditclose-btn');
const auditStartDate = document.getElementById('auditStartDate');
const auditEndDate = document.getElementById('auditEndDate');
const auditDownloadFormat = document.getElementById('auditDownloadFormat');
const auditDownloadButton = document.getElementById('auditDownloadButton');

// Function to set default dates based on view mode
function setDefaultDates(useGraphMode = false) {
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    
    if (useGraphMode) {
        // For graph view: 1st of current month to today
        const firstDayOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
        const firstDayStr = firstDayOfMonth.toISOString().split('T')[0];
        
        if (auditStartDate && (!auditStartDate.value || defaultDateRange.graph.start === null)) {
            auditStartDate.value = firstDayStr;
            defaultDateRange.graph.start = firstDayStr;
        }
        if (auditEndDate && (!auditEndDate.value || defaultDateRange.graph.end === null)) {
            auditEndDate.value = todayStr;
            defaultDateRange.graph.end = todayStr;
        }
    } else {
        // For table view: today's date for both
        if (auditStartDate && (!auditStartDate.value || defaultDateRange.table.start === null)) {
            auditStartDate.value = todayStr;
            defaultDateRange.table.start = todayStr;
        }
        if (auditEndDate && (!auditEndDate.value || defaultDateRange.table.end === null)) {
            auditEndDate.value = todayStr;
            defaultDateRange.table.end = todayStr;
        }
    }
}

// Function to fetch and update audit data
function fetchAuditData() {
    const searchQuery = searchField.value;
    const fromDate = auditStartDate ? auditStartDate.value : (window.isGraphMode ? defaultDateRange.graph.start : defaultDateRange.table.start);
    const toDate = auditEndDate ? auditEndDate.value : (window.isGraphMode ? defaultDateRange.graph.end : defaultDateRange.table.end);

    // Show loading state
    const tableBody = document.querySelector('.audit-table tbody');
    if (tableBody) {
        tableBody.innerHTML = '<tr><td colspan="13" class="loading-text">Loading...</td></tr>';
    }

    // Disable the entries dropdown while loading
    if (entriesDropdown) {
        entriesDropdown.disabled = true;
    }

    // Ensure we have valid dates
    if (!fromDate || !toDate) {
        setDefaultDates(window.isGraphMode);
    }

    let url = `/api/v1/feedback/?page=${currentPage}&page_size=${entriesPerPage}&search=${encodeURIComponent(searchQuery)}&from=${encodeURIComponent(fromDate)}&to=${encodeURIComponent(toDate)}`;
    if (selectedProject && selectedProject !== 'All') url += `&project=${encodeURIComponent(selectedProject)}`;
    if (selectedFeedbackRecorded && selectedFeedbackRecorded !== 'All') url += `&type=${encodeURIComponent(selectedFeedbackRecorded)}`;
    if (sortColumn) url += `&ordering=${sortOrder === 'asc' ? '' : '-'}${sortColumn}`;
    
    fetch(url)
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error || `Server error: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (!data || typeof data !== 'object') {
                throw new Error('Invalid data format received from server');
            }

            // Update global variables
            currentData = data.data && Array.isArray(data.data) ? data.data : (Array.isArray(data) ? data : []);
            totalEntries = data.meta ? data.meta.count : 0;
            currentPage = data.meta ? data.meta.page : currentPage;
            entriesPerPage = data.meta ? data.meta.page_size : entriesPerPage;
            
            // Update UI
            updateTable(currentData);
            updatePagination(totalEntries);

            // Re-enable the entries dropdown
            if (entriesDropdown) {
                entriesDropdown.disabled = false;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (tableBody) {
                tableBody.innerHTML = `<tr><td colspan="10" class="error-text">Error: ${error.message}</td></tr>`;
            }
            // Re-enable the entries dropdown
            if (entriesDropdown) {
                entriesDropdown.disabled = false;
            }
        });
}

// Function to update table with data
function updateTable(reports) {
    if (!Array.isArray(reports)) {
        console.error('Invalid reports data:', reports);
        reports = [];
    }

    const auditTable = document.querySelector('.audit-table tbody');
    if (!auditTable) {
        console.error('Audit table body not found');
        return;
    }

    auditTable.innerHTML = '';
    
    if (reports.length === 0) {
        auditTable.innerHTML = '<tr><td colspan="10" class="no-data-text">No records found</td></tr>';
        return;
    }
    
    reports.forEach(report => {
        if (!report) return; // Skip if report is null or undefined
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${report.created_at ? new Date(report.created_at).toLocaleDateString() : '-'}</td>
            <td>${report.emp_name || report.emp_id || '-'}</td>
            <td>${report.project || '-'}</td>
            <td>-</td>
            <td>${report.work_type || '-'}</td>
            <td>${report.order_batch_id || '-'}</td>
            <td><span class="severity-${(report.severity || '').toLowerCase()}">${report.severity || '-'}</span></td>
            <td>${report.feedback_type || '-'}</td>
            <td><span class="status-${report.is_acknowledged ? 'acknowledged' : 'pending'}">${report.is_acknowledged ? 'Acknowledged' : 'Pending'}</span></td>
            <td>${report.description ? 'Yes' : 'No'}</td>
            <td class="action-buttons">
                <button onclick="viewAuditDetail(${report.id})" class="auditview-btn" title="View Details">
                    <i class="fas fa-eye"></i>
                </button>
                <button onclick="editAuditDetail(${report.id})" class="auditedit-btn" title="Edit Feedback">
                    <i class="fas fa-edit"></i>
                </button>
                <button onclick="deleteAuditDetail(${report.id})" class="auditdelete-btn" title="Delete Feedback">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        auditTable.appendChild(row);
    });
}

// Function to update pagination
function updatePagination(total) {
    const totalPages = Math.ceil(total / entriesPerPage);
    document.getElementById('auditCurrentPage').textContent = currentPage;
    document.getElementById('auditTotalEntries').textContent = total;
    document.getElementById('auditStartEntry').textContent = total === 0 ? 0 : (currentPage - 1) * entriesPerPage + 1;
    document.getElementById('auditEndEntry').textContent = Math.min(currentPage * entriesPerPage, total);
    
    document.getElementById('auditPrevPage').disabled = currentPage === 1;
    document.getElementById('auditNextPage').disabled = currentPage >= totalPages;
}

// Event Listeners
if (datePicker) {
    datePicker.addEventListener('change', () => {
        currentPage = 1;
        fetchAuditData();
    });
}

entriesDropdown.addEventListener('change', (e) => {
    const newValue = parseInt(e.target.value);
    if (!isNaN(newValue) && newValue > 0) {
        entriesPerPage = newValue;
        currentPage = 1; // Reset to first page when changing entries per page
        fetchAuditData();
    }
});

// Enhanced search functionality
searchField.addEventListener('input', debounce(() => {
    currentPage = 1;
    fetchAuditData();
}, 500));

clearSearch.addEventListener('click', () => {
    searchField.value = '';
    if (datePicker) datePicker.value = '';
    currentPage = 1;
    fetchAuditData();
});

// Enhanced refresh button functionality
refreshButton.addEventListener('click', () => {
    // Show loading animation on the refresh button
    refreshButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    
    // Reset all filters
    if (datePicker) datePicker.value = '';
    searchField.value = '';
    currentPage = 1;
    sortColumn = 'processed_date';
    sortOrder = 'desc';
    
    // Fetch fresh data
    fetchAuditData();
    
    // Reset refresh button after a short delay
    setTimeout(() => {
        refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i>';
    }, 1000);
});

document.getElementById('auditPrevPage').addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        fetchAuditData();
    }
});

document.getElementById('auditNextPage').addEventListener('click', () => {
    if (currentPage * entriesPerPage < totalEntries) {
        currentPage++;
        fetchAuditData();
    }
});

// Sort functionality
document.querySelectorAll('.audit-sortable').forEach(header => {
    header.addEventListener('click', () => {
        const columnMap = {
            'date': 'processed_date',
            'emp id': 'emp_id',
            'emp name': 'emp_name',
            'project': 'project',
            'client code': 'client_code',
            'work type': 'work_type',
            'feedback': 'feedback',
            'feedback recorded': 'feedback_recorded',
            'severity': 'severity',
            'status': 'status'
        };
        
        const headerText = header.textContent.trim().toLowerCase().replace(/\s+/g, ' ');
        const column = columnMap[headerText] || headerText;
        
        if (sortColumn === column) {
            sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            sortColumn = column;
            sortOrder = 'asc';
        }
        fetchAuditData();
    });
});

// Modal close button event listener
closeBtn.addEventListener('click', () => {
    modal.style.display = 'none';
});

// Close modal when clicking outside
window.addEventListener('click', (event) => {
    if (event.target === modal) {
        modal.style.display = 'none';
    }
});

// Prevent modal close when clicking inside modal content
modal.querySelector('.auditmodal-content').addEventListener('click', (event) => {
    event.stopPropagation();
});

// Initial data fetch
fetchAuditData();

// Helper function to format acknowledgment status
function getAcknowledgmentDisplay(ack) {
    if (ack === null || ack === undefined) {
        return 'pending';
    }
    return ack === 1 ? 'yes' : 'no';
}

// View audit detail function (outside DOMContentLoaded because it's called from HTML)
async function viewAuditDetail(id) {
    const modal = document.getElementById('auditDetailModal');
    const contentArea = modal.querySelector('.audit-detail-content');
    
    modal.style.display = 'block';

    try {
        const response = await fetch(`/api/v1/feedback/${id}/`);
        const json = await response.json();
        const data = json.data || json;

        // Prepare the content HTML without images first
        let contentHtml = `
            <div class="detail-grid">
                <div class="detail-item">
                    <label>Order/Batch ID:</label>
                    <div class="detail-value">${data.order_batch_id || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Feedback Recorded:</label>
                    <div class="detail-value">${data.feedback_recorded || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Employee ID:</label>
                    <div class="detail-value">${data.emp_id || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Employee Name:</label>
                    <div class="detail-value">${data.emp_name || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Project:</label>
                    <div class="detail-value">${data.project || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Client Code:</label>
                    <div class="detail-value">${data.client_code || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Work Type:</label>
                    <div class="detail-value">${data.work_type || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Processed Date:</label>
                    <div class="detail-value">${data.processed_date || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Feedback Received Date:</label>
                    <div class="detail-value">${data.feedback_received_date || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Feedback Mode:</label>
                    <div class="detail-value">${data.feedback_received_mode || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Provided By:</label>
                    <div class="detail-value">${data.feedback_provided_by || '-'}</div>
                </div>
                <div class="detail-item full-width">
                    <label>Feedback:</label>
                    <div class="detail-value feedback-text">${data.feedback || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Severity:</label>
                    <div class="detail-value"><span class="severity-${(data.severity || '').toLowerCase()}">${data.severity || '-'}</span></div>
                </div>
                <div class="detail-item">
                    <label>Type:</label>
                    <div class="detail-value">${data.type || '-'}</div>
                </div>
                <div class="detail-item full-width">
                    <label>Comments:</label>
                    <div class="detail-value feedback-text">${data.comments || '-'}</div>
                </div>
                <div class="detail-item full-width">
                    <label>Action Taken:</label>
                    <div class="detail-value feedback-text">${data.action_taken || '-'}</div>
                </div>
                <div class="detail-item">
                    <label>Status:</label>
                    <div class="detail-value"><span class="status-${(data.status || '').toLowerCase()}">${data.status || '-'}</span></div>
                </div>
                <div class="detail-item">
                    <label>Acknowledgment:</label>
                    <div class="detail-value">${getAcknowledgmentDisplay(data.acknowledgment)}</div>
                </div>
                <div class="detail-item full-width">
                    <label>Acknowledgment Comment:</label>
                    <div class="detail-value feedback-text">${data.acknowledgment_comment || '-'}</div>
                </div>
            </div>`;

        // Add image gallery container
        if (data.images && data.images.length > 0) {
            contentHtml += `
                <div class="detail-item full-width">
                    <label>Screenshots:</label>
                    <div class="image-gallery" id="viewImageGallery">
                    </div>
                </div>`;
        }

        // Update content first
        contentArea.innerHTML = contentHtml;

        // Load images separately if they exist
        if (data.images && data.images.length > 0) {
            const imageGallery = document.getElementById('viewImageGallery');
            const imageUrls = [];
            
            data.images.forEach((img, index) => {
                const imgContainer = document.createElement('div');
                imgContainer.className = 'image-container';
                const image = new Image();
                const imageUrl = `data:image/jpeg;base64,${img.data}`;
                image.src = imageUrl;
                imageUrls.push(imageUrl);
                
                // Add click handler for image preview
                imgContainer.addEventListener('click', () => {
                    showImageViewer(imageUrls, index);
                });
                
                imgContainer.appendChild(image);
                imageGallery.appendChild(imgContainer);
            });
        }

    } catch (error) {
        console.error('Error fetching audit detail:', error);
        contentArea.innerHTML = '<div class="error-message">Error loading feedback details. Please try again.</div>';
    }
}

// Add these utility functions at the top
function showLoadingSpinner() {
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner';
    spinner.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    return spinner;
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.style.display = 'block';
    return modal;
}

// Function to check if project is TitleIndexing
function isTitleIndexingProject(projectName) {
    return projectName && projectName.toLowerCase().includes('titleindexing');
}

// Modify the editAuditDetail function
async function editAuditDetail(id) {
    const modal = openModal('auditEditModal');
    const form = document.getElementById('editFeedbackForm');
    
    try {
        const response = await fetch(`/api/v1/feedback/${id}/`);
        const json = await response.json();
        const data = json.data || json;

        // Set form fields
        document.getElementById('editFeedbackId').value = id;
        
        // Update type dropdown based on project
        const typeSelect = document.getElementById('editType');
        const project = data.project || '';
        
        if (isTitleIndexingProject(project)) {
            // Clear existing options
            typeSelect.innerHTML = '';
            
            // Add TitleIndexing specific options
            TITLE_INDEXING_CONFIG.types.forEach(type => {
                const option = document.createElement('option');
                option.value = type.toLowerCase().replace(/\s+/g, '_');
                option.textContent = type;
                typeSelect.appendChild(option);
            });
        } else {
            // Reset to default options
            typeSelect.innerHTML = `
                <option value="typoErrors">Typo Errors</option>
                <option value="missedToKey">Missed to Key</option>
                <option value="instructionsNotFollowed">Instructions not followed</option>
                <option value="misinterpretation">Misinterpretation</option>
                <option value="softwareIssue">Software Issue</option>
                <option value="wrongFeedback">Wrong Feedback</option>
                <option value="newFeedback">New Feedback</option>
                <option value="duplicateFeedback">Duplicate Feedback</option>
                <option value="repeatMistake">Repeat Mistake</option>
                <option value="errorpriortosopupdate">Error Prior to SOP Update</option>
            `;
        }

        // Update fields based on project
        const fieldsContainer = document.querySelector('.detail-item:has(#editFields)');
        if (fieldsContainer) {
            if (isTitleIndexingProject(project)) {
                fieldsContainer.innerHTML = `
                    <label for="editFields">Fields:</label>
                    <select id="editFields" name="fields" multiple class="fields-dropdown">
                        ${TITLE_INDEXING_CONFIG.fields.map(field => `
                            <option value="${field}">${field}</option>
                        `).join('')}
                    </select>
                `;
                
                // Initialize Select2 for fields dropdown
                $('#editFields').select2({
                    placeholder: 'Select fields',
                    allowClear: true,
                    multiple: true,
                    width: '100%'
                });

                // Set selected fields if they exist
                if (data.fields) {
                    const selectedFields = data.fields.split(', ');
                    $('#editFields').val(selectedFields).trigger('change');
                }
            } else {
                fieldsContainer.innerHTML = `
                    <label for="editFields">Fields:</label>
                    <input type="text" id="editFields" name="fields" value="${data.fields || ''}">
                `;
            }
        }
        
        // Batch DOM updates
        const updates = {
            'editOrderBatchId': data.order_batch_id || '',
            'editFeedbackRecorded': data.feedback_recorded || 'internalAudit',
            'editEmpId': data.emp_id || '',
            'editEmpName': data.emp_name || '',
            'editProject': data.project || '',
            'editClientCode': data.client_code || '',
            'editWorkType': data.work_type || '',
            'editProcessedDate': data.processed_date || '',
            'editFeedbackReceivedDate': data.feedback_received_date || '',
            'editFeedbackReceivedMode': data.feedback_received_mode || 'email',
            'editFeedbackProvidedBy': data.feedback_provided_by || '',
            'editFeedback': data.feedback || '',
            'editSeverity': data.severity || 'low',
            'editType': data.type || '',
            'editComments': data.comments || '',
            'editActionTaken': data.action_taken || '',
            'editStatus': data.status || 'open',
            'editAcknowledgment': data.acknowledgment !== null ? data.acknowledgment.toString() : '',
            'editAcknowledgmentComment': data.acknowledgment_comment || ''
        };

        // Batch update DOM
        Object.entries(updates).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                if (element.tagName === 'SELECT') {
                    // For select elements, try to find the option with matching text
                    const options = Array.from(element.options);
                    const matchingOption = options.find(opt => 
                        opt.textContent.toLowerCase() === value.toLowerCase() ||
                        opt.value.toLowerCase() === value.toLowerCase()
                    );
                    if (matchingOption) {
                        element.value = matchingOption.value;
                    } else {
                        element.value = value;
                    }
                } else {
                    element.value = value;
                }
            }
        });

        // Handle images
        const imageGallery = document.getElementById('existingImages');
        imageGallery.innerHTML = '';

        if (data.images && data.images.length > 0) {
            const imageUrls = [];
            
            data.images.forEach((img, index) => {
                const container = document.createElement('div');
                container.className = 'image-container';
                const image = new Image();
                const imageUrl = `data:image/jpeg;base64,${img.data}`;
                image.src = imageUrl;
                imageUrls.push(imageUrl);
                
                container.addEventListener('click', (e) => {
                    if (!e.target.closest('.delete-image')) {
                        showImageViewer(imageUrls, index);
                    }
                });
                
                container.appendChild(image);
                container.innerHTML += `                    <button type="button" class="delete-image" data-id="${img.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                `;
                imageGallery.appendChild(container);
            });
        }

    } catch (error) {
        console.error('Error fetching audit detail:', error);
        alert('Error loading feedback details. Please try again.');
    }
}


// Add event listener for the cancel button
document.querySelector('.audit-cancel-btn').addEventListener('click', function() {
    document.getElementById('auditEditModal').style.display = 'none';
});

// Add event listener for the close button
document.querySelectorAll('.auditclose-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        this.closest('.auditmodal').style.display = 'none';
    });
});

// Close modal when clicking outside
window.addEventListener('click', function(event) {
    if (event.target.classList.contains('auditmodal')) {
        event.target.style.display = 'none';
    }
});

// Handle form submission
document.getElementById('editFeedbackForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const id = document.getElementById('editFeedbackId').value;
    const formData = new FormData(this);
    const saveButton = document.querySelector('.audit-save-btn');
    
    // Get acknowledgment values
    const acknowledgment = document.getElementById('editAcknowledgment').value;
    const acknowledgmentComment = document.getElementById('editAcknowledgmentComment').value;
    
    // Add acknowledgment fields to formData
    formData.append('acknowledgment', acknowledgment);
    formData.append('acknowledgment_comment', acknowledgmentComment);
    
    // Disable save button and show loading state
    saveButton.disabled = true;
    saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    
    // Add deleted image IDs to formData
    const deletedImages = [];
    document.querySelectorAll('.image-container.marked-delete').forEach(container => {
        deletedImages.push(container.querySelector('.delete-image').dataset.id);
    });
    deletedImages.forEach(id => formData.append('deleted_images', id));

    fetch(`/api/v1/feedback/${id}/`, {
        method: 'PATCH',
        headers: { 'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '' },
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.ok || data.id) {
            document.getElementById('auditEditModal').style.display = 'none';
            // Refresh the table and show updated data
            fetchAuditData();
            // Show the detail view with updated data
            viewAuditDetail(id);
        } else {
            alert('Error updating feedback: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error updating feedback. Please try again.');
    })
    .finally(() => {
        // Re-enable save button and restore original text
        saveButton.disabled = false;
        saveButton.innerHTML = 'Save Changes';
    });
});

// Handle image deletion marking
document.getElementById('existingImages').addEventListener('click', function(e) {
    if (e.target.closest('.delete-image')) {
        const container = e.target.closest('.image-container');
        container.classList.toggle('marked-delete');
    }
});

// Utility function for debouncing
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Make editAuditDetail function globally available
window.editAuditDetail = editAuditDetail;
window.viewAuditDetail = viewAuditDetail;

// Add the delete function
function deleteAuditDetail(id) {
    if (confirm('Are you sure you want to delete this feedback? This action cannot be undone.')) {
        fetch(`/api/v1/feedback/${id}/`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '' }
        })
        .then(response => {
            if (response.ok) {
                fetchAuditData(); // Refresh the table
            } else {
                alert('Error deleting feedback');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error deleting feedback. Please try again.');
        });
    }
}

// Make deleteAuditDetail function globally available
window.deleteAuditDetail = deleteAuditDetail;

// Create and append the image viewer modal to the document
const imageViewerModal = document.createElement('div');
imageViewerModal.className = 'image-viewer-modal';
imageViewerModal.innerHTML = `
    <div class="image-viewer-content">
        <span class="image-viewer-close">&times;</span>
        <button class="nav-btn prev-btn"><i class="fas fa-chevron-left"></i></button>
        <div class="main-image-container">
            <img src="" alt="Full size image" id="fullSizeImage">
        </div>
        <button class="nav-btn next-btn"><i class="fas fa-chevron-right"></i></button>
        <div class="image-counter">Image <span id="currentImageIndex">1</span> of <span id="totalImages">1</span></div>
    </div>
`;
document.body.appendChild(imageViewerModal);

// Function to show image viewer
function showImageViewer(images, startIndex = 0) {
    imagesList = images;
    currentImageIndex = startIndex;
    updateImageViewer();
    imageViewerModal.style.display = 'flex';
}

// Function to update image viewer
function updateImageViewer() {
    const fullSizeImage = document.getElementById('fullSizeImage');
    const currentImage = imagesList[currentImageIndex];
    
    fullSizeImage.src = currentImage;
    
    // Update counter
    document.getElementById('currentImageIndex').textContent = currentImageIndex + 1;
    document.getElementById('totalImages').textContent = imagesList.length;
    
    // Update navigation buttons
    document.querySelector('.prev-btn').style.display = currentImageIndex > 0 ? 'block' : 'none';
    document.querySelector('.next-btn').style.display = currentImageIndex < imagesList.length - 1 ? 'block' : 'none';
}

// Add event listeners for image viewer controls
document.querySelector('.image-viewer-close').addEventListener('click', () => {
    imageViewerModal.style.display = 'none';
});

document.querySelector('.prev-btn').addEventListener('click', () => {
    if (currentImageIndex > 0) {
        currentImageIndex--;
        updateImageViewer();
    }
});

document.querySelector('.next-btn').addEventListener('click', () => {
    if (currentImageIndex < imagesList.length - 1) {
        currentImageIndex++;
        updateImageViewer();
    }
});


// Add event listeners for new filters
document.addEventListener('DOMContentLoaded', function() {
    // ... existing event listeners ...

    // Project filter change
    const projectFilter = document.querySelector('.audit-project-filter');
    if (projectFilter) {
        projectFilter.addEventListener('change', function() {
            selectedProject = this.value;
            currentPage = 1; // Reset to first page
            fetchAuditData();
        });
    }

    // Feedback Recorded filter change
    const feedbackRecordedFilter = document.querySelector('.audit-feedback-recorded-filter');
    if (feedbackRecordedFilter) {
        feedbackRecordedFilter.addEventListener('change', function() {
            selectedFeedbackRecorded = this.value;
            currentPage = 1; // Reset to first page
            fetchAuditData();
        });
    }

    // Load projects for the filter
    loadProjects();
});

// Function to load projects with caching
async function loadProjects() {
    try {
        const projects = await MasterDataCache.getOrFetch('master_projects', '/api/v1/masters/emp_get_projects/');
        
        const projectFilter = document.querySelector('.audit-project-filter');
        const workTypeFilter = document.querySelector('.audit-worktype-filter');
        
        if (projectFilter) {
            // Clear existing options
            projectFilter.innerHTML = '<option value="">All Projects</option>';
            
            // Add project options
            projects.forEach(project => {
                const option = document.createElement('option');
                option.value = project.project_name;
                option.textContent = project.project_name;
                projectFilter.appendChild(option);
            });

            // Remove existing event listener if any
            const newProjectFilter = projectFilter.cloneNode(true);
            projectFilter.parentNode.replaceChild(newProjectFilter, projectFilter);

            // Add event listener for project selection
            newProjectFilter.addEventListener('change', function() {
                selectedProject = this.value;
                
                // Update work types based on selected project
                if (selectedProject) {
                    const selectedProjectData = projects.find(p => p.project_name === selectedProject);
                    if (selectedProjectData && selectedProjectData.worktypes) {
                        const workTypes = selectedProjectData.worktypes.split('|').filter(wt => wt.trim());
                        updateWorkTypeFilter(workTypes);
                    }
                } else {
                    // Reset work type filter
                    if (workTypeFilter) {
                        workTypeFilter.innerHTML = '<option value="">All Work Types</option>';
                        selectedWorkType = '';
                    }
                }

                // Reset employee filter to "All Employees"
                const employeeFilter = document.querySelector('.audit-employee-filter');
                if (employeeFilter) {
                    employeeFilter.value = '';
                }

                // Update graphs if in graph mode
                if (window.isGraphMode) {
                    if (selectedProject) {
                        isProjectView = true;
                        updateProjectGraphs();
                    } else {
                        isProjectView = false;
                        // Revert to default employee view
                        const empId = employeeFilter ? employeeFilter.value : '';
                        updateGraphsForEmployee(empId);
                    }
                }
            });
        }

        // Initialize work type filter
        if (workTypeFilter) {
            workTypeFilter.innerHTML = '<option value="">All Work Types</option>';
            
            // Remove existing event listener if any
            const newWorkTypeFilter = workTypeFilter.cloneNode(true);
            workTypeFilter.parentNode.replaceChild(newWorkTypeFilter, workTypeFilter);

            // Add event listener for work type selection
            newWorkTypeFilter.addEventListener('change', function() {
                selectedWorkType = this.value;
                if (window.isGraphMode) {
                    updateProjectGraphs();
                }
            });
        }

    } catch (error) {
        console.error('Error loading projects:', error);
        const projectFilter = document.querySelector('.audit-project-filter');
        if (projectFilter) {
            projectFilter.innerHTML = '<option value="">Failed to load projects</option>';
        }
    }
}

function updateTypeDropdown(projectName) {
    const typeSelect = document.getElementById('type');
    typeSelect.innerHTML = ''; // Clear existing options

    if (isTitleIndexingProject(projectName)) {
        // Add TitleIndexing specific options
        TITLE_INDEXING_CONFIG.types.forEach(type => {
            const option = document.createElement('option');
            option.value = type.toLowerCase().replace(/\s+/g, '_');
            option.textContent = type;
            typeSelect.appendChild(option);
        });
    } else {
        // Add default options
        const defaultOptions = [
            'typoErrors',
            'missedToKey',
            'instructionsNotFollowed',
            'misinterpretation',
            'softwareIssue',
            'wrongFeedback',
            'newFeedback',
            'duplicateFeedback',
            'repeatMistake',
            'errorpriortosopupdate'
        ];

        defaultOptions.forEach(option => {
            const optionElement = document.createElement('option');
            optionElement.value = option;
            optionElement.textContent = option.replace(/([A-Z])/g, ' $1').trim();
            typeSelect.appendChild(optionElement);
        });
    }
}

function updateFields(projectName) {
    const fieldsContainer = document.getElementById('fieldsContainer');
    if (!fieldsContainer) return;

    if (isTitleIndexingProject(projectName)) {
        // Create multi-select dropdown for TitleIndexing
        fieldsContainer.innerHTML = `
            <label for="fields">
                <i class="fas fa-hashtag"></i> Fields:
            </label>
            <select id="fields" name="fields" multiple class="fields-dropdown">
                ${TITLE_INDEXING_CONFIG.fields.map(field => `
                    <option value="${field}">${field}</option>
                `).join('')}
            </select>
        `;

        // Initialize Select2 for the fields dropdown
        $('#fields').select2({
            placeholder: 'Select fields',
            allowClear: true,
            multiple: true,
            width: '100%'
        });
    } else {
        // Reset to default text input
        fieldsContainer.innerHTML = `
            <label for="fields">
                <i class="fas fa-hashtag"></i> Fields:
            </label>
            <input type="text" id="fields" name="fields">
        `;
    }
}

if (auditStartDate) {
    auditStartDate.addEventListener('change', () => {
        currentPage = 1;
        fetchAuditData();
    });
}
if (auditEndDate) {
    auditEndDate.addEventListener('change', () => {
        currentPage = 1;
        fetchAuditData();
    });
}

if (auditDownloadButton) {
    auditDownloadButton.addEventListener('click', function() {
        const format = auditDownloadFormat.value;
        if (!format) {
            alert('Please select a format (CSV or Excel) to export.');
            return;
        }
        exportAuditReports(format);
    });
}

function exportAuditReports(format) {
    const searchQuery = searchField.value;
    const selectedDate = datePicker ? datePicker.value : '';
    const fromDate = auditStartDate ? auditStartDate.value : '';
    const toDate = auditEndDate ? auditEndDate.value : '';

    const url = `/export_audit_reports?search=${encodeURIComponent(searchQuery)}&date=${encodeURIComponent(selectedDate)}&project=${encodeURIComponent(selectedProject)}&feedback_recorded=${encodeURIComponent(selectedFeedbackRecorded)}&from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}&format=${format}`;

    fetch(url)
        .then(response => {
            if (!response.ok) throw new Error('Failed to export data');
            return response.blob();
        })
        .then(blob => {
            const a = document.createElement('a');
            a.href = window.URL.createObjectURL(blob);
            a.download = `audit_reports.${format === 'csv' ? 'csv' : 'xlsx'}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
        })
        .catch(error => {
            alert('Export failed: ' + error.message);
        });
}

// --- Quality Metrics Cards for Audit Tab ---
function fetchAuditQualityMetrics() {
    const startDate = document.getElementById('auditStartDate').value;
    const endDate = document.getElementById('auditEndDate').value;
    if (!startDate || !endDate) {
        // Optionally clear the cards if dates are missing
        const cardRow = document.getElementById('qualityMetricsCardRow');
        if (cardRow) cardRow.innerHTML = '';
        return;
    }
    fetch(`/get_all_employees_work_data?start_date=${startDate}&end_date=${endDate}`)
        .then(response => response.json())
        .then(workData => {
            if (!Array.isArray(workData)) {
                // Optionally show error in UI
                return;
            }
                                    return fetch(`/api/v1/feedback/?from=${startDate}&to=${endDate}`)
                .then(response => response.json())
                .then(feedbackData => {
                    renderAuditQualityMetrics(workData, feedbackData.reports);
                });
        })
        .catch(error => console.error('Error fetching quality metrics:', error));
}

function renderAuditQualityMetrics(workData, feedbackData) {
    if (!Array.isArray(workData)) return;
    // Log for debugging
    console.log('workData:', workData);
    console.log('feedbackData:', feedbackData);

    // Only use records with a valid project name
    const filteredWorkData = workData.filter(r => r.project && typeof r.project === 'string' && r.project.trim() !== '');
    if (filteredWorkData.length === 0) {
        document.getElementById('qualityMetricsCardRow').innerHTML = '<div style="padding:24px;text-align:center;color:#888;">No quality metrics data available for this date range.</div>';
        return;
    }

    const projectWorkMetrics = {};
    filteredWorkData.forEach(record => {
        const project = record.project.trim();
        if (!projectWorkMetrics[project]) {
            projectWorkMetrics[project] = {
                totalTime: 0,
                totalUnits: 0,
                workCount: 0
            };
        }
        projectWorkMetrics[project].totalTime += parseFloat(record.total_time || 0);
        projectWorkMetrics[project].totalUnits += parseInt(record.work_units || 0);
        projectWorkMetrics[project].workCount++;
    });

    const projectFeedbackMetrics = {};
    feedbackData.forEach(record => {
        if (!record.project || typeof record.project !== 'string' || record.project.trim() === '') return;
        const project = record.project.trim();
        if (!projectFeedbackMetrics[project]) {
            projectFeedbackMetrics[project] = {
                total: 0,
                acknowledged: 0,
                notAcknowledged: 0,
                pending: 0
            };
        }
        projectFeedbackMetrics[project].total++;
        if (record.acknowledgment === 1) {
            projectFeedbackMetrics[project].acknowledged++;
        } else if (record.acknowledgment === 0) {
            projectFeedbackMetrics[project].notAcknowledged++;
        } else {
            projectFeedbackMetrics[project].pending++;
        }
    });

    const cardRow = document.getElementById('qualityMetricsCardRow');
    const cardsHtml = Object.keys(projectWorkMetrics).map(project => {
        const workMetrics = projectWorkMetrics[project];
        const feedbackMetrics = projectFeedbackMetrics[project] || { total: 0, acknowledged: 0, notAcknowledged: 0, pending: 0 };
        const avgTimePerUnit = workMetrics.totalUnits > 0 ? formatTimeToHHMMSS((workMetrics.totalTime / workMetrics.totalUnits).toFixed(2)) : '-';
        const acknowledgmentRate = feedbackMetrics.total > 0 ? ((feedbackMetrics.acknowledged / feedbackMetrics.total) * 100).toFixed(1) : 0;
        const noMistakeRate = feedbackMetrics.total > 0 ? ((feedbackMetrics.notAcknowledged / feedbackMetrics.total) * 100).toFixed(1) : 0;
        const pendingRate = feedbackMetrics.total > 0 ? ((feedbackMetrics.pending / feedbackMetrics.total) * 100).toFixed(1) : 0;
        return `<div class="quality-metric-card"><div class="qm-header">${project}</div><div class="qm-metrics"><div><span class="qm-label">Work Units</span><span class="qm-value">${workMetrics.totalUnits}</span></div><div><span class="qm-label">Avg. Time/Unit</span><span class="qm-value">${avgTimePerUnit}</span></div><div><span class="qm-label">Feedback</span><span class="qm-value">${feedbackMetrics.total}</span></div><div><span class="qm-label">Mistakes</span><span class="qm-value qm-bad">${acknowledgmentRate}%</span></div><div><span class="qm-label">No Mistakes</span><span class="qm-value qm-good">${noMistakeRate}%</span></div><div><span class="qm-label">Pending</span><span class="qm-value">${pendingRate}%</span></div></div></div>`;
    }).join('');

    cardRow.innerHTML = cardsHtml
        ? `<div class="quality-metrics-scroll">${cardsHtml}</div>`
        : '<div style="padding:24px;text-align:center;color:#888;">No quality metrics data available for this date range.</div>';

    // Add click event for modal
    cardRow.querySelectorAll('.quality-metric-card').forEach(card => {
        card.style.cursor = 'pointer';
        card.addEventListener('click', function() {
            const projectName = card.querySelector('.qm-header').textContent;
            showAuditProjectEmployeeQualityModal(projectName);
        });
    });
}

function showAuditProjectEmployeeQualityModal(projectName) {
    const startDate = document.getElementById('auditStartDate').value;
    const endDate = document.getElementById('auditEndDate').value;
    // Optionally show loading overlay here
    Promise.all([
        fetch(`/get_all_employees_work_data?start_date=${startDate}&end_date=${endDate}`).then(r => r.json()),
        fetch(`/get_audit_reports?from_date=${startDate}&to_date=${endDate}&entries=10000`).then(r => r.json())
    ]).then(([workData, feedbackData]) => {
        const projectWork = workData.filter(w => w.project === projectName);
        const employees = [...new Set(projectWork.map(w => w.emp_id))];
        const empRows = employees.map(emp_id => {
            const empRecords = projectWork.filter(w => w.emp_id === emp_id);
            const empName = empRecords[0]?.name || '-';
            const totalTime = empRecords.reduce((sum, r) => sum + parseFloat(r.total_time || 0), 0);
            const workUnits = empRecords.reduce((sum, r) => sum + parseInt(r.work_units || 0), 0);
            const empFeedbacks = (feedbackData.reports || []).filter(f => f.emp_id === emp_id && f.project === projectName);
            const totalFeedback = empFeedbacks.length;
            const ackYes = empFeedbacks.filter(f => f.acknowledgment === 1).length;
            const ackNo = empFeedbacks.filter(f => f.acknowledgment === 0).length;
            const ackRate = totalFeedback > 0 ? ((ackYes / totalFeedback) * 100).toFixed(1) : '0.0';
            return { empName, totalTime, workUnits, totalFeedback, ackYes, ackNo, ackRate };
        });
        empRows.sort((a, b) => b.workUnits - a.workUnits);
        const modal = document.createElement('div');
        modal.className = 'project-emp-quality-modal';
        modal.innerHTML = `<div class="peq-modal-content"><div class="peq-modal-header"><h3>${projectName} - Employee Quality Details</h3><div class="peq-search-group"><span class="peq-search-icon" title="Search"><i class="fas fa-search"></i></span><input type="text" class="peq-search-input" placeholder="Search employee..." style="display:none;" /><span class="peq-clear-search" title="Clear" style="display:none;">&times;</span></div><span class="peq-close">&times;</span></div><div class="peq-table-container"><table class="peq-table"><thead><tr><th>Employee</th><th>Total Time</th><th>Work Units</th><th>Total Feedback</th><th>Ack Yes</th><th>Ack No</th><th>Ack Rate (%)</th></tr></thead><tbody>${empRows.length === 0 ? '<tr><td colspan="7">No data available</td></tr>' : empRows.map(row => `<tr><td>${row.empName}</td><td>${formatTimeToHHMMSS(row.totalTime)}</td><td>${row.workUnits}</td><td>${row.totalFeedback}</td><td>${row.ackYes}</td><td>${row.ackNo}</td><td>${row.ackRate}</td></tr>`).join('')}</tbody></table></div></div>`;
        document.body.appendChild(modal);
        // Search logic
        const searchIcon = modal.querySelector('.peq-search-icon');
        const searchInput = modal.querySelector('.peq-search-input');
        const clearBtn = modal.querySelector('.peq-clear-search');
        const tableBody = modal.querySelector('.peq-table tbody');
        searchIcon.onclick = () => {
            searchInput.style.display = 'inline-block';
            searchInput.focus();
            clearBtn.style.display = 'inline-block';
            searchIcon.style.display = 'none';
        };
        clearBtn.onclick = () => {
            searchInput.value = '';
            clearBtn.style.display = 'none';
            searchIcon.style.display = 'inline-block';
            searchInput.style.display = 'none';
            renderRows(empRows);
        };
        searchInput.oninput = function() {
            const val = this.value.trim().toLowerCase();
            if (val === '') {
                renderRows(empRows);
                clearBtn.style.display = 'none';
            } else {
                clearBtn.style.display = 'inline-block';
                const filtered = empRows.filter(row => row.empName.toLowerCase().includes(val));
                renderRows(filtered);
            }
        };
        function renderRows(rows) {
            if (rows.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="7">No data available</td></tr>';
            } else {
                tableBody.innerHTML = rows.map(row => `<tr><td>${row.empName}</td><td>${formatTimeToHHMMSS(row.totalTime)}</td><td>${row.workUnits}</td><td>${row.totalFeedback}</td><td>${row.ackYes}</td><td>${row.ackNo}</td><td>${row.ackRate}</td></tr>`).join('');
            }
        }
        modal.querySelector('.peq-close').onclick = () => modal.remove();
        // Optionally hide loading overlay here
    }).catch(() => {/* Optionally hide loading overlay here */});
}

// Utility for time formatting
function formatTimeToHHMMSS(seconds) {
    if (!seconds || isNaN(seconds)) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return [hours.toString().padStart(2, '0'), minutes.toString().padStart(2, '0'), remainingSeconds.toString().padStart(2, '0')].join(':');
}

// Call metrics fetch on filter changes
if (document.getElementById('auditStartDate')) {
    document.getElementById('auditStartDate').addEventListener('change', fetchAuditQualityMetrics);
}
if (document.getElementById('auditEndDate')) {
    document.getElementById('auditEndDate').addEventListener('change', fetchAuditQualityMetrics);
}
// Initial call
if (document.getElementById('qualityMetricsCardRow')) {
    fetchAuditQualityMetrics();
}

// --- Toggle Graph/Table View Logic ---
function updateAuditFilterHeaderForMode() {
    const feedbackType = document.querySelector('.audit-feedback-recorded-filter');
    const entriesDropdown = document.querySelector('.audit-entries-dropdown');
    const searchContainer = document.querySelector('.audit-search-container');
    const exportControls = document.querySelector('.audit-export-controls');
    const worktypeFilter = document.querySelector('.audit-worktype-filter');
    const employeeFilter = document.querySelector('.audit-employee-filter');

    if (window.isGraphMode) {
        // Hide table-only controls
        if (feedbackType) feedbackType.style.display = 'none';
        if (entriesDropdown) entriesDropdown.style.display = 'none';
        if (searchContainer) searchContainer.style.display = 'none';
        if (exportControls) exportControls.style.display = 'none';
        // Show graph-only controls
        if (worktypeFilter) worktypeFilter.style.display = '';
        if (employeeFilter) employeeFilter.style.display = '';
    } else {
        // Show table-only controls
        if (feedbackType) feedbackType.style.display = '';
        if (entriesDropdown) entriesDropdown.style.display = '';
        if (searchContainer) searchContainer.style.display = '';
        if (exportControls) exportControls.style.display = 'flex'; // Ensure flex for alignment
        // Hide graph-only controls
        if (worktypeFilter) worktypeFilter.style.display = 'none';
        if (employeeFilter) employeeFilter.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const toggleBtn = document.querySelector('.audit-toggle-graph-btn');
    const toggleLabel = toggleBtn ? toggleBtn.querySelector('.toggle-label') : null;
    if (toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            window.isGraphMode = !window.isGraphMode;
            this.classList.toggle('active', window.isGraphMode);
            
            // Update button appearance
            if (window.isGraphMode) {
                this.title = 'Switch to Table View';
                this.setAttribute('aria-label', 'Switch to Table View');
                this.querySelector('i').className = 'fas fa-table';
                this.querySelector('.toggle-label').textContent = 'Table View';
                
                // Show graph container, hide table
                document.querySelector('.audit-table').style.display = 'none';
                document.getElementById('qualityMetricsCardRow').style.display = 'none';
                
                // Set graph-specific date range
                setDefaultDates(true);
                
                // Show graph container
                let graphDiv = document.getElementById('auditGraphView');
                if (!graphDiv) {
                    graphDiv = document.createElement('div');
                    graphDiv.id = 'auditGraphView';
                    graphDiv.style.minHeight = '400px';
                    graphDiv.innerHTML = `
                        <div class="audit-chart-section">
                            <div class="audit-chart-container">
                                <div class="audit-chart-wrapper">
                                    <canvas id="auditCombinedChart"></canvas>
                                </div>
                            </div>
                            <div id="graphNoDataMsg" class="audit-no-data-message" style="display:none;">
                                No data available for the selected date range.
                            </div>
                        </div>
                    `;
                    document.querySelector('.auditreportscontainer').appendChild(graphDiv);
                }
                graphDiv.style.display = '';
                
                // Update graph with new date range
                if (selectedProject) {
                    updateProjectGraphs();
                } else {
                    const empId = document.querySelector('.audit-employee-filter')?.value;
                    updateGraphsForEmployee(empId);
                }
            } else {
                this.title = 'Switch to Graph View';
                this.setAttribute('aria-label', 'Switch to Graph View');
                this.querySelector('i').className = 'fas fa-chart-bar';
                this.querySelector('.toggle-label').textContent = 'Graph View';
                
                // Show table, hide graph
                document.querySelector('.audit-table').style.display = '';
                document.getElementById('qualityMetricsCardRow').style.display = '';
                const graphDiv = document.getElementById('auditGraphView');
                if (graphDiv) graphDiv.style.display = 'none';
                
                // Set table-specific date range
                setDefaultDates(false);
                
                // Refresh table data
                fetchAuditData();
            }
            updateAuditFilterHeaderForMode();
        });
        // Initial state
        toggleBtn.classList.remove('active');
        if (toggleLabel) toggleLabel.textContent = 'Graph View';
        toggleBtn.querySelector('i').className = 'fas fa-chart-bar';
        updateAuditFilterHeaderForMode();
    }
});

// --- Graph Mode Logic ---
let feedbackChart = null;
let productivityChart = null;

function getMonthDateRange() {
    const now = new Date();
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    const today = now;
    return {
        from: first.toISOString().split('T')[0],
        to: today.toISOString().split('T')[0]
    };
}

async function populateEmployeeFilter() {
    const employeeFilter = document.querySelector('.audit-employee-filter');
    if (!employeeFilter) return;
    employeeFilter.innerHTML = '<option value="">All Employees</option>';
    try {
        const employees = await MasterDataCache.getOrFetch('master_employees', '/api/v1/auth/employees/');
        employees.forEach(emp => {
            const opt = document.createElement('option');
            opt.value = emp.employee_id;
            opt.textContent = `${emp.name} (${emp.employee_id})`;
            employeeFilter.appendChild(opt);
        });
        // --- Fix: Set default to logged-in user if present ---
        let loggedEmpId = sessionStorage.getItem('emp_id');
        if (!loggedEmpId) {
            // Try to get from DOM if not in sessionStorage
            const userNameBtn = document.getElementById('user-name');
            loggedEmpId = userNameBtn ? userNameBtn.getAttribute('data-employee-id') : null;
        }
        if (loggedEmpId) {
            // Try to select the logged-in user in the filter
            for (let i = 0; i < employeeFilter.options.length; i++) {
                if (employeeFilter.options[i].value === loggedEmpId) {
                    employeeFilter.selectedIndex = i;
                    break;
                }
            }
        }
    } catch (e) {
        employeeFilter.innerHTML = '<option value="">Failed to load</option>';
    }
}

// Function to set default dates for graph view
function setDefaultGraphDates() {
    const today = new Date();
    const firstDayOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    const lastDayOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    
    const auditStartDate = document.getElementById('auditStartDate');
    const auditEndDate = document.getElementById('auditEndDate');
    
    if (auditStartDate && !auditStartDate.value) {
        auditStartDate.value = firstDayOfMonth.toISOString().split('T')[0];
        defaultDateRange.start = firstDayOfMonth.toISOString().split('T')[0];
    }
    
    if (auditEndDate && !auditEndDate.value) {
        auditEndDate.value = lastDayOfMonth.toISOString().split('T')[0];
        defaultDateRange.end = lastDayOfMonth.toISOString().split('T')[0];
    }
}

function showGraphLoading() {
    let graphDiv = document.getElementById('auditGraphView');
    if (graphDiv) {
        graphDiv.innerHTML = `<div class="loading-overlay"><div class="loading-content"><div class="loading-bars">${'<div class=\'bar\'></div>'.repeat(5)}</div><div class="loading-text">Loading graphs...</div></div></div>`;
    }
}

function clearGraphLoading() {
    let graphDiv = document.getElementById('auditGraphView');
    if (graphDiv) graphDiv.innerHTML = '';
}

function renderGraphUI() {
    let graphDiv = document.getElementById('auditGraphView');
    if (!graphDiv) return;
    graphDiv.innerHTML = `
        <div class="audit-chart-section">
            <div class="audit-chart-container">
                <div class="audit-chart-wrapper">
                    <canvas id="auditCombinedChart"></canvas>
                    <canvas id="feedbackChart" style="display:none;"></canvas>
                    <canvas id="auditProductivityChart" style="display:none;"></canvas>
                </div>
            </div>
            <div id="graphNoDataMsg" class="audit-no-data-message" style="display:none;">
                No data available for the selected employee and date range.
            </div>
        </div>
    `;
}

// Function to initialize or update chart
function initializeChart(ctx, data, options) {
    if (window.feedbackChart) {
        window.feedbackChart.destroy();
    }
    window.feedbackChart = new Chart(ctx, {
        type: 'bar',
        data: data,
        options: options
    });
    return window.feedbackChart;
}

// Function to update graphs for employee
async function updateGraphsForEmployee(empId) {
    if (isProjectView) return;

    showGraphLoading();
    const auditStartDate = document.getElementById('auditStartDate').value;
    const auditEndDate = document.getElementById('auditEndDate').value;
    
    if (!empId) {
        clearGraphLoading();
        renderGraphUI();
        document.getElementById('graphNoDataMsg').style.display = '';
        return;
    }

    try {
        // Fetch data
        const [feedbackData, prodData] = await Promise.all([
            fetch(`/get_audit_reports?from_date=${auditStartDate}&to_date=${auditEndDate}&emp_id=${empId}&entries=1000`).then(r => r.json()),
            fetch(`/get_all_employees_work_data?start_date=${auditStartDate}&end_date=${auditEndDate}&emp_id=${empId}`).then(r => r.json())
        ]);

        if (feedbackData.error) throw new Error(feedbackData.error);
        if (prodData.error) throw new Error(prodData.error);

        const feedbacks = Array.isArray(feedbackData.reports) ? feedbackData.reports : [];
        const prodArray = Array.isArray(prodData) ? prodData : [];

        clearGraphLoading();
        renderGraphUI();

        // Process data by date
        const feedbackByDay = {};
        feedbacks.forEach(fb => {
            const date = fb.processed_date;
            if (!feedbackByDay[date]) feedbackByDay[date] = 0;
            feedbackByDay[date]++;
        });

        const prodByDay = {};
        prodArray.forEach(r => {
            const date = r.date;
            if (!prodByDay[date]) prodByDay[date] = 0;
            prodByDay[date] += parseInt(r.work_units || 0);
        });

        // Generate date range
        let days = [];
        let d = new Date(auditStartDate);
        let end = new Date(auditEndDate);
        while (d <= end) {
            const ds = d.toISOString().split('T')[0];
            days.push(ds);
            if (!feedbackByDay[ds]) feedbackByDay[ds] = 0;
            if (!prodByDay[ds]) prodByDay[ds] = 0;
            d.setDate(d.getDate() + 1);
        }

        // Prepare chart data
        const feedbackCounts = days.map(day => feedbackByDay[day] || 0);
        const prodCounts = days.map(day => prodByDay[day] || 0);

        // Get employee name
        const employeeFilter = document.querySelector('.audit-employee-filter');
        const selectedOption = employeeFilter ? employeeFilter.options[employeeFilter.selectedIndex] : null;
        const employeeName = selectedOption ? selectedOption.text : empId;

        // Initialize chart data
        const chartData = {
            labels: days.map(d => new Date(d).toLocaleDateString()),
            datasets: [
                {
                    label: 'Work Units',
                    data: prodCounts,
                    backgroundColor: '#4f8cff',
                    borderRadius: 6,
                    maxBarThickness: 32,
                    order: 2,
                    yAxisID: 'y1'
                },
                {
                    label: 'Feedbacks',
                    data: feedbackCounts,
                    type: 'line',
                    borderColor: '#1abc9c',
                    backgroundColor: 'rgba(26,188,156,0.15)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: '#1abc9c',
                    pointBorderColor: '#fff',
                    pointHoverRadius: 6,
                    order: 1,
                    yAxisID: 'y'
                }
            ]
        };

        // Initialize chart options
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 20,
                        font: {
                            size: 12,
                            weight: '600'
                        }
                    }
                },
                tooltip: {
                    enabled: true,
                    mode: 'index',
                    intersect: false,
                    padding: 12,
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    titleColor: '#2c3e50',
                    titleFont: { weight: '600' },
                    bodyColor: '#2c3e50',
                    bodyFont: { size: 13 },
                    borderColor: '#ddd',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            label += context.parsed.y;
                            return label;
                        }
                    }
                },
                title: {
                    display: true,
                    text: `Performance Overview - ${employeeName}`,
                    font: {
                        size: 16,
                        weight: '600'
                    },
                    padding: { bottom: 30 }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: true,
                        drawBorder: true,
                        drawOnChartArea: true,
                        drawTicks: true,
                        color: '#e9ecef'
                    },
                    ticks: {
                        font: {
                            size: 11
                        },
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Feedbacks',
                        font: {
                            weight: '600'
                        }
                    },
                    beginAtZero: true,
                    grid: {
                        display: true,
                        drawBorder: true,
                        drawOnChartArea: true,
                        drawTicks: true,
                        color: '#e9ecef'
                    }
                },
                y1: {
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Work Units',
                        font: {
                            weight: '600'
                        }
                    },
                    beginAtZero: true,
                    grid: {
                        display: false
                    }
                }
            }
        };

        // Initialize chart
        const ctx = document.getElementById('auditCombinedChart').getContext('2d');
        initializeChart(ctx, chartData, chartOptions);

        // Show no data message if both are empty
        if (feedbackCounts.every(v => v === 0) && prodCounts.every(v => v === 0)) {
            document.getElementById('graphNoDataMsg').style.display = '';
        } else {
            document.getElementById('graphNoDataMsg').style.display = 'none';
        }

    } catch (error) {
        console.error('Error updating employee graphs:', error);
        clearGraphLoading();
        renderGraphUI();
        document.getElementById('graphNoDataMsg').textContent = 'Failed to load data. ' + (error.message || '');
        document.getElementById('graphNoDataMsg').style.display = '';
    }
}


// --- Hook into toggle logic ---
const origUpdateAuditFilterHeaderForMode = updateAuditFilterHeaderForMode;
updateAuditFilterHeaderForMode = function() {
    origUpdateAuditFilterHeaderForMode();
    
    const workTypeFilter = document.querySelector('.audit-worktype-filter');
    const employeeFilter = document.querySelector('.audit-employee-filter');
    const footer = document.querySelector('.audit-reports-footer');
    
    if (window.isGraphMode) {
        if (footer) footer.style.display = 'none';
        if (workTypeFilter) workTypeFilter.style.display = '';
        if (employeeFilter) employeeFilter.style.display = '';
        
        // Set default dates to 1st of current month
        setDefaultGraphDates();
        
        // Load projects and work types
        loadProjects();
        
        // Set up employee filter and load default employee view
        populateEmployeeFilter().then(() => {
            renderGraphUI();
            setupGraphModeEvents();
            
            // Select logged-in user if present
            const employeeFilter = document.querySelector('.audit-employee-filter');
            let loggedEmpId = sessionStorage.getItem('emp_id');
            if (!loggedEmpId) {
                const userNameBtn = document.getElementById('user-name');
                loggedEmpId = userNameBtn ? userNameBtn.getAttribute('data-employee-id') : null;
            }
            
            let found = false;
            if (employeeFilter && loggedEmpId) {
                for (let i = 0; i < employeeFilter.options.length; i++) {
                    if (employeeFilter.options[i].value === loggedEmpId) {
                        employeeFilter.selectedIndex = i;
                        found = true;
                        break;
                    }
                }
            }
            
            if (employeeFilter) {
                if (found) {
                    updateGraphsForEmployee(employeeFilter.value);
                } else if (employeeFilter.options.length > 1) {
                    employeeFilter.selectedIndex = 1;
                    updateGraphsForEmployee(employeeFilter.value);
                } else {
                    updateGraphsForEmployee('');
                }
            }
        });
    } else {
        if (footer) footer.style.display = '';
        if (workTypeFilter) workTypeFilter.style.display = 'none';
        if (employeeFilter) employeeFilter.style.display = 'none';
        
        // Clean up charts
        if (feedbackChart) { feedbackChart.destroy(); feedbackChart = null; }
        if (productivityChart) { productivityChart.destroy(); productivityChart = null; }
        
        // Clear canvases
        const prodCanvas = document.getElementById('auditProductivityChart');
        if (prodCanvas) { const ctx = prodCanvas.getContext('2d'); ctx && ctx.clearRect(0, 0, prodCanvas.width, prodCanvas.height); }
        const feedCanvas = document.getElementById('feedbackChart');
        if (feedCanvas) { const ctx = feedCanvas.getContext('2d'); ctx && ctx.clearRect(0, 0, feedCanvas.width, feedCanvas.height); }
    }
};

// Function to update work type filter options
function updateWorkTypeFilter(workTypes) {
    const workTypeFilter = document.querySelector('.audit-worktype-filter');
    if (workTypeFilter) {
        workTypeFilter.innerHTML = '<option value="">All Work Types</option>';
        workTypes.forEach(workType => {
            const option = document.createElement('option');
            option.value = workType;
            option.textContent = workType;
            workTypeFilter.appendChild(option);
        });

        // Add event listener for work type selection
        workTypeFilter.addEventListener('change', function() {
            selectedWorkType = this.value;
            if (window.isGraphMode) {
                updateProjectGraphs();
            }
        });
    }
}

// Function to update graphs for project view
async function updateProjectGraphs() {
    if (!selectedProject) return;
    
    showGraphLoading();
    const startDate = auditStartDate?.value || defaultDateRange.start;
    const endDate = auditEndDate?.value || defaultDateRange.end;

    // Ensure we have valid dates
    if (!startDate || !endDate) {
        setDefaultDates(window.isGraphMode);
    }

    try {
        // Reset employee filter to "All Employees"
        const employeeFilter = document.querySelector('.audit-employee-filter');
        if (employeeFilter) {
            employeeFilter.value = '';
        }

        // Fetch feedback data with increased entries to ensure we get all data
        const feedbackRes = await fetch(`/get_audit_reports?from_date=${startDate}&to_date=${endDate}&project=${encodeURIComponent(selectedProject)}&work_type=${encodeURIComponent(selectedWorkType)}&entries=10000`);
        const feedbackData = await feedbackRes.json();
        if (feedbackData.error) throw new Error(feedbackData.error);
        const feedbacks = Array.isArray(feedbackData.reports) ? feedbackData.reports : [];

        // Fetch productivity data
        const prodRes = await fetch(`/get_all_employees_work_data?start_date=${startDate}&end_date=${endDate}&project=${encodeURIComponent(selectedProject)}&work_type=${encodeURIComponent(selectedWorkType)}`);
        const prodData = await prodRes.json();
        if (prodData.error) throw new Error(prodData.error);
        const prodArray = Array.isArray(prodData) ? prodData : [];

        clearGraphLoading();
        renderGraphUI();

        // Filter data by work type if selected
        const filteredFeedbacks = selectedWorkType 
            ? feedbacks.filter(fb => fb.work_type === selectedWorkType)
            : feedbacks;

        const filteredProdArray = selectedWorkType
            ? prodArray.filter(r => r.work_type === selectedWorkType)
            : prodArray;

        // Process feedback data by date
        const feedbackByDay = {};
        filteredFeedbacks.forEach(fb => {
            const date = fb.processed_date;
            if (!feedbackByDay[date]) feedbackByDay[date] = 0;
            feedbackByDay[date]++;
        });

        // Process productivity data by date
        const prodByDay = {};
        filteredProdArray.forEach(r => {
            const date = r.date;
            if (!prodByDay[date]) prodByDay[date] = 0;
            prodByDay[date] += parseInt(r.work_units || 0);
        });

        // Generate date range
        let days = [];
        let d = new Date(startDate);
        let end = new Date(endDate);
        while (d <= end) {
            const ds = d.toISOString().split('T')[0];
            days.push(ds);
            if (!feedbackByDay[ds]) feedbackByDay[ds] = 0;
            if (!prodByDay[ds]) prodByDay[ds] = 0;
            d.setDate(d.getDate() + 1);
        }

        // Prepare chart data
        const feedbackCounts = days.map(day => feedbackByDay[day] || 0);
        const prodCounts = days.map(day => prodByDay[day] || 0);

        // Initialize chart data
        const chartData = {
            labels: days.map(d => new Date(d).toLocaleDateString()),
            datasets: [
                {
                    label: 'Work Units',
                    data: prodCounts,
                    backgroundColor: '#4f8cff',
                    borderRadius: 6,
                    maxBarThickness: 32,
                    order: 2,
                    yAxisID: 'y1'
                },
                {
                    label: 'Feedbacks',
                    data: feedbackCounts,
                    type: 'line',
                    borderColor: '#1abc9c',
                    backgroundColor: 'rgba(26,188,156,0.15)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: '#1abc9c',
                    pointBorderColor: '#fff',
                    pointHoverRadius: 6,
                    order: 1,
                    yAxisID: 'y'
                }
            ]
        };

        // Initialize chart options
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 20,
                        font: {
                            size: 12,
                            weight: '600'
                        }
                    }
                },
                tooltip: {
                    enabled: true,
                    mode: 'index',
                    intersect: false,
                    padding: 12,
                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    titleColor: '#2c3e50',
                    titleFont: { weight: '600' },
                    bodyColor: '#2c3e50',
                    bodyFont: { size: 13 },
                    borderColor: '#ddd',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            label += context.parsed.y;
                            return label;
                        }
                    }
                },
                title: {
                    display: true,
                    text: `Project Performance Overview - ${selectedProject}${selectedWorkType ? ` (${selectedWorkType})` : ''}`,
                    font: {
                        size: 16,
                        weight: '600'
                    },
                    padding: { bottom: 30 }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: true,
                        drawBorder: true,
                        drawOnChartArea: true,
                        drawTicks: true,
                        color: '#e9ecef'
                    },
                    ticks: {
                        font: {
                            size: 11
                        },
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Feedbacks',
                        font: {
                            weight: '600'
                        }
                    },
                    beginAtZero: true,
                    grid: {
                        display: true,
                        drawBorder: true,
                        drawOnChartArea: true,
                        drawTicks: true,
                        color: '#e9ecef'
                    }
                },
                y1: {
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Work Units',
                        font: {
                            weight: '600'
                        }
                    },
                    beginAtZero: true,
                    grid: {
                        display: false
                    }
                }
            }
        };

        // Initialize chart
        const ctx = document.getElementById('auditCombinedChart').getContext('2d');
        initializeChart(ctx, chartData, chartOptions);

        // Show no data message if both are empty
        const noDataMsg = document.getElementById('graphNoDataMsg');
        if (noDataMsg) {
            if (feedbackCounts.every(v => v === 0) && prodCounts.every(v => v === 0)) {
                noDataMsg.style.display = '';
            } else {
                noDataMsg.style.display = 'none';
            }
        }

    } catch (error) {
        console.error('Error updating project graphs:', error);
        clearGraphLoading();
        renderGraphUI();
        const noDataMsg = document.getElementById('graphNoDataMsg');
        if (noDataMsg) {
            noDataMsg.textContent = 'Failed to load data. ' + (error.message || '');
            noDataMsg.style.display = '';
        }
    }
}

function setupGraphModeEvents() {
    const employeeFilter = document.querySelector('.audit-employee-filter');
    if (employeeFilter) {
        // Remove existing event listener if any
        const newEmployeeFilter = employeeFilter.cloneNode(true);
        employeeFilter.parentNode.replaceChild(newEmployeeFilter, employeeFilter);

        newEmployeeFilter.addEventListener('change', function() {
            if (this.value) {
                isProjectView = false;
                selectedProject = '';
                selectedWorkType = '';
                
                // Reset project and work type filters
                const projectFilter = document.querySelector('.audit-project-filter');
                const workTypeFilter = document.querySelector('.audit-worktype-filter');
                if (projectFilter) projectFilter.value = '';
                if (workTypeFilter) workTypeFilter.value = '';
                
                updateGraphsForEmployee(this.value);
            }
        });
    }

    const auditStartDate = document.getElementById('auditStartDate');
    const auditEndDate = document.getElementById('auditEndDate');
    
    if (auditStartDate && auditEndDate) {
        // Remove existing event listeners if any
        const newStartDate = auditStartDate.cloneNode(true);
        const newEndDate = auditEndDate.cloneNode(true);
        auditStartDate.parentNode.replaceChild(newStartDate, auditStartDate);
        auditEndDate.parentNode.replaceChild(newEndDate, auditEndDate);

        newStartDate.addEventListener('change', function() {
            if (isProjectView && selectedProject) {
                updateProjectGraphs();
            } else {
                const empId = document.querySelector('.audit-employee-filter').value;
                updateGraphsForEmployee(empId);
            }
        });

        newEndDate.addEventListener('change', function() {
            if (isProjectView && selectedProject) {
                updateProjectGraphs();
            } else {
                const empId = document.querySelector('.audit-employee-filter').value;
                updateGraphsForEmployee(empId);
            }
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Set initial default dates based on view mode
    setDefaultDates(window.isGraphMode);
    
    // Initialize the audit report view
    fetchAuditData();

    // Add date change listeners
    if (auditStartDate) {
        auditStartDate.addEventListener('change', function() {
            if (window.isGraphMode) {
                defaultDateRange.graph.start = this.value;
            } else {
                defaultDateRange.table.start = this.value;
            }
            fetchAuditData();
        });
    }

    if (auditEndDate) {
        auditEndDate.addEventListener('change', function() {
            if (window.isGraphMode) {
                defaultDateRange.graph.end = this.value;
            } else {
                defaultDateRange.table.end = this.value;
            }
            fetchAuditData();
        });
    }
});
