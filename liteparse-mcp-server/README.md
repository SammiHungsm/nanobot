# LiteParse MCP Server

Model Context Protocol (MCP) server for parsing financial reports with spatial awareness using LiteParse.

## Features

- **Spatial-Aware Parsing**: Preserves table structures, indentation, and bounding boxes
- **Financial Report Optimized**: Excellent for balance sheets, income statements, cash flow statements
- **Multi-Modal Support**: Generate screenshots for chart/graph analysis
- **Data Cleaning**: Built-in Python cleaner filters noise and formats tables as Markdown
- **Three Output Modes**: `json` (raw), `markdown` (cleaned), `context` (LLM-ready)

## Tools

### `parse_financial_table`

Parse a PDF document with spatial structure preservation.

**Parameters:**
- `pdf_path` (required): Path to the PDF file
- `pages` (optional): Page range (e.g., "1-5", "10", "1-3,5,7-9")
- `output_format` (optional): "json", "markdown", or "context"
- `max_tables` (optional): Maximum tables to return (default: 10)

**Output Formats:**
- `json`: Raw LiteParse output with bounding boxes
- `markdown`: Cleaned tables in Markdown format
- `context`: LLM-ready formatted context with prioritized financial tables

### `get_pdf_screenshot`

Generate screenshots of specific PDF pages.

### `query_financial_data`

Extract specific financial metrics from parsed data.

## Installation

```bash
cd nanobot/liteparse-mcp-server
npm install
```

## Usage with Nanobot

### 1. Configure MCP in Nanobot

Add to your `nanobot/config/config.yaml`:

```yaml
mcp:
  servers:
    liteparse:
      type: stdio
      command: node
      args:
        - /path/to/nanobot/liteparse-mcp-server/index.js
      cwd: /path/to/nanobot/liteparse-mcp-server
```

### 2. Start Nanobot

```bash
nanobot start
```

### 3. Example Query

```
幫我分析呢份財報嘅資產負債表
```

The agent will:
1. Use `parse_financial_table` with `output_format="context"`
2. Receive cleaned, prioritized Markdown tables
3. Analyze and respond in natural language

## Data Cleaning

The integrated Python data cleaner (`liteparse_data_cleaner.py`) provides:

1. **Noise Filtering**: Removes headers, footers, URLs, copyright notices
2. **Table Classification**: Auto-identifies balance sheets, income statements, cash flow statements
3. **Confidence Scoring**: Rates tables 0.3-0.9 based on keyword matching
4. **Markdown Formatting**: Converts tables to clean Markdown
5. **Priority Ordering**: Financial statements > Notes > Other tables

## Testing

```bash
# Test data cleaner directly
python liteparse_data_cleaner.py --mode stats --max-tables 5

# Test with sample JSON
python liteparse_data_cleaner.py --input-file parsed_data.json --mode context
```

## Docker Deployment

```bash
# Build image
docker build -t liteparse-mcp-server .

# Run container
docker run -v /path/to/pdfs:/data/pdfs liteparse-mcp-server
```

## License

MIT
