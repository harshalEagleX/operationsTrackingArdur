document.addEventListener("DOMContentLoaded", () => {
    const worktypesTable = document.getElementById("worktypes-table").getElementsByTagName("tbody")[0];
    const editWorktypeModal = document.getElementById("worktypeModal");
    const addWorktypeModal = document.getElementById("addWorktypeModal");
    const confirmDeleteModal = document.getElementById("confirmDeleteWorktypeModal");
    const addWtIdField = document.getElementById("add-wt_id");
    const editForm = document.getElementById("editWorktypeForm");
    const addForm = document.getElementById("addWorktypeForm");
    const confirmDeleteButton = document.getElementById("confirmDeleteWorktypeBtn");
    const cancelDeleteButton = document.getElementById("cancelDeleteWorktypeBtn");
    let deleteWorktypeId = null;

    // Expose to global to support inline handlers and cross-file calls
    window.worktypesData = window.worktypesData || [];
    window.filteredWorktypesData = window.filteredWorktypesData || [];
    let currentPage = 1;
    const rowsPerPage = 15;

    const worktypesTableBody = document.querySelector("#worktypes-table tbody");
    const prevButton = document.getElementById("wtprevPage");
    const nextButton = document.getElementById("wtnextPage");
    const pageNumberDisplay = document.getElementById("wtpageNumber"); // Page number display

    const notify = (message, type = 'info') => {
        const prefix = type === 'error' ? 'Error: ' : type === 'success' ? 'Success: ' : '';
        alert(`${prefix}${message}`);
    };

    function fetchWorktypes() {
        fetch("/api/v1/masters/worktypes/?active=true", { credentials: 'same-origin' })
            .then(response => response.json())
            .then(resp => {
                // DRF wraps results in {results:[...]} when paginated, or returns array directly
                const data = Array.isArray(resp) ? resp : (resp.results || resp.data || []);
                window.worktypesData = data;
                window.filteredWorktypesData = data; // initialize filtered set
                currentPage = 1; // Reset to first page
                displayPage(currentPage);
            })
            .catch(() => notify('Failed to load Work Types.', 'error'));
    }

    function displayPage(page) {
        worktypesTableBody.innerHTML = ""; // Clear existing rows
        const startIndex = (page - 1) * rowsPerPage;
        const endIndex = startIndex + rowsPerPage;
        const pageData = window.filteredWorktypesData.slice(startIndex, endIndex);

        pageData.forEach((worktype, index) => {
            // Preserve original serial number based on full dataset order
            const originalIndex = Array.isArray(window.worktypesData)
                ? window.worktypesData.findIndex(w => w.wt_id === worktype.wt_id) + 1
                : (startIndex + index + 1);
            const row = document.createElement("tr");
            row.innerHTML = `
                <td>${originalIndex}</td>
                <td>${worktype.wt_id}</td>
                <td>${worktype.work_type}</td>
                <td>
                    <button title="Edit Work Type" class="wtedit-btn" data-id="${worktype.wt_id}">
                        <img src="/static/icons/edit.png" alt="Edit">
                    </button>
                    <button title="Delete Work Type" class="wtdelete-btn" data-id="${worktype.wt_id}">
                        <img src="/static/icons/delete.png" alt="Delete">
                    </button>
                </td>
            `;
            worktypesTableBody.appendChild(row);
        });

        attachEventListeners();
        updatePagination();
    }
    // Expose renderer globally for cross-file and inline access
    window.renderWorktypesPage = displayPage;

    function updatePagination() {
        const totalPages = Math.ceil(window.filteredWorktypesData.length / rowsPerPage) || 1;
        prevButton.disabled = currentPage === 1;
        nextButton.disabled = currentPage >= totalPages;
        pageNumberDisplay.textContent = `${currentPage} of ${totalPages}`; // Show current and total pages
    }

    function attachEventListeners() {
        document.querySelectorAll(".wtedit-btn").forEach(button => {
            button.addEventListener("click", () => openEditModal(button.dataset.id));
        });

        document.querySelectorAll(".wtdelete-btn").forEach(button => {
            button.addEventListener("click", () => openDeleteModal(button.dataset.id));
        });
    }

    prevButton.addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage--;
            displayPage(currentPage);
        }
    });

    nextButton.addEventListener("click", () => {
        const totalPages = Math.ceil(window.filteredWorktypesData.length / rowsPerPage);
        if (currentPage < totalPages) {
            currentPage++;
            displayPage(currentPage);
        }
    });

    fetchWorktypes();

    // Open the edit modal
    function openEditModal(wt_id) {
        fetch(`/api/v1/masters/worktypes/${wt_id}/`, { credentials: 'same-origin' })
            .then(response => response.json())
            .then(resp => {
                const worktype = resp.data || resp;
                document.getElementById("worktype-id").value = worktype.wt_id;
                document.getElementById("worktype-wt_id").value = worktype.wt_id;
                document.getElementById("worktype-work_type").value = worktype.work_type;

                editWorktypeModal.style.display = "block";
            })
            .catch(() => notify('Failed to load Work Type details.', 'error'));
    }

    // Submit the edit form
    editForm.addEventListener("submit", (e) => {
        e.preventDefault();

        const wt_id = document.getElementById("worktype-wt_id").value;
        const worktypename = document.getElementById("worktype-work_type").value;

        fetch(`/api/v1/masters/worktypes/${wt_id}/`, {
            method: "PATCH",
            credentials: 'same-origin',
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "",
            },
            body: JSON.stringify({ work_type: worktypename }),
        })
            .then(response => response.json())
            .then(data => {
                if (!data.error) {
                    MasterDataCache.invalidate('master_worktypes');
                    notify('Work Type updated successfully!', 'success');
                    fetchWorktypes();
                    editWorktypeModal.style.display = "none";
                } else {
                    notify('Error updating Work Type: ' + (data.error || 'Unknown error'), 'error');
                }
            })
            .catch(() => notify('Failed to update Work Type.', 'error'));
    });

    // Open the add modal and fetch the next Work Type ID (scoped to worktypes section)
    document.getElementById("addWorktypeButton").addEventListener("click", () => {
        const section = document.getElementById('worktypes');
        if (!section) return;

        const localModal = section.querySelector('#addWorktypeModal');
        const localForm = section.querySelector('#addWorktypeForm');
        const localIdField = section.querySelector('#add-wt_id');

        if (localForm) localForm.reset();

        fetch("/api/v1/masters/worktypes/next-id/", { credentials: 'same-origin' })
            .then(response => response.json())
            .then(resp => {
                const data = resp.data || resp;
                if (data.next_id) {
                    if (localIdField) {
                        localIdField.value = data.next_id;
                        localIdField.readOnly = true;
                    }
                    if (localModal) localModal.style.display = "block";
                } else {
                    notify('Unable to fetch next Work Type ID.', 'error');
                }
            })
            .catch(() => notify('Failed to fetch next Work Type ID.', 'error'));
    });

    // Submit the add form
    const scopedAddForm = document.querySelector('#worktypes #addWorktypeForm');
    if (scopedAddForm) {
        scopedAddForm.addEventListener("submit", (e) => {
            e.preventDefault();

            const section = document.getElementById('worktypes');
            const localModal = section ? section.querySelector('#addWorktypeModal') : null;
            const localIdField = section ? section.querySelector('#add-wt_id') : null;
            const worktypenameInput = section ? section.querySelector('#add-work_type') : null;

            const wt_id = ((localIdField && localIdField.value) || '').trim();
            const worktypename = ((worktypenameInput && worktypenameInput.value) || '').trim();

            if (!wt_id || !worktypename) {
                notify('Work Type ID and Name are required.', 'error');
                return;
            }

            const submitBtn = scopedAddForm.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.disabled = true;

            fetch("/api/v1/masters/worktypes/", {
                method: "POST",
                credentials: 'same-origin',
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "",
                },
                body: JSON.stringify({ work_type: worktypename, wt_id }),
            })
                .then(response => response.json())
                .then(data => {
                    if (!data.error) {
                        MasterDataCache.invalidate('master_worktypes');
                        notify('Work Type added successfully!', 'success');
                        fetchWorktypes();
                        if (localModal) localModal.style.display = "none";
                    } else {
                        let errorMsg = 'Unknown error';
                        if (data.error) {
                            errorMsg = data.error.message || JSON.stringify(data.error);
                        }
                        notify('Error adding Work Type: ' + errorMsg, 'error');
                    }
                })
                .catch(() => {
                    notify('Failed to add Work Type.', 'error');
                })
                .finally(() => {
                    if (submitBtn) submitBtn.disabled = false;
                });
        });
    }

    // Open the delete modal
    function openDeleteModal(wt_id) {
        deleteWorktypeId = wt_id;
        confirmDeleteModal.style.display = "flex";
    }

    // Confirm delete
    confirmDeleteButton.addEventListener("click", () => {
        fetch(`/api/v1/masters/worktypes/${deleteWorktypeId}/`, {
            method: "DELETE",
            credentials: 'same-origin',
            headers: { "X-CSRFToken": (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "" },
        })
            .then(response => {
                if (response.ok) {
                    MasterDataCache.invalidate('master_worktypes');
                    fetchWorktypes();
                    confirmDeleteModal.style.display = "none";
                } else {
                    notify('Error deleting Work Type.', 'error');
                }
            });
    });

    // Cancel delete
    cancelDeleteButton.addEventListener("click", () => {
        confirmDeleteModal.style.display = "none";
        deleteWorktypeId = null;
    });

    // Close modals
    document.querySelectorAll(".modal .close-btn").forEach(button => {
        button.addEventListener("click", () => {
            button.closest(".modal").style.display = "none";
        });
    });


    // Initial fetch
    fetchWorktypes();
});

window.filterWorktypes = function() {
    const input = document.getElementById("searchWorktype");
    const term = (input?.value || "").toLowerCase();

    if (!term) {
        window.filteredWorktypesData = window.worktypesData.slice();
    } else {
        window.filteredWorktypesData = window.worktypesData.filter(wt => {
            const id = String(wt.wt_id || '').toLowerCase();
            const name = String(wt.work_type || '').toLowerCase();
            return id.includes(term) || name.includes(term);
        });
    }
    currentPage = 1;
    if (typeof window.renderWorktypesPage === 'function') {
        window.renderWorktypesPage(currentPage);
    }
}
