# News Radar Pro

App đọc báo mobile-first: quản lý nguồn RSS, lướt tin, phân trang tự cuộn lên đầu, lưu bài, đánh dấu đã đọc, đọc nội dung gốc và tóm tắt AI theo từng bài được chọn.

## 1. Cấu trúc

```text
news-radar-pro/
  backend/              # FastAPI chạy trên Render hoặc máy local
    main.py
    fetch_once.py
    requirements.txt
    .env.example
  docs/                 # Frontend tĩnh chạy GitHub Pages
    index.html
    app.js
    styles.css
    config.js
    manifest.json
    sw.js
  render.yaml           # Blueprint tham khảo cho Render
```

## 2. Chạy local trên máy tính

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Mở kiểm tra:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

### Frontend

Mở file:

```text
docs/index.html
```

Hoặc chạy server tĩnh:

```bash
cd docs
python -m http.server 5500
```

Sau đó mở:

```text
http://localhost:5500
```

## 3. Cấu hình AI tóm tắt

Trong `backend/.env`, điền:

```env
SUMMARY_ENGINE=local
OPENAI_MODEL=gpt-4o-mini
```

Không điền API key thì app vẫn chạy, nhưng nút tóm tắt chỉ trả về bản xem nhanh nội dung, chưa gọi AI thật.

## 4. Deploy backend lên Render

Cách nhanh:

1. Đẩy toàn bộ thư mục này lên GitHub.
2. Vào Render → New → Web Service.
3. Chọn repo.
4. Root Directory: `backend`.
5. Build Command: `pip install -r requirements.txt`.
6. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
7. Environment Variables:
   - `DB_PATH=/var/data/news.db`
   - `CORS_ORIGINS=*`
   - `SUMMARY_ENGINE=local`
   - `OPENAI_MODEL=gpt-4o-mini`
8. Nên gắn Persistent Disk vào `/var/data` để SQLite không mất dữ liệu khi service rebuild/restart.

Sau khi deploy, Render sẽ cho link dạng:

```text
https://ten-service-cua-anh.onrender.com
```

## 5. Deploy frontend lên GitHub Pages

1. File frontend nằm trong thư mục `docs/`.
2. Sửa `docs/config.js`:

```js
window.NEWS_RADAR_API_BASE = "https://ten-service-cua-anh.onrender.com";
```

3. Push lên GitHub.
4. Vào repo → Settings → Pages.
5. Source: Deploy from branch.
6. Branch: `main`, Folder: `/docs`.
7. Mở link GitHub Pages trên iPhone.
8. iPhone Safari → Share → Add to Home Screen để dùng như app.

## 6. Tự động quét tin định kỳ

Cách 1: Dùng Render Cron Job, command:

```bash
python fetch_once.py
```

Lịch gợi ý:

```text
*/30 * * * *
```

Nghĩa là mỗi 30 phút quét một lần.

Cách 2: Không dùng Cron, mở app rồi bấm nút `↻` để quét thủ công.

## 7. Nguồn báo

App có sẵn vài RSS mẫu. Anh có thể thêm nguồn bằng màn hình `Nguồn báo`.

Gợi ý cấu trúc nhập:

- Tên nguồn: `BBC World`
- RSS URL: `https://feeds.bbci.co.uk/news/world/rss.xml`
- Nhóm: `World`
- Ngôn ngữ: `en`

## 8. Lưu ý vận hành

- Không phải báo nào cũng cho RSS đầy đủ.
- Một số báo chỉ cho tiêu đề/mô tả, khi bấm đọc app mới cố lấy nội dung bài.
- Một số trang chặn bot hoặc tải bằng JavaScript nặng có thể lấy thiếu nội dung.
- Muốn giảm miss tin thì nên ưu tiên RSS chính thức, quét định kỳ, và giữ lịch sử 7–30 ngày.
- Tóm tắt AI chỉ chạy khi anh bấm tóm tắt từng bài, giúp tiết kiệm chi phí.


## Bản local summary
Bản này dùng tóm tắt nội bộ bằng thuật toán trích xuất câu quan trọng. Không cần OPENAI_API_KEY và không tốn tiền AI. Chất lượng phù hợp để đọc lướt/lọc tin, nhưng không suy luận sâu như AI thật.
