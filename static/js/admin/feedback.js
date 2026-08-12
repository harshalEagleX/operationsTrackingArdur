// Wait for document ready
$(document).ready(function() {
    // Initialize select2 dropdowns
    initializeSelect2();
    loadInitialData();

    function initializeSelect2() {
        $('#project').select2({
            placeholder: 'Select a project',
            allowClear: true,
            width: '100%'
        });

        $('#empIdName').select2({
            placeholder: 'Select employee(s)',
            allowClear: true,
            multiple: true,
            width: '100%',
            selectionCssClass: 'select2-selection--multiple',
            dropdownCssClass: 'select2-dropdown',
            minimumResultsForSearch: 0,
            closeOnSelect: false,
            templateResult: formatEmployee,
            templateSelection: formatEmployeeSelection
        });

        $('#clientCode').select2({
            placeholder: 'Select client code',
            allowClear: true,
            width: '100%'
        });

        $('#workType').select2({
            placeholder: 'Select work type',
            allowClear: true,
            width: '100%'
        });
    }

    function loadInitialData() {
        // Load projects on page load with MasterDataCache
        MasterDataCache.getOrFetch('master_projects_v2', '/api/v1/masters/emp_get_projects/')
            .then(data => {
                const projects = Array.isArray(data) ? data : (data.projects || data.results || []);
                const projectDropdown = document.getElementById('project');
                if (projectDropdown) {
                    projectDropdown.innerHTML = '<option value="">Select a project</option>';
                    projects.forEach(project => {
                        const option = document.createElement('option');
                        option.value = project.project_name;
                        option.textContent = project.project_name;
                        projectDropdown.appendChild(option);
                    });
                    $('#project').trigger('change');
                }
            })
            .catch(error => console.error('Error loading projects:', error));
    }

    // Project change handler
    $('#project').on('change', function() {
        const selectedProject = $(this).find('option:selected').text();
        updateFields(selectedProject);
        updateTypeDropdown(selectedProject);
        resetDependentDropdowns('empIdName');
        
        if (selectedProject) {
            fetch(`/api/v1/auth/employees/?project=${encodeURIComponent(selectedProject)}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    const empDropdown = document.getElementById('empIdName');
                    empDropdown.innerHTML = '<option value="">Select employee(s)</option>';
                    empDropdown.innerHTML += '<option value="all">Select All</option>';
                    
                    if (Array.isArray(data)) {
                        data.forEach(emp => {
                            const empId = emp.employee_id || emp.emp_id;
                            const option = document.createElement('option');
                            option.value = empId;
                            option.textContent = `${emp.name} (${empId})`;
                            empDropdown.appendChild(option);
                        });
                    } else if (data.data && Array.isArray(data.data)) {
                        data.data.forEach(emp => {
                            const empId = emp.employee_id || emp.emp_id;
                            const option = document.createElement('option');
                            option.value = empId;
                            option.textContent = `${emp.name} (${empId})`;
                            empDropdown.appendChild(option);
                        });
                    } else {
                        console.error('Unexpected data format:', data);
                    }
                    
                    $('#empIdName').trigger('change');
                })
                .catch(error => {
                    console.error('Error fetching employees:', error);
                    const empDropdown = document.getElementById('empIdName');
                    empDropdown.innerHTML = '<option value="">Error loading employees</option>';
                });
        }
    });

    // Helper function to reset dependent dropdowns
    function resetDependentDropdowns(startFrom) {
        const dropdowns = ['empIdName', 'clientCode', 'workType'];
        const startIndex = dropdowns.indexOf(startFrom);
        if (startIndex !== -1) {
            dropdowns.slice(startIndex).forEach(id => {
                const dropdown = document.getElementById(id);
                dropdown.innerHTML = '<option value="">Select an option</option>';
                $(dropdown).trigger('change'); // Trigger select2 update
            });
        }
    }

    // Employee change handler
    $('#empIdName').on('change', function() {
        const selectedValues = $(this).val();
        const selectedProject = document.getElementById('project').value;
        resetDependentDropdowns('clientCode');
        
        // Clear employee details if no selection
        if (!selectedValues || selectedValues.length === 0) {
            document.getElementById('empId').value = '';
            document.getElementById('empName').value = '';
            return;
        }
        
        if (selectedValues && selectedValues.length > 0) {
            // If "Select All" is chosen, select all other options
            if (selectedValues.includes('all')) {
                const allOptions = $(this).find('option').not(':first').not('[value="all"]');
                allOptions.prop('selected', true);
                // Update select2 without triggering change event
                $(this).trigger('select2:select', { data: allOptions });
                
                // Get client codes for all employees
                const employeeIds = allOptions.map(function() {
                    return this.value;
                }).get();
                fetchAllEmployeeClientCodes(employeeIds, selectedProject);
                return;
            }

            // Get the first selected employee for initial form population
            const firstEmpId = selectedValues[0];
            // Only make the API call if we have both an employee ID and project name
            if (firstEmpId && selectedProject) {
                fetch(`/get_employee_project_details/${encodeURIComponent(firstEmpId)}/${encodeURIComponent(selectedProject)}`)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error('Network response was not ok');
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (data.error) {
                            console.error('Error:', data.error);
                            return;
                        }
                        
                        // Update client codes dropdown
                        const clientCodeDropdown = document.getElementById('clientCode');
                        clientCodeDropdown.innerHTML = '<option value="">Select a client code</option>';
                        data.client_codes.forEach(code => {
                            const option = document.createElement('option');
                            option.value = code;
                            option.textContent = code;
                            clientCodeDropdown.appendChild(option);
                        });
                        $(clientCodeDropdown).trigger('change');

                        // Set employee details for the first selected employee
                        document.getElementById('empId').value = firstEmpId;
                        document.getElementById('empName').value = data.emp_name;
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        // Clear the dropdowns on error
                        document.getElementById('clientCode').innerHTML = '<option value="">Select a client code</option>';
                        document.getElementById('workType').innerHTML = '<option value="">Select a work type</option>';
                    });
            }
        }
    });

    // Function to fetch client codes for all selected employees
    function fetchAllEmployeeClientCodes(employeeIds, projectName) {
        // Create an array of promises for each employee
        const promises = employeeIds.map(empId => 
            fetch(`/get_employee_project_details/${encodeURIComponent(empId)}/${encodeURIComponent(projectName)}`)
                .then(response => response.json())
                .catch(error => {
                    console.error(`Error fetching details for employee ${empId}:`, error);
                    return { client_codes: [] };
                })
        );

        // Wait for all promises to resolve
        Promise.all(promises)
            .then(results => {
                // Get unique client codes from all employees
                const allClientCodes = new Set();
                results.forEach(result => {
                    if (result.client_codes) {
                        result.client_codes.forEach(code => allClientCodes.add(code));
                    }
                });

                // Update client codes dropdown with unique codes
                const clientCodeDropdown = document.getElementById('clientCode');
                clientCodeDropdown.innerHTML = '<option value="">Select a client code</option>';
                Array.from(allClientCodes).forEach(code => {
                    const option = document.createElement('option');
                    option.value = code;
                    option.textContent = code;
                    clientCodeDropdown.appendChild(option);
                });
                $(clientCodeDropdown).trigger('change');

                // Set employee details for the first employee
                if (results[0] && results[0].emp_name) {
                    document.getElementById('empId').value = employeeIds[0];
                    document.getElementById('empName').value = results[0].emp_name;
                }
            })
            .catch(error => console.error('Error fetching all employee details:', error));
    }

    // Client code change handler
    $('#clientCode').on('change', function() {
        const selectedClientCode = this.value;
        const selectedProject = document.getElementById('project').value;
        const selectedEmployees = $('#empIdName').val();
        resetDependentDropdowns('workType');

        if (selectedClientCode && selectedProject && selectedEmployees && selectedEmployees.length > 0) {
            // Remove 'all' from selectedEmployees if present
            const employeeIds = selectedEmployees.filter(id => id !== 'all');
            
            // Create promises for each employee
            const promises = employeeIds.map(empId =>
                fetch(`/get_work_types/${encodeURIComponent(empId)}/${encodeURIComponent(selectedProject)}/${encodeURIComponent(selectedClientCode)}`)
                    .then(response => response.json())
                    .catch(error => {
                        console.error(`Error fetching work types for employee ${empId}:`, error);
                        return { work_types: [] };
                    })
            );

            // Wait for all promises to resolve
            Promise.all(promises)
                .then(results => {
                    // Get intersection of work types from all employees
                    let commonWorkTypes = null;
                    results.forEach(result => {
                        if (result.work_types) {
                            const workTypesSet = new Set(result.work_types);
                            if (commonWorkTypes === null) {
                                commonWorkTypes = workTypesSet;
                            } else {
                                commonWorkTypes = new Set(
                                    [...commonWorkTypes].filter(type => workTypesSet.has(type))
                                );
                            }
                        }
                    });

                    // Update work types dropdown with common work types
                    const workTypeDropdown = document.getElementById('workType');
                    workTypeDropdown.innerHTML = '<option value="">Select a work type</option>';
                    
                    if (commonWorkTypes && commonWorkTypes.size > 0) {
                        Array.from(commonWorkTypes).forEach(type => {
                            const option = document.createElement('option');
                            option.value = type;
                            option.textContent = type;
                            workTypeDropdown.appendChild(option);
                        });
                    }
                    
                    $(workTypeDropdown).trigger('change');
                })
                .catch(error => {
                    console.error('Error fetching work types:', error);
                    const workTypeDropdown = document.getElementById('workType');
                    workTypeDropdown.innerHTML = '<option value="">Error loading work types</option>';
                });
        }
    });

    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("closureScreenshot");
    const previewContainer = document.getElementById("previewContainer");
    let uploadedFiles = new Set(); // To track uploaded files

    // Initialize the file input and dropzone
    function initializeFileUpload() {
        // Only trigger file input click if the click was directly on the dropzone
        dropZone.addEventListener("click", (e) => {
            if (e.target === dropZone || e.target.tagName === 'P') {
                fileInput.click();
            }
        });
        
        dropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropZone.style.borderColor = "#1abc9c";
            dropZone.classList.add("loading");
        });

        dropZone.addEventListener("dragleave", () => {
            dropZone.style.borderColor = "#ccc";
            dropZone.classList.remove("loading");
        });

        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropZone.style.borderColor = "#ccc";
            dropZone.classList.remove("loading");
            handleFiles(e.dataTransfer.files);
        });

        fileInput.addEventListener("change", (e) => {
            handleFiles(e.target.files);
        });

        // Add paste event listener
        document.addEventListener('paste', (e) => {
            const activeElement = document.activeElement;
            const isTextInput = activeElement.tagName === 'INPUT' && activeElement.type === 'text';
            const isTextArea = activeElement.tagName === 'TEXTAREA';
            
            if (isTextInput || isTextArea) return;

            if (e.clipboardData.files.length > 0) {
                e.preventDefault();
                handleFiles(e.clipboardData.files);
            }
        });
    }

    function handleFiles(files) {
        // Clear existing files when new files are selected
        uploadedFiles.clear();
        previewContainer.innerHTML = '';
        
        Array.from(files).forEach(file => {
            if (!file.type.startsWith("image/")) {
                alert("Only image files are allowed!");
                return;
            }

            // Check if file is already uploaded
            if (uploadedFiles.has(file.name)) {
                alert(`File "${file.name}" has already been added!`);
                return;
            }

            uploadedFiles.add(file.name);
            
            const reader = new FileReader();
            reader.onload = (e) => {
                const wrapper = document.createElement("div");
                wrapper.className = "preview-image-wrapper";
                
                const img = document.createElement("img");
                img.src = e.target.result;
                img.className = 'preview-image';
                img.setAttribute('data-filename', file.name);
                
                const removeBtn = document.createElement("button");
                removeBtn.className = "remove-image";
                removeBtn.innerHTML = '<i class="fas fa-times"></i>';
                removeBtn.onclick = (e) => {
                    e.preventDefault();
                    removeFile(file.name, wrapper);
                };
                
                wrapper.appendChild(img);
                wrapper.appendChild(removeBtn);
                previewContainer.appendChild(wrapper);
            };
            reader.readAsDataURL(file);
        });

        // Update the file input with all new files at once
        updateFileInputFiles(Array.from(files));
    }

    function removeFile(fileName, wrapper) {
        // Remove from tracking Set
        uploadedFiles.delete(fileName);
        
        // Remove preview
        wrapper.remove();
        
        // Update the file input
        const newFileList = Array.from(fileInput.files).filter(file => file.name !== fileName);
        updateFileInputFiles(newFileList);
    }

    function updateFileInputFiles(files) {
        const dataTransfer = new DataTransfer();
        files.forEach(file => dataTransfer.items.add(file));
        fileInput.files = dataTransfer.files;
    }

    // Initialize file upload when document is ready
    initializeFileUpload();

    document.getElementById('feedbackForm').addEventListener('submit', async function (e) {
        e.preventDefault();
        
        const submitButton = this.querySelector('button[type="submit"]');
        const originalButtonText = submitButton.innerHTML;
        submitButton.disabled = true;
        submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
        
        try {
            const selectedEmployees = $('#empIdName').val();
            if (!selectedEmployees || selectedEmployees.length === 0) {
                alert("Please select at least one employee.");
                throw new Error("No employees selected");
            }
            
            // 1. Upload files first
            const fileIds = [];
            if (fileInput.files.length > 0) {
                const fileFormData = new FormData();
                Array.from(fileInput.files).forEach(file => {
                    fileFormData.append('file', file);
                });
                
                const fileRes = await fetch('/api/v1/files/', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '' },
                    body: fileFormData
                });
                const fileJson = await fileRes.json();
                if (!fileRes.ok) throw new Error(fileJson.error || 'Failed to upload files');
                
                // If the file endpoint returns an array of files in data.data or data
                const files = fileJson.data || fileJson;
                (Array.isArray(files) ? files : [files]).forEach(f => fileIds.push(f.id));
            }
            
            // 2. Prepare common payload
            const typeSelect = document.getElementById('type');
            const typeText = typeSelect.options[typeSelect.selectedIndex].text;
            let description = document.getElementById('feedbackText').value;
            const comments = document.getElementById('comments').value;
            if (comments) description += '\\n\\nComments: ' + comments;
            const fieldsVal = document.getElementById('fields').value;
            if (fieldsVal) description += '\\n\\nFields: ' + fieldsVal;
            const actionTaken = document.getElementById('actionTaken').value;
            if (actionTaken) description += '\\n\\nAction Taken: ' + actionTaken;
            
            let feedbackType = document.getElementById('type').value;
            // DRF FeedbackType choices: quality, audit, coaching, appreciation. Map if necessary.
            if (!['quality', 'audit', 'coaching', 'appreciation'].includes(feedbackType)) {
                feedbackType = 'quality'; // Default to quality for typo errors etc
            }
            
            const commonPayload = {
                feedback_type: feedbackType,
                severity: document.getElementById('severity').value,
                project: document.getElementById('project').value,
                order_batch_id: document.getElementById('orderBatchId').value,
                work_type: document.getElementById('workType').value,
                subject: typeText,
                description: description,
                file_ids: fileIds
            };
            
            // 3. Submit for each employee
            const promises = selectedEmployees.map(empId => {
                if (empId === 'all') return Promise.resolve(); // Skip 'all' dummy value
                
                const payload = { ...commonPayload, emp_id: empId };
                return fetch('/api/v1/feedback/', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || ''
                    },
                    body: JSON.stringify(payload)
                }).then(res => res.json()).then(data => {
                    if (!data.ok && !data.id) throw new Error(data.error || JSON.stringify(data));
                });
            });
            
            await Promise.all(promises);
            
            alert('Feedback submitted successfully!');
            fileInput.value = '';
            previewContainer.innerHTML = '';
            uploadedFiles.clear();
            
        } catch (error) {
            console.error('Error:', error);
            alert('Error: ' + error.message);
        } finally {
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonText;
        }
    });

    // Add event listener for project change
    const projectSelect = document.getElementById('project');
    if (projectSelect) {
        projectSelect.addEventListener('change', handleProjectChange);
    }

    // Add this function after initializeSelect2()
    function setDefaultDates() {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('processedDate').value = today;
        document.getElementById('feedbackReceivedDate').value = today;
        document.getElementById('openDate').value = today;
    }

    // Add this function after setDefaultDates()
    function setFeedbackProvidedBy() {
        fetch('/get_current_user')
            .then(response => response.json())
            .then(data => {
                if (data.name) {
                    document.getElementById('feedbackProvidedBy').value = data.name;
                }
            })
            .catch(error => console.error('Error fetching current user:', error));
    }

    // Update the updateMandatoryFields function
    function updateMandatoryFields(isInternalAudit) {
        const mandatoryFields = ['orderBatchId', 'project', 'empIdName', 'clientCode', 'workType', 'feedbackText'];
        const feedbackProvidedByField = document.getElementById('feedbackProvidedBy');
        
        // Handle feedbackProvidedBy field
        if (feedbackProvidedByField) {
            if (isInternalAudit) {
                feedbackProvidedByField.setAttribute('readonly', 'readonly');
                setFeedbackProvidedBy(); // Set logged in user for internal audit
            } else {
                feedbackProvidedByField.removeAttribute('readonly');
                feedbackProvidedByField.value = ''; // Clear the value for external
            }
        }
        
        mandatoryFields.forEach(fieldId => {
            const element = document.getElementById(fieldId);
            if (element) {
                if (isInternalAudit) {
                    element.setAttribute('required', 'required');
                    // Add red asterisk to labels - safely handle missing form-group
                    const formGroup = element.closest('.form-group') || element.closest('.feedback-field') || element.parentElement;
                    if (formGroup) {
                        const label = formGroup.querySelector('label');
                        if (label && !label.querySelector('.required-asterisk')) {
                            const asterisk = document.createElement('span');
                            asterisk.className = 'required-asterisk';
                            asterisk.style.color = 'red';
                            asterisk.textContent = ' *';
                            label.appendChild(asterisk);
                        }
                    }
                } else {
                    element.removeAttribute('required');
                    // Remove red asterisk from labels - safely handle missing form-group
                    const formGroup = element.closest('.form-group') || element.closest('.feedback-field') || element.parentElement;
                    if (formGroup) {
                        const label = formGroup.querySelector('label');
                        if (label) {
                            const asterisk = label.querySelector('.required-asterisk');
                            if (asterisk) {
                                asterisk.remove();
                            }
                        }
                    }
                }
            }
        });
    }

    // Update the feedbackRecorded change handler
    $('#feedbackRecorded').on('change', function() {
        const isInternalAudit = this.value === 'internalAudit';
        
        if (isInternalAudit) {
            setDefaultDates();
            updateMandatoryFields(true);
        } else {
            updateMandatoryFields(false);
        }
    });

    // Update the employee formatting functions
    function formatEmployee(employee) {
        if (!employee.id || employee.id === 'all') return employee.text;
        return $('<div>').text(employee.text).addClass('employee-option');
    }

    function formatEmployeeSelection(employee) {
        if (!employee.id || employee.id === 'all') return employee.text;
        return $('<div>').text(employee.text).addClass('employee-selection');
    }


    // Add event listener for type dropdown change
    $('#type').on('change', function() {
        const selectedType = $(this).find('option:selected').text();
        const feedbackText = document.getElementById('feedbackText');
        if (feedbackText) {
            feedbackText.value = selectedType;
        }
    });
});

    // Keep the toggleFeedbackForm function outside
    function toggleFeedbackForm(event) {
        event.preventDefault();
        const feedbackForm = document.getElementById('feedbackformContainer');
        feedbackForm.style.display = feedbackForm.style.display === 'none' || feedbackForm.style.display === '' ? 'block' : 'none';
    }

    // Define the ScaleInvoice fields at the top of the file
    const scaleInvoiceFields = [
        'PO#',
        'Vendor name',
        'Company location',
        'BOL#',
        'Reference#',
        'Contract#',
        'Account#',
        'Invoice#',
        'Invoice Date',
        'Freight',
        'Tax',
        'Gross Total'
    ];

    // Function to check if project is ScaleInvoice
    function isScaleInvoiceProject(projectName) {
        return projectName && projectName.toLowerCase().includes('scaleinvoice');
    }

    // Function to check if project is TitleIndexing
    function isTitleIndexingProject(projectName) {
        return projectName && projectName.toLowerCase().includes('titleindexing');
    }

    // Function to update type dropdown based on project
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

    // Function to update fields based on project
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

    // Define handleProjectChange function
    function handleProjectChange() {
        const projectSelect = document.getElementById('project');
        const selectedProject = projectSelect ? projectSelect.options[projectSelect.selectedIndex]?.text || '' : '';
        updateFields(selectedProject);
        updateTypeDropdown(selectedProject);
    }

    // Modify the DOMContentLoaded event listener
    document.addEventListener('DOMContentLoaded', function() {
        // Create fields container
        if (!document.getElementById('fieldsContainer')) {
            const fieldsGroup = document.createElement('div');
            fieldsGroup.id = 'fieldsContainer';
            fieldsGroup.className = 'form-group';
            
            // Insert after workType
            const workTypeGroup = document.querySelector('#workType').closest('.form-group');
            if (workTypeGroup && workTypeGroup.parentNode) {
                workTypeGroup.parentNode.insertBefore(fieldsGroup, workTypeGroup.nextSibling);
            }
        }

        // Handle initial project selection
        const projectSelect = document.getElementById('project');
        if (projectSelect) {
            projectSelect.addEventListener('change', handleProjectChange);
            // Initial setup
            handleProjectChange();
        }
    });

    // Add these styles to your CSS
    const styles = `
        .fields-dropdown {
            width: 100%;
            min-height: 38px;
            padding: 6px 12px;
            border: 1px solid #ced4da;
            border-radius: 4px;
        }

        .select2-container {
            width: 100% !important;
        }

        .select2-container--default .select2-selection--multiple {
            border: 1px solid #ced4da;
            min-height: 38px;
            padding: 5px;
        }

        .select2-container--default .select2-selection--multiple .select2-selection__choice {
            background-color: #e9ecef;
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 2px 8px;
            margin: 2px;
        }
    `;
