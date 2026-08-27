import requests

payload = {
    "efficiency_factors": [0.3, 0.3, 0.3, 0.3],
    "compute_capabilities": [1.0, 1.0, 1.0, 1.0]
}

r = requests.post("http://127.0.0.1:5000/api/compare", json=payload)
print(r.status_code)
print(r.json())
