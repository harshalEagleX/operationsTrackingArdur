import { api } from './core/api.js';
import { toast } from './core/toast.js';

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

document.getElementById('login-form').addEventListener('submit', async function(event) {
    event.preventDefault();

    const empId = document.getElementById('emp_id').value;
    const password = document.getElementById('password').value;
    
    const submitBtn = this.querySelector('button[type="submit"]');
    const originalContent = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Logging in...';
    submitBtn.disabled = true;

    try {
        const data = await api.post('/auth/login/', { emp_id: empId, password: password });
        window.location.href = data?.redirect || "/dashboard/";
    } catch (error) {
        console.error('Login error:', error);
        
        let msg = error.message || 'An unexpected error occurred. Please try again.';
        if (msg.includes("already logged in")) {
            msg += "\n\n⚠️ Make sure to end your break and work session before logging out.";
        }
        
        toast.error(msg);
        
        submitBtn.innerHTML = originalContent;
        submitBtn.disabled = false;
    }
});
