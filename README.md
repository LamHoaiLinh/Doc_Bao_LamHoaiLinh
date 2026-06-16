# News Radar Pro

App đọc báo mobile-first: quản lý nguồn RSS, lướt tin, phân trang tự cuộn lên đầu, lưu bài, đánh dấu đã đọc, đọc nội dung gốc và tóm tắt từng bài được chọn. Bản này dùng tóm tắt nội bộ bằng thuật toán, không cần OpenAI API key.

## Điểm mới bản clean summary

- Bỏ toàn bộ dòng ghi chú kiểu “tóm tắt nội bộ miễn phí bằng thuật toán”.
- Lọc rác giao diện web như bình luận, tặng sao, nạp thêm, tin liên quan, chủ đề, dòng sự kiện.
- Khi gặp nội dung cũ bị dính rác, backend tự lấy lại nội dung sạch hơn.
- Tóm tắt lại luôn bằng phiên bản thuật toán mới, không dùng cache cũ bị lỗi.
- Frontend không còn hiển thị “Đang tóm tắt bằng AI”.

## Deploy backend lên Render Free

Root Directory:

```text
backend
```

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port $PORT
```

Environment Variables:

```env
PYTHON_VERSION=3.12.11
DB_PATH=/tmp/news.db
CORS_ORIGINS=*
SUMMARY_ENGINE=local
```

Không cần:

```env
OPENAI_API_KEY
OPENAI_MODEL
```

Lưu ý: Render Free không có Persistent Disk. Vì vậy `/tmp/news.db` là database tạm, có thể mất dữ liệu khi redeploy/restart. Dùng để chạy thử là ổn. Khi cần lưu bền, chuyển sang Render paid disk hoặc PostgreSQL/Supabase/Neon.

## Deploy frontend lên GitHub Pages

Sửa file:

```text
docs/config.js
```

Đổi thành link backend Render của anh:

```js
window.NEWS_RADAR_API_BASE = "https://ten-service-cua-anh.onrender.com";
```

GitHub Pages:

```text
Settings → Pages → Deploy from a branch → main → /docs
```

## Cách dùng

1. Mở link GitHub Pages trên điện thoại.
2. Vào tab Nguồn để kiểm tra nguồn RSS.
3. Bấm nút làm mới/quét tin.
4. Vào Tin mới để lướt tiêu đề.
5. Bấm Đọc hoặc Tóm tắt khi gặp tin đáng quan tâm.
6. Bấm Bài sau/Bài trước để đọc tiếp, app sẽ tự cuộn lên đầu.

## Ghi chú kỹ thuật

Thuật toán tóm tắt là extractive summarization: lọc nội dung sạch, chấm điểm câu theo vị trí đầu bài, độ khớp tiêu đề, từ khóa lặp lại, số liệu, tên riêng, rồi trình bày lại thành gạch đầu dòng có liên từ. Không suy luận sâu như AI thật, nhưng miễn phí và đủ dùng để lướt tin.
