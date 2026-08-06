document.addEventListener("DOMContentLoaded", () => {
    // Modal handling
    const clientCodeModal = document.getElementById("clientcodeModal");
    const addClientCodeModal = document.getElementById("addClientCodeModal");
    const confirmDeleteClientCodeModal = document.getElementById("confirmDeleteClientCodeModal");
    const closeButtons = document.querySelectorAll(".close-btn");

    // Buttons
    const addClientCodeButton = document.getElementById("addClientCodeButton");
    const confirmDeleteClientCodeBtn = document.getElementById("confirmDeleteClientCodeBtn");
    const cancelDeleteClientCodeBtn = document.getElementById("cancelDeleteClientCodeBtn");

    // Forms
    const editClientCodeForm = document.getElementById("editClientCodeForm");
    const addClientCodeForm = document.getElementById("addClientCodeForm");

    // Table
    const clientCodesTableBody = document.querySelector("#clientcodes-table tbody");

    // Data
    let currentClientCodeIdToDelete = null;

    // Expose to global to support inline handlers and cross-file calls
    window.clientCodes = window.clientCodes || [];
    window.filteredClientCodes = window.filteredClientCodes || [];
    let currentPage = 1;
    const rowsPerPage = 15;

    const prevButton = document.getElementById("ccprevPage");
    const nextButton = document.getElementById("ccnextPage");
    const pageNumberDisplay = document.getElementById("ccpageNumber"); // Page number display

    const notify = (message, type = 'info') => {
        const prefix = type === 'error' ? 'Error: ' : type === 'success' ? 'Success: ' : '';
        alert(`${prefix}${message}`);
    };

    function fetchClientCodes() {
        fetch("/api/v1/masters/clientcodes/", { credentials: 'same-origin' })
            .then(response => response.json())
            .then(resp => {
                const data = Array.isArray(resp) ? resp : (resp.results || resp.data || []);
                window.clientCodes = data;
                window.filteredClientCodes = data; // initialize filtered set
                currentPage = 1; // Reset to first page
                displayClientCodesPage(currentPage);
            })
            .catch(() => notify('Failed to load Client Codes.', 'error'));
    }

    function displayClientCodesPage(page) {
        clientCodesTableBody.innerHTML = ""; // Clear existing rows
        const startIndex = (page - 1) * rowsPerPage;
        const endIndex = startIndex + rowsPerPage;
        const pageData = window.filteredClientCodes.slice(startIndex, endIndex);

        pageData.forEach((clientCode, index) => {
            const workTypes = clientCode.worktypes ? clientCode.worktypes.split("|") : [];
            const workTypeCount = workTypes.length;
            // Preserve original serial number based on full dataset order
            const originalIndex = Array.isArray(window.clientCodes)
                ? window.clientCodes.findIndex(cc => cc.cc_id === clientCode.cc_id) + 1
                : (startIndex + index + 1);

            const row = document.createElement("tr");
            row.innerHTML = `
                <td>${originalIndex}</td>
                <td>${clientCode.cc_id}</td>
                <td>${clientCode.client_code}</td>
                <td>
                    <a href="javascript:void(0);" 
                    title="View Work Types" 
                    class="worktype-count" 
                    data-cc-id="${clientCode.cc_id}" 
                    data-client-code="${clientCode.client_code}" 
                    data-worktypes="${clientCode.worktypes}">
                        <i class="fas fa-tasks"></i>${workTypeCount}
                    </a>
                </td>
                <td>
                    <button title="Edit Client Code" class="clientcodeedit-btn" data-id="${clientCode.cc_id}">
                        <img src="/static/icons/edit.png" alt="Edit">
                    </button>
                    <button title="Delete Client Code" class="clientcodedelete-btn" data-id="${clientCode.cc_id}">
                        <img src="/static/icons/delete.png" alt="Delete">
                    </button>
                </td>
            `;
            clientCodesTableBody.appendChild(row);
        });

        attachEventListeners();
        updatePagination();
    }
    // Expose renderer globally for cross-file and inline access
    window.renderClientCodesPage = displayClientCodesPage;

    function updatePagination() {
        const totalPages = Math.ceil(window.filteredClientCodes.length / rowsPerPage) || 1;
        prevButton.disabled = currentPage === 1;
        nextButton.disabled = currentPage >= totalPages;
        pageNumberDisplay.textContent = `${currentPage} of ${totalPages}`; // Show current and total pages
    }

    prevButton.addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage--;
            displayClientCodesPage(currentPage);
        }
    });

    nextButton.addEventListener("click", () => {
        const totalPages = Math.ceil(window.filteredClientCodes.length / rowsPerPage);
        if (currentPage < totalPages) {
            currentPage++;
            displayClientCodesPage(currentPage);
        }
    });

    fetchClientCodes();

    // Attach event listeners to dynamically created buttons
    function attachEventListeners() {
        document.querySelectorAll(".clientcodeedit-btn").forEach((button) => {
            button.addEventListener("click", () => {
                const clientCodeId = button.dataset.id;
                fetch(`/api/v1/masters/clientcodes/${clientCodeId}/`, { credentials: 'same-origin' })
                    .then((response) => response.json())
                    .then((resp) => {
                        const client = resp.data || resp;
                        if (client.error) {
                            notify(client.error, 'error');
                            return;
                        }
                        document.getElementById("clientcode-cc_id").value = client.cc_id;
                        document.getElementById("clientcode-client_code").value = client.client_code;

                        // Split and pass existing work types for pre-selection
                        const selectedWorkTypes = client.worktypes.split("|");
                        fetchWorkTypes(selectedWorkTypes, true);

                        clientCodeModal.style.display = "block";
                    })
                    .catch(() => notify('Failed to load Client Code details.', 'error'));
            });
        });

        document.querySelectorAll(".clientcodedelete-btn").forEach((button) => {
            button.addEventListener("click", () => {
                currentClientCodeIdToDelete = button.dataset.id;
                confirmDeleteClientCodeModal.style.display = "flex";
            });
        });

        document.querySelectorAll(".worktype-count").forEach((span) => {
            span.addEventListener("click", () => {
                const workTypes = span.dataset.worktypes.split("|");
                const clientCode = span.dataset.clientCode;
    
                // Populate header
                document.getElementById("workTypesHeader").textContent = `Work Types for Client Code: ${clientCode}`;
    
                // Populate table body
                const workTypesTableBody = document.getElementById("workTypesTableBody");
                workTypesTableBody.innerHTML = ""; // Clear previous entries
                workTypes.forEach((workType, index) => {
                    const row = `
                        <tr>
                            <td>${index + 1}</td>
                            <td>${workType}</td>
                        </tr>
                    `;
                    workTypesTableBody.innerHTML += row;
                });
    
                // Show the modal
                document.getElementById("workTypesModal").style.display = "block";
            });
        });
    
        // Close modal event
        document.getElementById("closeWorkTypesModal").addEventListener("click", () => {
            document.getElementById("workTypesModal").style.display = "none";
        });
    }

    // Open Add Client Code Modal (scoped to clientcode section to avoid duplicate IDs)
    addClientCodeButton.addEventListener("click", () => {
        const section = document.getElementById("clientcodes");
        if (!section) return;
        const modal = section.querySelector('#addClientCodeModal');
        if (!modal) return;

        // reset form safely within this modal
        const localForm = modal.querySelector('#addClientCodeForm');
        if (localForm) localForm.reset();

        // Fetch next CC ID
        fetch('/api/v1/masters/clientcodes/next-id/', { credentials: 'same-origin' })
            .then(res => res.json())
            .then(resp => {
                const data = resp.data || resp;
                const idInput = modal.querySelector('#add-cc_id');
                if (data.next_cc_id) {
                    if (idInput) idInput.value = data.next_cc_id;
                } else {
                    notify('Unable to fetch next Client Code ID.', 'error');
                    return;
                }

                // Populate worktypes inside this modal only
                const container = modal.querySelector('#addWorkTypesContainer');
                if (container) {
                    container.innerHTML = '';
                    fetch('/api/v1/masters/worktypes/', { credentials: 'same-origin' })
                        .then(r => r.json())
                        .then(resp => {
                            const wts = Array.isArray(resp) ? resp : (resp.results || resp.data || []);
                            const preselect = new Set(['Training']);
                            wts.forEach(wt => {
                                const isChecked = preselect.has(wt.worktypename) ? 'checked' : '';
                                container.innerHTML += `
                                    <label>
                                        <input type="checkbox" value="${wt.worktypename}" ${isChecked}>
                                        ${wt.worktypename}
                                    </label>
                                `;
                            });
                        })
                        .catch(() => notify('Failed to load Work Types.', 'error'));
                }

                modal.style.display = 'block';
            })
            .catch(() => notify('Failed to fetch next Client Code ID.', 'error'));
    });

    // Collect selected work types (scoped helper)
    function getSelectedWorkTypesFrom(containerEl) {
        const checkboxes = containerEl ? containerEl.querySelectorAll('input[type="checkbox"]:checked') : [];
        return Array.from(checkboxes).map(checkbox => checkbox.value).join('|');
    }

    // Handle Add Client Code Form Submission (scoped to clientcodes section)
    const scopedAddClientCodeForm = document.querySelector('#clientcodes #addClientCodeForm');
    if (scopedAddClientCodeForm) {
        scopedAddClientCodeForm.addEventListener("submit", function (e) {
            e.preventDefault();

            const section = document.getElementById("clientcodes");
            const modal = section ? section.querySelector('#addClientCodeModal') : null;
            if (!modal) return;

            const ccInput = modal.querySelector('#add-cc_id');
            const codeInput = modal.querySelector('#add-cclient_code');
            const container = modal.querySelector('#addWorkTypesContainer');

            const cc_id = (ccInput?.value || '').trim();
            const client_code = (codeInput?.value || '').trim();
            const worktypes = getSelectedWorkTypesFrom(container);

            if (!cc_id || !client_code) {
                notify('CC_ID and Client Code are required.', 'error');
                return;
            }

            const submitBtn = modal.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.disabled = true;

            fetch('/api/v1/masters/clientcodes/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '',
                },
                body: JSON.stringify({ cc_id, client_code, worktypes }),
            })
                .then(response => response.json())
                .then(data => {
                    if (!data.error) {
                        MasterDataCache.invalidate('master_clientcodes');
                        notify('Client Code added successfully!', 'success');
                        fetchClientCodes();
                        modal.style.display = 'none';
                    } else {
                        notify('Error adding Client Code: ' + (data.error || 'Unknown error'), 'error');
                    }
                })
                .catch(() => {
                    notify('Failed to add Client Code.', 'error');
                })
                .finally(() => {
                    if (submitBtn) submitBtn.disabled = false;
                });
        });
    }

    // Handle Edit Client Code Form Submission
    editClientCodeForm.addEventListener("submit", function (e) {
        e.preventDefault();

        const cc_id = document.getElementById("clientcode-cc_id").value;
        const client_code = document.getElementById("clientcode-client_code").value;
        const worktypes = getSelectedWorkTypesFrom(document.getElementById("editWorkTypesContainer"));

        fetch(`/api/v1/masters/clientcodes/${cc_id}/`, {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '',
            },
            body: JSON.stringify({ cc_id, client_code, worktypes }),
        })
            .then(response => response.json())
            .then(data => {
                if (!data.error) {
                    MasterDataCache.invalidate('master_clientcodes');
                    notify('Client Code updated successfully!', 'success');
                    fetchClientCodes();
                    clientCodeModal.style.display = "none";
                } else {
                    notify('Error updating Client Code: ' + data.error, 'error');
                }
            })
            .catch(() => notify('Failed to update Client Code.', 'error'));
    });

    // Fetch work types and populate the checkbox list for Add/Edit forms with caching
    function fetchWorkTypes(selectedWorkTypes = [], isEditForm = false) {
        MasterDataCache.getOrFetch('master_worktypes', '/api/v1/masters/worktypes/')
            .then(resp => {
                const data = Array.isArray(resp) ? resp : (resp.results || resp.data || []);
                const container = isEditForm
                    ? document.getElementById("editWorkTypesContainer")
                    : document.getElementById("addWorkTypesContainer");

                container.innerHTML = "";

                data.forEach(workType => {
                    const isChecked = selectedWorkTypes.includes(workType.worktypename) ? "checked" : "";
                    container.innerHTML += `
                        <label>
                            <input type="checkbox" value="${workType.worktypename}" ${isChecked}>
                            ${workType.worktypename}
                        </label>
                    `;
                });

                if (isEditForm) {
                    // Update active work types count
                    document.getElementById('active-worktypes').textContent = selectedWorkTypes.length;
                    
                    // Update last updated date
                    const currentDate = new Date().toISOString().split('T')[0];
                    document.getElementById('last-updated').textContent = currentDate;
                    
                    initializeWorkTypeSearch();
                }
            })
            .catch(() => {
                notify('Failed to load Work Types.', 'error');
            });
    }

    // Call the function to populate the work types on page load
    fetchWorkTypes();

    // Delete client code
    confirmDeleteClientCodeBtn.addEventListener("click", () => {
        fetch(`/api/v1/masters/clientcodes/${currentClientCodeIdToDelete}/`, {
            method: "DELETE",
            credentials: 'same-origin',
            headers: { "X-CSRFToken": (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "" },
        })
            .then((response) => response.json())
            .then((result) => {
                if (!result.error) {
                    MasterDataCache.invalidate('master_clientcodes');
                    confirmDeleteClientCodeModal.style.display = "none";
                    fetchClientCodes();
                } else {
                    notify('Error deleting Client Code.', 'error');
                }
            })
            .catch(() => notify('Failed to delete Client Code.', 'error'));
    });

    cancelDeleteClientCodeBtn.addEventListener("click", () => {
        confirmDeleteClientCodeModal.style.display = "none";
    });

    // Initial fetch of client codes
    fetchClientCodes();
});

    window.filterClientCodes = function() {
        const input = document.getElementById("searchClientCode");
        const term = (input?.value || "").toLowerCase();

        if (!term) {
            window.filteredClientCodes = window.clientCodes.slice();
        } else {
            window.filteredClientCodes = window.clientCodes.filter(cc => {
                const ccId = String(cc.cc_id || '').toLowerCase();
                const code = String(cc.client_code || '').toLowerCase();
                const worktypes = String(cc.worktypes || '').toLowerCase();
                return ccId.includes(term) || code.includes(term) || worktypes.includes(term);
            });
        }
        currentPage = 1;
        if (typeof window.renderClientCodesPage === 'function') {
            window.renderClientCodesPage(currentPage);
        }
    }

    function initializeWorkTypeSearch() {
        const searchInput = document.getElementById('worktype-search');
        const clearSearchIcon = document.querySelector('.clear-search-icon');
        
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const workTypeLabels = document.querySelectorAll('#editWorkTypesContainer label');
            
            workTypeLabels.forEach(label => {
                const workTypeName = label.textContent.toLowerCase();
                if (workTypeName.includes(searchTerm)) {
                    label.style.display = 'flex';
                } else {
                    label.style.display = 'none';
                }
            });
        });

    // Clear search functionality
    clearSearchIcon.addEventListener('click', () => {
        searchInput.value = '';
        const workTypeLabels = document.querySelectorAll('#editWorkTypesContainer label');
        workTypeLabels.forEach(label => {
            label.style.display = 'flex';
        });
    });

    // Update active work types count when checkboxes change
    const checkboxContainer = document.getElementById('editWorkTypesContainer');
    checkboxContainer.addEventListener('change', (e) => {
        if (e.target.type === 'checkbox') {
            const checkedBoxes = checkboxContainer.querySelectorAll('input[type="checkbox"]:checked');
            document.getElementById('active-worktypes').textContent = checkedBoxes.length;
        }
    });
}
