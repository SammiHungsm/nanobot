/**
 * Nanobot WebUI - API Communication
 * Handles all API calls to the backend
 */

// API Configuration
const API = {
    BASE_URL: window.location.origin,
    
    // Chat endpoints
    async chatStream(message, username, documentPath = null, sessionId = null) {
        const response = await fetch(`${this.BASE_URL}/api/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: message,
                username: username,
                document_path: documentPath,
                session_id: sessionId
            })
        });
        
        if (!response.ok) {
            const errorMsg = await response.text();
            throw new Error(errorMsg);
        }
        
        return response;
    },
    
    // Document management
    async getDocuments() {
        const response = await fetch(`${this.BASE_URL}/api/documents`);
        if (!response.ok) {
            throw new Error('Failed to load documents');
        }
        return await response.json();
    },
    
    // 🌟 支援單一檔案或檔案陣列，支援 v2.3 新架構
    async uploadFile(files, username, options = {}) {
        const formData = new FormData();
        
        // 處理多檔案上傳
        if (Array.isArray(files)) {
            files.forEach(f => formData.append('files', f));
        } else {
            formData.append('files', files);
        }
        
        formData.append('username', username);
        
        // 🌟 將新架構需要嘅參數加落 FormData
        if (options.replace !== undefined) formData.append('replace', options.replace);
        if (options.docType) formData.append('doc_type', options.docType);
        if (options.isIndexReport !== undefined) formData.append('is_index_report', options.isIndexReport);
        if (options.indexTheme) formData.append('index_theme', options.indexTheme);
        if (options.confirmedIndustry) formData.append('confirmed_doc_industry', options.confirmedIndustry);
        
        const response = await fetch(`${this.BASE_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Upload failed');
        }
        
        return await response.json();
    },
    
    async getDocumentStatus(docId) {
        const response = await fetch(`${this.BASE_URL}/api/status/${docId}`);
        if (!response.ok) {
            throw new Error('Failed to load document status');
        }
        return await response.json();
    },
    
    async deleteDocument(docId) {
        const response = await fetch(`${this.BASE_URL}/api/documents/${docId}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Delete failed');
        }
        return await response.json();
    },
    
    async retryDocument(docId) {
        const response = await fetch(`${this.BASE_URL}/api/documents/${docId}/retry`, {
            method: 'POST'
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Retry failed');
        }
        return await response.json();
    },
    
    async batchDeleteDocuments(docIds) {
        const response = await fetch(`${this.BASE_URL}/api/documents/batch-delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(docIds)
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Batch delete failed');
        }
        return await response.json();
    },
    
    getBatchDownloadUrl(docIds) {
        return `${this.BASE_URL}/api/documents/batch-download?doc_ids=${encodeURIComponent(docIds.join(','))}`;
    },

    async getQueueStatus() {
        const response = await fetch(`${this.BASE_URL}/api/queue/status`);
        if (!response.ok) {
            throw new Error('Failed to load queue status');
        }
        return await response.json();
    },
    
    // PDF operations
    getPDFPreviewUrl(docId) {
        return `${this.BASE_URL}/api/pdf/${docId}/preview`;
    },
    
    getPDFDownloadUrl(docId) {
        return `${this.BASE_URL}/api/pdf/${docId}/download`;
    },
    
    async getProcessedOutput(docId) {
        const response = await fetch(`${this.BASE_URL}/api/pdf/${docId}/output`);
        if (!response.ok) {
            throw new Error('Failed to load processed output');
        }
        return await response.json();
    },
    
    getProcessedOutputDownloadUrl(docId) {
        return `${this.BASE_URL}/api/pdf/${docId}/output/download`;
    },
    
    getAllRawOutputDownloadUrl(docId) {
        return `${this.BASE_URL}/api/pdf/${docId}/output/download-all`;
    },
    
    // Processing logs
    async getProcessingLogs() {
        const response = await fetch(`${this.BASE_URL}/api/logs`);
        if (!response.ok) {
            throw new Error('Failed to load processing logs');
        }
        return await response.json();
    },
    
    // Queue control
    async startQueue() {
        const response = await fetch(`${this.BASE_URL}/api/queue/start`, {
            method: 'POST'
        });
        return await response.json();
    },
    
    async stopQueue() {
        const response = await fetch(`${this.BASE_URL}/api/queue/stop`, {
            method: 'POST'
        });
        return await response.json();
    }
};

// Export for use in other modules
window.API = API;
