# 🚀 Quick Start Guide - Two-Tab WebUI

## What's New?

Your Nanobot WebUI now has **2 tabs**:

1. **Chat Tab** - Your existing chatbot interface
2. **PDF Library Tab** - New document management interface

---

## Start the Server

```bash
cd C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\webui
python main.py
```

Then open: **http://localhost:8080**

---

## Tab 1: Chat (What You Already Know)

✅ Everything works the same as before
- Chat with AI financial assistant
- Upload PDFs with paperclip icon 📎
- Tag documents in messages
- Left sidebar shows document list

---

## Tab 2: PDF Library (New!)

### Switch to Library Tab
Click **"PDF Library"** tab at the top

### What You Can Do

#### 📤 Upload PDF
- Click **"Upload PDF"** button (top-right)
- Select PDF from your computer
- Watch it process in real-time

#### 👀 Preview PDF
- **Double-click** any PDF card
- Opens in full-screen preview
- Uses your browser's PDF viewer

#### 📊 View Details
- **Single-click** any PDF card
- Details panel opens on the right
- See: size, date, uploader, pages, status

#### 🔍 Search PDFs
- Type in the search box (top-right)
- Filters by filename or uploader
- Real-time results

#### 📥 Download
- Select a PDF
- Click **"Download"** in details panel
- Downloads original PDF file

#### 📄 View Processed Output
- Select a **completed** PDF
- Click **"View JSON"** button
- See OpenDataLoader output
- Copy or download the JSON

---

## Quick Actions Reference

| Action | How To Do It |
|--------|--------------|
| Upload PDF | Click "Upload PDF" button |
| Preview PDF | Double-click PDF card |
| Select PDF | Single-click PDF card |
| Tag in Chat | Click PDF in sidebar (Chat tab) |
| Search PDFs | Type in search box |
| Download PDF | Select → Click "Download" |
| View JSON | Select → Click "View JSON" |
| Refresh List | Click refresh icon (🔄) |

---

## Status Indicators

- 🔵 **Processing/Queued** - Document is being processed
- ✅ **Ready** - Document is ready to use
- ❌ **Failed** - Processing failed (check error)

---

## Keyboard Shortcuts

- **Double-click** PDF → Preview
- **Single-click** PDF → Select
- **ESC** → Close modal

---

## Files Changed

- `ui.html` - Complete rewrite with tabs
- `main.py` - Added 4 new API endpoints
- `ui.html.backup` - Your old UI (backup)

---

## New API Endpoints

```
GET /api/pdf/{id}/preview          - Preview PDF
GET /api/pdf/{id}/download         - Download PDF
GET /api/pdf/{id}/output           - Get JSON output
GET /api/pdf/{id}/output/download  - Download JSON
```

---

## Troubleshooting

**Can't preview PDF?**
- Make sure it's uploaded completely
- Try opening in new tab (link icon in preview modal)

**JSON not available?**
- Wait for processing to complete (status = "Ready")
- Check if OpenDataLoader output was generated

**Search not working?**
- Clear search box and try again
- Make sure you're typing filename or uploader name

---

## Need Help?

Check the full documentation:
- [`TWO_TAB_UPDATE_COMPLETE.md`](./TWO_TAB_UPDATE_COMPLETE.md) - Complete feature list
- [`UPLOAD_INTEGRATION_COMPLETE.md`](./UPLOAD_INTEGRATION_COMPLETE.md) - Upload integration details

---

**That's it! Enjoy your new two-tab interface! 🎉**
