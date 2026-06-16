# News Radar Pro

App đọc RSS trên điện thoại: GitHub Pages làm frontend, Render chạy backend FastAPI.

## Biến môi trường Render tối thiểu

```env
PYTHON_VERSION=3.12.11
DB_PATH=/tmp/news.db
CORS_ORIGINS=*
SUMMARY_ENGINE=local
```

## Lưu thư viện nguồn RSS vào GitHub

Tạo GitHub Fine-grained Personal Access Token cho đúng repo, cấp quyền **Repository contents: Read and write**. Sau đó thêm vào Render:

```env
GITHUB_SYNC_ENABLED=true
GITHUB_TOKEN=github_pat_xxx
GITHUB_OWNER=LamHoaiLinh
GITHUB_REPO=Doc_Bao_LamHoaiLinh
GITHUB_BRANCH=main
GITHUB_SOURCES_PATH=backend/default_sources.json
```

Khi thêm/sửa/xóa/sắp xếp nguồn trong app, backend sẽ commit lại file `backend/default_sources.json` vào GitHub. Khi Render Free reset `/tmp/news.db`, app sẽ tự nạp lại thư viện nguồn từ file này.

## Frontend

Sửa `docs/config.js`:

```js
window.NEWS_RADAR_API_BASE = "https://ten-service-render.onrender.com";
```

GitHub Pages: branch `main`, folder `/docs`.
