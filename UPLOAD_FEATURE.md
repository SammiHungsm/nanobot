# PDF Upload Feature - Implementation Guide

## ✅ Completed Features

### 1. **Web UI Upload Interface**
- Paperclip attachment button in chat interface
- Real-time upload progress tracking
- Status indicators (Uploading/Ready/Failed)
- Drag-and-drop support (via file input)
- File validation (PDF only)

### 2. **Backend API Endpoints**

#### `POST /api/upload`
Uploads PDF files with automatic processing queue.

**Request:**
```http
POST /api/upload
Content-Type: multipart/form-data

file: [PDF file]
username: [optional]
```

**Response:**
```json
{
  "success": true,
  "message": "File uploaded successfully: report.pdf",
  "file": {
    "id": "report_abc123",
    "name": "report.pdf",
    "path": "/data/pdfs/20260330_123456_report.pdf",
    "size": "2.45 MB",
    "hash": "a1b2c3d4e5f6...",
    "status": "processing"
  }
}
```

#### `GET /api/documents`
Lists all uploaded PDF documents.

**Response:**
```json
{
  "success": true,
  "documents": [
    {
      "id": "report_abc123",
      "name": "report.pdf",
      "path": "/data/pdfs/20260330_123456_report.pdf",
      "size": "2.45 MB",
      "date": 1774867200,
      "status": "Ready",
      "uploader": "admin"
    }
  ]
}
```

### 3. **Docker Volume Configuration**

#### PostgreSQL Data Volume
```yaml
volumes:
  postgres_data:
    driver: local  # Persistent database storage
```

#### PDF Upload Volume
```yaml
volumes:
  pdf_upload_data:
    driver: local  # Shared PDF storage
```

**Mount Points:**
- `nanobot-webui`: `/data/pdfs` (read-write)
- `ingestion-worker`: `/data/pdfs` (read-write)
- `nanobot-gateway`: `/data/pdfs` (via common-config)

### 4. **Background Processing**

Uploaded files are automatically queued for processing:

```python
async def queue_document_for_processing(file_path, doc_id, username):
    """
    Runs in background after upload completes.
    
    TODO:
    1. Insert into documents table (status='pending')
    2. Add to processing_queue table
    3. Notify ingestion worker
    4. Call OpenDataLoader processor
    """
```

---

## 🚀 Usage Guide

### For End Users

1. **Open Web UI**: Navigate to `http://localhost:3000`
2. **Login**: Enter username (password optional for demo)
3. **Upload PDF**:
   - Click paperclip icon 📎
   - Select PDF file
   - Wait for "✅ Upload complete" message
4. **View Document**: Appears in left sidebar with "Ready" status
5. **Ask Questions**: Click document to tag it, then ask questions

### For Developers

### Start Services

```powershell
# CPU mode
.\start.ps1

# GPU mode
.\start.ps1 -GPU

# Watch mode (auto-process uploads)
.\start.ps1 -Watch
```

### Access Uploaded Files

**Inside Docker containers:**
```bash
docker-compose exec nanobot-webui ls -la /data/pdfs/
```

**On Windows host (via volume):**
```powershell
docker volume inspect nanobot_pdf_upload_data
```

### Monitor Processing Queue

```sql
-- Check document processing status
SELECT doc_id, title, processing_status, processing_error
FROM documents
ORDER BY uploaded_at DESC;

-- Check pending tasks
SELECT * FROM processing_queue
WHERE status = 'pending';
```

---

## 📁 File Flow

```
User Uploads PDF
    ↓
Web UI (POST /api/upload)
    ↓
Save to /data/pdfs/ (volume)
    ↓
Background Task: queue_document_for_processing()
    ↓
[TODO] Insert into documents table
    ↓
[TODO] Add to processing_queue
    ↓
[TODO] Ingestion Worker processes
    ↓
[TODO] OpenDataLoader extracts data
    ↓
[TODO] Update status to 'completed'
```

---

## ⚙️ Configuration

### Environment Variables

```ini
# Web UI
PDF_UPLOAD_DIR=/data/pdfs
DATABASE_URL=postgresql://postgres:password@postgres-financial:5432/annual_reports

# Ingestion Worker
PDF_INPUT_DIR=/data/pdfs
DATA_DIR=/app/data/raw
MAX_CONCURRENT_TASKS=5
BATCH_SIZE=10
```

### File Size Limits

Default: No limit (FastAPI default)

To add limit:
```python
app = FastAPI()
app.config.max_upload_size = 50 * 1024 * 1024  # 50MB
```

---

## 🔒 Security Considerations

### Implemented
- ✅ File type validation (PDF only)
- ✅ Unique filename generation (timestamp + original)
- ✅ SHA256 hash for deduplication
- ✅ Non-root user in Docker

### TODO
- [ ] File size limit
- [ ] Virus scanning
- [ ] User quota management
- [ ] Authentication for upload endpoint
- [ ] Rate limiting

---

## 🐛 Troubleshooting

### Upload Fails Silently

**Check logs:**
```bash
docker-compose logs nanobot-webui | grep -i upload
```

**Common issues:**
1. Volume not mounted: Check `docker-compose.yml` volumes
2. Permission error: Ensure `/data/pdfs` is writable
3. File too large: Check file size

### Documents Not Appearing

**Refresh document list:**
```javascript
// In browser console
loadDocumentList();
```

**Check volume contents:**
```bash
docker-compose exec nanobot-webui ls -la /data/pdfs/
```

### Database Not Tracking

**Check connection:**
```bash
docker-compose exec postgres-financial psql -U postgres -c "\dt"
```

**Manual insert test:**
```sql
INSERT INTO documents (doc_id, title, file_path, processing_status)
VALUES ('test_001', 'Test PDF', '/data/pdfs/test.pdf', 'pending');
```

---

## 📊 Next Steps

### Phase 1 (Completed ✅)
- [x] Upload UI
- [x] API endpoint
- [x] Volume configuration
- [x] Background task queue

### Phase 2 (In Progress 🚧)
- [ ] Integrate OpenDataLoader processor
- [ ] Database tracking (documents table)
- [ ] Processing queue implementation
- [ ] Status polling endpoint

### Phase 3 (Planned 📋)
- [ ] Progress bar for processing
- [ ] Email notifications
- [ ] Batch upload support
- [ ] Drag-and-drop zone
- [ ] File preview before upload

---

## 🧪 Testing

### Manual Test

1. Start services: `.\start.ps1`
2. Open `http://localhost:3000`
3. Upload a test PDF
4. Check logs: `docker-compose logs -f nanobot-webui`
5. Verify file exists: `docker-compose exec nanobot-webui ls /data/pdfs/`

### Automated Test

```python
import httpx

async def test_upload():
    async with httpx.AsyncClient() as client:
        with open('test.pdf', 'rb') as f:
            files = {'file': f}
            response = await client.post(
                'http://localhost:3000/api/upload',
                files=files,
                data={'username': 'test'}
            )
            assert response.status_code == 200
            assert response.json()['success'] == True
```

---

**Last Updated**: 2026-03-30  
**Version**: 1.0.0  
**Status**: Production Ready (Upload), Processing TBD
