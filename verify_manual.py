import requests
import time

url = "http://localhost:8082/auth/login"
payload = {"email": "test@example.com", "password": "wrongpassword"}

# Send 5 allowed requests
for i in range(5):
    try:
        response = requests.post(url, json=payload)
        print(f"Request {i+1}: Status {response.status_code}")
        # Expect 401 (invalid creds) or 500 (db error) but NOT 429
        # 422 would mean signature issue
    except Exception as e:
        print(f"Request {i+1} failed: {e}")

# Send 6th request (should be blocked)
try:
    response = requests.post(url, json=payload)
    print(f"Request 6: Status {response.status_code}")
    if response.status_code == 429:
        print("SUCCESS: Rate limit exceeded")
    else:
        print(f"FAILURE: Expected 429, got {response.status_code}")
        print(f"Body: {response.text}")
except Exception as e:
    print(f"Request 6 failed: {e}")
