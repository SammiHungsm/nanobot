/**
 * Nanobot WebUI - Authentication Module
 * Handles user login, logout, and session management
 */

const Auth = {
    currentUser: null,
    
    // DOM elements
    elements: {
        overlay: null,
        form: null,
        usernameInput: null,
        passwordInput: null,
        logoutBtn: null,
        displayUsername: null
    },
    
    /**
     * Initialize authentication module
     */
    init() {
        // Cache DOM elements
        this.elements.overlay = document.getElementById('login-overlay');
        this.elements.form = document.getElementById('login-form');
        this.elements.usernameInput = document.getElementById('login-username');
        this.elements.passwordInput = document.getElementById('login-password');
        this.elements.logoutBtn = document.getElementById('logout-btn');
        this.elements.displayUsername = document.getElementById('display-username');
        
        // Bind event listeners
        this.elements.form.addEventListener('submit', (e) => this.handleLogin(e));
        this.elements.logoutBtn.addEventListener('click', () => this.handleLogout());
    },
    
    /**
     * Handle login form submission
     */
    handleLogin(e) {
        e.preventDefault();
        const username = this.elements.usernameInput.value.trim();
        
        if (username) {
            this.currentUser = username;
            this.elements.displayUsername.textContent = username;
            
            // Hide overlay with animation
            this.elements.overlay.classList.add('opacity-0');
            setTimeout(() => {
                this.elements.overlay.classList.add('hidden');
                this.elements.overlay.classList.remove('opacity-0');
            }, 300);
            
            // Trigger app initialization after login
            if (window.App && typeof App.init === 'function') {
                App.init();
            }
        }
    },
    
    /**
     * Handle logout
     */
    handleLogout() {
        this.currentUser = null;
        this.elements.usernameInput.value = '';
        this.elements.passwordInput.value = '';
        
        // Show overlay
        this.elements.overlay.classList.remove('hidden');
        
        // Clear chat history
        const chatContainer = document.getElementById('chat-container');
        const messages = chatContainer.querySelectorAll('.animate-fade-in-up');
        messages.forEach(msg => msg.remove());
        
        // Clear documents
        if (window.UI && typeof UI.clearDocuments === 'function') {
            UI.clearDocuments();
        }
    },
    
    /**
     * Get current logged-in user
     */
    getUser() {
        return this.currentUser || 'anonymous';
    },
    
    /**
     * Check if user is logged in
     */
    isLoggedIn() {
        return this.currentUser !== null;
    }
};

// Export for use in other modules
window.Auth = Auth;
