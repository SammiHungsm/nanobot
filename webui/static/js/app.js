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
        
        // Database functions
        window.Database = {
            loadStats: () => this.loadDatabaseStats(),
            loadChunks: () => this.loadDatabaseChunks()
        };
    },
    
    /**
     * Switch between chat, library, and database tabs
     */
    switchTab(tab) {
        const tabs = ['chat', 'library', 'database'];
        
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
                if (t === 'database') this.loadDatabaseStats();
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
     * Load database statistics
     */
    async loadDatabaseStats() {
        try {
            const response = await fetch('/api/database/stats');
            if (!response.ok) throw new Error('Failed to fetch stats');
            
            const stats = await response.json();
            
            document.getElementById('db-doc-count').textContent = stats.documents || 0;
            document.getElementById('db-chunk-count').textContent = stats.chunks || 0;
            document.getElementById('db-table-count').textContent = stats.tables || 0;
            document.getElementById('db-image-count').textContent = stats.images || 0;
            
            // Load recent chunks
            this.loadDatabaseChunks();
        } catch (error) {
            console.error('Failed to load database stats:', error);
            // Show error in UI
            document.getElementById('db-doc-count').textContent = 'Error';
            document.getElementById('db-chunk-count').textContent = 'Error';
            document.getElementById('db-table-count').textContent = 'Error';
            document.getElementById('db-image-count').textContent = 'Error';
        }
    },
    
    /**
     * Load recent document chunks from database
     */
    async loadDatabaseChunks() {
        try {
            const response = await fetch('/api/database/chunks?limit=50');
            if (!response.ok) throw new Error('Failed to fetch chunks');
            
            const chunks = await response.json();
            const tbody = document.getElementById('db-data-body');
            
            if (!chunks || chunks.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-slate-400">No chunks found</td></tr>';
                return;
            }
            
            tbody.innerHTML = chunks.map(chunk => `
                <tr class="border-b border-slate-200 hover:bg-slate-50">
                    <td class="py-2 px-3 font-mono text-xs">${chunk.doc_id || 'N/A'}</td>
                    <td class="py-2 px-3">
                        <span class="px-2 py-1 rounded text-xs font-medium ${
                            chunk.chunk_type === 'table' ? 'bg-purple-100 text-purple-700' :
                            chunk.chunk_type === 'image' ? 'bg-orange-100 text-orange-700' :
                            'bg-blue-100 text-blue-700'
                        }">${chunk.chunk_type || 'text'}</span>
                    </td>
                    <td class="py-2 px-3 text-slate-600">${chunk.page_num || '-'}</td>
                    <td class="py-2 px-3 text-slate-700 max-w-md truncate" title="${chunk.content || ''}">
                        ${(chunk.content || chunk.metadata || '').toString().substring(0, 100)}${(chunk.content || '').length > 100 ? '...' : ''}
                    </td>
                </tr>
            `).join('');
        } catch (error) {
            console.error('Failed to load database chunks:', error);
            document.getElementById('db-data-body').innerHTML = '<tr><td colspan="4" class="text-center py-4 text-red-400">Error loading data</td></tr>';
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
