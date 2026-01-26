import requests
import time

url = "http://localhost:8082/test-limit"

print(f"Testing {url}")
# Request 1: Should be 200
try:
    resp = requests.get(url)
    print(f"Req 1: {resp.status_code}")
except Exception as e:
    print(f"Req 1 failed: {e}")

# Request 2: Should be 429
try:
    resp = requests.get(url)
    print(f"Req 2: {resp.status_code}")
    if resp.status_code == 429:
        print("SUCCESS")
    else:
        print("FAILURE")
        print(resp.text)
except Exception as e:
    print(f"Req 2 failed: {e}")
