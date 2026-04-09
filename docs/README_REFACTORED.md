# Nanobot WebUI - Refactored Structure

## 📁 New File Structure

```
webui/
├── main.py                 # FastAPI backend server
├── static/
│   ├── index.html          # Main HTML file (served at /)
│   ├── css/
│   │   └── style.css       # All custom styles
│   └── js/
│       ├── api.js          # API communication layer
│       ├── auth.js         # Authentication module
│       ├── ui.js           # Chat UI rendering
│       ├── library.js      # PDF library management
│       └── app.js          # Main application initialization
├── ui.html                 # Legacy file (backup only)
└── ui.html.backup          # Original backup
```

## 🎯 What Changed

### Before (Single File)
- All HTML, CSS, and JavaScript in `ui.html`
- ~800 lines of mixed concerns
- Difficult to maintain and debug
- Incomplete file caused blank screen

### After (Separated Modules)
- **Clean separation of concerns**
- **Reusable API layer** (`api.js`)
- **Independent modules** (auth, ui, library, app)
- **Easy to debug and extend**
- **Professional file structure**

## 🔧 Module Responsibilities

### `api.js`
All backend API communication:
- `/api/chat/stream` - Streaming chat
- `/api/documents` - List documents
- `/api/upload` - File upload
- `/api/status/:id` - Document status
- `/api/pdf/:id/*` - PDF operations

### `auth.js`
User authentication:
- Login/logout handling
- Session management
- User state

### `ui.js`
Chat interface:
- Message rendering
- File upload (chat tab)
- Document list sidebar
- Chat form handling
- Markdown formatting

### `library.js`
PDF library management:
- Document grid rendering
- Search/filter
- Details panel
- PDF preview modal
- JSON output viewer

### `app.js`
Application lifecycle:
- Module initialization
- Tab switching
- Status polling coordinator
- Global function bindings

## 🚀 Running the Server

```bash
cd webui
python main.py
```

Server will start at: `http://localhost:8080`

## 📝 Static Files

Static files are served from `/static/` directory:
- CSS: `/static/css/style.css`
- JavaScript: `/static/js/*.js`

## 🔍 Key Features

1. **Two Tabs**: Chat and PDF Library
2. **Real-time Status**: Polling for processing documents
3. **Streaming Chat**: Typewriter effect for bot responses
4. **PDF Preview**: In-browser PDF viewing
5. **JSON Output**: View/download processed document output
6. **Responsive**: Works on mobile and desktop

## 🐛 Bug Fixes

- ✅ Fixed incomplete HTML structure (was missing `<!DOCTYPE html>`, `<head>`, `<body>`)
- ✅ Fixed static file serving
- ✅ Added proper module initialization order
- ✅ Fixed API base URL detection

## 📦 Dependencies

No additional dependencies needed. Uses:
- **Tailwind CSS** (CDN) for styling
- **FontAwesome** (CDN) for icons
- **FastAPI** for backend
- **Vanilla JavaScript** (no framework)

## 🤝 Contributing

When adding features:
1. Add CSS to `static/css/style.css`
2. Add API calls to `static/js/api.js`
3. Create new module in `static/js/` if needed
4. Initialize in `app.js`

---

**Last Updated**: 2026-03-31
**Version**: 2.0.0 (refactored)
