/**
 * Nanobot WebUI - Main Application
 * Initializes all modules and handles app lifecycle
 * 
 * 🌟 Architecture: Uses recursive setTimeout for polling (prevents avalanche)
 */

const App = {
    // State
    isPolling: false,              // 🌟 使用 boolean 旗標
    statusPollingTimer: null,      // 🌟 使用 setTimeout timer
    STATUS_POLL_INTERVAL: 2000,    // ms (2 seconds)
    STATUS_POLL_ERROR_INTERVAL: 4000, // ms (错误时放慢到 4 seconds)
    
    /**
     * Initialize the application
     */
    init() {
        console.log('🚀 Nanobot WebUI initializing...');
        
        // Initialize all modules
        Auth.init();
        UI.init();
        Library.init();
        
        // Set up global functions for HTML onclick handlers
        this.setupGlobalFunctions();
        
        console.log('✅ Nanobot WebUI ready');
    },
    
    /**
     * Set up global functions referenced in HTML
     */
    setupGlobalFunctions() {
        // Tab switching
        window.switchTab = (tab) => this.switchTab(tab);
        
        // Document list refresh
        window.refreshDocumentList = () => UI.loadDocuments();
        
        // Library functions
        window.filterLibrary = () => Library.filterLibrary();
        window.previewPDF = () => Library.previewPDF();
        window.closePreviewModal = () => Library.closePreviewModal();
        window.downloadPDF = () => Library.downloadPDF();
        window.viewProcessedOutput = () => Library.viewProcessedOutput();
        window.closeJsonModal = () => Library.closeJsonModal();
        window.copyJsonOutput = () => Library.copyJsonOutput();
        window.downloadProcessedOutput = () => Library.downloadProcessedOutput();
        window.closeDetailsPanel = () => Library.closeDetailsPanel();
    },
    
    /**
     * Switch between chat and library tabs (Database tab removed)
     */
    switchTab(tab) {
        const tabs = ['chat', 'library'];
        
        tabs.forEach(t => {
            const btn = document.getElementById(`tab-${t}`);
            const content = document.getElementById(`content-${t}`);
            
            if (!btn || !content) return;
            
            if (t === tab) {
                btn.className = 'tab-active px-6 py-3 rounded-t-lg font-medium text-sm transition-colors border border-b-0';
                content.classList.remove('hidden');
                
                // Load data when switching to tab
                if (t === 'chat') UI.loadDocuments();
                if (t === 'library') Library.loadDocuments();
            } else {
                btn.className = 'tab-inactive px-6 py-3 rounded-t-lg font-medium text-sm transition-colors border border-b-0';
                content.classList.add('hidden');
            }
        });
        
        // Update current tab
        if (window.UI) {
            UI.currentTab = tab;
        }
    },
    
    /**
     * Start status polling for processing documents
     * 🌟 使用递归 setTimeout 防止雪崩效应
     */
    startStatusPolling() {
        if (this.isPolling) return;  // 避免重复启动
        this.isPolling = true;
        
        const poll = async () => {
            if (!this.isPolling) return;  // 检查是否已停止
            
            try {
                const queueStatus = await API.getQueueStatus();
                const isProcessing = queueStatus.processing_count > 0 || queueStatus.queued_count > 0;
                
                if (isProcessing) {
                    // Refresh based on current tab
                    if (window.UI.currentTab === 'chat' || !window.Library) {
                        UI.loadDocuments();
                    } else {
                        Library.loadDocuments();
                    }
                    
                    // Update details panel if open
                    if (Library.selectedDocument && ['queued', 'processing'].includes(Library.selectedDocument.status)) {
                        Library.loadDocumentDetails(Library.selectedDocument.id);
                    }
                    
                    // 🌟 请求完成后，才排程下一次请求（防止雪崩）
                    this.statusPollingTimer = setTimeout(poll, this.STATUS_POLL_INTERVAL);
                } else {
                    this.stopStatusPolling();
                }
            } catch (error) {
                console.error('Status polling failed:', error);
                // 🌟 发生错误也继续重试，但放慢速度（避免永久中断）
                this.statusPollingTimer = setTimeout(poll, this.STATUS_POLL_ERROR_INTERVAL);
            }
        };
        
        poll();  // 立即触发第一次请求
    },
    
    /**
     * Stop status polling
     */
    stopStatusPolling() {
        this.isPolling = false;
        if (this.statusPollingTimer) {
            clearTimeout(this.statusPollingTimer);
            this.statusPollingTimer = null;
        }
    }
};

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => App.init());
} else {
    App.init();
}

// Export for use in other modules
window.App = App;