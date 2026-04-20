import httpx

response = httpx.post(
    'http://vanna-service:8082/api/embed',
    json={'texts': ['test text']},
    timeout=30
)

print(f'Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f"Dimension: {data['dimension']}")
    print(f"Model: {data['model']}")
    print(f"Embeddings count: {len(data['embeddings'])}")
else:
    print(f"Error: {response.text}")
