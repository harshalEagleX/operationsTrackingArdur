document.addEventListener("DOMContentLoaded", function () {
    // --- Date Range Helper Functions ---
    function getCurrentMonthRange() {
        const now = new Date();
        const istOffset = 5.5 * 60; // IST is UTC+5:30 in minutes
        const localOffset = now.getTimezoneOffset(); // in minutes
        const istTime = new Date(now.getTime() + (istOffset + localOffset) * 60000);

        const first = new Date(istTime.getFullYear(), istTime.getMonth(), 1);
        const today = istTime;

        const pad = n => n.toString().padStart(2, '0');
        const format = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

        return {
            from: format(first),
            to: format(today)
        };
    }

    function setDefaultFeedbackDateRange() {
        const range = getCurrentMonthRange();
        const fromInput = document.getElementById('feedback-from-date');
        const toInput = document.getElementById('feedback-to-date');
        if (fromInput && toInput) {
            fromInput.value = '';
            toInput.value = '';
            fromInput.value = range.from;
            toInput.value = range.to;
            // Debug log
            console.log('Default Feedback Date Range set:', range.from, range.to);
        }
    }

    function getSelectedFeedbackDateRange() {
        return {
            from: document.getElementById('feedback-from-date').value,
            to: document.getElementById('feedback-to-date').value
        };
    }

    window.fetchFeedbackCounts = async function fetchFeedbackCounts() {
        const {from, to} = getSelectedFeedbackDateRange();
        try {
            const currentUserRes = await fetch('/api/v1/auth/me/');
            const currentUserJson = await currentUserRes.json();
            const me = currentUserJson.data || currentUserJson;
            const myEmpId = me.emp_id;

            const res = await fetch(`/api/v1/feedback/?from=${from}&to=${to}`);
            const json = await res.json();
            const data = json.data || json;
            
            let received = 0;
            let sent = 0;
            if (Array.isArray(data)) {
                data.forEach(item => {
                    if (item.emp_id === myEmpId) received++;
                    if (item.created_by === myEmpId) sent++;
                });
            }
            
            const receivedCountEl = document.querySelector('#feedback-received-count span');
            const sentCountEl = document.querySelector('#feedback-sent-count span');
            if (receivedCountEl) receivedCountEl.textContent = received;
            if (sentCountEl) sentCountEl.textContent = sent;
        } catch (error) {
            console.error('Error fetching feedback counts:', error);
        }
    }

    window.fetchFeedbackReports = async function fetchFeedbackReports() {
        const {from, to} = getSelectedFeedbackDateRange();
        try {
            const currentUserRes = await fetch('/api/v1/auth/me/');
            const currentUserJson = await currentUserRes.json();
            const me = currentUserJson.data || currentUserJson;
            const myEmpId = me.emp_id;

            const res = await fetch(`/api/v1/feedback/?from=${from}&to=${to}`);
            const json = await res.json();
            let data = json.data || json;
            
            const feedbackTable = document.getElementById('feedback-table');
            if(!feedbackTable) return;
            const tableBody = feedbackTable.querySelector('tbody');
            if(!tableBody) return;
            
            tableBody.innerHTML = '';
            
            // Filter to only feedback received by this user
            if (Array.isArray(data)) {
                data = data.filter(item => item.emp_id === myEmpId);
                data.forEach(feedback => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>Report-${feedback.id}</td>
                        <td>${feedback.project || '-'}</td>
                        <td>-</td>
                        <td>${feedback.work_type || 'N/A'}</td>
                        <td>${new Date(feedback.created_at).toLocaleDateString()}</td>
                        <td><span class="severity-${(feedback.severity || '').toLowerCase()}">${feedback.severity}</span></td>
                        <td><span class="status-${feedback.is_acknowledged ? 'acknowledged' : 'pending'}">${feedback.is_acknowledged ? 'Acknowledged' : 'Pending'}</span></td>
                        <td>${feedback.description || 'N/A'}</td>
                        <td>${feedback.response || 'N/A'}</td>
                        <td>-</td>
                        <td>-</td>
                        <td>${feedback.is_acknowledged ? 'Acknowledged' : '<span class="ack-pending">Pending</span>'}</td>
                        <td>${feedback.acknowledged_at ? new Date(feedback.acknowledged_at).toLocaleDateString() : 'N/A'}</td>
                        <td>
                            <button onclick="showFeedbackDetail(${feedback.id})" class="btn-view">
                                <i class="fas fa-eye"></i> View
                            </button>
                        </td>
                    `;
                    tableBody.appendChild(row);
                });
            }
        } catch (error) {
            console.error('Error fetching feedback:', error);
        }
    }

    // Helper function to display acknowledgment status
    function getAcknowledgmentStatus(ack) {
        if (ack === null || ack === undefined) {
            return '<span class="ack-pending">Pending</span>';
        } else if (ack === 1) {
            return '<span class="ack-yes">Acknowledged</span>';
        } else if (ack === 0) {
            return '<span class="ack-no">Declined</span>';
        }
    }

    function navigateFeedback(currentId, direction) {
        const rows = Array.from(document.querySelectorAll('#feedback-table tbody tr'));
        if (!rows.length) return;

        const currentIndex = rows.findIndex(row => {
            const firstCell = row.querySelector('td');
            return firstCell && firstCell.textContent === `Report-${currentId}`;
        });

        if (currentIndex === -1) return;

        let newIndex;
        if (direction === 'prev') {
            newIndex = currentIndex === 0 ? rows.length - 1 : currentIndex - 1;
        } else if (direction === 'next') {
            newIndex = currentIndex === rows.length - 1 ? 0 : currentIndex + 1;
        }

        const newRow = rows[newIndex];
        const newIdCell = newRow.querySelector('td');
        if (newIdCell) {
            const newId = newIdCell.textContent.replace('Report-', '');
            window.showFeedbackDetail(newId);
            updateNavigationButtonStates(newIndex, rows.length);
        }
    }

    function updateNavigationButtonStates(currentIndex, totalItems) {
        const prevBtn = document.querySelector('.nav-btn.prev-btn');
        const nextBtn = document.querySelector('.nav-btn.next-btn');
        
        if (prevBtn && nextBtn) {
            prevBtn.disabled = currentIndex === 0;
            nextBtn.disabled = currentIndex === totalItems - 1;
        }
    }

    window.showFeedbackDetail = function showFeedbackDetail(feedbackId) {
        const feedbackReports = document.querySelector('.feedback-reports');
        const feedbackDetailPreview = document.querySelector('.feedback-detail-preview');
        
        if(feedbackReports) {
            feedbackReports.style.display = 'none';
        }
        if(feedbackDetailPreview) {
            feedbackDetailPreview.style.display = 'flex';
            feedbackDetailPreview.style.gridColumn = '1 / -1';
        }

        const detailHeader = document.querySelector('.detail-header');
        if (detailHeader && !document.querySelector('.detail-nav-controls')) {
            const navControls = document.createElement('div');
            navControls.className = 'detail-nav-controls';
            
            navControls.innerHTML = `
                <button class="back-to-reports">
                    <i class="fas fa-arrow-left"></i> Back to Reports
                </button>
                <div class="nav-buttons">
                    <button class="nav-btn prev-btn" title="Previous Report">
                        <i class="fas fa-chevron-left"></i>
                    </button>
                    <span id="report-id-display" class="report-id-badge"></span>
                    <button class="nav-btn next-btn" title="Next Report">
                        <i class="fas fa-chevron-right"></i>
                    </button>
                </div>
            `;

            navControls.querySelector('.back-to-reports').onclick = () => {
                if(feedbackReports) {
                    feedbackReports.style.display = 'flex';
                    feedbackReports.style.gridColumn = '1 / -1';
                }
                if(feedbackDetailPreview) {
                    feedbackDetailPreview.style.display = 'none';
                }
            };

            navControls.querySelector('.prev-btn').onclick = () => navigateFeedback(feedbackId, 'prev');
            navControls.querySelector('.next-btn').onclick = () => navigateFeedback(feedbackId, 'next');
            
            detailHeader.insertBefore(navControls, detailHeader.firstChild);
        }

        fetch(`/get_feedback_detail/${feedbackId}`)
            .then(response => response.json())
            .then(data => {
                const reportIdDisplay = document.getElementById('report-id-display');
                if(reportIdDisplay) reportIdDisplay.textContent = `Report-${feedbackId}`;
                
                const noDetailsText = document.querySelector('.no-details-text');
                const detailsContent = document.querySelector('.details-content');
                const acknowledgmentSection = document.querySelector('.acknowledgment-section');
                
                if (noDetailsText) noDetailsText.style.display = 'none';
                if (detailsContent) {
                    detailsContent.style.display = 'grid';
                    
                    const getAcknowledgmentDisplay = (ack) => {
                        if (ack === null || ack === undefined) {
                            return '<span class="ack-pending">Pending</span>';
                        } else if (ack === 1) {
                            return '<span class="ack-yes">Yes</span>';
                        } else if (ack === 0) {
                            return '<span class="ack-no">No</span>';
                        }
                    };

                    detailsContent.innerHTML = `
                        <div class="detail-item"><strong>Project:</strong> ${data.project}</div>
                        <div class="detail-item"><strong>Client Code:</strong> ${data.client_code}</div>
                        <div class="detail-item"><strong>Work Type:</strong> ${data.work_type || 'N/A'}</div>
                        <div class="detail-item"><strong>Feedback Date:</strong> ${new Date(data.feedback_received_date).toLocaleDateString()}</div>
                        <div class="detail-item"><strong>Severity:</strong> <span class="severity-${data.severity.toLowerCase()}">${data.severity}</span></div>
                        <div class="detail-item"><strong>Status:</strong> ${data.status}</div>
                        <div class="detail-item feedback-text"><strong>Feedback:</strong> ${data.feedback}</div>
                        <div class="detail-item"><strong>Action Taken:</strong> ${data.action_taken || 'N/A'}</div>
                        <div class="detail-item"><strong>Comments:</strong> ${data.comments || 'N/A'}</div>
                        <div class="detail-item"><strong>Fields:</strong> ${data.fields || 'N/A'}</div>
                        <div class="detail-item"><strong>Feedback Provided By:</strong> ${data.feedback_provided_by || 'N/A'}</div>
                        <div class="detail-item acknowledgment-info">
                            <strong>Acknowledgment Status:</strong> 
                            ${getAcknowledgmentDisplay(data.acknowledgment)}
                        </div>
                        ${data.acknowledgment_date ? `
                            <div class="detail-item"><strong>Acknowledged On:</strong> ${new Date(data.acknowledgment_date).toLocaleString()}</div>
                        ` : ''}
                        ${data.acknowledgment_comment ? `
                            <div class="detail-item"><strong>Acknowledgment Comment:</strong> ${data.acknowledgment_comment}</div>
                        ` : ''}
                    `;
                }

                if (acknowledgmentSection) {
                    acknowledgmentSection.style.display = 
                        (data.acknowledgment === null || data.acknowledgment === undefined) ? 'block' : 'none';
                    acknowledgmentSection.dataset.feedbackId = feedbackId;
                }

                const imageCarousel = document.getElementById('image-carousel');
                const noImageText = document.querySelector('.no-image-text');
                
                if (data.images && data.images.length > 0) {
                    if(noImageText) noImageText.style.display = 'none';
                    if(imageCarousel) {
                        imageCarousel.innerHTML = '';
                        const imageCount = document.getElementById('image-count');
                        if(imageCount) imageCount.textContent = data.images.length;
                        
                        data.images.forEach((image, index) => {
                            const imgElement = document.createElement('img');
                            imgElement.className = 'loading';
                            imgElement.src = `data:image/jpeg;base64,${image.data}`;
                            imgElement.alt = `Feedback screenshot ${index + 1}`;
                            imgElement.dataset.index = index;
                            
                            imgElement.onload = () => {
                                imgElement.classList.remove('loading');
                            };
                            
                            if (typeof window.showFullImage === 'function') {
                                imgElement.onclick = () => window.showFullImage(imgElement.src, index);
                            }
                            imageCarousel.appendChild(imgElement);
                        });
                    }

                    const counterBadge = document.querySelector('.image-counter-badge');
                    if (counterBadge) {
                        counterBadge.style.display = 'flex';
                    }
                } else {
                    if(imageCarousel) imageCarousel.innerHTML = '';
                    if (noImageText) {
                        noImageText.innerHTML = '<i class="fas fa-image"></i> No screenshots attached to this feedback';
                        noImageText.style.display = 'flex';
                    }
                    const counterBadge = document.querySelector('.image-counter-badge');
                    if (counterBadge) {
                        counterBadge.style.display = 'none';
                    }
                }

                const rows = document.querySelectorAll('#feedback-table tbody tr');
                const currentIndex = Array.from(rows).findIndex(row => 
                    row.querySelector('td').textContent === `Report-${feedbackId}`
                );
                updateNavigationButtonStates(currentIndex, rows.length);
            })
            .catch(error => console.error('Error:', error));
    }


    // --- Event Listeners Initialization ---

    const prevBtn = document.querySelector('.nav-btn.prev-btn');
    const nextBtn = document.querySelector('.nav-btn.next-btn');

    if (prevBtn) {
        prevBtn.addEventListener('click', function() {
            const reportIdDisplay = document.getElementById('report-id-display');
            if(reportIdDisplay) {
                const currentId = reportIdDisplay.textContent.replace('Report-', '');
                navigateFeedback(currentId, 'prev');
            }
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            const reportIdDisplay = document.getElementById('report-id-display');
            if(reportIdDisplay) {
                const currentId = reportIdDisplay.textContent.replace('Report-', '');
                navigateFeedback(currentId, 'next');
            }
        });
    }

    // Acknowledgment handling
    const ackCommentPopup = document.getElementById('ack-comment-popup');
    const ackComment = document.getElementById('ack-comment');
    const submitAckComment = document.getElementById('submit-ack-comment');
    const cancelAckComment = document.getElementById('cancel-ack-comment');
    const ackYesBtn = document.getElementById('ack-yes-btn');
    const ackNoBtn = document.getElementById('ack-no-btn');

    if (ackYesBtn) {
        ackYesBtn.addEventListener('click', () => {
            const ackSection = document.querySelector('.acknowledgment-section');
            if(!ackSection) return;
            const feedbackId = ackSection.dataset.feedbackId;
            if (ackCommentPopup) {
                ackCommentPopup.classList.remove('hidden');
                if (ackComment) {
                    ackComment.required = false;
                    ackComment.placeholder = 'Optional: Add a comment for your acknowledgment';
                }
                ackCommentPopup.dataset.actionType = 'accept';
                ackCommentPopup.dataset.feedbackId = feedbackId;
            }
        });
    }

    if (ackNoBtn) {
        ackNoBtn.addEventListener('click', () => {
            const ackSection = document.querySelector('.acknowledgment-section');
            if(!ackSection) return;
            const feedbackId = ackSection.dataset.feedbackId;
            if (ackCommentPopup) {
                ackCommentPopup.classList.remove('hidden');
                if (ackComment) {
                    ackComment.required = true;
                    ackComment.placeholder = 'Please provide a reason for declining';
                }
                ackCommentPopup.dataset.actionType = 'decline';
                ackCommentPopup.dataset.feedbackId = feedbackId;
            }
        });
    }

    if (submitAckComment) {
        submitAckComment.addEventListener('click', () => {
            const feedbackId = ackCommentPopup.dataset.feedbackId;
            const isAccepted = ackCommentPopup.dataset.actionType === 'accept';
            const comment = ackComment ? ackComment.value.trim() : '';
            
            if (!isAccepted && !comment) {
                alert('Please provide a reason for declining the acknowledgment.');
                return;
            }

            fetch('/update_feedback_acknowledgment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    feedback_id: feedbackId,
                    acknowledged: isAccepted,
                    comment: comment
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (ackCommentPopup) ackCommentPopup.classList.add('hidden');
                    if (ackComment) ackComment.value = '';
                    window.showFeedbackDetail(feedbackId); 
                    window.fetchFeedbackReports(); 
                } else {
                    alert('Error updating acknowledgment. Please try again.');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error updating acknowledgment. Please try again.');
            });
        });
    }

    if (cancelAckComment) {
        cancelAckComment.addEventListener('click', () => {
            if (ackCommentPopup) ackCommentPopup.classList.add('hidden');
            if (ackComment) ackComment.value = '';
        });
    }

    const backToReportsBtn = document.querySelector('.back-to-reports');
    if (backToReportsBtn) {
        backToReportsBtn.addEventListener('click', function() {
            const feedbackReports = document.querySelector('.feedback-reports');
            const feedbackDetailPreview = document.querySelector('.feedback-detail-preview');
            
            if (feedbackReports && feedbackDetailPreview) {
                feedbackReports.style.display = 'block';
                feedbackDetailPreview.style.display = 'none';
            }
            window.fetchFeedbackReports();
        });
    }

    // Default filters
    if (document.getElementById('feedback-from-date') && document.getElementById('feedback-to-date')) {
        setDefaultFeedbackDateRange();
        window.fetchFeedbackCounts();
        window.fetchFeedbackReports();
        document.getElementById('feedback-from-date').addEventListener('change', function() {
            window.fetchFeedbackCounts();
            window.fetchFeedbackReports();
        });
        document.getElementById('feedback-to-date').addEventListener('change', function() {
            window.fetchFeedbackCounts();
            window.fetchFeedbackReports();
        });
    }

});
