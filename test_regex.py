"""Simple test for pdf_core regex"""
import re

# 🌟 Test regex for image path correction
test_md = """![Abstract graphic design featuring a swirl of colorful squares forming a globe at the bottom](page_1_image_1_v2.jpg)

# 2023
# ANNUAL REPORT
"""

# 🌟 Apply regex
corrected_md = re.sub(
    r'!\[([^\]]*)\]\((page_[^)]+)\)',
    r'![\1](images/\2)',
    test_md
)

print("Original Markdown:")
print(test_md)
print("\nCorrected Markdown:")
print(corrected_md)

# 🌟 Check if correction worked
assert "images/page_1_image_1_v2.jpg" in corrected_md
print("\n✅ Regex correction works!")