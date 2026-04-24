import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

doc_id = "stock_00001_2023_v2_17b4fbe5"
response = requests.get(f"http://localhost:3000/api/status/{doc_id}", timeout=10)
print(f"Doc status: {response.json()}")
