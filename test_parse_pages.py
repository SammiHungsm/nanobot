#!/usr/bin/env python3
"""Test parse_pages functionality"""

import sys
sys.path.insert(0, '/app')

from nanobot.ingestion.parsers.opendataloader_parser import OpenDataLoaderParser

parser = OpenDataLoaderParser()

# Test parse_pages
pdf_path = '/app/data/uploads/20260410_095254_stock_00001_2023.pdf'
result = parser.parse_pages(pdf_path, pages=[1, 2])

print('Result:', len(result), 'artifacts')
for a in result[:5]:
    page = a.get('page_num')
    typ = a.get('type')
    cnt = len(str(a.get('content', '')))
    print(f'  Page {page}: {typ} ({cnt} chars)')