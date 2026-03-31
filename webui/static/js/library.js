/**
 * Nanobot WebUI - Library Module
 * Handles PDF library grid, details panel, file management, and processing logs
 */

const Library = {
    // State
    documents: [],
    selectedDocument: null,
    currentJsonOutput: null,
    
    // DOM elements
    elements: {
        grid: null,
        emptyState: null,
        detailsPanel: null,
        searchInput: null,
        fileUpload: null,
        processLog: null
    },
    
    // Processing logs storage
    processingLogs: [],
    
    /**
     * Initialize library module
     */
    init() {
        // Cache DOM elements
        this.elements.grid = document.getElementById('library-grid');
        this.elements.emptyState = document.getElementById('library-empty');
        this.elements.detailsPanel = document.getElementById('details-panel');
        this.elements.searchInput = document.getElementById('library-search');
        this.elements.fileUpload = document.getElementById('library-file-upload');
        this.elements.processLog = document.getElementById('process-log-container');
        
        // Bind event listeners
        this.elements.fileUpload.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);
            await this.handleFileUpload(files);
            e.target.value = '';
        });
        
        // Log processing events
        this.log('Library module initialized');
    },
    
    /**
     * Add processing log entry
     */
    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
        const logEntry = {
            timestamp,
            message,
            type,
            id: `log_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`
        };
        
        this.processingLogs.push(logEntry);
        
        // Keep only last 100 logs
        if (this.processingLogs.length > 100) {
            this.processingLogs.shift();
        }
        
        // Update log display if visible
        this.renderProcessLog();
        
        // Also log to console
        console.log(`[${timestamp}] [${type.toUpperCase()}] ${message}`);
    },
    
    /**
     * Render processing log
     */
    renderProcessLog() {
        if (!this.elements.processLog) return;
        
        const logContainer = this.elements.processLog;
        logContainer.innerHTML = '';
        
        if (this.processingLogs.length === 0) {
            logContainer.innerHTML = '<p class="text-slate-500 text-sm text-center py-4">No processing logs yet</p>';
            return;
        }
        
        // Show last 20 logs
        const recentLogs = this.processingLogs.slice(-20).reverse();
        
        recentLogs.forEach(log => {
            const logDiv = document.createElement('div');
            logDiv.className = 'text-xs font-mono py-1 border-b border-slate-700/50';
            
            const colorClass = log.type === 'error' ? 'text-red-400' : 
                              log.type === 'success' ? 'text-green-400' : 
                              log.type === 'warning' ? 'text-yellow-400' : 'text-slate-300';
            
            logDiv.innerHTML = `
                <span class="text-slate-500 mr-2">[${log.timestamp}]</span>
                <span class="${colorClass}">${log.message}</span>
            `;
            logContainer.appendChild(logDiv);
        });
        
        // Auto-scroll to bottom
        logContainer.scrollTop = logContainer.scrollHeight;
    },
    
    /**
     * Load library documents
     */
    async loadDocuments() {
        try {
            this.log('Loading documents...');
            const data = await API.getDocuments();
            if (data.success && data.documents) {
                // Deduplicate by path
                const seenPaths = new Set();
                const uniqueDocs = [];
                
                for (const doc of data.documents) {
                    if (!seenPaths.has(doc.path)) {
                        seenPaths.add(doc.path);
                        uniqueDocs.push({
                            ...doc,
                            uploader: doc.uploader || 'System',
                            date: this.formatDate(doc.date * 1000),
                            status: doc.status || 'Ready',
                            progress: doc.progress || 100
                        });
                    }
                }
                
                this.documents = uniqueDocs;
                this.log(`Loaded ${this.documents.length} documents`, 'success');
                this.renderGrid();
                
                // Load processing logs
                await this.loadProcessingLogs();
                
                // Check if polling is needed
                const isProcessing = this.documents.some(d => ['queued', 'processing'].includes(d.status));
                if (isProcessing && window.App) {
                    this.log('Starting status polling for processing documents');
                    App.startStatusPolling();
                }
            }
        } catch (error) {
            this.log(`Failed to load documents: ${error.message}`, 'error');
            console.error('Failed to load library documents:', error);
        }
    },
    
    /**
     * Load processing logs from server
     */
    async loadProcessingLogs() {
        try {
            const data = await API.getProcessingLogs();
            if (data.success && data.logs) {
                // Merge with local logs (avoid duplicates)
                const existingIds = new Set(this.processingLogs.map(l => l.id));
                for (const log of data.logs) {
                    if (!existingIds.has(log.id)) {
                        this.processingLogs.push(log);
                    }
                }
                this.renderProcessLog();
            }
        } catch (error) {
            // Silently fail - logs are not critical
            console.error('Failed to load processing logs:', error);
        }
    },
    
    /**
     * Handle file upload in library (supports multiple files)
     */
    async handleFileUpload(files) {
        if (!files || files.length === 0) return;
        
        this.log(`Starting upload of ${files.length} file(s)`);
        
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
            this.log(`Preparing file: ${files[i].name}`);
        }
        
        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Upload failed');
            }
            
            const result = await response.json();
            this.log(`Upload response received: ${result.message}`);
            
            // Process each uploaded file
            let uploadedCount = 0;
            let duplicateCount = 0;
            
            result.files.forEach(fileData => {
                if (fileData.is_duplicate) {
                    duplicateCount++;
                    this.log(`Skipped duplicate: ${fileData.name}`, 'warning');
                    if (window.UI) {
                        UI.appendMessage('bot', `⚠️ **${fileData.name}** is already in the library (Status: ${fileData.status})`);
                    }
                } else {
                    const now = new Date();
                    const timeStr = UI.formatDate(now.getTime());
                    
                    const newDoc = {
                        id: fileData.id,
                        name: fileData.name,
                        path: fileData.path,
                        size: fileData.size,
                        date: timeStr,
                        uploader: Auth.getUser(),
                        status: fileData.status,
                        progress: fileData.progress || 0
                    };
                    
                    // Check for duplicates before adding
                    const existingIndex = this.documents.findIndex(d => d.id === fileData.id || d.name === fileData.name);
                    if (existingIndex === -1) {
                        this.documents.unshift(newDoc);
                        uploadedCount++;
                        this.log(`Added to library: ${fileData.name} (Status: ${fileData.status})`, 'success');
                    } else {
                        this.log(`File already in list: ${fileData.name}`, 'warning');
                    }
                    
                    if (window.App) {
                        App.startStatusPolling();
                    }
                }
            });
            
            // Refresh the grid
            this.renderGrid();
            
            // Show success message
            if (window.UI && uploadedCount > 0) {
                UI.appendMessage('bot', `✅ Uploaded **${uploadedCount}** file(s) successfully!${duplicateCount > 0 ? ` (Skipped ${duplicateCount} duplicate(s))` : ''}\n\nProcessing will start automatically.`);
                this.log(`Upload complete: ${uploadedCount} files uploaded, ${duplicateCount} duplicates skipped`, 'success');
            }
            
        } catch (error) {
            this.log(`Upload failed: ${error.message}`, 'error');
            alert(`Upload failed: ${error.message}`);
        }
    },
    
    /**
     * Render library grid
     */
    renderGrid(searchTerm = '') {
        if (!this.elements.grid) return;
        
        this.elements.grid.innerHTML = '';
        
        const filtered = this.documents.filter(doc => 
            doc.name.toLowerCase().includes(searchTerm) ||
            (doc.uploader && doc.uploader.toLowerCase().includes(searchTerm))
        );
        
        if (filtered.length === 0) {
            this.elements.emptyState.classList.remove('hidden');
            this.elements.emptyState.classList.add('flex');
        } else {
            this.elements.emptyState.classList.add('hidden');
            this.elements.emptyState.classList.remove('flex');
            
            filtered.forEach(doc => {
                const card = document.createElement('div');
                const isProcessing = ['queued', 'processing'].includes(doc.status);
                const isFailed = doc.status === 'Failed' || doc.status === 'failed';
                const isCompleted = doc.status === 'completed' || doc.status === 'Ready';
                
                card.className = `pdf-card bg-white rounded-xl border ${isFailed ? 'border-red-200' : 'border-slate-200'} p-4 cursor-pointer ${isCompleted ? 'hover:border-blue-300' : ''}`;
                card.ondblclick = () => this.previewPDF(doc);
                card.onclick = (e) => {
                    e.stopPropagation();
                    this.selectDocument(doc);
                };
                
                let statusBadge = '';
                if (isProcessing) {
                    statusBadge = `<span class="text-blue-600 text-xs font-medium flex items-center"><i class="fas fa-circle-notch fa-spin mr-1.5"></i> ${this.capitalizeFirst(doc.status)}</span>`;
                } else if (isFailed) {
                    statusBadge = `<span class="text-red-600 text-xs font-medium flex items-center"><i class="fas fa-exclamation-circle mr-1.5"></i> Failed</span>`;
                } else {
                    statusBadge = `<span class="text-green-600 text-xs font-medium flex items-center"><i class="fas fa-check-circle mr-1.5"></i> Ready</span>`;
                }
                
                card.innerHTML = `
                    <div class="flex items-start justify-between mb-3">
                        <div class="bg-red-100 text-red-600 p-3 rounded-lg">
                            <i class="fas fa-file-pdf text-xl"></i>
                        </div>
                        ${statusBadge}
                    </div>
                    <h3 class="font-medium text-slate-800 truncate mb-1" title="${doc.name}">${doc.name}</h3>
                    <div class="text-xs text-slate-500 space-y-1">
                        <p><i class="fas fa-hdd mr-1.5"></i>${doc.size}</p>
                        <p><i class="fas fa-calendar mr-1.5"></i>${doc.date}</p>
                        <p><i class="fas fa-user mr-1.5"></i>${doc.uploader}</p>
                    </div>
                    ${isProcessing ? `
                    <div class="mt-3">
                        <div class="flex justify-between text-[10px] text-slate-500 mb-1">
                            <span>Processing</span>
                            <span>${Math.round(doc.progress)}%</span>
                        </div>
                        <div class="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                            <div class="h-full bg-blue-500 transition-all duration-300" style="width: ${doc.progress}%"></div>
                        </div>
                    </div>
                    ` : ''}
                `;
                this.elements.grid.appendChild(card);
            });
        }
    },
    
    /**
     * Filter library by search term
     */
    filterLibrary() {
        const searchTerm = this.elements.searchInput.value.toLowerCase();
        this.renderGrid(searchTerm);
    },
    
    /**
     * Select document and show details panel
     */
    async selectDocument(doc) {
        this.selectedDocument = doc;
        this.log(`Selected document: ${doc.name}`);
        
        // Show details panel
        this.elements.detailsPanel.classList.remove('hidden');
        
        // Populate details
        document.getElementById('detail-name').textContent = doc.name;
        document.getElementById('detail-size').textContent = doc.size;
        document.getElementById('detail-date').textContent = doc.date;
        document.getElementById('detail-uploader').textContent = doc.uploader;
        
        // Update status
        const statusEl = document.getElementById('detail-status');
        const progressContainer = document.getElementById('detail-progress-container');
        
        if (['queued', 'processing'].includes(doc.status)) {
            progressContainer.classList.remove('hidden');
            document.getElementById('detail-progress-bar').style.width = `${doc.progress}%`;
            document.getElementById('detail-progress-text').textContent = `${Math.round(doc.progress)}%`;
            statusEl.textContent = this.capitalizeFirst(doc.status);
            statusEl.className = 'text-xs text-blue-600 font-medium';
        } else if (doc.status === 'Failed' || doc.status === 'failed') {
            progressContainer.classList.add('hidden');
            statusEl.textContent = 'Failed';
            statusEl.className = 'text-xs text-red-600 font-medium';
        } else {
            progressContainer.classList.add('hidden');
            statusEl.textContent = 'Ready';
            statusEl.className = 'text-xs text-green-600 font-medium';
            
            // Load full details for completed documents
            await this.loadDocumentDetails(doc.id);
        }
    },
    
    /**
     * Load document details
     */
    async loadDocumentDetails(docId) {
        try {
            const details = await API.getDocumentStatus(docId);
            
            if (this.selectedDocument && this.selectedDocument.id === docId) {
                // Update progress
                if (['queued', 'processing'].includes(details.status)) {
                    document.getElementById('detail-progress-bar').style.width = `${details.progress}%`;
                    document.getElementById('detail-progress-text').textContent = `${Math.round(details.progress)}%`;
                }
                
                // Update page count if available
                if (details.page_count) {
                    document.getElementById('detail-pages').textContent = details.page_count;
                }
            }
            
            // Update in library
            const idx = this.documents.findIndex(d => d.id === docId);
            if (idx !== -1) {
                this.documents[idx] = { ...this.documents[idx], ...details };
                this.renderGrid();
            }
        } catch (error) {
            this.log(`Failed to load document details: ${error.message}`, 'error');
            console.error('Failed to load document details:', error);
        }
    },
    
    /**
     * Close details panel
     */
    closeDetailsPanel() {
        this.elements.detailsPanel.classList.add('hidden');
        this.selectedDocument = null;
    },
    
    /**
     * Preview PDF in modal (not download)
     */
    previewPDF(doc = null) {
        const targetDoc = doc || this.selectedDocument;
        if (!targetDoc) {
            this.log('No document selected for preview', 'warning');
            return;
        }
        
        this.log(`Opening preview: ${targetDoc.name}`);
        
        const modal = document.getElementById('pdf-preview-modal');
        const frame = document.getElementById('pdf-preview-frame');
        const title = document.getElementById('preview-title');
        
        title.textContent = targetDoc.name;
        
        // Set iframe source to preview URL (should display in browser, not download)
        const previewUrl = API.getPDFPreviewUrl(targetDoc.id);
        frame.src = previewUrl;
        
        // Update "Open in new tab" link
        const openNewLink = document.getElementById('preview-open-new');
        if (openNewLink) {
            openNewLink.href = previewUrl;
        }
        
        modal.classList.remove('hidden');
        this.log('PDF preview modal opened');
    },
    
    /**
     * Close PDF preview modal
     */
    closePreviewModal() {
        const modal = document.getElementById('pdf-preview-modal');
        const frame = document.getElementById('pdf-preview-frame');
        frame.src = ''; // Clear to stop loading
        modal.classList.add('hidden');
        this.log('PDF preview modal closed');
    },
    
    /**
     * Download PDF
     */
    downloadPDF() {
        if (!this.selectedDocument) return;
        this.log(`Downloading PDF: ${this.selectedDocument.name}`);
        window.location.href = API.getPDFDownloadUrl(this.selectedDocument.id);
    },
    
    /**
     * View processed output
     */
    async viewProcessedOutput() {
        if (!this.selectedDocument) {
            this.log('No document selected for viewing output', 'warning');
            return;
        }
        
        this.log(`Loading processed output for: ${this.selectedDocument.name}`);
        
        try {
            const jsonData = await API.getProcessedOutput(this.selectedDocument.id);
            this.currentJsonOutput = jsonData;
            
            const content = document.getElementById('json-output-content');
            content.innerHTML = this.syntaxHighlight(jsonData);
            
            const modal = document.getElementById('json-output-modal');
            modal.classList.remove('hidden');
            
            // Also show in details panel preview
            const previewContainer = document.getElementById('processed-output-preview');
            const previewContent = document.getElementById('processed-output-content');
            previewContent.innerHTML = this.syntaxHighlight(jsonData);
            previewContainer.classList.remove('hidden');
            
            this.log('Processed output loaded successfully', 'success');
        } catch (error) {
            this.log(`Failed to load processed output: ${error.message}`, 'error');
            alert(`Failed to load processed output.\n\nDocument status: ${this.selectedDocument.status}\n\nThe document may still be processing or the output file was not generated.\n\nError: ${error.message}`);
        }
    },
    
    /**
     * Close JSON modal
     */
    closeJsonModal() {
        document.getElementById('json-output-modal').classList.add('hidden');
        this.currentJsonOutput = null;
    },
    
    /**
     * Copy JSON output to clipboard
     */
    copyJsonOutput() {
        if (!this.currentJsonOutput) return;
        navigator.clipboard.writeText(JSON.stringify(this.currentJsonOutput, null, 2));
    },
    
    /**
     * Download processed output
     */
    downloadProcessedOutput() {
        if (!this.selectedDocument) return;
        window.location.href = API.getProcessedOutputDownloadUrl(this.selectedDocument.id);
    },
    
    /**
     * Syntax highlight JSON
     */
    syntaxHighlight(json) {
        if (typeof json !== 'string') {
            json = JSON.stringify(json, null, 2);
        }
        json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
            var cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-boolean';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return '<span class="' + cls + '">' + match + '</span>';
        });
    },
    
    /**
     * Format date to readable string
     */
    formatDate(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric', 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    },
    
    /**
     * Capitalize first letter
     */
    capitalizeFirst(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }
};

// Export for use in other modules
window.Library = Library;
