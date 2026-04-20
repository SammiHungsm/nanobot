/**
 * Nanobot WebUI - Authentication Module
 * Handles user login, logout, and session management with localStorage persistence
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
        // Cache DOM elements (with null checks)
        this.elements.overlay = document.getElementById('login-overlay');
        this.elements.form = document.getElementById('login-form');
        this.elements.usernameInput = document.getElementById('login-username');
        this.elements.passwordInput = document.getElementById('login-password');
        this.elements.logoutBtn = document.getElementById('logout-btn');
        this.elements.displayUsername = document.getElementById('display-username');
        
        // Bind event listeners (with null checks)
        if (this.elements.form) {
            this.elements.form.addEventListener('submit', (e) => this.handleLogin(e));
        }
        if (this.elements.logoutBtn) {
            this.elements.logoutBtn.addEventListener('click', () => this.handleLogout());
        }
        
        // 🔧 修復：檢查 localStorage 是否有登入記錄，自動恢復登入狀態
        this.restoreSession();
    },
    
    /**
     * 🔧 新增：從 localStorage 恢復登入狀態
     */
    restoreSession() {
        const savedUser = localStorage.getItem('nanobot_user');
        if (savedUser && this.elements.overlay && this.elements.displayUsername) {
            this.currentUser = savedUser;
            this.elements.displayUsername.textContent = savedUser;
            
            // 隱藏登入畫面
            this.elements.overlay.classList.add('opacity-0');
            setTimeout(() => {
                this.elements.overlay.classList.add('hidden');
                this.elements.overlay.classList.remove('opacity-0');
            }, 300);
            
            console.log(`✅ Session restored for user: ${savedUser}`);
        }
    },
    
    /**
     * Handle login form submission
     */
    handleLogin(e) {
        e.preventDefault();
        if (!this.elements.usernameInput) return;
        
        const username = this.elements.usernameInput.value.trim();
        
        if (username && this.elements.overlay && this.elements.displayUsername) {
            this.currentUser = username;
            this.elements.displayUsername.textContent = username;
            
            // 🔧 新增：保存到 localStorage
            localStorage.setItem('nanobot_user', username);
            
            // Hide overlay with animation
            this.elements.overlay.classList.add('opacity-0');
            setTimeout(() => {
                this.elements.overlay.classList.add('hidden');
                this.elements.overlay.classList.remove('opacity-0');
            }, 300);
        }
    },
    
    /**
     * Handle logout
     */
    handleLogout() {
        this.currentUser = null;
        this.elements.usernameInput.value = '';
        this.elements.passwordInput.value = '';
        
        // 🔧 新增：清除 localStorage
        localStorage.removeItem('nanobot_user');
        
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
