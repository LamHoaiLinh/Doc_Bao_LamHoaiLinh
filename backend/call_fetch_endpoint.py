import os
import sys
import requests

base = os.getenv("NEWS_API_BASE", "").rstrip("/")
if not base:
    print("Thiếu biến môi trường NEWS_API_BASE, ví dụ: https://news-radar-pro-api.onrender.com")
    sys.exit(1)

url = f"{base}/api/fetch"
res = requests.post(url, timeout=120)
print(res.status_code)
print(res.text[:4000])
res.raise_for_status()
