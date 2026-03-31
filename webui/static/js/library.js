/**
 * Nanobot WebUI - Library Module
 * Handles PDF library grid, details panel, file management, and processing logs
 */

const Library = {
    // State
    documents: [],
    selectedDocument: null,
    currentJsonOutput: null,
    selectedDocs: new Set(), // For batch operations
    currentPage: 1,
    pageSize: 12,
    currentFilter: 'all',
    currentSort: 'date_desc',
    searchTerm: '',
    
    // DOM elements
    elements: {},
    
    // Processing logs storage
    processingLogs: [],
    
    // Upload state
    uploadXHR: null,
    
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
        this.elements.pagination = document.getElementById('library-pagination');
        this.elements.countLabel = document.getElementById('library-count');
        this.elements.batchDeleteBtn = document.getElementById('batch-delete-btn');
        this.elements.batchDownloadBtn = document.getElementById('batch-download-btn');
        
        // Bind event listeners
        this.elements.fileUpload.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);
            await this.handleFileUpload(files);
            e.target.value = '';
        });
        
        // Start polling the server logs every 2 seconds
        setInterval(() => this.loadProcessingLogs(), 2000);
        
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
        if (this.processingLogs.length > 100) {
            this.processingLogs.shift();
        }
        
        this.renderProcessLog();
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
                this.filterLibrary();
                
                await this.loadProcessingLogs();
                
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
                const existingIds = new Set(this.processingLogs.map(l => l.id));
                for (const log of data.logs) {
                    if (!existingIds.has(log.id)) {
                        this.processingLogs.push(log);
                    }
                }
                this.renderProcessLog();
            }
        } catch (error) {
            console.error('Failed to load processing logs:', error);
        }
    },
    
    /**
     * Handle file upload with size check and progress
     */
    async handleFileUpload(files) {
        if (!files || files.length === 0) return;
        
        const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
        
        // Check file sizes upfront
        const oversized = files.filter(f => f.size > MAX_FILE_SIZE);
        if (oversized.length > 0) {
            const names = oversized.map(f => `${f.name} (${(f.size / 1024 / 1024).toFixed(1)}MB)`).join('\n');
            alert(`File(s) exceed 50MB limit:\n\n${names}\n\nPlease upload smaller files.`);
            return;
        }
        
        // Check for duplicates
        const duplicates = files.filter(f => this.documents.some(d => d.name === f.name));
        let replaceDocs = false;
        let finalFiles = files;
        
        if (duplicates.length > 0) {
            const names = duplicates.map(f => f.name).join(', ');
            const userChoice = confirm(`File(s) already exist: \n\n${names}\n\nClick "OK" to REPLACE them, or "Cancel" to SKIP duplicates.`);
            
            if (userChoice) {
                replaceDocs = true;
            } else {
                finalFiles = files.filter(f => !this.documents.some(d => d.name === f.name));
                if (finalFiles.length === 0) {
                    this.log('Upload cancelled - all files were duplicates.', 'warning');
                    return;
                }
            }
        }
        
        // Show upload progress modal
        this.showUploadProgress(finalFiles[0].name, 0, 'Starting upload...');
        
        try {
            const formData = new FormData();
            for (let i = 0; i < finalFiles.length; i++) {
                formData.append('files', finalFiles[i]);
            }
            
            // Use XMLHttpRequest for progress tracking
            await this.uploadWithProgress(formData, replaceDocs);
            
        } catch (error) {
            this.closeUploadModal();
            this.log(`Upload failed: ${error.message}`, 'error');
            alert(`Upload failed: ${error.message}`);
        }
    },
    
    /**
     * Upload with progress tracking using XMLHttpRequest
     */
    uploadWithProgress(formData, replaceDocs) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            this.uploadXHR = xhr;
            
            xhr.open('POST', `/api/upload?replace=${replaceDocs}`, true);
            
            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    this.updateUploadProgress(percent, `Uploading... ${percent}%`);
                }
            });
            
            xhr.addEventListener('load', () => {
                this.closeUploadModal();
                
                if (xhr.status >= 200 && xhr.status < 300) {
                    const result = JSON.parse(xhr.responseText);
                    setTimeout(() => this.loadDocuments(), 1000);
                    
                    if (window.UI) {
                        UI.appendMessage('bot', `✅ Uploaded successfully! Processing has started.`);
                    }
                    resolve(result);
                } else {
                    try {
                        const errorData = JSON.parse(xhr.responseText);
                        reject(new Error(errorData.detail || 'Upload failed'));
                    } catch (e) {
                        reject(new Error('Upload failed'));
                    }
                }
            });
            
            xhr.addEventListener('error', () => {
                this.closeUploadModal();
                reject(new Error('Network error during upload'));
            });
            
            this.updateUploadProgress(10, 'Preparing files...');
            xhr.send(formData);
        });
    },
    
    /**
     * Show upload progress modal
     */
    showUploadProgress(fileName, percent, status) {
        const modal = document.getElementById('upload-progress-modal');
        if (!modal) return;
        
        modal.classList.remove('hidden');
        document.getElementById('upload-file-name').textContent = fileName;
        this.updateUploadProgress(percent, status);
    },
    
    /**
     * Update upload progress
     */
    updateUploadProgress(percent, status) {
        const progressBar = document.getElementById('upload-progress-bar');
        const percentLabel = document.getElementById('upload-percent');
        const statusLabel = document.getElementById('upload-status');
        
        if (progressBar) progressBar.style.width = `${percent}%`;
        if (percentLabel) percentLabel.textContent = `${percent}%`;
        if (statusLabel) statusLabel.textContent = status;
    },
    
    /**
     * Close upload modal
     */
    closeUploadModal() {
        const modal = document.getElementById('upload-progress-modal');
        if (modal) modal.classList.add('hidden');
        this.uploadXHR = null;
    },
    
    /**
     * Filter and sort library
     */
    filterLibrary() {
        const searchInput = document.getElementById('library-search');
        const filterSelect = document.getElementById('library-filter-status');
        const sortSelect = document.getElementById('library-sort');
        
        if (searchInput) this.searchTerm = searchInput.value.toLowerCase();
        if (filterSelect) this.currentFilter = filterSelect.value;
        if (sortSelect) this.currentSort = sortSelect.value;
        
        // Filter
        let filtered = this.documents.filter(doc => {
            // Search filter
            const matchesSearch = doc.name.toLowerCase().includes(this.searchTerm) ||
                                 (doc.uploader && doc.uploader.toLowerCase().includes(this.searchTerm));
            
            // Status filter
            let matchesStatus = true;
            if (this.currentFilter !== 'all') {
                if (this.currentFilter === 'completed') {
                    matchesStatus = doc.status === 'completed' || doc.status === 'Ready';
                } else if (this.currentFilter === 'failed') {
                    matchesStatus = doc.status === 'Failed' || doc.status === 'failed';
                } else {
                    matchesStatus = doc.status.toLowerCase() === this.currentFilter.toLowerCase();
                }
            }
            
            return matchesSearch && matchesStatus;
        });
        
        // Sort
        filtered.sort((a, b) => {
            switch (this.currentSort) {
                case 'date_desc':
                    return new Date(b.date) - new Date(a.date);
                case 'date_asc':
                    return new Date(a.date) - new Date(b.date);
                case 'size_desc':
                    return parseFloat(b.size) - parseFloat(a.size);
                case 'size_asc':
                    return parseFloat(a.size) - parseFloat(b.size);
                case 'name_asc':
                    return a.name.localeCompare(b.name);
                default:
                    return 0;
            }
        });
        
        // Update count
        if (this.elements.countLabel) {
            this.elements.countLabel.textContent = `${filtered.length} documents`;
        }
        
        // Update pagination
        this.totalPages = Math.ceil(filtered.length / this.pageSize);
        if (this.currentPage > this.totalPages && this.totalPages > 0) {
            this.currentPage = this.totalPages;
        }
        
        // Show/hide pagination
        if (this.elements.pagination) {
            if (this.totalPages > 1) {
                this.elements.pagination.classList.remove('hidden');
                document.getElementById('pagination-info').textContent = 
                    `Page ${this.currentPage} of ${this.totalPages}`;
            } else {
                this.elements.pagination.classList.add('hidden');
            }
        }
        
        // Render current page
        const start = (this.currentPage - 1) * this.pageSize;
        const end = start + this.pageSize;
        const pageItems = filtered.slice(start, end);
        
        this.renderGrid(pageItems);
    },
    
    /**
     * Pagination navigation
     */
    prevPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.filterLibrary();
        }
    },
    
    nextPage() {
        if (this.currentPage < this.totalPages) {
            this.currentPage++;
            this.filterLibrary();
        }
    },
    
    /**
     * Render library grid
     */
    renderGrid(docsToRender = null) {
        if (!this.elements.grid) return;
        
        this.elements.grid.innerHTML = '';
        
        const docs = docsToRender || this.documents;
        
        if (docs.length === 0) {
            this.elements.emptyState.classList.remove('hidden');
            this.elements.emptyState.classList.add('flex');
        } else {
            this.elements.emptyState.classList.add('hidden');
            this.elements.emptyState.classList.remove('flex');
            
            docs.forEach(doc => {
                const card = document.createElement('div');
                const isProcessing = ['queued', 'processing'].includes(doc.status);
                const isFailed = doc.status === 'Failed' || doc.status === 'failed';
                const isCompleted = doc.status === 'completed' || doc.status === 'Ready';
                const isSelected = this.selectedDocs.has(doc.id);
                
                card.className = `pdf-card bg-white rounded-xl border ${isFailed ? 'border-red-200' : 'border-slate-200'} p-4 cursor-pointer ${isCompleted ? 'hover:border-blue-300' : ''} ${isSelected ? 'ring-2 ring-blue-500' : ''}`;
                card.ondblclick = () => this.previewPDF(doc);
                card.onclick = (e) => {
                    if (!e.target.closest('.checkbox-container')) {
                        this.selectDocument(doc);
                    }
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
                    <div class="checkbox-container absolute top-3 left-3">
                        <input type="checkbox" ${isSelected ? 'checked' : ''} 
                               onchange="Library.toggleDocSelection('${doc.id}', this.checked)"
                               onclick="event.stopPropagation()"
                               class="rounded border-slate-300 text-blue-600 focus:ring-blue-500">
                    </div>
                    <div class="flex items-start justify-between mb-3">
                        <div class="bg-red-100 text-red-600 p-3 rounded-lg ml-8">
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
        
        this.updateBatchButtons();
    },
    
    /**
     * Toggle document selection
     */
    toggleDocSelection(docId, isSelected) {
        if (isSelected) {
            this.selectedDocs.add(docId);
        } else {
            this.selectedDocs.delete(docId);
        }
        this.updateBatchButtons();
    },
    
    /**
     * Toggle select all
     */
    toggleSelectAll(checkbox) {
        const docsToRender = this.getFilteredDocs();
        if (checkbox.checked) {
            docsToRender.forEach(doc => this.selectedDocs.add(doc.id));
        } else {
            docsToRender.forEach(doc => this.selectedDocs.delete(doc.id));
        }
        this.renderGrid();
    },
    
    /**
     * Get filtered documents
     */
    getFilteredDocs() {
        let filtered = this.documents.filter(doc => {
            const matchesSearch = doc.name.toLowerCase().includes(this.searchTerm) ||
                                 (doc.uploader && doc.uploader.toLowerCase().includes(this.searchTerm));
            
            let matchesStatus = true;
            if (this.currentFilter !== 'all') {
                if (this.currentFilter === 'completed') {
                    matchesStatus = doc.status === 'completed' || doc.status === 'Ready';
                } else if (this.currentFilter === 'failed') {
                    matchesStatus = doc.status === 'Failed' || doc.status === 'failed';
                } else {
                    matchesStatus = doc.status.toLowerCase() === this.currentFilter.toLowerCase();
                }
            }
            
            return matchesSearch && matchesStatus;
        });
        
        filtered.sort((a, b) => {
            switch (this.currentSort) {
                case 'date_desc': return new Date(b.date) - new Date(a.date);
                case 'date_asc': return new Date(a.date) - new Date(b.date);
                case 'size_desc': return parseFloat(b.size) - parseFloat(a.size);
                case 'size_asc': return parseFloat(a.size) - parseFloat(b.size);
                case 'name_asc': return a.name.localeCompare(b.name);
                default: return 0;
            }
        });
        
        return filtered;
    },
    
    /**
     * Update batch action buttons
     */
    updateBatchButtons() {
        const count = this.selectedDocs.size;
        
        if (this.elements.batchDeleteBtn) {
            if (count > 0) {
                this.elements.batchDeleteBtn.classList.remove('hidden');
                document.getElementById('batch-delete-count').textContent = count;
            } else {
                this.elements.batchDeleteBtn.classList.add('hidden');
            }
        }
        
        if (this.elements.batchDownloadBtn) {
            if (count > 0) {
                this.elements.batchDownloadBtn.classList.remove('hidden');
                document.getElementById('batch-download-count').textContent = count;
            } else {
                this.elements.batchDownloadBtn.classList.add('hidden');
            }
        }
    },
    
    /**
     * Batch delete selected documents
     */
    async batchDeleteSelected() {
        if (this.selectedDocs.size === 0) return;
        
        const count = this.selectedDocs.size;
        if (!confirm(`Are you sure you want to delete ${count} document(s)?\n\nThis action cannot be undone.`)) {
            return;
        }
        
        this.log(`Deleting ${count} document(s)...`, 'warning');
        
        try {
            const result = await API.batchDeleteDocuments(Array.from(this.selectedDocs));
            
            // Remove from local cache
            this.documents = this.documents.filter(d => !this.selectedDocs.has(d.id));
            this.selectedDocs.clear();
            
            this.closeDetailsPanel();
            this.filterLibrary();
            
            this.log(`✅ Deleted ${result.deleted_count} document(s)`, 'success');
            
            if (window.UI) {
                UI.appendMessage('bot', `🗑️ Deleted **${result.deleted_count}** document(s)`);
            }
            
            if (result.failed_count > 0) {
                this.log(`⚠️ Failed to delete ${result.failed_count} document(s)`, 'warning');
            }
        } catch (error) {
            this.log(`Failed to batch delete: ${error.message}`, 'error');
            alert(`Failed to delete: ${error.message}`);
        }
    },
    
    /**
     * Batch download selected documents
     */
    batchDownloadSelected() {
        if (this.selectedDocs.size === 0) return;
        
        this.log(`Downloading ${this.selectedDocs.size} document(s)...`, 'info');
        window.location.href = API.getBatchDownloadUrl(Array.from(this.selectedDocs));
        this.selectedDocs.clear();
        this.renderGrid();
    },
    
    /**
     * Retry failed document
     */
    async retryDocument() {
        if (!this.selectedDocument) return;
        
        const docName = this.selectedDocument.name;
        const docId = this.selectedDocument.id;
        
        this.log(`Retrying: ${docName}...`, 'warning');
        
        try {
            await API.retryDocument(docId);
            
            // Update local state
            const doc = this.documents.find(d => d.id === docId);
            if (doc) {
                doc.status = 'queued';
                doc.progress = 0;
                doc.error_message = null;
            }
            
            this.closeDetailsPanel();
            this.filterLibrary();
            
            this.log(`✅ Queued for retry: ${docName}`, 'success');
            
            if (window.App) {
                App.startStatusPolling();
            }
            
            if (window.UI) {
                UI.appendMessage('bot', `🔄 Retrying: **${docName}**`);
            }
        } catch (error) {
            this.log(`Failed to retry: ${error.message}`, 'error');
            alert(`Failed to retry: ${error.message}`);
        }
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
        
        logContainer.scrollTop = logContainer.scrollHeight;
    },
    
    /**
     * Select document and show details panel
     */
    async selectDocument(doc) {
        this.selectedDocument = doc;
        this.log(`Selected document: ${doc.name}`);
        
        this.elements.detailsPanel.classList.remove('hidden');
        
        document.getElementById('detail-name').textContent = doc.name;
        document.getElementById('detail-size').textContent = doc.size;
        document.getElementById('detail-date').textContent = doc.date;
        document.getElementById('detail-uploader').textContent = doc.uploader;
        
        const statusEl = document.getElementById('detail-status');
        const progressContainer = document.getElementById('detail-progress-container');
        const retryButton = document.getElementById('retry-button-container');
        
        // Show/hide retry button for failed documents
        const isFailed = doc.status === 'Failed' || doc.status === 'failed';
        if (retryButton) {
            retryButton.classList.toggle('hidden', !isFailed);
        }
        
        if (['queued', 'processing'].includes(doc.status)) {
            progressContainer.classList.remove('hidden');
            document.getElementById('detail-progress-bar').style.width = `${doc.progress}%`;
            document.getElementById('detail-progress-text').textContent = `${Math.round(doc.progress)}%`;
            statusEl.textContent = this.capitalizeFirst(doc.status);
            statusEl.className = 'text-xs text-blue-600 font-medium';
        } else if (isFailed) {
            progressContainer.classList.add('hidden');
            statusEl.textContent = 'Failed';
            statusEl.className = 'text-xs text-red-600 font-medium';
        } else {
            progressContainer.classList.add('hidden');
            statusEl.textContent = 'Ready';
            statusEl.className = 'text-xs text-green-600 font-medium';
            
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
                if (['queued', 'processing'].includes(details.status)) {
                    document.getElementById('detail-progress-bar').style.width = `${details.progress}%`;
                    document.getElementById('detail-progress-text').textContent = `${Math.round(details.progress)}%`;
                }
                
                if (details.page_count) {
                    document.getElementById('detail-pages').textContent = details.page_count;
                }
            }
            
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
     * Preview PDF in modal
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
        
        const previewUrl = API.getPDFPreviewUrl(targetDoc.id);
        frame.src = previewUrl;
        
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
        frame.src = '';
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
            
            const previewContainer = document.getElementById('processed-output-preview');
            const previewContent = document.getElementById('processed-output-content');
            previewContent.innerHTML = this.syntaxHighlight(jsonData);
            previewContainer.classList.remove('hidden');
            
            this.log('Processed output loaded successfully', 'success');
        } catch (error) {
            this.log(`Failed to load processed output: ${error.message}`, 'error');
            alert(`Failed to load processed output.\n\nDocument status: ${this.selectedDocument.status}\n\nError: ${error.message}`);
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
