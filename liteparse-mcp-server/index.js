/**
 * LiteParse MCP Server
 * 
 * Provides Model Context Protocol tools for parsing financial reports
 * with spatial awareness using LiteParse CLI.
 * 
 * Tools:
 * - parse_financial_table: Parse PDF with spatial structure preservation
 * - get_pdf_screenshot: Generate screenshots of specific pages
 * - query_financial_data: Query parsed data for specific metrics
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { spawn } from "child_process";
import { existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// LiteParse CLI wrapper
class LiteParseCLI {
  constructor() {
    this.litPath = null;
  }

  async findLitCli() {
    // Common paths for lit CLI
    const paths = [
      "lit",
      join(process.cwd(), "node_modules", ".bin", "lit"),
      join(__dirname, "node_modules", ".bin", "lit"),
    ];

    for (const path of paths) {
      try {
        const { execSync } = await import("child_process");
        execSync(`${path} --version`, { stdio: "ignore" });
        this.litPath = path;
        return path;
      } catch {
        continue;
      }
    }
    return null;
  }

  async execute(args) {
    return new Promise((resolve, reject) => {
      const lit = spawn(this.litPath || "lit", args);
      let stdout = "";
      let stderr = "";

      lit.stdout.on("data", (data) => {
        stdout += data.toString();
      });

      lit.stderr.on("data", (data) => {
        stderr += data.toString();
      });

      lit.on("close", (code) => {
        if (code === 0) {
          resolve({ stdout, stderr });
        } else {
          reject(new Error(`LiteParse exited with code ${code}: ${stderr}`));
        }
      });

      lit.on("error", (err) => {
        reject(err);
      });
    });
  }

  async parse(pdfPath, options = {}) {
    const args = ["parse", pdfPath, "--format", options.format || "json"];
    
    if (options.pages) {
      args.push("--pages", options.pages);
    }

    const result = await this.execute(args);
    return JSON.parse(result.stdout);
  }

  async screenshot(pdfPath, pages, outputDir) {
    const args = [
      "screenshot",
      pdfPath,
      "--target-pages",
      pages,
      "--output-dir",
      outputDir,
    ];

    await this.execute(args);
    return outputDir;
  }
}

// Create MCP server
const server = new McpServer({
  name: "liteparse-mcp-server",
  version: "1.0.0",
});

const liteparse = new LiteParseCLI();

// Tool: parse_financial_table
server.tool(
  "parse_financial_table",
  "Parse a financial PDF document with spatial awareness. Preserves table structures, indentation, and bounding boxes. Ideal for balance sheets, income statements, and cash flow statements. Returns cleaned, LLM-ready Markdown tables.",
  {
    pdf_path: {
      type: "string",
      description: "Absolute or relative path to the PDF file",
    },
    pages: {
      type: "string",
      description: "Optional page range (e.g., '1-5', '10', '1-3,5,7-9')",
      optional: true,
    },
    output_format: {
      type: "string",
      description: "Output format: 'json' (raw), 'markdown' (cleaned tables), or 'context' (LLM-ready)",
      enum: ["json", "markdown", "context"],
      optional: true,
    },
    max_tables: {
      type: "integer",
      description: "Maximum number of tables to return (default: 10, used for markdown/context modes)",
      optional: true,
    },
  },
  async ({ pdf_path, pages, output_format, max_tables }) => {
    try {
      // Check if file exists
      if (!existsSync(pdf_path)) {
        return {
          content: [
            {
              type: "text",
              text: `Error: PDF file not found: ${pdf_path}`,
            },
          ],
        };
      }

      // Find LiteParse CLI
      await liteparse.findLitCli();
      if (!liteparse.litPath) {
        return {
          content: [
            {
              type: "text",
              text: "Error: LiteParse CLI not found. Install with: npm install -g @llamaindex/liteparse",
            },
          ],
        };
      }

      // Parse the PDF
      const rawResult = await liteparse.parse(pdf_path, {
        pages,
        format: "json",
      });

      // Process based on output format
      const format = output_format || "json";
      
      if (format === "json") {
        // Return raw JSON with metadata
        const metadata = {
          pdf_path,
          pages_parsed: pages || "all",
          element_count: rawResult.elements?.length || 0,
          has_tables: rawResult.elements?.some((e) => e.type === "table") || false,
        };

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  ...rawResult,
                  _metadata: metadata,
                },
                null,
                2
              ),
            },
          ],
        };
      } else {
        // Use Python data cleaner for markdown/context modes
        const { spawn } = await import("child_process");
        
        const cleanerPath = join(__dirname, "liteparse_data_cleaner.py");
        
        return new Promise((resolve) => {
          const python = spawn("python", [
            cleanerPath,
            "--input-json",
            JSON.stringify(rawResult),
            "--mode",
            format,
            "--max-tables",
            String(max_tables || 10),
          ]);

          let stdout = "";
          let stderr = "";

          python.stdout.on("data", (data) => {
            stdout += data.toString();
          });

          python.stderr.on("data", (data) => {
            stderr += data.toString();
          });

          python.on("close", (code) => {
            if (code === 0) {
              resolve({
                content: [
                  {
                    type: "text",
                    text: stdout.trim(),
                  },
                ],
              });
            } else {
              resolve({
                content: [
                  {
                    type: "text",
                    text: `Error in data cleaner: ${stderr}\n\nFallback to raw JSON:\n${JSON.stringify(rawResult, null, 2)}`,
                  },
                ],
              });
            }
          });
        });
      }
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Error parsing PDF: ${error.message}`,
          },
        ],
      };
    }
  }
);

// Tool: get_pdf_screenshot
server.tool(
  "get_pdf_screenshot",
  "Generate screenshots of specific PDF pages for visual analysis of charts, graphs, and complex layouts.",
  {
    pdf_path: {
      type: "string",
      description: "Absolute or relative path to the PDF file",
    },
    pages: {
      type: "string",
      description: "Page range to screenshot (e.g., '10', '10-12', '1-3,5,7-9')",
    },
    output_dir: {
      type: "string",
      description: "Directory to save screenshots",
      optional: true,
    },
  },
  async ({ pdf_path, pages, output_dir }) => {
    try {
      if (!existsSync(pdf_path)) {
        return {
          content: [
            {
              type: "text",
              text: `Error: PDF file not found: ${pdf_path}`,
            },
          ],
        };
      }

      await liteparse.findLitCli();
      if (!liteparse.litPath) {
        return {
          content: [
            {
              type: "text",
              text: "Error: LiteParse CLI not found",
            },
          ],
        };
      }

      const defaultOutputDir = join(dirname(pdf_path), "_liteparse_screenshots");
      const targetOutputDir = output_dir || defaultOutputDir;

      await liteparse.screenshot(pdf_path, pages, targetOutputDir);

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                success: true,
                output_directory: targetOutputDir,
                pdf_path: pdf_path,
                pages: pages,
              },
              null,
              2
            ),
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Error generating screenshot: ${error.message}`,
          },
        ],
      };
    }
  }
);

// Tool: query_financial_data
server.tool(
  "query_financial_data",
  "Extract specific financial metrics from parsed data (revenue, profit, assets, liabilities, etc.).",
  {
    parsed_data: {
      type: "string",
      description: "JSON string of parsed LiteParse output",
    },
    metric: {
      type: "string",
      description: "Financial metric to extract (e.g., 'revenue', 'net profit', 'total assets')",
    },
    year: {
      type: "string",
      description: "Optional year or period (e.g., '2023', 'FY2024', 'Q3')",
      optional: true,
    },
  },
  async ({ parsed_data, metric, year }) => {
    try {
      const data = JSON.parse(parsed_data);
      const elements = data.elements || [];
      
      // Search for the metric in text elements
      const results = [];
      const metricLower = metric.toLowerCase();
      
      for (const elem of elements) {
        const text = elem.text || "";
        if (text.toLowerCase().includes(metricLower)) {
          // Check year filter if specified
          if (year && !text.includes(year)) {
            continue;
          }
          
          results.push({
            text: text.trim(),
            type: elem.type,
            bbox: elem.bbox || elem.bounding_box,
          });
        }
      }

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                metric,
                year: year || "any",
                matches: results.length,
                results: results.slice(0, 10), // Limit to top 10
              },
              null,
              2
            ),
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Error querying data: ${error.message}`,
          },
        ],
      };
    }
  }
);

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("LiteParse MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});
