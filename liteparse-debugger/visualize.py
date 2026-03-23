"""LiteParse Debugger - Visualize bounding boxes on PDF pages.

This tool renders parsed elements as visual overlays on PDF pages,
helping debug and validate LiteParse parsing accuracy.

Usage:
    python visualize.py --pdf path/to/report.pdf --output output_dir
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Required packages not installed.")
    print("Install with: pip install pymupdf pillow")
    sys.exit(1)


def load_parsed_data(json_path: str) -> dict:
    """Load LiteParse JSON output."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_bbox_coordinates(element: dict, page_height: int) -> tuple[int, int, int, int]:
    """Extract bounding box coordinates, handling different formats.
    
    LiteParse may return bbox in different formats:
    - {"x0", "y0", "x1", "y1"}
    - {"x", "y", "width", "height"}
    - [x0, y0, x1, y1]
    """
    bbox = element.get("bbox") or element.get("bounding_box")
    
    if not bbox:
        return None
    
    # Handle list format
    if isinstance(bbox, list) and len(bbox) == 4:
        x0, y0, x1, y1 = bbox
        return (x0, y0, x1, y1)
    
    # Handle dict format with coordinates
    if isinstance(bbox, dict):
        if all(k in bbox for k in ["x0", "y0", "x1", "y1"]):
            return (bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
        
        # Handle x/y/width/height format
        if all(k in bbox for k in ["x", "y", "width", "height"]):
            x = bbox["x"]
            y = bbox["y"]
            w = bbox["width"]
            h = bbox["height"]
            return (x, y, x + w, y + h)
    
    return None


def draw_bounding_boxes(
    pdf_path: str,
    elements: list[dict],
    output_dir: str,
    page_numbers: list[int] | None = None,
    show_text: bool = False,
    color_by_type: bool = True,
):
    """Draw bounding boxes on PDF pages.
    
    Args:
        pdf_path: Path to the PDF file
        elements: List of parsed elements with bounding boxes
        output_dir: Directory to save output images
        page_numbers: Specific pages to render (None = all)
        show_text: Whether to overlay text on boxes
        color_by_type: Use different colors for different element types
    """
    # Open PDF
    doc = fitz.open(pdf_path)
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Color mapping for element types
    type_colors = {
        "text": (255, 0, 0, 128),      # Red
        "table": (0, 255, 0, 128),      # Green
        "image": (0, 0, 255, 128),      # Blue
        "header": (255, 255, 0, 128),   # Yellow
        "footer": (255, 0, 255, 128),   # Magenta
        "figure": (0, 255, 255, 128),   # Cyan
        "list": (255, 165, 0, 128),     # Orange
        "default": (128, 128, 128, 128) # Gray
    }
    
    # Determine pages to render
    if page_numbers is None:
        page_numbers = list(range(len(doc)))
    else:
        page_numbers = [p - 1 for p in page_numbers]  # Convert to 0-indexed
    
    print(f"Rendering {len(page_numbers)} pages...")
    
    for page_num in page_numbers:
        if page_num < 0 or page_num >= len(doc):
            continue
        
        page = doc[page_num]
        
        # Render page to image (2x zoom for better quality)
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        draw = ImageDraw.Draw(img, "RGBA")
        
        # Get page dimensions for coordinate conversion
        page_rect = page.rect
        scale_x = pix.width / page_rect.width
        scale_y = pix.height / page_rect.height
        
        # Filter elements for this page
        page_elements = [
            e for e in elements 
            if e.get("page") == page_num + 1 or e.get("page_number") == page_num + 1
        ]
        
        print(f"  Page {page_num + 1}: {len(page_elements)} elements")
        
        # Draw bounding boxes
        for elem in page_elements:
            bbox = get_bbox_coordinates(elem, page_rect.height)
            if not bbox:
                continue
            
            # Scale coordinates
            x0 = bbox[0] * scale_x
            y0 = bbox[1] * scale_y
            x1 = bbox[2] * scale_x
            y1 = bbox[3] * scale_y
            
            # Determine color
            elem_type = elem.get("type", "default").lower()
            if color_by_type and elem_type in type_colors:
                color = type_colors[elem_type]
            else:
                color = type_colors["default"]
            
            # Draw rectangle
            draw.rectangle([x0, y0, x1, y1], outline=color[:3], width=2, fill=color)
            
            # Add text label if requested
            if show_text:
                text = elem.get("text", "")[:50]
                if text:
                    try:
                        font = ImageFont.truetype("arial.ttf", 12)
                    except:
                        font = ImageFont.load_default()
                    draw.text((x0 + 2, y0 + 2), text, fill=(255, 255, 255))
        
        # Save output
        output_path = os.path.join(output_dir, f"page_{page_num + 1:03d}.png")
        img.save(output_path)
        print(f"  Saved: {output_path}")
    
    doc.close()
    print(f"\nDone! Output saved to: {output_dir}")


def visualize_from_pdf(pdf_path: str, output_dir: str):
    """First parse PDF with LiteParse, then visualize.
    
    This is a convenience function that runs LiteParse and visualizes in one step.
    """
    import subprocess
    
    print(f"Parsing PDF with LiteParse: {pdf_path}")
    
    # Run LiteParse
    result = subprocess.run(
        ["lit", "parse", pdf_path, "--format", "json"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"LiteParse failed: {result.stderr}")
        return
    
    # Parse output
    parsed_data = json.loads(result.stdout)
    elements = parsed_data.get("elements", [])
    
    print(f"Parsed {len(elements)} elements")
    
    # Visualize
    draw_bounding_boxes(pdf_path, elements, output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Visualize LiteParse bounding boxes on PDF pages"
    )
    parser.add_argument(
        "--pdf",
        required=True,
        help="Path to the PDF file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for visualization images",
    )
    parser.add_argument(
        "--json",
        help="Path to LiteParse JSON output (optional, will parse if not provided)",
    )
    parser.add_argument(
        "--pages",
        help="Specific pages to render (e.g., '1-5,10,15')",
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="Overlay text on bounding boxes",
    )
    parser.add_argument(
        "--no-color-type",
        action="store_true",
        help="Don't color by element type (use default gray)",
    )
    
    args = parser.parse_args()
    
    # Parse page range
    page_numbers = None
    if args.pages:
        page_numbers = []
        for part in args.pages.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                page_numbers.extend(range(start, end + 1))
            else:
                page_numbers.append(int(part))
    
    # Load or parse data
    if args.json:
        print(f"Loading parsed data from: {args.json}")
        parsed_data = load_parsed_data(args.json)
        elements = parsed_data.get("elements", [])
    else:
        print("No JSON provided, attempting to parse with LiteParse...")
        try:
            import subprocess
            result = subprocess.run(
                ["lit", "parse", args.pdf, "--format", "json"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                parsed_data = json.loads(result.stdout)
                elements = parsed_data.get("elements", [])
            else:
                print(f"LiteParse failed: {result.stderr}")
                sys.exit(1)
        except FileNotFoundError:
            print("LiteParse CLI not found. Please provide --json file.")
            sys.exit(1)
    
    # Draw bounding boxes
    draw_bounding_boxes(
        args.pdf,
        elements,
        args.output,
        page_numbers=page_numbers,
        show_text=args.show_text,
        color_by_type=not args.no_color_type,
    )


if __name__ == "__main__":
    main()
