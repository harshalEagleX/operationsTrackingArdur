// Setup password visibility toggle
document.addEventListener('DOMContentLoaded', function() {
    const group = document.querySelector('.input-group.has-toggle');
    if (group) {
        const input = group.querySelector('input#password');
        const btn = group.querySelector('.password-toggle');
        if (input && btn) {
            btn.addEventListener('click', () => {
                const isPwd = input.type === 'password';
                input.type = isPwd ? 'text' : 'password';
                btn.setAttribute('aria-pressed', String(isPwd));
                const icon = btn.querySelector('i');
                if (icon) {
                    icon.classList.toggle('fa-eye', !isPwd);
                    icon.classList.toggle('fa-eye-slash', isPwd);
                }
            });
        }
    }
});

document.getElementById('login-form').addEventListener('submit', function(event) {
    event.preventDefault();

    const empId = document.getElementById('emp_id').value;
    const password = document.getElementById('password').value;

    fetch('/api/v1/auth/login/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ emp_id: empId, password: password })
    })
    .then(response => response.json().then(data => ({ status: response.status, body: data })))
    .then(({ status, body }) => {
        if (status === 200 || body.message === "Login successful") {
            window.location.href = body.redirect || "/dashboard/";
        } else {
            showAlert(body.error || body.detail || 'An error occurred', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('An unexpected error occurred. Please try again.', 'error');
    });
});

function showAlert(message, type) {
    const alertBox = document.createElement('div');
    alertBox.className = `custom-alert ${type}`;
    
    const icon = document.createElement('i');
    icon.className = type === 'error' ? 'fas fa-exclamation-circle' : 'fas fa-check-circle';
    
    const messageText = document.createElement('span');
    messageText.textContent = message;
    
    if (type === 'error' && message.includes("already logged in")) {
        messageText.innerHTML = `${message}<br><br>⚠️ Make sure to end your break and work session before logging out.`;
    }
    
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '×';
    closeBtn.className = 'close-btn';
    closeBtn.onclick = () => alertBox.remove();
    
    alertBox.appendChild(icon);
    alertBox.appendChild(messageText);
    alertBox.appendChild(closeBtn);
    
    document.body.appendChild(alertBox);
    
    // Auto-remove after 10 seconds
    setTimeout(() => {
        if (alertBox.parentElement) {
            alertBox.classList.add('fade-out');
            setTimeout(() => alertBox.remove(), 5000);
        }
    }, 10000);
}
