# 統一使用基於 Debian 12 (Bookworm) 的 Node.js 官方輕量級 Image
# 這樣能完美避開 Alpine 系統與 Python C-extensions (如 pymupdf) 的相容性地雷
FROM node:20-bookworm-slim

WORKDIR /app

# 安裝 Python 3, pip 以及必要的系統工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 建立 Python 虛擬環境 (venv) 並安裝套件
# (Debian 12 預設限制直接使用 pip，使用 venv 是最標準安全的做法)
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN pip install --no-cache-dir pymupdf pillow

# 全域安裝 LiteParse CLI
RUN npm install -g @llamaindex/liteparse

# 複製 Node.js 的 package 設定檔
COPY package*.json ./

# 安裝 Node.js 依賴 (請確保 package.json 內有包含 zod 同 @modelcontextprotocol/sdk)
RUN npm install --omit=dev

# 複製伺服器源代碼與 Python 清洗腳本
COPY index.js ./
COPY liteparse_data_cleaner.py ./

# 建立 PDF 資料夾
RUN mkdir -p /data/pdfs

# Node image 已經內建了一個叫 'node' 的非 root 用戶，直接使用它並賦予權限
RUN chown -R node:node /app /data/pdfs

# 切換到非 root 用戶確保安全
USER node

# 開放 HTTP 通訊埠
EXPOSE 3000

# 設定環境變數
ENV MODE=http
ENV PORT=3000

# 啟動 MCP Server
CMD ["node", "index.js"]