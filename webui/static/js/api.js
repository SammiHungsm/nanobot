/**
 * Nanobot WebUI - API Communication
 * Handles all API calls to the backend
 */

// API Configuration
const API = {
    BASE_URL: window.location.origin,
    
    // Chat endpoints
    async chatStream(message, username, documentPath = null) {
        const response = await fetch(`${this.BASE_URL}/api/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: message,
                username: username,
                document_path: documentPath
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
    
    async uploadFile(file, username) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('username', username);
        
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
