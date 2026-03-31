/**
 * Nanobot WebUI - Main Application
 * Initializes all modules and handles app lifecycle
 */

const App = {
    // State
    statusPollingInterval: null,
    STATUS_POLL_INTERVAL: 2000, // ms
    
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
     * Switch between chat and library tabs
     */
    switchTab(tab) {
        // Update tab buttons
        const tabChat = document.getElementById('tab-chat');
        const tabLibrary = document.getElementById('tab-library');
        const contentChat = document.getElementById('content-chat');
        const contentLibrary = document.getElementById('content-library');
        
        if (tab === 'chat') {
            tabChat.className = 'tab-active px-6 py-3 rounded-t-lg font-medium text-sm transition-colors border border-b-0';
            tabLibrary.className = 'tab-inactive px-6 py-3 rounded-t-lg font-medium text-sm transition-colors border border-b-0';
            contentChat.classList.remove('hidden');
            contentLibrary.classList.add('hidden');
            
            // Load document list
            UI.loadDocuments();
        } else if (tab === 'library') {
            tabLibrary.className = 'tab-active px-6 py-3 rounded-t-lg font-medium text-sm transition-colors border border-b-0';
            tabChat.className = 'tab-inactive px-6 py-3 rounded-t-lg font-medium text-sm transition-colors border border-b-0';
            contentLibrary.classList.remove('hidden');
            contentChat.classList.add('hidden');
            
            // Load library documents
            Library.loadDocuments();
        }
        
        // Update current tab
        if (window.UI) {
            UI.currentTab = tab;
        }
    },
    
    /**
     * Start status polling for processing documents
     */
    startStatusPolling() {
        if (this.statusPollingInterval) return;
        
        this.statusPollingInterval = setInterval(async () => {
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
                } else {
                    this.stopStatusPolling();
                }
            } catch (error) {
                console.error('Status polling failed:', error);
            }
        }, this.STATUS_POLL_INTERVAL);
    },
    
    /**
     * Stop status polling
     */
    stopStatusPolling() {
        if (this.statusPollingInterval) {
            clearInterval(this.statusPollingInterval);
            this.statusPollingInterval = null;
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
