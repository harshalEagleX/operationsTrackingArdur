// Setup password visibility toggle
function togglePasswordVisibility(inputId, button) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isPwd = input.type === 'password';
    input.type = isPwd ? 'text' : 'password';
    const icon = button.querySelector('i');
    if (icon) {
        icon.classList.toggle('fa-eye', !isPwd);
        icon.classList.toggle('fa-eye-slash', isPwd);
    }
}

function showAlert(message, type) {
    const alertBox = document.createElement('div');
    alertBox.className = `custom-alert ${type}`;
    
    const icon = document.createElement('i');
    icon.className = type === 'error' ? 'fas fa-exclamation-circle' : 'fas fa-check-circle';
    
    const messageText = document.createElement('span');
    messageText.textContent = message;
    
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

document.getElementById('emp_id').addEventListener('blur', function () {
    const empId = this.value;

    if (empId) {
        // Send a request to check the employee ID
        fetch('/api/v1/auth/check-employee/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ emp_id: empId }),
        })
        .then((response) => response.json().then(data => ({ status: response.status, body: data })))
        .then(({ status, body }) => {
            if (status === 200 && body.name) {
                // Autofill the name if employee ID exists
                document.getElementById('name').value = body.name;
                document.getElementById('name').classList.remove('error');
            } else {
                document.getElementById('name').value = '';
                showAlert(body.error || 'Employee ID not found', 'error');
            }
        })
        .catch((error) => {
            console.error('Error:', error);
            showAlert('An error occurred while checking the employee ID.', 'error');
        });
    }
});

document.getElementById('signup-form').addEventListener('submit', function (event) {
    event.preventDefault();

    const empId = document.getElementById('emp_id').value;
    const name = document.getElementById('name').value;
    const password = document.getElementById('password').value;

    if (!empId || !name || !password) {
        showAlert('All fields are required', 'error');
        return;
    }

    // Add password validation
    if (password.length < 6) {
        showAlert('Password must be at least 6 characters long', 'error');
        return;
    }

    fetch('/api/v1/auth/signup/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ emp_id: empId, name: name, password: password }),
    })
    .then((response) => response.json().then(data => ({ status: response.status, body: data })))
    .then(({ status, body }) => {
        if (status === 201 || body.message === 'User registered successfully') {
            showAlert('Registration successful! Redirecting to login...', 'success');
            setTimeout(() => {
                window.location.href = '/login/';
            }, 2000);
        } else {
            showAlert(body.error || 'Registration failed', 'error');
        }
    })
    .catch((error) => {
        console.error('Error:', error);
        showAlert('An unexpected error occurred. Please try again.', 'error');
    });
});
