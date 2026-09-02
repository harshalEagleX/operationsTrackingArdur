function openLeaveModal() {
    document.getElementById('markLeaveModal').style.display = 'block';
}
function closeLeaveModal() {
    document.getElementById('markLeaveModal').style.display = 'none';
}

$(document).ready(function() {
    const csrftoken = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
    
    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
        }
    });
    
    // Load attendance history
    function loadAttendance() {
        $.get('/api/v1/tracking/attendance-history/', function(res) {
            const data = res.data || res;
            const tbody = $('#attendance-history-body');
            tbody.empty();
            
            if (data.length === 0) {
                tbody.html('<tr><td colspan="4" style="text-align:center;">No records for this month</td></tr>');
                return;
            }

            data.forEach(function(day) {
                const dateObj = new Date(day.date);
                const dateStr = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                
                let loginStr = '--:--';
                if (day.login_time) {
                    loginStr = new Date(day.login_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                }
                
                let logoutStr = '--:--';
                if (day.logout_time) {
                    logoutStr = new Date(day.logout_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                }
                
                // Helper to format seconds to hh:mm:ss
                const formatTime = (seconds) => {
                    const h = Math.floor(seconds / 3600);
                    const m = Math.floor((seconds % 3600) / 60);
                    const s = seconds % 60;
                    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
                };
                
                const netStr = formatTime(day.net_seconds || 0);
                const netColor = (day.net_seconds > 0) ? '#2ecc71' : 'inherit';

                tbody.append(`
                    <tr>
                        <td style="font-size: 0.85rem; padding: 6px;">${dateStr}</td>
                        <td style="font-size: 0.85rem; padding: 6px;">${loginStr}</td>
                        <td style="font-size: 0.85rem; padding: 6px;">${logoutStr}</td>
                        <td style="font-size: 0.85rem; padding: 6px; font-weight: 600; color: ${netColor};">${netStr}</td>
                    </tr>
                `);
            });
        });
    }
    loadAttendance();

    // Handle Leave Submit
    $('#mark-leave-form').on('submit', function(e) {
        e.preventDefault();
        const date = $('#leave-date').val();
        $.ajax({
            url: '/api/v1/tracking/attendance/mark-leave/',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ date: date }),
            success: function() {
                alert("Leave marked successfully");
                closeLeaveModal();
                loadAttendance();
            },
            error: function(err) {
                alert("Error marking leave: " + (err.responseJSON?.error || err.statusText));
            }
        });
    });

    // Shift Timer Logic
    let shiftTimerInterval = null;
    let shiftStartTime = null;

    function updateShiftTimerDisplay() {
        if (!shiftStartTime) return;
        const now = new Date();
        const diff = Math.floor((now - shiftStartTime) / 1000);
        const hrs = String(Math.floor(diff / 3600)).padStart(2, '0');
        const mins = String(Math.floor((diff % 3600) / 60)).padStart(2, '0');
        const secs = String(diff % 60).padStart(2, '0');
        $('#shift-timer').text(`${hrs}:${mins}:${secs}`);
    }

    // Check current shift status
    $.get('/api/v1/tracking/attendance/status/', function(res) {
        let data = res.data || res;
        if (data.is_active && data.first_login) {
            shiftStartTime = new Date(data.first_login);
            shiftTimerInterval = setInterval(updateShiftTimerDisplay, 1000);
            $('#btn-start-shift').hide();
            $('#btn-end-shift').show();
        }
    });

    window.startShift = function() {
        $.post('/api/v1/tracking/attendance/start-shift/', function(res) {
            let data = res.data || res;
            shiftStartTime = new Date(data.first_login);
            shiftTimerInterval = setInterval(updateShiftTimerDisplay, 1000);
            $('#btn-start-shift').hide();
            $('#btn-end-shift').show();
            loadAttendance();
        });
    };

    window.endShift = function() {
        if (!confirm("Are you sure you want to end your shift for the day?")) return;
        $.post('/api/v1/tracking/attendance/end-shift/', function(res) {
            clearInterval(shiftTimerInterval);
            $('#btn-end-shift').hide();
            $('#btn-start-shift').show();
            loadAttendance();
            $('#shift-timer').text('00:00:00');
        });
    };
});
