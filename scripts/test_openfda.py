import requests
r = requests.get("https://api.fda.gov/drug/label.json", params={"search": "openfda.generic_name:\"aspirin\"", "limit": 1}, timeout=15)
print(r.status_code)
print(r.text[:300])
