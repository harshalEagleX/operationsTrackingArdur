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
        $.get('/api/v1/tracking/attendance/my-history/', function(data) {
            const tbody = $('#attendance-history-body');
            tbody.empty();
            data.forEach(function(row) {
                tbody.append(`
                    <tr>
                        <td style="font-size: 0.8rem; padding: 6px;">${row.date}</td>
                        <td style="font-size: 0.8rem; padding: 6px;"><span style="text-transform: capitalize;">${row.status}</span></td>
                        <td style="font-size: 0.8rem; padding: 6px;">${row.first_login ? new Date(row.first_login).toLocaleTimeString() : '-'}</td>
                        <td style="font-size: 0.8rem; padding: 6px;">${row.last_logout ? new Date(row.last_logout).toLocaleTimeString() : '-'}</td>
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
