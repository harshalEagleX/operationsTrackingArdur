document.addEventListener('DOMContentLoaded', function() {
    // Add toggle form functionality
    const toggleFormBtn = document.getElementById('toggleFormBtn');
    const formContainer = document.getElementById('orderAllocationFormContainer');
    const orderDetailsSelect = document.getElementById('oa_orderDetails');
    const stateSelect = document.getElementById('oa_state');
    const countySelect = document.getElementById('oa_county');
    const searchTypeSelect = document.getElementById('oa_searchType');
    const feesInput = document.getElementById('oa_fees');
    const vendorRatesContainer = document.getElementById('vendor-rates-container');

    // Fetch orders immediately when the tab is loaded
    const orderAllocationTab = document.getElementById('orderallocation');
    if (orderAllocationTab) {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                    const isVisible = orderAllocationTab.style.display !== 'none';
                    if (isVisible) {
                        fetchExistingOrders();
                    }
                }
            });
        });

        observer.observe(orderAllocationTab, {
            attributes: true,
            attributeFilter: ['style']
        });

        // Also fetch if the tab is already visible
        if (orderAllocationTab.style.display !== 'none') {
            fetchExistingOrders();
        }
    }

    // Load order types with MasterDataCache
    MasterDataCache.getOrFetch('oa_order_types', '/api/v1/allocations/rates/order_types/')
        .then(orderTypes => {
            const types = orderTypes.data || orderTypes;
            orderDetailsSelect.innerHTML = '<option value="">Select Order Type</option>' +
                types.map(type => `<option value="${type}">${type}</option>`).join('');
        })
        .catch(error => console.error('Error loading order types:', error));

    // Handle order type change
    orderDetailsSelect.addEventListener('change', function() {
        const selectedOrderType = this.value;
        if (selectedOrderType) {
            // Load states for selected order type with caching
            MasterDataCache.getOrFetch(`oa_states_${selectedOrderType}`, `/api/v1/allocations/rates/states/${selectedOrderType}/`)
                .then(states => {
                    stateSelect.innerHTML = '<option value="">Select State</option>' +
                        states.map(state => `<option value="${state}">${state}</option>`).join('');
                    stateSelect.disabled = false;
                    countySelect.innerHTML = '<option value="">Select County</option>';
                    countySelect.disabled = true;
                })
                .catch(error => console.error('Error loading states:', error));
        } else {
            stateSelect.innerHTML = '<option value="">Select State</option>';
            stateSelect.disabled = true;
            countySelect.innerHTML = '<option value="">Select County</option>';
            countySelect.disabled = true;
        }
    });

    // Handle state change
    stateSelect.addEventListener('change', function() {
        const selectedOrderType = orderDetailsSelect.value;
        const selectedStateOption = this.value;
        
        // Extract actual state name from the format "stateabr - state"
        const selectedState = selectedStateOption.split(' - ')[1];
        
        if (selectedOrderType && selectedState) {
            // Load counties for selected state with caching
            MasterDataCache.getOrFetch(`oa_counties_${selectedOrderType}_${selectedState}`, `/api/v1/allocations/rates/counties/${selectedOrderType}/${encodeURIComponent(selectedState)}/`)
                .then(counties => {
                    countySelect.innerHTML = '<option value="">Select County</option>' +
                        counties.map(county => `<option value="${county}">${county}</option>`).join('');
                    countySelect.disabled = false;
                })
                .catch(error => console.error('Error loading counties:', error));
        } else {
            countySelect.innerHTML = '<option value="">Select County</option>';
            countySelect.disabled = true;
        }
    });

    // Handle search type change
    searchTypeSelect.addEventListener('change', function() {
        switch(this.value) {
            case 'Free':
                feesInput.value = '0';
                feesInput.readOnly = true;
                vendorRatesContainer.style.display = 'none';
                document.querySelector('.margin-field').style.display = 'none';
                break;
            case 'Paid':
                feesInput.value = '';
                feesInput.readOnly = false;
                vendorRatesContainer.style.display = 'none';
                document.querySelector('.margin-field').style.display = 'none';
                break;
            case 'Ground':
                feesInput.value = '0';
                feesInput.readOnly = true;
                vendorRatesContainer.style.display = 'block';
                document.querySelector('.margin-field').style.display = 'block';
                loadVendorRates();
                break;
        }
    });

    // Function to load vendor rates
    function loadVendorRates() {
        const orderType = orderDetailsSelect.value;
        const state = stateSelect.value;  // Keep the full state format as backend will handle it
        const county = countySelect.value;
        const vendorRatesList = document.querySelector('.vendor-rates-list');
        const marginInput = document.getElementById('oa_margin');

        if (!orderType || !state || !county) {
            console.error('Please select order type, state, and county first');
            searchTypeSelect.value = 'Free';
            vendorRatesContainer.style.display = 'none';
            document.querySelector('.margin-field').style.display = 'none';
            return;
        }

        fetch(`/api/v1/allocations/rates/?order_type=${encodeURIComponent(orderType)}&state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(vendors => {
                if (!Array.isArray(vendors)) {
                    throw new Error('Invalid response format: expected an array');
                }

                if (vendors.length === 0) {
                    console.warn('No vendor rates found');
                    vendorRatesList.innerHTML = '<p>No vendor rates available</p>';
                    return;
                }
                const row = vendors[0];
                let html = '';
                if (row.vendor_rts !== null) {
                    html += `
                    <div class="vendor-rate-item">
                        <input type="radio" name="vendor_rate" id="vendor_rts" value="${row.vendor_rts}">
                        <label for="vendor_rts">
                            <span>RTS</span>
                            <span class="vendor-rate-value">$${row.vendor_rts}</span>
                        </label>
                    </div>`;
                }
                if (row.vendor_slt !== null) {
                    html += `
                    <div class="vendor-rate-item">
                        <input type="radio" name="vendor_rate" id="vendor_slt" value="${row.vendor_slt}">
                        <label for="vendor_slt">
                            <span>SLT</span>
                            <span class="vendor-rate-value">$${row.vendor_slt}</span>
                        </label>
                    </div>`;
                }
                vendorRatesList.innerHTML = html;

                // Add event listeners to radio buttons
                document.querySelectorAll('input[name="vendor_rate"]').forEach(radio => {
                    radio.addEventListener('change', function() {
                        feesInput.value = this.value;
                        // Update margin if it exists
                        if (marginInput && marginInput.value) {
                            const vendorRate = parseFloat(this.value);
                            const margin = parseFloat(marginInput.value);
                            feesInput.value = (vendorRate + margin).toFixed(2);
                        }
                    });
                });

                // Add event listener to margin input
                if (marginInput) {
                    marginInput.addEventListener('input', function() {
                        const selectedVendorRate = document.querySelector('input[name="vendor_rate"]:checked');
                        if (selectedVendorRate) {
                            const vendorRate = parseFloat(selectedVendorRate.value);
                            const margin = parseFloat(this.value) || 0;
                            feesInput.value = (vendorRate + margin).toFixed(2);
                        }
                    });
                }
            })
            .catch(error => {
                console.error('Error loading vendor rates:', error);
                vendorRatesList.innerHTML = '<p>Error loading vendor rates</p>';
                searchTypeSelect.value = 'Free';
                vendorRatesContainer.style.display = 'none';
                document.querySelector('.margin-field').style.display = 'none';
            });
    }

    // Add event listeners for state and county changes to update vendor rates
    stateSelect.addEventListener('change', function() {
        if (searchTypeSelect.value === 'Ground') {
            loadVendorRates();
        }
    });

    countySelect.addEventListener('change', function() {
        if (searchTypeSelect.value === 'Ground') {
            loadVendorRates();
        }
    });

    if (toggleFormBtn && formContainer) {
        toggleFormBtn.addEventListener('click', function() {
            const isHidden = formContainer.style.display === 'none';
            formContainer.style.display = isHidden ? 'block' : 'none';
            toggleFormBtn.classList.toggle('active');
            if (isHidden && typeof jQuery !== 'undefined' && typeof jQuery.fn.select2 !== 'undefined') {
                setTimeout(() => {
                    $('#oa_empIdName').select2({
                        placeholder: 'Select an employee',
                        allowClear: true,
                        width: '100%'
                    });
                }, 50);
            }
        });
    }

    // Function to format date and time as required by datetime-local input
    function formatDateTimeForInput(dateTimeStr) {
        
        if (!dateTimeStr) {
            return '';
        }
        
        try {
            let date;
            
            // Check if the input is already a Date object
            if (dateTimeStr instanceof Date) {
                date = dateTimeStr;
            } else if (typeof dateTimeStr === 'string') {
                
                // Check if it's in ISO format (YYYY-MM-DDTHH:mm)
                const isoMatch = dateTimeStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
                if (isoMatch) {
                    const [_, year, month, day, hours, minutes] = isoMatch;
                    // Return as is since it's already in the correct format
                    return `${year}-${month}-${day}T${hours}:${minutes}`;
                }
                
                // Try direct parsing
                date = new Date(dateTimeStr);
                
                if (isNaN(date.getTime())) {
                    // Try MySQL format
                    const mysqlMatch = dateTimeStr.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/);
                    if (mysqlMatch) {
                        const [_, year, month, day, hours, minutes, seconds] = mysqlMatch;
                        date = new Date(year, month - 1, day, hours, minutes, seconds);
                    }
                }
            } else {
                console.warn('Invalid input type:', typeof dateTimeStr);
                return '';
            }

            // Validate the date
            if (!date || isNaN(date.getTime())) {
                console.warn('Invalid date after parsing:', date);
                return '';
            }
            
            // Format the date
            const formatted = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}T${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
            return formatted;
            
        } catch (error) {
            console.error('Error in formatDateTimeForInput:', error);
            console.error('Problematic input:', dateTimeStr);
            return '';
        }
    }

    // Function to calculate and update ETA and SLA based on received date
    function updateETAandSLA(receivedDateTime) {
        try {
            const receivedDate = new Date(receivedDateTime);
            
            // Only update if receivedDate is valid
            if (isNaN(receivedDate.getTime())) {
                return;
            }
            
            // Calculate ETA (received date + 2.5 hours)
            const etaDate = new Date(receivedDate.getTime());
            etaDate.setHours(etaDate.getHours() + 2);
            etaDate.setMinutes(etaDate.getMinutes() + 30);
            
            // Calculate SLA (received date + 24 hours)
            const slaDate = new Date(receivedDate.getTime());
            slaDate.setHours(slaDate.getHours() + 24);
            
            // Update the input fields with the new calculated times
            etaInput.value = formatDateTimeForInput(etaDate);
            slaInput.value = formatDateTimeForInput(slaDate);

        } catch (error) {
            console.error('Error updating ETA and SLA:', error);
        }
    }

    // Function to update all date fields
    function updateDateFields() {
        const now = new Date();
        receivedDateInput.value = formatDateTimeForInput(now);
        updateETAandSLA(receivedDateInput.value);
    }

    // Convert input fields to datetime-local and set step to "1" for seconds precision
    const receivedDateInput = document.getElementById('oa_receivedDate');
    const etaInput = document.getElementById('oa_eta');
    const slaInput = document.getElementById('oa_sla');

    receivedDateInput.type = 'datetime-local';
    receivedDateInput.step = '1';
    etaInput.type = 'datetime-local';
    etaInput.step = '1';
    slaInput.type = 'datetime-local';
    slaInput.step = '1';

    // Set initial values with current IST time
    updateDateFields();

    // Add event listeners for manual datetime changes
    [receivedDateInput, etaInput, slaInput].forEach(input => {
        input.addEventListener('change', function() {
            if (this.value) {
                this.value = ensureSecondsInDateTime(this.value);
            }
        });

        input.addEventListener('blur', function() {
            if (this.value) {
                this.value = ensureSecondsInDateTime(this.value);
            }
        });
    });

    // Function to ensure datetime string includes seconds
    function ensureSecondsInDateTime(dateTimeStr) {
        if (!dateTimeStr) return dateTimeStr;
        // If the string doesn't include seconds, add ':00'
        if (dateTimeStr.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)) {
            return dateTimeStr + ':00';
        }
        return dateTimeStr;
    }

    // Handle real-time updates for received date
    receivedDateInput.addEventListener('input', function(e) {
        if (this.value) {
            updateETAandSLA(this.value);
        }
    });

    // Ensure updates happen on all types of changes
    ['change', 'keyup', 'blur'].forEach(eventType => {
        receivedDateInput.addEventListener(eventType, function(e) {
            if (this.value) {
                updateETAandSLA(this.value);
            }
        });
    });

    // Handle programmatic changes
    const receivedDateObserver = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'value') {
                const newValue = receivedDateInput.value;
                if (newValue) {
                    updateETAandSLA(newValue);
                }
            }
        });
    });

    receivedDateObserver.observe(receivedDateInput, {
        attributes: true,
        attributeFilter: ['value']
    });

    // Initialize form functionality
    initializeOrderAllocationForm();
});

    // Function to initialize form functionality
    function initializeOrderAllocationForm() {
        const form = document.getElementById('orderallocationForm');
        const projectSelect = document.getElementById('oa_project');
        const clientCodeSelect = document.getElementById('oa_clientCode');
        const workTypeSelect = document.getElementById('oa_workType');
        const employeeSelect = document.getElementById('oa_empIdName');
        const feesInput = document.getElementById('oa_fees');
        const receivedDateInput = document.getElementById('oa_receivedDate');
        const etaInput = document.getElementById('oa_eta');
        const slaInput = document.getElementById('oa_sla');
        const vendorRatesContainer = document.getElementById('vendor-rates-container');
        let currentOrderId = 1;

        // Store project and employee mappings
        let projectMap = new Map();
        let employeeMap = new Map();

    // Function to format date and time as required by datetime-local input
    function formatDateTimeForInput(date) {
        // Convert to IST
        const istDate = new Date(date.getTime() + (5.5 * 60 * 60 * 1000)); // Add 5:30 hours for IST
        
        const year = istDate.getUTCFullYear();
        const month = String(istDate.getUTCMonth() + 1).padStart(2, '0');
        const day = String(istDate.getUTCDate()).padStart(2, '0');
        const hours = String(istDate.getUTCHours()).padStart(2, '0');
        const minutes = String(istDate.getUTCMinutes()).padStart(2, '0');
        const seconds = String(istDate.getUTCSeconds()).padStart(2, '0');
        
        return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
    }

    // Function to calculate and update ETA and SLA based on received date
    function updateETAandSLA(receivedDateTime) {
        try {
            const receivedDate = new Date(receivedDateTime);
            
            // Only update if receivedDate is valid
            if (isNaN(receivedDate.getTime())) {
                return;
            }
            
            // Calculate ETA (received date + 2.5 hours)
            const etaDate = new Date(receivedDate.getTime());
            etaDate.setHours(etaDate.getHours() + 2);
            etaDate.setMinutes(etaDate.getMinutes() + 30);
            
            // Calculate SLA (received date + 24 hours)
            const slaDate = new Date(receivedDate.getTime());
            slaDate.setHours(slaDate.getHours() + 24);
            
            // Update the input fields with the new calculated times
            etaInput.value = formatDateTimeForInput(etaDate);
            slaInput.value = formatDateTimeForInput(slaDate);

        } catch (error) {
            console.error('Error updating ETA and SLA:', error);
        }
    }

    // Function to update all date fields
    function updateDateFields() {
        const now = new Date();
        receivedDateInput.value = formatDateTimeForInput(now);
        updateETAandSLA(receivedDateInput.value);
    }

    // Fetch project data and populate dropdowns with MasterDataCache
    MasterDataCache.getOrFetch('oa_projects', '/api/v1/masters/projects/')
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            
            let clientCodes = [];
            let workTypes = [];
            let defaultProjectId = '';
            let defaultProjectName = '';

            if (Array.isArray(data)) {
                // Handle raw array of projects
                data.forEach(p => {
                    if (p.project_id && p.project_name) {
                        projectMap.set(p.project_id.toString(), p.project_name);
                    }
                    (p.client_code || '').split('|').forEach(c => {
                        const code = c.trim();
                        if (code && !clientCodes.includes(code)) clientCodes.push(code);
                    });
                    (p.worktypes || '').split('|').forEach(w => {
                        const wt = w.trim();
                        if (wt && !workTypes.includes(wt)) workTypes.push(wt);
                    });
                });
                if (data.length > 0) {
                    const def = data.find(p => (p.project_name || '').toLowerCase().includes('title')) || data[0];
                    defaultProjectId = def.project_id;
                    defaultProjectName = def.project_name;
                }
            } else {
                // Handle structured response
                if (data.project && data.project.id) {
                    defaultProjectId = data.project.id;
                    defaultProjectName = data.project.name;
                    projectMap.set(data.project.id.toString(), data.project.name);
                } else if (data.projects && Array.isArray(data.projects) && data.projects.length > 0) {
                    const def = data.projects.find(p => (p.project_name || '').toLowerCase().includes('title')) || data.projects[0];
                    defaultProjectId = def.project_id;
                    defaultProjectName = def.project_name;
                    data.projects.forEach(p => {
                        if (p.project_id && p.project_name) projectMap.set(p.project_id.toString(), p.project_name);
                    });
                }

                clientCodes = Array.isArray(data.client_codes) ? data.client_codes : [];
                workTypes = Array.isArray(data.work_types) ? data.work_types : [];
            }

            if (projectSelect && defaultProjectId) {
                projectSelect.innerHTML = `<option value="${defaultProjectId}">${defaultProjectName}</option>`;
            }

            // Populate client codes
            if (clientCodeSelect) {
                if (clientCodes.length > 0) {
                    clientCodeSelect.innerHTML = '<option value="">Select client code</option>' +
                        clientCodes.map(code => `<option value="${code}">${code}</option>`).join('');
                } else {
                    clientCodeSelect.innerHTML = '<option value="">No client codes found</option>';
                }
            }

            // Populate work types
            if (workTypeSelect) {
                if (workTypes.length > 0) {
                    workTypeSelect.innerHTML = '<option value="">Select work type</option>' +
                        workTypes.map(type => `<option value="${type}">${type}</option>`).join('');
                } else {
                    workTypeSelect.innerHTML = '<option value="">No work types found</option>';
                }
            }
        })
        .catch(error => {
            console.error('Error fetching project data:', error);
            if (clientCodeSelect) clientCodeSelect.innerHTML = '<option value="">Error loading client codes</option>';
            if (workTypeSelect) workTypeSelect.innerHTML = '<option value="">Error loading work types</option>';
        });

    // Helper function to initialize Select2 combo box on Assign To field
    function initEmployeeSelect2() {
        if (typeof jQuery !== 'undefined' && typeof jQuery.fn.select2 !== 'undefined') {
            $('#oa_empIdName').select2({
                placeholder: 'Select an employee',
                allowClear: true,
                width: '100%',
                matcher: function(params, data) {
                    if ($.trim(params.term) === '') {
                        return data;
                    }
                    if (typeof data.text === 'undefined') {
                        return null;
                    }
                    const term = params.term.toLowerCase();
                    const text = data.text.toLowerCase();
                    const empId = (data.id || '').toString().toLowerCase();
                    if (text.indexOf(term) > -1 || empId.indexOf(term) > -1) {
                        return data;
                    }
                    return null;
                }
            });
        }
    }

    // Fetch and populate employees with mapping using MasterDataCache
    MasterDataCache.getOrFetch('oa_employees', '/api/v1/auth/employees/')
        .then(employees => {
            if (employees.data) {
                employees = employees.data;
            }
            if (!Array.isArray(employees)) {
                if (employees.error) {
                    throw new Error(employees.error);
                }
                throw new Error('Invalid response format');
            }
            
            if (employees.length === 0) {
                employeeSelect.innerHTML = '<option value="">No employees found</option>';
                initEmployeeSelect2();
                if (typeof jQuery !== 'undefined' && typeof jQuery.fn.select2 !== 'undefined') {
                    $('#oa_empIdName').trigger('change.select2');
                }
                return;
            }

            // Store employee mapping
            employees.forEach(emp => {
                employeeMap.set(emp.employee_id.toString(), emp.name);
            });

            employeeSelect.innerHTML = '<option value="">Select an employee</option>' +
                employees.map(emp => `<option value="${emp.employee_id}">${emp.name} (${emp.employee_id})</option>`).join('');

            initEmployeeSelect2();
            if (typeof jQuery !== 'undefined' && typeof jQuery.fn.select2 !== 'undefined') {
                $('#oa_empIdName').trigger('change.select2');
            }
        })
        .catch(error => {
            console.error('Error fetching employees:', error);
            employeeSelect.innerHTML = '<option value="">Error loading employees</option>';
            initEmployeeSelect2();
            if (typeof jQuery !== 'undefined' && typeof jQuery.fn.select2 !== 'undefined') {
                $('#oa_empIdName').trigger('change.select2');
            }
            console.error('Error loading employees: ' + error.message);
        });


    // Generate Task ID
    function generateTaskId() {
        return `Task-${String(currentOrderId).padStart(6, '0')}`;
    }

    // Handle file upload preview
    document.getElementById('oa_document').addEventListener('change', function(e) {
        const files = e.target.files;
        const fileContainer = this.parentNode;
        
        // Clear any existing file previews
        const existingPreviews = fileContainer.querySelectorAll('.selected-file');
        existingPreviews.forEach(preview => preview.remove());

        // Check each file
        for (let file of files) {
            if (file.size > 35 * 1024 * 1024) { // 35MB limit per file
                console.error('File size should not exceed 35MB:', file.name);
                continue;
            }
            
            const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
            if (!allowedTypes.includes(file.type)) {
                console.error('Only PDF and Word documents are allowed:', file.name);
                continue;
            }
            
            // Create preview element for each file
            const filePreview = document.createElement('div');
            filePreview.className = 'selected-file';
            filePreview.innerHTML = `
                <span class="file-name">${file.name}</span>
                <button type="button" class="remove-file" aria-label="Remove file">×</button>
            `;
            fileContainer.appendChild(filePreview);

            // Add remove button functionality
            filePreview.querySelector('.remove-file').addEventListener('click', function() {
                filePreview.remove();
                // Create a new FileList without the removed file
                const dt = new DataTransfer();
                const input = document.getElementById('oa_document');
                for (let i = 0; i < input.files.length; i++) {
                    const f = input.files[i];
                    if (f.name !== file.name) {
                        dt.items.add(f);
                    }
                }
                input.files = dt.files;
            });
        }
    });

    // Function to send chat notification for task assignment
    async function sendTaskAssignmentMessage(assignedToId, taskDetails) {
        try {
            // Get project name from projectMap
            const projectName = projectMap.get(taskDetails.project) || taskDetails.project;
            
            const assignedByName = document.querySelector('#user-name')?.textContent.trim() || 'System';
            const currentUserId = document.querySelector('#user-id')?.value;

            // Check if this is a self-assignment
            const isSelfAssignment = assignedToId === currentUserId;

            let message;
            if (taskDetails.isUpdate) {
                message = `Title Search - Order Allocation Update Notification\n\n` +
                    `${isSelfAssignment ? 'You have updated a task assigned to yourself' : `A task assigned to you has been updated by ${assignedByName}`}\n\n` +
                    `Task Details:\n` +
                    `Task ID: ${taskDetails.task_id}\n` +
                    `Client Code: ${taskDetails.client_code}\n` +
                    `Work Type: ${taskDetails.work_type}\n` +
                    `Search Type: ${taskDetails.search_type}\n\n` +
                    `Please review the updated task details in your task list.\n` +
                    `${isSelfAssignment ? '' : 'For any queries, please contact the updater.'}`;
            } else {
                message = `Title Search - Order Allocation Notification\n\n` +
                    `${isSelfAssignment ? 'You have created a new task for yourself' : `A new task has been assigned to you by ${assignedByName}`}\n\n` +
                    `Task Details:\n` +
                    `Task ID: ${taskDetails.task_id}\n` +
                    `Client Code: ${taskDetails.client_code}\n` +
                    `Work Type: ${taskDetails.work_type}\n` +
                    `Search Type: ${taskDetails.search_type}\n\n` +
                    `Please review the task details in your task list and begin work accordingly.\n` +
                    `${isSelfAssignment ? '' : 'For any queries, please contact the assigner.'}`;
            }

            const response = await fetch('/send_message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    receiver_id: assignedToId,
                    message: message
                })
            });

            if (!response.ok) {
                throw new Error('Failed to send chat notification');
            }

            return await response.json();
        } catch (error) {
            console.error('Error sending chat notification:', error);
        }
    }

    // Handle form submission
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.classList.add('loading');
            
            const formData = new FormData();
            const taskId = generateTaskId();
            
            // Calculate ETA and SLA based on received date
            const receivedDate = document.getElementById('oa_receivedDate').value;
            if (receivedDate) {
                const etaDate = new Date(receivedDate);
                etaDate.setHours(etaDate.getHours() + 2);
                etaDate.setMinutes(etaDate.getMinutes() + 30);
                
                const slaDate = new Date(receivedDate);
                slaDate.setHours(slaDate.getHours() + 24);
                
                document.getElementById('oa_eta').value = formatDateTimeForInput(etaDate);
                document.getElementById('oa_sla').value = formatDateTimeForInput(slaDate);
            }
            
            // Get form values
            const orderData = {
                project: document.getElementById('oa_project').value,
                client_code: document.getElementById('oa_clientCode').value,
                work_type: document.getElementById('oa_workType').value,
                batch_id: document.getElementById('oa_orderBatchId').value,
                order_details: document.getElementById('oa_orderDetails').value,
                employee_id: document.getElementById('oa_empIdName').value,
                task_id: taskId,
                owner_name: document.getElementById('oa_ownerName').value,
                property_address: document.getElementById('oa_propertyAddress').value,
                state: document.getElementById('oa_state').value,
                received_date: document.getElementById('oa_receivedDate').value,
                search_type: document.getElementById('oa_searchType').value,
                fees: feesInput.value || '0',
                eta: document.getElementById('oa_eta').value,
                sla: document.getElementById('oa_sla').value,
                remarks: document.getElementById('oa_remarks').value,
                county: document.getElementById('oa_county').value
            };

            // Add margin value if search type is Ground
            if (orderData.search_type === 'Ground') {
                const marginInput = document.getElementById('oa_margin');
                if (marginInput) {
                    orderData.margin = marginInput.value || '0';
                }
            }

            // Add form data
            Object.entries(orderData).forEach(([key, value]) => {
                formData.append(key, value || '');
            });

            // Add all document files
            const documentFiles = document.getElementById('oa_document').files;
            for (let i = 0; i < documentFiles.length; i++) {
                formData.append('documents[]', documentFiles[i]);
            }

            // Function to show message
            function showMessage(type, text) {
                // Remove any existing messages
                const existingMessage = document.querySelector('.allocation-form-message');
                if (existingMessage) {
                    existingMessage.remove();
                }

                // Create new message
                const message = document.createElement('div');
                message.className = `allocation-form-message ${type}`;
                message.innerHTML = `
                    <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i>
                    ${text}
                `;
                document.body.appendChild(message);

                // Remove message after 3 seconds
                setTimeout(() => {
                    message.remove();
                }, 3000);
            }

            // Validate required fields
            const requiredFields = ['project', 'client_code', 'work_type', 'batch_id', 'order_details', 'employee_id', 'received_date', 'search_type'];
            const missingFields = requiredFields.filter(field => !orderData[field]);
            
            if (missingFields.length > 0) {
                submitBtn.classList.remove('loading');
                showMessage('error', `Please fill in all required fields: ${missingFields.join(', ')}`);
                return;
            }

            // Submit to API
            fetch('/api/v1/allocations/', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(data => {
                        throw new Error(data.error || 'Failed to allocate task');
                    });
                }
                return response.json();
            })
            .then(async data => {
                if (data.success) {
                    // Send chat notification to assigned employee
                    await sendTaskAssignmentMessage(orderData.employee_id, {
                        task_id: orderData.task_id,
                        client_code: orderData.client_code,
                        project: orderData.project,
                        work_type: orderData.work_type,
                        search_type: orderData.search_type
                    });

                    showMessage('success', 'Order allocated successfully!');
                    fetchExistingOrders();
                    form.reset();
                    if (typeof jQuery !== 'undefined' && typeof jQuery.fn.select2 !== 'undefined') {
                        $('#oa_empIdName').val('').trigger('change');
                    }
                    feesInput.value = '0';
                    feesInput.readOnly = true;
                    vendorRatesContainer.style.display = 'none';
                    document.getElementById('oa_document').value = '';
                    updateDateFields();
                    currentOrderId++;
                } else {
                    throw new Error(data.message || 'Error allocating task');
                }
            })
            .catch(error => {
                showMessage('error', error.message || 'Error allocating task. Please try again.');
            })
            .finally(() => {
                submitBtn.classList.remove('loading');
            });
        });
    }

    // State for allocation table pagination and search
    const allocationState = {
        allOrders: [],
        filteredOrders: [],
        currentPage: 1,
        pageSize: 25,
        searchTerm: ''
    };

    // Filter in memory for instant responsiveness
    function filterAllocatedOrders() {
        const term = allocationState.searchTerm.toLowerCase().trim();
        if (!term) {
            allocationState.filteredOrders = [...allocationState.allOrders];
        } else {
            allocationState.filteredOrders = allocationState.allOrders.filter(order => {
                if (!order) return false;
                const taskId = (order.taskId || order.task_id || '').toLowerCase();
                const clientCode = (order.client_code || order.clientCode || '').toLowerCase();
                const workType = (order.work_type || order.workType || '').toLowerCase();
                const batchId = (order.batch_id || order.batchId || '').toLowerCase();
                const ownerName = (order.owner_name || order.ownerName || '').toLowerCase();
                const propertyAddress = (order.property_address || order.propertyAddress || '').toLowerCase();
                const state = (order.state || '').toLowerCase();
                const county = (order.county || '').toLowerCase();
                const employeeId = (order.employee_id || order.employeeId || '').toString().toLowerCase();
                const employeeName = (order.employee_name || order.employeeName || employeeMap.get(employeeId) || '').toLowerCase();
                const status = (order.status || '').toLowerCase();

                return taskId.includes(term) ||
                    clientCode.includes(term) ||
                    workType.includes(term) ||
                    batchId.includes(term) ||
                    ownerName.includes(term) ||
                    propertyAddress.includes(term) ||
                    state.includes(term) ||
                    county.includes(term) ||
                    employeeName.includes(term) ||
                    employeeId.includes(term) ||
                    status.includes(term);
            });
        }
    }

    // Function to display allocated orders in the table with pagination
    function displayAllocatedOrders(orders) {
        allocationState.allOrders = Array.isArray(orders) ? orders : [];
        filterAllocatedOrders();
        allocationState.currentPage = 1;
        renderAllocatedOrdersPage();
    }

    function renderPaginationButtons(container, current, total) {
        if (total <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        const prevDisabled = current === 1 ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : '';
        const nextDisabled = current === total ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : '';

        html += `<button type="button" class="btn btn-sm btn-outline-secondary oa-page-btn" data-page="${current - 1}" ${prevDisabled}>&laquo; Prev</button>`;

        let pages = [];
        if (total <= 7) {
            for (let i = 1; i <= total; i++) pages.push(i);
        } else {
            pages.push(1);
            if (current > 3) pages.push('...');
            const start = Math.max(2, current - 1);
            const end = Math.min(total - 1, current + 1);
            for (let i = start; i <= end; i++) pages.push(i);
            if (current < total - 2) pages.push('...');
            pages.push(total);
        }

        pages.forEach(p => {
            if (p === '...') {
                html += `<span style="padding: 4px 8px; color: #94a3b8; font-size: 13px;">...</span>`;
            } else {
                const isActive = p === current;
                const activeStyle = isActive ? 'background: #2563eb; color: #fff; border-color: #2563eb; font-weight: 600;' : '';
                html += `<button type="button" class="btn btn-sm btn-outline-secondary oa-page-btn" data-page="${p}" style="${activeStyle}">${p}</button>`;
            }
        });

        html += `<button type="button" class="btn btn-sm btn-outline-secondary oa-page-btn" data-page="${current + 1}" ${nextDisabled}>Next &raquo;</button>`;
        container.innerHTML = html;

        container.querySelectorAll('.oa-page-btn:not([disabled])').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(btn.getAttribute('data-page'), 10);
                if (page >= 1 && page <= total) {
                    allocationState.currentPage = page;
                    renderAllocatedOrdersPage();
                }
            });
        });
    }

    function renderAllocatedOrdersPage() {
        const resultsContainer = document.getElementById('allocationResults');
        const paginationInfo = document.getElementById('allocationPaginationInfo');
        const paginationBtns = document.getElementById('allocationPaginationBtns');
        if (!resultsContainer) return;

        const totalItems = allocationState.filteredOrders.length;
        if (totalItems === 0) {
            resultsContainer.innerHTML = '<tr><td colspan="10" class="no-data">No orders allocated yet</td></tr>';
            if (paginationInfo) paginationInfo.textContent = 'Showing 0 to 0 of 0 entries';
            if (paginationBtns) paginationBtns.innerHTML = '';
            return;
        }

        const pageSize = allocationState.pageSize === 'all' ? totalItems : parseInt(allocationState.pageSize, 10);
        const totalPages = Math.ceil(totalItems / pageSize) || 1;
        if (allocationState.currentPage > totalPages) allocationState.currentPage = totalPages;
        if (allocationState.currentPage < 1) allocationState.currentPage = 1;

        const startIdx = allocationState.pageSize === 'all' ? 0 : (allocationState.currentPage - 1) * pageSize;
        const endIdx = allocationState.pageSize === 'all' ? totalItems : Math.min(startIdx + pageSize, totalItems);
        const pageItems = allocationState.filteredOrders.slice(startIdx, endIdx);

        if (paginationInfo) {
            paginationInfo.textContent = `Showing ${startIdx + 1} to ${endIdx} of ${totalItems} entries`;
        }

        const ordersList = pageItems.map(order => {
            if (!order) return '';

            const taskId = order.taskId || order.task_id || '-';
            const clientCode = order.client_code || order.clientCode || '-';
            const workType = order.work_type || order.workType || '-';
            const batchId = order.batch_id || order.batchId || '-';
            const ownerName = order.owner_name || order.ownerName || '-';
            const propertyAddress = order.property_address || order.propertyAddress || '-';
            const state = order.state || '-';
            const county = order.county || '-';
            const employeeId = order.employee_id || order.employeeId || '';
            const employeeName = order.employee_name || employeeMap.get(employeeId.toString()) || employeeId || '-';
            const status = order.status || 'Pending';

            return `
                <tr class="order-row" data-task-id="${taskId}" data-employee-id="${employeeId}">
                    <td>${taskId}</td>
                    <td>${clientCode}</td>
                    <td>${workType}</td>
                    <td>${batchId}</td>
                    <td>${ownerName}</td>
                    <td>${propertyAddress}</td>
                    <td>${state}</td>
                    <td>${county}</td>
                    <td data-employee-id="${employeeId}">${employeeName}</td>
                    <td class="status-cell">
                        <span class="status-badge ${status.toLowerCase()}">${status}</span>
                        <button class="allocation-info-btn" data-task-id="${taskId}" title="View history" aria-label="View history">
                            <i class="fas fa-info-circle"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).filter(row => row).join('');

        resultsContainer.innerHTML = ordersList;

        if (paginationBtns) {
            renderPaginationButtons(paginationBtns, allocationState.currentPage, totalPages);
        }

        attachAllocationRowListeners();
    }

    function attachAllocationRowListeners() {
        const tableEl = document.querySelector('.allocation-table');
        if (!tableEl) return;

        // Attach info button handlers (expand/collapse history rows)
        tableEl.querySelectorAll('.allocation-info-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const button = e.currentTarget;
                const taskId = button.getAttribute('data-task-id');
                const row = button.closest('tr');

                // Toggle existing history row
                const nextRow = row.nextElementSibling;
                if (nextRow && nextRow.classList.contains('allocation-history-row')) {
                    nextRow.remove();
                    return;
                }

                // Remove any other open history rows to avoid clutter
                document.querySelectorAll('.allocation-history-row').forEach(r => r.remove());

                // Create new expandable row
                const colCount = row.parentElement.parentElement.querySelector('thead tr').children.length;
                const expRow = document.createElement('tr');
                expRow.className = 'allocation-history-row';
                const td = document.createElement('td');
                td.colSpan = colCount;
                td.innerHTML = `
                    <div class="allocation-history">
                        <div class="allocation-history-header">
                            <span><i class="fas fa-history"></i> Assignment History</span>
                            <span class="allocation-history-task">${taskId}</span>
                        </div>
                        <div class="allocation-history-body">
                            <div class="allocation-history-loading"><span class="spinner"></span> Loading history...</div>
                        </div>
                    </div>
                `;
                expRow.appendChild(td);
                row.parentElement.insertBefore(expRow, row.nextElementSibling);

                try {
                    const resp = await fetch(`/api/order-allocation/${encodeURIComponent(taskId)}/history`);
                    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                    const data = await resp.json();
                    const body = expRow.querySelector('.allocation-history-body');
                    if (!data.success || !Array.isArray(data.history) || data.history.length === 0) {
                        body.innerHTML = '<div class="oa-empty-state"><i class="fas fa-database"></i><p>No history found.</p></div>';
                        return;
                    }
                    body.innerHTML = renderHistoryTable(data.history);
                } catch (err) {
                    const body = expRow.querySelector('.allocation-history-body');
                    body.innerHTML = `<div class="oa-error-message"><i class="fas fa-exclamation-circle"></i> Failed to load history</div>`;
                    console.error('Error loading history:', err);
                }
            });
        });

        // Utility to close any open menu
        function closeOpenStatusMenus() {
            document.querySelectorAll('.status-action-menu').forEach(m => m.remove());
        }

        // Attach status badge click for dropdown
        tableEl.querySelectorAll('.status-cell .status-badge').forEach(badge => {
            badge.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();

                const isCompleted = badge.classList.contains('completed');
                const isCancelled = badge.classList.contains('cancelled');
                if (isCompleted || isCancelled) {
                    return; // no dropdown for final states
                }

                const cell = badge.closest('.status-cell');
                const row = badge.closest('tr.order-row');
                const taskId = row?.getAttribute('data-task-id');
                if (!cell || !taskId) return;

                // Toggle: close if already open
                const existingMenu = cell.querySelector('.status-action-menu');
                if (existingMenu) {
                    existingMenu.remove();
                    return;
                }
                // Close others
                closeOpenStatusMenus();

                // Build menu
                const menu = document.createElement('div');
                menu.className = 'status-action-menu';
                const cancelBtn = document.createElement('button');
                cancelBtn.className = 'status-action-item danger';
                cancelBtn.innerHTML = '<i class="fas fa-ban"></i> Cancel order';
                menu.appendChild(cancelBtn);
                cell.appendChild(menu);

                // Handle cancel action
                cancelBtn.addEventListener('click', async (ev) => {
                    ev.stopPropagation();
                    ev.preventDefault();
                    const ok = window.confirm('Are you sure you want to cancel this order? This cannot be undone.');
                    if (!ok) return;
                    cancelBtn.disabled = true;
                    try {
                        const resp = await fetch(`/api/order-allocation/${encodeURIComponent(taskId)}/cancel`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({})
                        });
                        const data = await resp.json().catch(() => ({}));
                        if (!resp.ok || !data.success) {
                            throw new Error(data.error || `Failed to cancel (HTTP ${resp.status})`);
                        }
                        // Update badge UI
                        badge.className = 'status-badge cancelled';
                        badge.textContent = 'Cancelled';
                        closeOpenStatusMenus();
                    } catch (err) {
                        console.error('Cancel order failed:', err);
                        alert(err.message || 'Failed to cancel order');
                        cancelBtn.disabled = false;
                    }
                });
            });
        });

        // Add click event listeners to rows for detailed view
        tableEl.querySelectorAll('.order-row').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('.status-cell') || e.target.closest('.allocation-info-btn') || e.target.closest('.status-action-menu')) {
                    return;
                }
                const taskId = this.dataset.taskId;
                if (!taskId) return;

                fetch(`/api/order-allocation/${taskId}`)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (data.success) { 
                            // Add project and employee names to the order data
                            data.order.projectName = projectMap.get(data.order.project?.toString()) || data.order.project;
                            data.order.employeeName = employeeMap.get(data.order.employee_id?.toString()) || data.order.employee_id;
                            displayOrderDetails(data.order);
                        } else {
                            throw new Error(data.error || 'Failed to fetch task details');
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        console.error('Error fetching task details: ' + error.message);
                    });
            });
        });
    }

    function renderHistoryTable(history) {
        function pad(v) { return String(v).padStart(2, '0'); }
        function formatFromSeconds(totalSeconds) {
            if (!totalSeconds || totalSeconds <= 0) return '-';
            const hours = Math.floor(totalSeconds / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const seconds = totalSeconds % 60;
            return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
        }

        const historyWithStatus = (() => {
            const lastByType = {};
            return history.map(h => {
                let status = h.status || '';
                const wt = h.work_type;
                const toNameOrId = h.assigned_to_name || h.assigned_to || '';
                if (!status && wt) {
                    if (lastByType.hasOwnProperty(wt) && lastByType[wt] !== toNameOrId) {
                        status = 'Reassigned';
                    }
                    lastByType[wt] = toNameOrId;
                }
                return { ...h, status };
            });
        })();

        const rows = historyWithStatus.map(h => {
            const assignedOn = h.assigned_on ? new Date(h.assigned_on.replace(' ', 'T')).toLocaleString() : '-';
            const total = (h.total_time_seconds || 0);
            const totalFmt = formatFromSeconds(total);
            const assignedTo = h.assigned_to_name || h.assigned_to || '-';
            const assignedBy = h.assigned_by_name || h.assigned_by || '-';
            return `
                <tr>
                    <td>${h.work_type || '-'}</td>
                    <td>${assignedTo}</td>
                    <td>${assignedBy}</td>
                    <td>${assignedOn}</td>
                    <td>${totalFmt}</td>
                    <td>${h.status || '-'}</td>
                </tr>
            `;
        }).join('');

        return `
            <table class="allocation-history-table">
                <thead>
                    <tr>
                        <th>Work Type</th>
                        <th>Assigned To</th>
                        <th>Assigned By</th>
                        <th>Assigned On</th>
                        <th>Total Time</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        `;
    }


    // Function to display order details in popup
    function displayOrderDetails(order) {
        
        // Parse dates
        const receivedDate = order.received_date ? new Date(order.received_date).toLocaleString() : '-';
        const eta = order.eta ? new Date(order.eta).toLocaleString() : '-';
        const slaDate = order.sla_date ? new Date(order.sla_date).toLocaleString() : '-';


        // Remove any existing popups
        const existingPopup = document.querySelector('.oa-details-popup');
        if (existingPopup) {
            existingPopup.remove();
        }

        // Create the popup content
        const popup = document.createElement('div');
        popup.className = 'oa-details-popup';
        popup.innerHTML = `
            <div class="oa-details-container">
                <div class="oa-details-header">
                    <h3><i class="fas fa-file-alt"></i> Order Details</h3>
                    <div class="oa-details-actions">
                        <button class="oa-save-btn" style="display: none;"><i class="fas fa-save"></i> Save</button>
                        <button class="oa-details-close">&times;</button>
                    </div>
                </div>
                <div class="oa-details-body">
                    <div class="oa-details-grid">
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Task ID</div>  
                            <div class="oa-detail-value">${order.task_id || '-'}</div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Project</div>
                            <div class="oa-detail-value">${order.projectName || '-'}</div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Client Code</div>
                            <div class="oa-detail-value">${order.client_code || '-'}</div>
                        </div>
                        <div class="oa-detail-item editable">
                            <div class="oa-detail-label">Work Type</div>
                            <div class="oa-detail-value">
                                <select class="oa-edit-worktype" style="display: none;">
                                    <option value="${order.work_type}">${order.work_type}</option>
                                </select>
                                <span class="oa-display-value">${order.work_type || '-'}</span>
                            </div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Batch ID</div>
                            <div class="oa-detail-value">${order.batch_id || '-'}</div>
                        </div>
                        <div class="oa-detail-item editable">
                            <div class="oa-detail-label">Order Type</div>
                            <div class="oa-detail-value">
                                <select class="oa-edit-ordertype" style="display: none;">
                                    <option value="${order.order_details}">${order.order_details}</option>
                                </select>
                                <span class="oa-display-value">${order.order_details || '-'}</span>
                            </div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Owner Name</div>
                            <div class="oa-detail-value">${order.owner_name || '-'}</div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Property Address</div>
                            <div class="oa-detail-value">${order.property_address || '-'}</div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">State</div>
                            <div class="oa-detail-value">${order.state || '-'}</div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">County</div>
                            <div class="oa-detail-value">${order.county || '-'}</div>
                        </div>
                        <div class="oa-detail-item editable">
                            <div class="oa-detail-label">Assigned To</div>
                            <div class="oa-detail-value">
                                <select class="oa-edit-employee" style="display: none;">
                                    <option value="${order.employee_id}">${order.employeeName}</option>
                                </select>
                                <span class="oa-display-value">${order.employeeName || '-'}</span>
                            </div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Received Date</div>
                            <div class="oa-detail-value">${receivedDate}</div>
                        </div>
                        <div class="oa-detail-item editable eta-field" ${order.search_type !== 'Ground' ? 'style="display: block;"' : ''}>
                            <div class="oa-detail-label">ETA</div>
                            <div class="oa-detail-value">
                                <input type="datetime-local" class="oa-edit-eta" style="display: none;" value="${order.eta || ''}">
                                <span class="oa-display-value">${eta}</span>
                            </div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Dispatch Date</div>
                            <div class="oa-detail-value">${slaDate}</div>
                        </div>
                        <div class="oa-detail-item editable">
                            <div class="oa-detail-label">Fee Type</div>
                            <div class="oa-detail-value">
                                <select class="oa-edit-searchtype" style="display: none;">
                                    <option value="Free" ${order.search_type === 'Free' ? 'selected' : ''}>Free</option>
                                    <option value="Paid" ${order.search_type === 'Paid' ? 'selected' : ''}>Paid</option>
                                    <option value="Ground" ${order.search_type === 'Ground' ? 'selected' : ''}>Ground Abstractor</option>
                                </select>
                                <span class="oa-display-value">${order.search_type || '-'}</span>
                            </div>
                        </div>
                        <div class="oa-detail-item editable">
                            <div class="oa-detail-label">Fees</div>
                            <div class="oa-detail-value">
                                <div class="oa-edit-controls" style="display: none;">
                                    <input type="number" class="oa-edit-fees" value="${order.fees || '0'}" readonly>
                                    <select class="oa-edit-vendor-rates" style="display: none;">
                                        <option value="">Select Vendor</option>
                                    </select>
                                </div>
                                <span class="oa-display-value">$${order.fees || '0'}</span>
                            </div>
                        </div>
                        <div class="oa-detail-item editable">
                            <div class="oa-detail-label">Remarks</div>
                            <div class="oa-detail-value">
                                <textarea class="oa-edit-remarks" style="display: none;">${order.remarks || ''}</textarea>
                                <span class="oa-display-value">${order.remarks || '-'}</span>
                            </div>
                        </div>
                        <div class="oa-detail-item">
                            <div class="oa-detail-label">Status</div>
                            <div class="oa-detail-value">
                                ${(() => {
                                    let status = order.status || 'Pending';
                                    let cssClass = status.toLowerCase().replace(/ /g, '.');
                                    
                                    // Special handling for "Send for" status
                                    if (status.startsWith('Send for')) {
                                        cssClass = 'send';
                                    }
                                    
                                    return `<span class="oa-status-badge ${cssClass}">
                                        ${status}
                                    </span>`;
                                })()}
                            </div>
                        </div>
                    </div>
                    
                    <!-- Add Documents Section -->
                    <div class="oa-documents-section">
                        <div class="oa-documents-header">
                            <h4><i class="fas fa-file-upload"></i> Attachments </h4>
                        </div>
                        <div class="oa-documents-grid">
                            ${order.batch_documents && order.batch_documents.length > 0 ? 
                                order.batch_documents.map(doc => `
                                    <div class="oa-document-item">
                                        <div class="oa-document-icon">
                                            <i class="fas ${getDocumentIcon(doc.name)}"></i>
                                        </div>
                                        <div class="oa-document-info">
                                            <span class="oa-document-name" title="${doc.name}">${doc.name}</span>
                                            <a href="/api/download-document/${order.task_id}/${encodeURIComponent(doc.name)}" 
                                               class="oa-document-download" 
                                               target="_blank">
                                                <i class="fas fa-download"></i> Download
                                            </a>
                                        </div>
                                    </div>
                                `).join('')
                                : '<div class="oa-no-documents">No documents attached</div>'
                            }
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Add helper function to determine document icon
        function getDocumentIcon(filename) {
            if (!filename) return 'fa-file';
            
            const ext = filename.split('.').pop().toLowerCase();
            switch(ext) {
                case 'pdf':
                    return 'fa-file-pdf';
                case 'doc':
                case 'docx':
                    return 'fa-file-word';
                case 'xls':
                case 'xlsx':
                    return 'fa-file-excel';
                case 'jpg':
                case 'jpeg':
                case 'png':
                case 'gif':
                    return 'fa-file-image';
                case 'zip':
                case 'rar':
                    return 'fa-file-archive';
                case 'txt':
                    return 'fa-file-alt';
                default:
                    return 'fa-file';
            }
        }

        // First append the popup to the document
        document.body.appendChild(popup);

        // Add edit button
        const actionsContainer = popup.querySelector('.oa-details-actions');
        const editBtn = document.createElement('button');
        editBtn.className = 'oa-edit-btn';
        editBtn.innerHTML = '<i class="fas fa-edit"></i> Edit';
        actionsContainer.insertBefore(editBtn, actionsContainer.firstChild);

        // Get save button
        const saveBtn = popup.querySelector('.oa-save-btn');

        // Load employees for dropdown
        fetch('/api/v1/auth/employees/')
            .then(response => response.json())
            .then(employees => {
                const employeeSelect = popup.querySelector('.oa-edit-employee');
                employeeSelect.innerHTML = employees.map(emp => 
                    `<option value="${emp.employee_id}" ${emp.employee_id === order.employee_id ? 'selected' : ''}>
                        ${emp.name}
                    </option>`
                ).join('');
            });

        // Load order types for dropdown
        fetch('/api/v1/allocations/rates/order_types/')
            .then(response => response.json())
            .then(orderTypes => {
                const orderTypeSelect = popup.querySelector('.oa-edit-ordertype');
                orderTypeSelect.innerHTML = orderTypes.map(type => 
                    `<option value="${type}" ${type === order.order_details ? 'selected' : ''}>
                        ${type}
                    </option>`
                ).join('');
            });

        // Load work types for dropdown
        fetch('/api/v1/masters/projects/')
            .then(response => response.json())
            .then(data => {
                if (data.work_types && Array.isArray(data.work_types)) {
                    const workTypeSelect = popup.querySelector('.oa-edit-worktype');
                    workTypeSelect.innerHTML = data.work_types.map(type => 
                        `<option value="${type}" ${type === order.work_type ? 'selected' : ''}>
                            ${type}
                        </option>`
                    ).join('');
                }
            })
            .catch(error => {
                console.error('Error loading work types:', error);
            });

        // Handle search type change
        const searchTypeSelect = popup.querySelector('.oa-edit-searchtype');
        const feesInput = popup.querySelector('.oa-edit-fees');
        const vendorRatesSelect = popup.querySelector('.oa-edit-vendor-rates');
        const etaInput = popup.querySelector('.oa-edit-eta');
        const etaField = popup.querySelector('.eta-field');

        searchTypeSelect.addEventListener('change', function() {
            const selectedType = this.value;
            
            // Hide both fees input and vendor rates by default
            feesInput.style.display = 'none';
            vendorRatesSelect.style.display = 'none';
            
            switch(selectedType) {
                case 'Free':
                    feesInput.value = '0';
                    feesInput.readOnly = true;
                    feesInput.style.display = 'block';
                    vendorRatesSelect.style.display = 'none';
                    break;
                    
                case 'Paid':
                    feesInput.value = order.fees || '0';
                    feesInput.readOnly = false;
                    feesInput.style.display = 'block';
                    vendorRatesSelect.style.display = 'none';
                    break;
                    
                case 'Ground':
                    etaField.style.display = 'block';
                    vendorRatesSelect.style.display = 'block';
                    // Fetch vendor rates
                    const orderType = order.order_details;
                    const state = order.state;
                    const county = order.county;
                    
                    if (orderType && state && county) {
                        fetch(`/api/v1/allocations/rates/?order_type=${encodeURIComponent(orderType)}&state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}`)
                            .then(response => response.json())
                            .then(vendors => {
                                vendorRatesSelect.innerHTML = `
                                    <option value="">Select Vendor</option>
                                    ${vendors.map(vendor => `
                                        <option value="${vendor.rate === -1 ? '0' : vendor.rate}" ${order.fees == vendor.rate ? 'selected' : ''}>
                                            ${vendor.name} - ${vendor.rate === -1 ? 'QUOTE ONLY' : `$${vendor.rate}`}
                                        </option>
                                    `).join('')}
                                `;
                                vendorRatesSelect.style.display = 'block';
                                if (order.fees) {
                                    feesInput.value = order.fees === -1 ? '0' : order.fees;
                                }
                            })
                            .catch(error => console.error('Error loading vendor rates:', error));
                    }
                    break;
            }
        });

        // Handle vendor rate selection
        vendorRatesSelect.addEventListener('change', function() {
            const selectedRate = parseFloat(this.value);
            if (selectedRate === -1 || this.options[this.selectedIndex].text.includes('QUOTE ONLY')) {
                feesInput.value = '0';
            } else {
                feesInput.value = selectedRate;
            }
            feesInput.readOnly = true;
        });

        // Handle edit button click
        editBtn.addEventListener('click', function() {
            popup.querySelectorAll('.oa-edit-employee, .oa-edit-worktype, .oa-edit-ordertype, .oa-edit-searchtype, .oa-edit-remarks, .oa-edit-eta').forEach(el => {
                el.style.display = 'block';
            });
            // Show the fees edit controls container
            popup.querySelector('.oa-edit-controls').style.display = 'block';
            
            popup.querySelectorAll('.oa-display-value').forEach(el => {
                el.style.display = 'none';
            });
            editBtn.style.display = 'none';
            saveBtn.style.display = 'inline-block';

            // Show document controls in edit mode
            const addDocBtn = popup.querySelector('.oa-add-document');
            addDocBtn.style.display = 'inline-flex';
            popup.querySelectorAll('.oa-document-remove').forEach(btn => {
                btn.style.display = 'inline-block';
            });

            // Trigger the search type change to show/hide appropriate fees controls
            searchTypeSelect.dispatchEvent(new Event('change'));

            isEditMode = true;
            renderDocumentsGrid();
        });

        // Handle save button click
        saveBtn.addEventListener('click', function() {
            const updatedData = {
                task_id: order.task_id,
                work_type: popup.querySelector('.oa-edit-worktype').value,
                order_details: popup.querySelector('.oa-edit-ordertype').value,
                employee_id: popup.querySelector('.oa-edit-employee').value,
                search_type: popup.querySelector('.oa-edit-searchtype').value,
                remarks: popup.querySelector('.oa-edit-remarks').value || '',
                fees: searchTypeSelect.value === 'Ground' ? vendorRatesSelect.value : feesInput.value
            };
            // Handle ETA
            const etaInput = popup.querySelector('.oa-edit-eta');
            if (etaInput && etaInput.value) {
                const originalEtaValue = order.eta || '';
                const newEtaValue = etaInput.value;
                if (originalEtaValue !== newEtaValue) {
                    updatedData.eta = newEtaValue;
                }
            }
            // Gather removed files (old attachments marked _removed)
            const removedFiles = (order.batch_documents || [])
                .filter(doc => doc._removed)
                .map(doc => doc.name);
            // Prepare FormData
            const formData = new FormData();
            formData.append('data', JSON.stringify(updatedData));
            formData.append('removed_files', JSON.stringify(removedFiles));
            // Add new files
            newDocuments.forEach((doc, idx) => {
                if (doc.file) {
                    formData.append(`file_${idx}`, doc.file, doc.name);
                }
            });
            // Show loading state
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
            // Send update to server
            fetch(`/api/order-allocation/${encodeURIComponent(order.task_id)}/update`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(data => {
                        throw new Error(data.error || 'Failed to update order');
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Send chat notification to assigned employee for updated task
                    sendTaskAssignmentMessage(updatedData.employee_id, {
                        task_id: updatedData.task_id,
                        client_code: order.client_code,
                        project: order.project,
                        work_type: updatedData.work_type,
                        search_type: updatedData.search_type,
                        isUpdate: true // flag to indicate update
                    });

                    const successMessage = document.createElement('div');
                    successMessage.className = 'oa-success-message';
                    successMessage.innerHTML = '<i class="fas fa-check-circle"></i> Order updated successfully';
                    popup.querySelector('.oa-details-body').prepend(successMessage);
                    setTimeout(() => {
                        successMessage.remove();
                        fetchExistingOrders();
                        popup.remove();
                    }, 2000);
                } else {
                    throw new Error(data.message || 'Unknown error occurred');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                const errorMessage = document.createElement('div');
                errorMessage.className = 'oa-error-message';
                errorMessage.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${error.message}`;
                popup.querySelector('.oa-details-body').prepend(errorMessage);
                setTimeout(() => {
                    errorMessage.remove();
                }, 3000);
            })
            .finally(() => {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fas fa-save"></i> Save';
            });
        });

        // Trigger initial search type handling
        searchTypeSelect.dispatchEvent(new Event('change'));

        // Force a reflow to ensure the transition works
        popup.offsetHeight;

        // Add the show class to trigger the animation
        requestAnimationFrame(() => {
            popup.classList.add('show');
        });

        // Handle close button click
        const closeBtn = popup.querySelector('.oa-details-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                closePopup(popup);
            });
        }

        // Handle click outside
        function handleOutsideClick(e) {
            if (!popup.querySelector('.oa-details-container').contains(e.target) && !e.target.closest('.order-row')) {
                // Do nothing
            }
        }

        // Add click outside event listener
        document.addEventListener('click', handleOutsideClick);

        // Handle escape key
        function handleEscKey(e) {
            if (e.key === 'Escape') {
                closePopup(popup);
            }
        }

        // Add escape key event listener
        document.addEventListener('keydown', handleEscKey);

        // Function to handle closing the popup
        function closePopup(popup) {
            popup.classList.remove('show');
            
            // Remove the popup after the animation
            setTimeout(() => {
                popup.remove();
                document.removeEventListener('click', handleOutsideClick);
                document.removeEventListener('keydown', handleEscKey);
            }, 300); // Match this with your CSS transition duration
        }

        // Declare newDocuments at the top so it's available for all functions
        let newDocuments = [];
        const documentsSection = popup.querySelector('.oa-documents-section');
        const documentsGrid = popup.querySelector('.oa-documents-grid');
        const addDocBtn = document.createElement('button');
        addDocBtn.className = 'oa-add-document';
        addDocBtn.innerHTML = '<i class="fas fa-plus"></i> Add Document';
        addDocBtn.type = 'button';
        addDocBtn.style.display = 'none'; // Hide by default in readonly mode
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.pdf,.doc,.docx,.xls,.xlsx,.txt,image/*';
        fileInput.multiple = true;
        fileInput.style.display = 'none';
        // Place Add Document button and file input in header, right-aligned
        const documentsHeader = documentsSection.querySelector('.oa-documents-header');
        documentsHeader.style.display = 'flex';
        documentsHeader.style.justifyContent = 'space-between';
        documentsHeader.style.alignItems = 'center';
        documentsHeader.appendChild(addDocBtn);
        documentsHeader.appendChild(fileInput);
        addDocBtn.addEventListener('click', () => fileInput.click());

        // Helper to render all documents (existing + new)
        let isEditMode = false;
        function showDocumentEditControls() {
            addDocBtn.style.display = 'inline-flex';
            documentsGrid.querySelectorAll('.oa-document-remove').forEach(btn => {
                btn.style.display = 'inline-block';
            });
        }
        
        function renderDocumentsGrid() {
            documentsGrid.innerHTML = '';
            // Existing documents
            (order.batch_documents || []).forEach((doc, idx) => {
                if (doc._removed) return; // skip removed
                const item = document.createElement('div');
                item.className = 'oa-document-item';
                item.innerHTML = `
                    <div class="oa-document-icon">
                        <i class="fas ${getDocumentIcon(doc.name)}"></i>
                    </div>
                    <div class="oa-document-info" style="position:relative;">
                        <span class="oa-document-name" title="${doc.name}">${doc.name}</span>
                        <div class="oa-document-actions">
                            <a href="/api/download-document/${order.task_id}/${encodeURIComponent(doc.name)}" 
                               class="oa-document-download" 
                               target="_blank">
                                <i class="fas fa-download"></i> Download
                            </a>
                            <button class="oa-document-remove" title="Remove" style="display: none;">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                `;
                // Attach remove handler for existing document
                const removeBtn = item.querySelector('.oa-document-remove');
                removeBtn.addEventListener('click', () => {
                    doc._removed = true;
                    renderDocumentsGrid();
                });
                documentsGrid.appendChild(item);
            });
            // New documents
            newDocuments.forEach((doc, idx) => {
                const item = document.createElement('div');
                item.className = 'oa-document-item new';
                item.innerHTML = `
                    <div class="oa-document-icon">
                        <i class="fas ${getDocumentIcon(doc.name)}"></i>
                    </div>
                    <div class="oa-document-info">
                        <span class="oa-document-name" title="${doc.name}">${doc.name}</span>
                        <div class="oa-document-actions">
                            <button class="oa-document-remove" title="Remove" style="display: none;">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                `;
                // Attach remove handler for new document
                const removeBtn = item.querySelector('.oa-document-remove');
                removeBtn.addEventListener('click', () => {
                    newDocuments.splice(idx, 1);
                    renderDocumentsGrid();
                });
                documentsGrid.appendChild(item);
            });
            if (!order.batch_documents?.some(doc => !doc._removed) && !newDocuments.length) {
                documentsGrid.innerHTML = '<div class="oa-no-documents">No documents attached</div>';
            }
            // Always show remove buttons in edit mode after render
            if (isEditMode) showDocumentEditControls();
        }

        // Initial render
        renderDocumentsGrid();

        // Handle file input change
        fileInput.addEventListener('change', function(e) {
            const files = Array.from(e.target.files);
            const allowedTypes = [
                'image/jpeg', 'image/png', 'image/jpg', 'image/gif',
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'text/plain'
            ];
            const validFiles = files.filter(file => {
                const fileType = file.type.toLowerCase();
                const fileExtension = file.name.split('.').pop().toLowerCase();
                return allowedTypes.includes(fileType) || 
                    ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'].includes(fileExtension);
            });
            if (validFiles.length !== files.length) {
                alert('Only images, PDF, Word, Excel, and text files are allowed');
                return;
            }
            validFiles.forEach(file => {
                if (file.size > 35 * 1024 * 1024) { // 35MB limit
                    alert(`File ${file.name} exceeds 35MB limit`);
                    return;
                }
                const reader = new FileReader();
                reader.onload = function(e) {
                    newDocuments.push({
                        data: e.target.result,
                        name: file.name,
                        type: file.type,
                        file: file
                    });
                    renderDocumentsGrid();
                };
                reader.readAsDataURL(file);
            });
        });
    }

    // Set up auto-refresh for orders table every 5 minutes
    let autoRefreshInterval;
    let isRefreshing = false;

    function startAutoRefresh() {
        // Clear any existing interval first
        if (autoRefreshInterval) {
            clearInterval(autoRefreshInterval);
        }
        // Set new interval to refresh every 5 minutes (300000 milliseconds)
        autoRefreshInterval = setInterval(fetchExistingOrders, 300000);
    }

    function stopAutoRefresh() {
        if (autoRefreshInterval) {
            clearInterval(autoRefreshInterval);
            autoRefreshInterval = null;
        }
    }

    // Enhanced fetchExistingOrders with refresh button handling
    async function fetchExistingOrders(isManualRefresh = false) {
        if (isRefreshing) return; // Prevent multiple simultaneous refreshes
        
        isRefreshing = true;
        const refreshBtn = document.getElementById('refreshAllocationTable');
        
        if (isManualRefresh && refreshBtn) {
            refreshBtn.classList.add('spinning');
        }

        try {
            const response = await fetch('/api/v1/allocations/');
            const data = await response.json();
            
            if (response.ok) {
                const orders = data.data ? (data.data.results || data.data) : (data.results || data || []);
                displayAllocatedOrders(orders);
                if (orders && orders.length > 0) {
                    const maxId = Math.max(...orders.map(order => {
                        const taskId = order.taskId || order.task_id || order.allocation_id;
                        if (!taskId) return 0;
                        const idMatch = String(taskId).match(/\d+/);
                        return idMatch ? parseInt(idMatch[0]) : 0;
                    }));
                    currentOrderId = maxId + 1;
                }
            } else {
                throw new Error(data.detail || data.error || 'Failed to fetch orders');
            }
        } catch (error) {
            console.error('Error:', error);
            console.error('Error fetching orders: ' + error.message);
            displayAllocatedOrders([]); // Show empty state
        } finally {
            isRefreshing = false;
            if (refreshBtn) {
                refreshBtn.classList.remove('spinning');
            }
        }
    }

    // Make fetchExistingOrders available globally
    window.fetchExistingOrders = fetchExistingOrders;

    // Start auto-refresh when the page loads
    startAutoRefresh();

    // Add manual refresh button handler
    const refreshBtn = document.getElementById('refreshAllocationTable');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            fetchExistingOrders(true); // Pass true to indicate manual refresh
        });
    }

    // Stop auto-refresh when the tab is hidden to save resources
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            stopAutoRefresh();
        } else {
            // When tab becomes visible again, fetch immediately and restart auto-refresh
            fetchExistingOrders();
            startAutoRefresh();
        }
    });

    // Clean up interval when the page is unloaded
    window.addEventListener('beforeunload', stopAutoRefresh);

    // Global search and page size functionality for allocation table
    function setupAllocationSearch() {
        const searchInput = document.getElementById('allocationSearchInput');
        const clearSearchBtn = document.getElementById('clearAllocationSearch');
        const pageSizeSelect = document.getElementById('allocationPageSize');

        function performSearch() {
            allocationState.searchTerm = searchInput.value;
            allocationState.currentPage = 1;
            filterAllocatedOrders();
            renderAllocatedOrdersPage();

            // Show/hide clear button based on search input
            if (searchInput.value.trim() !== '') {
                clearSearchBtn.style.display = 'block';
            } else {
                clearSearchBtn.style.display = 'none';
            }
        }

        function clearSearch() {
            searchInput.value = '';
            allocationState.searchTerm = '';
            allocationState.currentPage = 1;
            filterAllocatedOrders();
            renderAllocatedOrdersPage();
            clearSearchBtn.style.display = 'none';
            searchInput.focus();
        }

        // Event listeners
        if (searchInput) {
            searchInput.addEventListener('input', performSearch);
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    clearSearch();
                }
            });
        }
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', clearSearch);
            clearSearchBtn.style.display = 'none';
        }
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', function() {
                allocationState.pageSize = this.value;
                allocationState.currentPage = 1;
                renderAllocatedOrdersPage();
            });
        }
    }

    setupAllocationSearch();
}