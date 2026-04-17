"""Remove deprecated methods from stage0_preprocessor.py"""
import re

file_path = r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\nanobot\ingestion\stages\stage0_preprocessor.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 🌟 删除 _extract_from_text 方法（从 @staticmethod def _extract_from_text 到 return stock_code, year, name_en）
pattern1 = r'\n    @staticmethod\n    def _extract_from_text.*?return stock_code, year, name_en'
content = re.sub(pattern1, '', content, flags=re.DOTALL)

# 🌟 删除 _extract_from_filename 方法（从 @staticmethod def _extract_from_filename 到 return stock_code, year）
pattern2 = r'\n    @staticmethod\n    def _extract_from_filename.*?return stock_code, year'
content = re.sub(pattern2, '', content, flags=re.DOTALL)

# 🌟 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"[OK] Removed deprecated methods from {file_path}")
print(f"   - _extract_from_text")
print(f"   - _extract_from_filename")