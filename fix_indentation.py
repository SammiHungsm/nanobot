#!/usr/bin/env python3
"""Fix loop.py indentation error"""

with open('nanobot/agent/loop.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复缩进：将 for 循环和其内容全部缩进一级
old_block = '''        try:
        for attempt in range(max_retries):
            try:'''

new_block = '''        try:
            for attempt in range(max_retries):
                try:'''

content = content.replace(old_block, new_block)

# 写回文件
with open('nanobot/agent/loop.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] Fixed loop.py indentation')