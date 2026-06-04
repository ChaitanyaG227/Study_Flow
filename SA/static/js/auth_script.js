document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('container');
    const signUpButton = document.getElementById('signUp');
    const signInButton = document.getElementById('signIn');
    
    // Switch between Sign In and Sign Up panels
    if(signUpButton) {
        signUpButton.addEventListener('click', () => container.classList.add("right-panel-active"));
    }
    if(signInButton) {
        signInButton.addEventListener('click', () => container.classList.remove("right-panel-active"));
    }

    // --- Form Handling ---
    const registerForm = document.getElementById('registerForm');
    const loginForm = document.getElementById('loginForm');

    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            if (!validateRegisterForm()) {
                e.preventDefault(); // Stop submission if validation fails
            } else {
                addLoadingState(this.querySelector('button[type="submit"]'));
            }
        });
    }

    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            if (!validateLoginForm()) {
                e.preventDefault();
            } else {
                addLoadingState(this.querySelector('button[type="submit"]'));
            }
        });
    }
    
    // --- Validation Logic ---
    const setError = (input, message) => {
        const inputGroup = input.parentElement;
        const errorDisplay = inputGroup.querySelector('.error-message');
        errorDisplay.innerText = message;
        input.style.borderColor = '#ff4b2b';
    };

    const setSuccess = (input) => {
        const inputGroup = input.parentElement;
        const errorDisplay = inputGroup.querySelector('.error-message');
        errorDisplay.innerText = '';
        input.style.borderColor = '#28a745';
    };

    const isValidEmail = email => {
        const re = /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
        return re.test(String(email).toLowerCase());
    };

    const validateRegisterForm = () => {
        let isValid = true;
        const name = document.getElementById('registerName');
        const email = document.getElementById('registerEmail');
        const password = document.getElementById('registerPassword');
        const confirmPassword = document.getElementById('confirmPassword');
        
        if (name.value.trim() === '') {
            setError(name, 'Name is required');
            isValid = false;
        } else {
            setSuccess(name);
        }

        if (email.value.trim() === '') {
            setError(email, 'Email is required');
            isValid = false;
        } else if (!isValidEmail(email.value.trim())) {
            setError(email, 'Provide a valid email address');
            isValid = false;
        } else {
            setSuccess(email);
        }

        if (password.value.trim() === '') {
            setError(password, 'Password is required');
            isValid = false;
        } else if (password.value.length < 6) {
            setError(password, 'Password must be at least 6 characters.');
            isValid = false;
        } else {
            setSuccess(password);
        }

        if (confirmPassword.value.trim() === '') {
            setError(confirmPassword, 'Please confirm your password');
            isValid = false;
        } else if (password.value !== confirmPassword.value) {
            setError(confirmPassword, "Passwords don't match");
            isValid = false;
        } else {
            setSuccess(confirmPassword);
        }
        
        return isValid;
    };
    
    const validateLoginForm = () => {
        let isValid = true;
        const email = document.getElementById('loginEmail');
        const password = document.getElementById('loginPassword');

        if (email.value.trim() === '') {
            setError(email, 'Email is required');
            isValid = false;
        } else {
            setSuccess(email);
        }
        
        if (password.value.trim() === '') {
            setError(password, 'Password is required');
            isValid = false;
        } else {
            setSuccess(password);
        }

        return isValid;
    };
    
    // --- UI Helpers ---
    const addLoadingState = (button) => {
        button.disabled = true;
        button.innerHTML = '<span class="spinner"></span> Signing In...';
    };
    
    // Password visibility toggle
    document.querySelectorAll('.toggle-password').forEach(toggle => {
        toggle.addEventListener('click', function() {
            const passwordInput = this.previousElementSibling;
            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                this.classList.remove('fa-eye-slash');
                this.classList.add('fa-eye');
            } else {
                passwordInput.type = 'password';
                this.classList.remove('fa-eye');
                this.classList.add('fa-eye-slash');
            }
        });
    });
});