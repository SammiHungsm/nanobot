#!/usr/bin/env python3
"""Fix loop.py syntax error - add missing try block"""

with open('nanobot/agent/loop.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 在第 271 行前添加 try:
if lines[270].strip() == 'for attempt in range(max_retries):':
    # 找到正确的缩进
    indent = '        '  # 8 spaces
    lines.insert(270, indent + 'try:\n')
    print(f'Added "try:" before line 271')

# 写回文件
with open('nanobot/agent/loop.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('[OK] Fixed loop.py syntax error')