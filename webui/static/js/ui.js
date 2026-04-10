/**
 * Nanobot WebUI - UI Rendering Module
 * Handles all UI rendering and updates
 * 
 * 🌟 Version 2.0: Support for Agentic Dynamic Ingestion
 * - Added document type selection (annual_report vs index_report)
 * - Added index_theme and confirmed_doc_industry fields
 */

const UI = {
    // State
    documents: [],
    selectedDocument: null,
    currentTab: 'chat',
    chatSessionId: null, // 存儲聊天 Session ID
    
    // 🌟 上傳選項
    uploadOptions: {
        doc_type: 'annual_report',
        is_index_report: false,
        index_theme: '',
        confirmed_industry: ''
    },
    
    // DOM elements
    elements: {
        documentList: null,
        chatContainer: null,
        chatForm: null,
        chatInput: null,
        sendBtn: null,
        attachBtn: null,
        fileUpload: null
    },
    
    /**
     * Initialize UI module
     */
    init() {
        // Cache DOM elements
        this.elements.documentList = document.getElementById('document-list');
        this.elements.chatContainer = document.getElementById('chat-container');
        this.elements.chatForm = document.getElementById('chat-form');
        this.elements.chatInput = document.getElementById('chat-input');
        this.elements.sendBtn = document.getElementById('send-btn');
        this.elements.attachBtn = document.getElementById('attach-btn');
        this.elements.fileUpload = document.getElementById('file-upload');
        
        // Bind event listeners (with null checks)
        if (this.elements.chatForm) {
            this.elements.chatForm.addEventListener('submit', (e) => this.handleChatSubmit(e));
        }
        if (this.elements.attachBtn && this.elements.fileUpload) {
            this.elements.attachBtn.addEventListener('click', () => this.elements.fileUpload.click());
            this.elements.fileUpload.addEventListener('change', async (e) => {
                const files = Array.from(e.target.files);
                await this.handleMultipleFileUpload(files, true);
                e.target.value = '';
            });
        }
        
        // Auto-resize textarea
        if (this.elements.chatInput) {
            this.elements.chatInput.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 120) + 'px';
            });
            
            // Enter to send
            this.elements.chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (this.elements.chatForm) {
                        this.elements.chatForm.dispatchEvent(new Event('submit'));
                    }
                }
            });
        }
        
        console.log('[UI] ✅ UI module initialized');
    },
    
    /**
     * 🌟 顯示文檔類型選擇對話框
     * @returns {Promise<Object|null>} 選擇結果或 null (取消)
     */
    showDocTypeDialog() {
        return new Promise((resolve) => {
            // 創建對話框
            const dialog = document.createElement('div');
            dialog.id = 'doc-type-dialog';
            dialog.className = 'fixed inset-0 bg-black/50 z-50 flex items-center justify-center';
            dialog.innerHTML = `
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden animate-fade-in-up">
                    <div class="bg-gradient-to-r from-blue-600 to-indigo-600 p-4">
                        <h3 class="text-lg font-semibold text-white">
                            <i class="fas fa-file-upload mr-2"></i>選擇文檔類型
                        </h3>
                        <p class="text-blue-100 text-sm mt-1">請選擇您要上傳的文檔類型</p>
                    </div>
                    
                    <div class="p-5 space-y-4">
                        <!-- 文檔類型選擇 -->
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-2">文檔類型</label>
                            <div class="grid grid-cols-2 gap-2">
                                <button type="button" class="doc-type-btn active flex flex-col items-center p-4 border-2 border-blue-500 bg-blue-50 rounded-xl text-blue-700" data-type="annual_report">
                                    <i class="fas fa-file-invoice-dollar text-2xl mb-2"></i>
                                    <span class="font-medium">年報</span>
                                    <span class="text-xs text-slate-500">Annual Report</span>
                                </button>
                                <button type="button" class="doc-type-btn flex flex-col items-center p-4 border-2 border-slate-200 hover:border-blue-300 rounded-xl text-slate-600 hover:bg-blue-50" data-type="index_report">
                                    <i class="fas fa-chart-line text-2xl mb-2"></i>
                                    <span class="font-medium">指數報告</span>
                                    <span class="text-xs text-slate-500">Index Report</span>
                                </button>
                            </div>
                        </div>
                        
                        <!-- 指數報告選項 (默認隱藏) -->
                        <div id="index-options-container" class="hidden space-y-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
                            <div class="flex items-center text-sm text-amber-700 bg-amber-50 p-2 rounded-lg">
                                <i class="fas fa-info-circle mr-2"></i>
                                <span>指數報告會自動將所有成分股指派到指定的行業</span>
                            </div>
                            
                            <div>
                                <label class="block text-sm font-medium text-slate-700 mb-1">指數主題</label>
                                <input type="text" id="dialog-index-theme" placeholder="例如: Hang Seng Biotech Index" 
                                    class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm">
                            </div>
                            
                            <div>
                                <label class="block text-sm font-medium text-slate-700 mb-1">確認行業</label>
                                <input type="text" id="dialog-confirmed-industry" placeholder="例如: Biotech" 
                                    class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm">
                                <p class="text-xs text-slate-500 mt-1">所有成分股都會被指派這個行業 (規則 A)</p>
                            </div>
                        </div>
                        
                        <!-- 說明 -->
                        <div class="text-xs text-slate-500 bg-slate-50 p-3 rounded-lg">
                            <p id="doc-type-description">
                                <i class="fas fa-info-circle mr-1"></i>
                                年報：AI 會自動提取公司信息和行業
                            </p>
                        </div>
                    </div>
                    
                    <div class="flex border-t border-slate-200">
                        <button type="button" id="dialog-cancel" class="flex-1 py-3 text-slate-600 hover:bg-slate-50 font-medium transition-colors">
                            取消
                        </button>
                        <button type="button" id="dialog-confirm" class="flex-1 py-3 bg-blue-600 text-white hover:bg-blue-700 font-medium transition-colors">
                            確認上傳
                        </button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(dialog);
            
            // 選中的類型
            let selectedType = 'annual_report';
            
            // 類型按鈕點擊
            dialog.querySelectorAll('.doc-type-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    // 更新樣式
                    dialog.querySelectorAll('.doc-type-btn').forEach(b => {
                        b.classList.remove('active', 'border-blue-500', 'bg-blue-50', 'text-blue-700');
                        b.classList.add('border-slate-200', 'text-slate-600');
                    });
                    btn.classList.add('active', 'border-blue-500', 'bg-blue-50', 'text-blue-700');
                    btn.classList.remove('border-slate-200', 'text-slate-600');
                    
                    selectedType = btn.dataset.type;
                    console.log(`[DEBUG] 選擇文檔類型: ${selectedType}`);
                    
                    // 顯示/隱藏指數選項
                    const indexOptions = dialog.querySelector('#index-options-container');
                    const description = dialog.querySelector('#doc-type-description');
                    
                    if (selectedType === 'index_report') {
                        indexOptions.classList.remove('hidden');
                        description.innerHTML = '<i class="fas fa-info-circle mr-1"></i>指數報告：所有成分股會被指派到指定行業 (規則 A)';
                    } else {
                        indexOptions.classList.add('hidden');
                        description.innerHTML = '<i class="fas fa-info-circle mr-1"></i>年報：AI 會自動提取公司信息和行業 (規則 B)';
                    }
                });
            });
            
            // 取消按鈕
            dialog.querySelector('#dialog-cancel').addEventListener('click', () => {
                dialog.remove();
                resolve(null);
            });
            
            // 確認按鈕
            dialog.querySelector('#dialog-confirm').addEventListener('click', () => {
                const indexTheme = dialog.querySelector('#dialog-index-theme')?.value || '';
                const confirmedIndustry = dialog.querySelector('#dialog-confirmed-industry')?.value || '';
                
                const result = {
                    type: selectedType,
                    is_index_report: selectedType === 'index_report',
                    index_theme: indexTheme,
                    confirmed_industry: confirmedIndustry
                };
                
                console.log('[DEBUG] 確認上傳選項:', result);
                
                dialog.remove();
                resolve(result);
            });
            
            // 點擊背景關閉
            dialog.addEventListener('click', (e) => {
                if (e.target === dialog) {
                    dialog.remove();
                    resolve(null);
                }
            });
        });
    },
    
    /**
     * Clear all documents
     */
    clearDocuments() {
        this.documents = [];
        this.renderDocumentList();
    },
    
    /**
     * Load and render document list
     */
    async loadDocuments() {
        try {
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
                this.renderDocumentList();
                
                // Check if polling is needed
                const isProcessing = this.documents.some(d => ['queued', 'processing'].includes(d.status));
                if (isProcessing && window.App) {
                    App.startStatusPolling();
                }
            }
        } catch (error) {
            console.error('Failed to load documents:', error);
        }
    },
    
    /**
     * Render document list in sidebar
     */
    renderDocumentList() {
        if (!this.elements.documentList) return;
        
        this.elements.documentList.innerHTML = '';
        
        if (this.documents.length === 0) {
            this.elements.documentList.innerHTML = '<li class="text-center text-slate-500 text-sm py-4">No documents yet</li>';
            return;
        }
        
        this.documents.forEach(doc => {
            const li = document.createElement('li');
            const isProcessing = ['queued', 'processing'].includes(doc.status);
            const isFailed = doc.status === 'Failed' || doc.status === 'failed';
            const isCompleted = doc.status === 'completed' || doc.status === 'Ready';
            
            li.className = `group flex items-start p-3 rounded-xl transition-colors border border-transparent 
                ${isProcessing ? 'bg-slate-800/50' : ''}
                ${isFailed ? 'bg-red-900/20 opacity-80' : ''}
                ${isCompleted ? 'hover:bg-slate-800 cursor-pointer hover:border-slate-700/50' : ''}`;
            
            if (isCompleted) {
                li.onclick = () => this.tagDocument(doc.path);
            }
            
            // Progress bar for processing documents
            let progressHtml = '';
            if (isProcessing) {
                const progress = doc.progress || 0;
                progressHtml = `
                    <div class="mt-2">
                        <div class="flex justify-between text-[9px] text-slate-400 mb-1">
                            <span>${doc.status === 'processing' ? 'Processing...' : 'Queued'}</span>
                            <span>${Math.round(progress)}%</span>
                        </div>
                        <div class="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
                            <div class="h-full bg-blue-500 transition-all duration-300" style="width: ${progress}%"></div>
                        </div>
                    </div>
                `;
            }
            
            // Status badge
            let statusHtml = '';
            if (isProcessing) {
                statusHtml = `<span class="text-blue-400 font-medium flex items-center text-[10px] mt-1.5"><i class="fas fa-${doc.status === 'processing' ? 'cog fa-spin' : 'clock'} mr-1.5"></i> ${this.capitalizeFirst(doc.status)}</span>`;
            } else if (isFailed) {
                statusHtml = `<span class="text-red-400 font-medium flex items-center text-[10px] mt-1.5"><i class="fas fa-exclamation-circle mr-1.5"></i> Failed</span>`;
            } else {
                statusHtml = `<span class="text-emerald-500 flex items-center text-[10px] mt-1.5"><i class="fas fa-check-circle mr-1.5"></i> Ready</span>`;
            }
            
            // Uploader badge
            const uploaderBadge = (doc.uploader === Auth.getUser() || doc.uploader === 'You')
                ? `<span class="text-blue-300 font-medium">${doc.uploader}</span>`
                : `<span class="text-slate-500">${doc.uploader}</span>`;
            
            li.innerHTML = `
                <div class="mr-3 p-2.5 bg-slate-800 group-hover:bg-blue-600/20 group-hover:text-blue-400 rounded-lg text-slate-400 transition-colors mt-0.5">
                    <i class="fas ${isProcessing ? 'fa-cog text-blue-400' : isFailed ? 'fa-file-pdf text-red-400' : 'fa-file-pdf'}"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <h3 class="text-sm font-medium text-slate-200 truncate group-hover:text-white transition-colors" title="${doc.name}">${doc.name}</h3>
                    <p class="text-[10px] text-slate-400 mt-1 flex justify-between pr-2">
                        <span>By: ${uploaderBadge}</span>
                        <span class="text-slate-500">${doc.size}</span>
                    </p>
                    <p class="text-[10px] text-slate-500 mt-0.5">${doc.date}</p>
                    ${statusHtml}
                    ${progressHtml}
                </div>
                ${isCompleted ? `
                <div class="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-white self-center">
                    <i class="fas fa-plus-circle text-sm"></i>
                </div>
                ` : ''}
            `;
            
            this.elements.documentList.appendChild(li);
        });
    },
    
    /**
     * Tag document in chat input
     */
    tagDocument(filepath) {
        const chatInput = this.elements.chatInput;
        const tagText = `[Doc: ${filepath}] `;
        
        if (chatInput.value.length === 0 || chatInput.value.endsWith(' ')) {
            chatInput.value += tagText;
        } else {
            chatInput.value += ' ' + tagText;
        }
        
        chatInput.focus();
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    },
    
    /**
     * Show duplicate handling dialog
     */
    showDuplicateDialog(fileName, resolve) {
        const dialog = document.createElement('div');
        dialog.className = 'fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4';
        dialog.innerHTML = `
            <div class="bg-white rounded-xl shadow-2xl p-6 max-w-md w-full">
                <div class="text-center mb-6">
                    <div class="bg-yellow-100 w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4">
                        <i class="fas fa-exclamation-triangle text-yellow-600 text-xl"></i>
                    </div>
                    <h3 class="text-lg font-semibold text-slate-800 mb-2">File Already Exists</h3>
                    <p class="text-slate-600 text-sm">"<strong>${fileName}</strong>" is already in the library.</p>
                </div>
                <div class="space-y-3">
                    <button class="w-full bg-blue-600 text-white py-2.5 rounded-lg hover:bg-blue-700 transition font-medium" onclick="this.closest('.fixed').dataset.action='replace'">
                        <i class="fas fa-sync-alt mr-2"></i>Replace with new version
                    </button>
                    <button class="w-full bg-slate-200 text-slate-700 py-2.5 rounded-lg hover:bg-slate-300 transition font-medium" onclick="this.closest('.fixed').dataset.action='skip'">
                        <i class="fas fa-forward mr-2"></i>Skip this file
                    </button>
                    <button class="w-full bg-white border border-slate-300 text-slate-700 py-2.5 rounded-lg hover:bg-slate-50 transition font-medium" onclick="this.closest('.fixed').dataset.action='cancel'">
                        <i class="fas fa-times mr-2"></i>Cancel upload
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        
        const checkInterval = setInterval(() => {
            const action = dialog.dataset.action;
            if (action) {
                clearInterval(checkInterval);
                dialog.remove();
                resolve(action);
            }
        }, 200);
    },
    
    /**
     * Handle multiple file uploads
     * 🌟 支援指數報告和財務報告的選擇
     */
    async handleMultipleFileUpload(files, showChatNotification) {
        if (!files || files.length === 0) return;
        
        // 🌟 顯示文檔類型選擇對話框
        const docType = await this.showDocTypeDialog();
        if (!docType) {
            console.log('使用者取消上傳');
            return;
        }
        
        console.log(`[DEBUG] 選擇的文檔類型: ${docType.type}`);
        console.log(`[DEBUG] 是否為指數報告: ${docType.is_index_report}`);
        if (docType.is_index_report) {
            console.log(`[DEBUG] 指數主題: ${docType.index_theme}`);
            console.log(`[DEBUG] 確認行業: ${docType.confirmed_industry}`);
        }
        
        const filesToUpload = [];
        
        for (const file of files) {
            const existingDoc = this.documents.find(d => d.name === file.name);
            
            if (existingDoc) {
                // Show dialog for duplicate
                const action = await new Promise(resolve => this.showDuplicateDialog(file.name, resolve));
                
                if (action === 'cancel') {
                    continue;
                } else if (action === 'skip') {
                    if (showChatNotification) {
                        this.appendMessage('bot', `⚠️ Skipped **${file.name}** (already exists)`);
                    }
                    continue;
                } else if (action === 'replace') {
                    // Remove old document from list
                    const idx = this.documents.findIndex(d => d.id === existingDoc.id);
                    if (idx !== -1) {
                        this.documents.splice(idx, 1);
                    }
                    filesToUpload.push(file);
                }
            } else {
                filesToUpload.push(file);
            }
        }
        
        if (filesToUpload.length === 0) {
            this.renderDocumentList();
            return;
        }
        
        const formData = new FormData();
        for (const file of filesToUpload) {
            formData.append('files', file);
        }
        
        // 🌟 添加文檔類型參數
        formData.append('doc_type', docType.type);
        formData.append('is_index_report', docType.is_index_report);
        
        if (docType.is_index_report) {
            formData.append('index_theme', docType.index_theme || '');
            formData.append('confirmed_doc_industry', docType.confirmed_industry || '');
        }
        
        console.log('[DEBUG] 準備上傳文檔...');
        console.log('[DEBUG] formData:', Object.fromEntries(formData.entries()));
        
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
            
            // Process each uploaded file
            let uploadedCount = 0;
            let duplicateCount = 0;
            
            result.files.forEach(fileData => {
                if (fileData.is_duplicate) {
                    duplicateCount++;
                    if (showChatNotification) {
                        this.appendMessage('bot', `⚠️ **${fileData.name}** is already in the library (Status: ${fileData.status})`);
                    }
                } else {
                    const now = new Date();
                    const timeStr = this.formatDate(now.getTime());
                    const fileSize = fileData.size || '< 0.01 MB';
                    
                    const newDoc = {
                        id: fileData.id,
                        name: fileData.name,
                        path: fileData.path,
                        size: fileSize,
                        date: timeStr,
                        uploader: Auth.getUser(),
                        status: fileData.status,
                        progress: fileData.progress || 0
                    };
                    
                    // Check if document already exists in list (prevent duplicates)
                    const existingIndex = this.documents.findIndex(d => d.id === fileData.id || d.name === fileData.name);
                    if (existingIndex === -1) {
                        this.documents.unshift(newDoc);
                        uploadedCount++;
                    }
                }
                
                if (window.App) {
                    App.startStatusPolling();
                }
            });
            
            this.renderDocumentList();
            
            // Show success message
            if (showChatNotification && uploadedCount > 0) {
                let summary = `✅ Uploaded **${uploadedCount}** file(s) successfully!`;
                if (duplicateCount > 0) summary += ` (Skipped ${duplicateCount} duplicate(s))`;
                summary += `\n\nProcessing will start automatically.`;
                this.appendMessage('bot', summary);
            }
            
        } catch (error) {
            if (showChatNotification) {
                this.appendMessage('bot', `❌ Upload failed: ${error.message}\n\nPlease try again or check if the files are valid PDFs.`);
            }
        }
    },
    
    /**
     * Handle chat form submission
     */
    async handleChatSubmit(e) {
        e.preventDefault();
        const message = this.elements.chatInput.value.trim();
        if (!message) return;
        
        // 生成 Session ID（如果還沒有的話）
        if (!this.chatSessionId) {
            this.chatSessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        }
        
        // Display user message
        this.appendMessage('user', message);
        this.elements.chatInput.value = '';
        this.elements.chatInput.style.height = 'auto';
        this.elements.sendBtn.disabled = true;
        this.appendLoadingIndicator();
        
        // 解析文件路徑
        let docPath = null;
        const docMatch = message.match(/\[Doc:\s([^\]]+)\]/);
        if (docMatch) {
            docPath = docMatch[1];
        }
        
        try {
            // 必須加上 sessionId 以及解析出來的 docPath
            const response = await API.chatStream(message, Auth.getUser(), docPath, this.chatSessionId);
            
            this.removeLoadingIndicator();
            
            // Create bot message container
            const botMsgId = 'msg-' + Date.now();
            const botMsg = document.createElement('div');
            botMsg.className = 'flex justify-start mb-6';
            botMsg.innerHTML = `
                <div class="p-4 max-w-[85%] md:max-w-[75%] bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm shadow-sm">
                    <p id="${botMsgId}" class="text-sm md:text-base leading-relaxed"><span class="typing-indicator"><span></span><span></span><span></span></span></p>
                </div>
            `;
            this.elements.chatContainer.appendChild(botMsg);
            this.scrollToBottom();
            
            const bubbleText = document.getElementById(botMsgId);
            let accumulatedText = "";
            
            // Process streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6).trim();
                        if (!dataStr || dataStr === '[DONE]') continue;
                        
                        try {
                            const data = JSON.parse(dataStr);
                            if (data.error) {
                                accumulatedText += `<br><span class="text-red-500">❌ ${data.error}</span>`;
                            } else if (data.content) {
                                accumulatedText += data.content;
                            }
                            bubbleText.innerHTML = this.formatMarkdown(accumulatedText);
                            this.scrollToBottom();
                        } catch (err) {
                            console.error("Error parsing stream JSON:", err, dataStr);
                        }
                    }
                }
            }
        } catch (error) {
            this.removeLoadingIndicator();
            this.appendMessage('bot', `❌ **連線錯誤**\n\n伺服器發生異常或無法連線。\n\n錯誤詳情：${error.message}`);
        }
        
        this.elements.sendBtn.disabled = false;
    },
    
    /**
     * Append message to chat
     */
    appendMessage(sender, text) {
        const isUser = sender === 'user';
        const msgDiv = document.createElement('div');
        msgDiv.className = `flex ${isUser ? 'justify-end' : 'justify-start'} mb-6 animate-fade-in-up`;
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = `p-4 max-w-[85%] md:max-w-[75%] shadow-sm ${isUser
                ? 'bg-blue-600 text-white rounded-2xl rounded-tr-sm'
                : 'bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm'
            }`;
        
        // Format text
        let formattedText = text.replace(/\[Doc:\s([^\]]+)\]/g, '<span class="inline-block bg-blue-500/20 text-blue-100 px-2 py-0.5 rounded text-xs font-mono mb-1 mr-1 border border-blue-500/30"><i class="fas fa-paperclip mr-1"></i>$1</span>');
        formattedText = formattedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formattedText = formattedText.replace(/\n/g, '<br>');
        
        bubbleDiv.innerHTML = `<p class="text-sm md:text-base leading-relaxed">${formattedText}</p>`;
        msgDiv.appendChild(bubbleDiv);
        this.elements.chatContainer.appendChild(msgDiv);
        this.scrollToBottom();
    },
    
    /**
     * Append loading indicator
     */
    appendLoadingIndicator() {
        const msgDiv = document.createElement('div');
        msgDiv.id = 'loading-indicator';
        msgDiv.className = 'flex justify-start mb-6';
        msgDiv.innerHTML = `
            <div class="bg-white border border-slate-200 rounded-2xl rounded-tl-sm shadow-sm p-4 py-5 flex items-center typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        this.elements.chatContainer.appendChild(msgDiv);
        this.scrollToBottom();
    },
    
    /**
     * Remove loading indicator
     */
    removeLoadingIndicator() {
        const indicator = document.getElementById('loading-indicator');
        if (indicator) indicator.remove();
    },
    
    /**
     * Scroll chat to bottom
     */
    scrollToBottom() {
        this.elements.chatContainer.scrollTop = this.elements.chatContainer.scrollHeight;
    },
    
    /**
     * Format Markdown text
     */
    formatMarkdown(text) {
        let formatted = text.replace(/\[Doc:\s([^\]]+)\]/g, '<span class="inline-block bg-blue-500/20 text-blue-100 px-2 py-0.5 rounded text-xs font-mono mb-1 mr-1 border border-blue-500/30"><i class="fas fa-paperclip mr-1"></i>$1</span>');
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\n/g, '<br>');
        return formatted;
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
window.UI = UI;
