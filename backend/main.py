import os
import re
import json
import hashlib
import sqlite3
import datetime as dt
from typing import Optional, Any
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "News Radar Pro"
DB_PATH = os.getenv("DB_PATH", "./news.db")
SUMMARY_ENGINE = os.getenv("SUMMARY_ENGINE", "local")
ARTICLE_TIMEOUT = int(os.getenv("ARTICLE_TIMEOUT", "15"))
MAX_ARTICLE_CHARS = int(os.getenv("MAX_ARTICLE_CHARS", "18000"))
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]

USER_AGENT = os.getenv(
    "NEWS_USER_AGENT",
    "Mozilla/5.0 (compatible; NewsRadarPro/1.0; +https://github.com/)"
)

app = FastAPI(title=APP_NAME, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEED_SOURCES = [
    {"name": "VnExpress - Tin mới", "url": "https://vnexpress.net/rss/tin-moi-nhat.rss", "category": "Việt Nam", "language": "vi", "priority": 10},
    {"name": "Tuổi Trẻ - Tin mới", "url": "https://tuoitre.vn/rss/tin-moi-nhat.rss", "category": "Việt Nam", "language": "vi", "priority": 9},
    {"name": "Thanh Niên - Trang chủ", "url": "https://thanhnien.vn/rss/home.rss", "category": "Việt Nam", "language": "vi", "priority": 8},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "World", "language": "en", "priority": 8},
    {"name": "The Guardian - World", "url": "https://www.theguardian.com/world/rss", "category": "World", "language": "en", "priority": 7},
    {"name": "NYTimes - World", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "category": "World", "language": "en", "priority": 7},
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def ensure_parent_dir(path: str) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)


def db() -> sqlite3.Connection:
    ensure_parent_dir(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT '',
                language TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                priority INTEGER DEFAULT 5,
                last_fetch TEXT,
                last_status TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                guid TEXT,
                url TEXT NOT NULL,
                url_hash TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                image_url TEXT DEFAULT '',
                author TEXT DEFAULT '',
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                content TEXT DEFAULT '',
                content_fetched_at TEXT,
                summary TEXT DEFAULT '',
                summary_style TEXT DEFAULT '',
                summary_model TEXT DEFAULT '',
                summary_at TEXT,
                is_read INTEGER DEFAULT 0,
                is_saved INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
            CREATE INDEX IF NOT EXISTS idx_articles_read ON articles(is_read);
            CREATE INDEX IF NOT EXISTS idx_articles_saved ON articles(is_saved);
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM sources").fetchone()["c"]
        if count == 0:
            for s in SEED_SOURCES:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO sources
                    (name, url, category, language, enabled, priority, created_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (s["name"], s["url"], s["category"], s["language"], s["priority"], now_iso()),
                )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row) if row else {}


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.get_text(" ", strip=True)


def normalize_url(url: str) -> str:
    return (url or "").strip()


def make_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def parse_date(entry: Any) -> str:
    # feedparser gives parsed structs when available. Keep UTC ISO where possible.
    for attr in ["published_parsed", "updated_parsed", "created_parsed"]:
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return dt.datetime(*parsed[:6], tzinfo=dt.timezone.utc).replace(microsecond=0).isoformat()
            except Exception:
                pass
    for attr in ["published", "updated", "created"]:
        value = getattr(entry, attr, "")
        if value:
            return str(value)
    return now_iso()


def pick_image(entry: Any, html: str = "") -> str:
    media_content = getattr(entry, "media_content", None) or []
    if media_content and isinstance(media_content, list):
        url = media_content[0].get("url")
        if url:
            return url
    media_thumbnail = getattr(entry, "media_thumbnail", None) or []
    if media_thumbnail and isinstance(media_thumbnail, list):
        url = media_thumbnail[0].get("url")
        if url:
            return url
    soup = BeautifulSoup(html or getattr(entry, "summary", "") or "", "html.parser")
    img = soup.find("img")
    if img and img.get("src"):
        return img.get("src")
    return ""


def request_url(url: str) -> requests.Response:
    return requests.get(
        url,
        timeout=ARTICLE_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        allow_redirects=True,
    )


NOISE_PHRASES = [
    "nạp thêm", "tặng sao", "hoàn thành tặng sao", "bình luận", "quay lại bài viết",
    "tối đa:", "được quan tâm nhất", "mới nhất", "chưa có bình luận", "hãy là người đầu tiên",
    "chia sẻ", "theo dõi", "đăng nhập", "đăng ký", "quảng cáo", "đọc tiếp",
    "trở lại chủ đề", "dòng sự kiện", "chủ đề:", "xem thêm", "tin liên quan",
    "back to", "sign in", "subscribe", "advertisement", "related articles", "comments"
]

ARTICLE_SELECTORS = [
    "article .fck_detail", ".fck_detail", "article .Normal", ".Normal",
    ".detail-content", ".detail__content", ".cms-body", ".article-body", ".article__body",
    ".story-body", ".entry-content", ".post-content", ".main-content", "#main-detail-body",
    "article", "main"
]


def normalize_text_block(text: str) -> str:
    text = re.sub(r"[\t\r]+", " ", text or "")
    text = re.sub(r"\u00a0", " ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_noise_paragraph(text: str) -> bool:
    t = normalize_text_block(text)
    low = t.lower()
    if len(t) < 45:
        return True
    if any(p in low for p in NOISE_PHRASES):
        return True
    # Loại các dòng menu/tag hoặc cụm rác có quá nhiều nhãn ngắn nối nhau.
    if len(t) < 140 and sum(1 for ch in t if ch.isupper()) > max(12, len(t) * 0.35):
        return True
    if re.fullmatch(r"[\W\d\s]+", t):
        return True
    if low.count("tặng sao") >= 1 or low.count("bình luận") >= 2:
        return True
    return False


def paragraph_score(paragraphs: list[str]) -> float:
    if not paragraphs:
        return 0
    text = " ".join(paragraphs)
    low = text.lower()
    score = sum(min(len(p), 900) for p in paragraphs)
    score += 180 * min(len(paragraphs), 12)
    score -= 900 * sum(low.count(x) for x in NOISE_PHRASES)
    # Ưu tiên đoạn báo thật có nhiều câu hoàn chỉnh.
    score += 80 * len(re.findall(r"[.!?。！？]", text))
    return score


def extract_clean_paragraphs_from_node(node) -> list[str]:
    # Ưu tiên paragraph/list item thay vì lấy toàn bộ node, vì toàn bộ node thường dính comment, menu, nút sao.
    raw = []
    for child in node.find_all(["p", "li"], recursive=True):
        txt = child.get_text(" ", strip=True)
        txt = normalize_text_block(txt)
        if txt and not is_noise_paragraph(txt):
            raw.append(txt)
    if not raw:
        txt = normalize_text_block(node.get_text("\n", strip=True))
        raw = [x.strip() for x in re.split(r"\n+", txt) if not is_noise_paragraph(x.strip())]

    cleaned = []
    seen = set()
    for x in raw:
        x = re.sub(r"\s+", " ", x).strip()
        # Cắt bỏ các đuôi UI thường dính vào paragraph cuối.
        x = re.split(r"(?:Nạp thêm|Tặng sao|Quay lại bài viết|Bình luận\s*\(|Được quan tâm nhất|Mới nhất|Tin liên quan)", x, flags=re.IGNORECASE)[0].strip()
        if not x or is_noise_paragraph(x):
            continue
        key = re.sub(r"\W+", "", x.lower())[:160]
        if key not in seen:
            cleaned.append(x)
            seen.add(key)
    return cleaned


def content_is_noisy(text: str) -> bool:
    low = (text or "").lower()
    if not text or len(text.strip()) < 200:
        return True
    noise_hits = sum(low.count(x) for x in NOISE_PHRASES)
    if noise_hits >= 3:
        return True
    if "nạp thêm" in low or "tặng sao" in low or "hoàn thành tặng sao" in low:
        return True
    return False


def extract_article(url: str) -> dict[str, str]:
    try:
        res = request_url(url)
        res.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Không lấy được nội dung bài: {e}")

    soup = BeautifulSoup(res.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "form", "button", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = ""
    og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    if og_title:
        title = og_title.get("content", "").strip()
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    image = ""
    og_image = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
    if og_image:
        image = og_image.get("content", "").strip()

    meta_desc = ""
    md = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if md:
        meta_desc = normalize_text_block(md.get("content", ""))

    best_paragraphs = []
    best_score = 0
    for sel in ARTICLE_SELECTORS:
        for node in soup.select(sel):
            ps = extract_clean_paragraphs_from_node(node)
            score = paragraph_score(ps)
            if score > best_score:
                best_paragraphs = ps
                best_score = score

    if not best_paragraphs:
        best_paragraphs = extract_clean_paragraphs_from_node(soup)

    # Nếu meta description là lead tốt và chưa có trong bài, đưa lên đầu.
    if meta_desc and len(meta_desc) > 50 and not is_noise_paragraph(meta_desc):
        joined_low = " ".join(best_paragraphs[:2]).lower()
        if meta_desc.lower()[:80] not in joined_low:
            best_paragraphs.insert(0, meta_desc)

    text = "\n\n".join(best_paragraphs)
    text = normalize_text_block(text)[:MAX_ARTICLE_CHARS]
    return {"title": title, "image_url": image, "content": text}

def fetch_source(source: sqlite3.Row) -> dict[str, Any]:
    src = row_to_dict(source)
    inserted = 0
    updated = 0
    errors = []
    parsed = feedparser.parse(src["url"])

    if getattr(parsed, "bozo", False):
        errors.append(str(getattr(parsed, "bozo_exception", "RSS có lỗi định dạng")))

    with db() as conn:
        for entry in parsed.entries[:80]:
            link = normalize_url(getattr(entry, "link", ""))
            title = clean_html(getattr(entry, "title", "")).strip()
            if not link or not title:
                continue
            guid = str(getattr(entry, "id", "") or getattr(entry, "guid", "") or link)
            description = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))[:800]
            image_url = pick_image(entry)
            author = clean_html(getattr(entry, "author", ""))[:200]
            published_at = parse_date(entry)
            url_hash = make_hash(link)
            exists = conn.execute("SELECT id FROM articles WHERE url_hash=?", (url_hash,)).fetchone()
            if exists:
                updated += 1
                conn.execute(
                    """
                    UPDATE articles
                    SET title=COALESCE(NULLIF(?, ''), title), description=COALESCE(NULLIF(?, ''), description),
                        image_url=COALESCE(NULLIF(?, ''), image_url), published_at=COALESCE(NULLIF(?, ''), published_at)
                    WHERE url_hash=?
                    """,
                    (title, description, image_url, published_at, url_hash),
                )
                continue
            conn.execute(
                """
                INSERT INTO articles
                (source_id, guid, url, url_hash, title, description, image_url, author, published_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (src["id"], guid, link, url_hash, title, description, image_url, author, published_at, now_iso()),
            )
            inserted += 1

        status = "OK" if not errors else "WARN"
        conn.execute(
            "UPDATE sources SET last_fetch=?, last_status=?, last_error=? WHERE id=?",
            (now_iso(), status, " | ".join(errors)[:1000], src["id"]),
        )

    return {"source_id": src["id"], "name": src["name"], "inserted": inserted, "seen_existing": updated, "errors": errors}


def fetch_all_sources() -> dict[str, Any]:
    init_db()
    results = []
    with db() as conn:
        sources = conn.execute("SELECT * FROM sources WHERE enabled=1 ORDER BY priority DESC, name ASC").fetchall()
    for source in sources:
        try:
            results.append(fetch_source(source))
        except Exception as e:
            with db() as conn:
                conn.execute("UPDATE sources SET last_fetch=?, last_status='ERROR', last_error=? WHERE id=?", (now_iso(), str(e)[:1000], source["id"]))
            results.append({"source_id": source["id"], "name": source["name"], "inserted": 0, "seen_existing": 0, "errors": [str(e)]})
    return {"fetched_at": now_iso(), "results": results}


class SourceIn(BaseModel):
    name: str
    url: HttpUrl
    category: str = ""
    language: str = ""
    enabled: bool = True
    priority: int = 5


class SourcePatch(BaseModel):
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    category: Optional[str] = None
    language: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class SummarizeIn(BaseModel):
    style: str = "normal"  # normal | 5w1h | language_learning
    force: bool = False


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def root():
    return {"app": APP_NAME, "status": "ok", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "time": now_iso()}


@app.get("/api/sources")
def list_sources():
    init_db()
    with db() as conn:
        rows = conn.execute("SELECT * FROM sources ORDER BY priority DESC, name ASC").fetchall()
    return [row_to_dict(r) for r in rows]


@app.post("/api/sources")
def create_source(payload: SourceIn):
    init_db()
    with db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO sources (name, url, category, language, enabled, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (payload.name.strip(), str(payload.url), payload.category.strip(), payload.language.strip(), int(payload.enabled), payload.priority, now_iso()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Nguồn này đã tồn tại")
        row = conn.execute("SELECT * FROM sources WHERE id=?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.patch("/api/sources/{source_id}")
def update_source(source_id: int, payload: SourcePatch):
    init_db()
    fields = []
    values = []
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if key == "enabled":
            value = int(value)
        if key == "url":
            value = str(value)
        fields.append(f"{key}=?")
        values.append(value)
    if not fields:
        raise HTTPException(status_code=400, detail="Không có dữ liệu cập nhật")
    values.append(source_id)
    with db() as conn:
        conn.execute(f"UPDATE sources SET {', '.join(fields)} WHERE id=?", values)
        row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn")
    return row_to_dict(row)


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    init_db()
    with db() as conn:
        conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
    return {"ok": True}


@app.post("/api/fetch")
def fetch_news():
    return fetch_all_sources()


@app.get("/api/articles")
def list_articles(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=5, le=100),
    source_id: Optional[int] = None,
    q: str = "",
    unread: bool = False,
    saved: bool = False,
    hidden: bool = False,
):
    init_db()
    where = ["a.is_hidden=?"]
    params: list[Any] = [int(hidden)]
    if source_id:
        where.append("a.source_id=?")
        params.append(source_id)
    if q.strip():
        where.append("(a.title LIKE ? OR a.description LIKE ? OR s.name LIKE ? OR s.category LIKE ?)")
        like = f"%{q.strip()}%"
        params.extend([like, like, like, like])
    if unread:
        where.append("a.is_read=0")
    if saved:
        where.append("a.is_saved=1")
    where_sql = " AND ".join(where)
    offset = (page - 1) * limit
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM articles a JOIN sources s ON s.id=a.source_id WHERE {where_sql}",
            params,
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT a.id, a.source_id, a.url, a.title, a.description, a.image_url, a.author,
                   a.published_at, a.fetched_at, a.summary_at, a.is_read, a.is_saved,
                   s.name AS source_name, s.category AS source_category, s.language AS source_language
            FROM articles a
            JOIN sources s ON s.id=a.source_id
            WHERE {where_sql}
            ORDER BY COALESCE(a.published_at, a.fetched_at) DESC, a.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
    return {"page": page, "limit": limit, "total": total, "items": [row_to_dict(r) for r in rows]}


@app.get("/api/articles/{article_id}")
def get_article(article_id: int):
    init_db()
    with db() as conn:
        row = conn.execute(
            """
            SELECT a.*, s.name AS source_name, s.category AS source_category, s.language AS source_language
            FROM articles a JOIN sources s ON s.id=a.source_id WHERE a.id=?
            """,
            (article_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài báo")
    article = row_to_dict(row)
    if (not article.get("content")) or content_is_noisy(article.get("content", "")):
        data = extract_article(article["url"])
        content = data.get("content", "")
        if data.get("image_url") and not article.get("image_url"):
            article["image_url"] = data["image_url"]
        if data.get("title") and len(data["title"]) > len(article.get("title", "")):
            article["title"] = data["title"]
        with db() as conn:
            conn.execute(
                "UPDATE articles SET content=?, content_fetched_at=?, image_url=COALESCE(NULLIF(?, ''), image_url), title=COALESCE(NULLIF(?, ''), title), summary='', summary_model='', summary_at=NULL WHERE id=?",
                (content, now_iso(), article.get("image_url", ""), article.get("title", ""), article_id),
            )
        article["content"] = content
        article["summary"] = ""
        article["summary_model"] = ""
        article["content_fetched_at"] = now_iso()
    return article


@app.post("/api/articles/{article_id}/read")
def mark_read(article_id: int, is_read: bool = True):
    init_db()
    with db() as conn:
        conn.execute("UPDATE articles SET is_read=? WHERE id=?", (int(is_read), article_id))
    return {"ok": True, "is_read": is_read}


@app.post("/api/articles/{article_id}/save")
def mark_saved(article_id: int, is_saved: bool = True):
    init_db()
    with db() as conn:
        conn.execute("UPDATE articles SET is_saved=? WHERE id=?", (int(is_saved), article_id))
    return {"ok": True, "is_saved": is_saved}


@app.post("/api/articles/{article_id}/hide")
def mark_hidden(article_id: int, is_hidden: bool = True):
    init_db()
    with db() as conn:
        conn.execute("UPDATE articles SET is_hidden=? WHERE id=?", (int(is_hidden), article_id))
    return {"ok": True, "is_hidden": is_hidden}



SUMMARY_MODEL_VERSION = "local-clean-v2"


def split_sentences(text: str) -> list[str]:
    text = normalize_text_block(text)
    if not text:
        return []
    # Tách theo câu, nhưng vẫn giữ các bài tiếng Việt/Anh/Trung tương đối ổn.
    raw = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    cleaned = []
    for p in raw:
        p = normalize_text_block(p)
        if not p or is_noise_paragraph(p):
            continue
        if 50 <= len(p) <= 520:
            cleaned.append(p)
        elif len(p) > 520:
            # Đoạn quá dài thường là nhiều câu dính nhau; cắt mềm theo dấu chấm/phẩy.
            pieces = re.split(r"(?<=[.;:。！？])\s+", p)
            cleaned.extend([x.strip() for x in pieces if 50 <= len(x.strip()) <= 520 and not is_noise_paragraph(x.strip())])
    return cleaned[:100]


def tokenize_for_score(text: str) -> list[str]:
    text = (text or "").lower()
    latin = re.findall(r"[a-zà-ỹ0-9]{2,}", text, flags=re.IGNORECASE)
    cjk = re.findall(r"[\u4e00-\u9fff]{1,}", text)
    tokens = latin[:]
    for block in cjk:
        tokens.extend([block[i:i+2] for i in range(max(0, len(block)-1))])
    stop = {
        'và','của','cho','các','một','những','được','trong','khi','với','này','đã','là','có','theo','từ','về','tại','sau','trên','năm','ngày',
        'rằng','thì','như','đó','đây','vào','ra','bị','cũng','đến','nếu','hay','nhiều','ông','bà','anh','chị','theo','thêm','không',
        'the','and','for','that','with','from','this','have','has','was','were','are','but','not','you','they','their','about','after','into','over','said','will','would','could','there','which'
    }
    return [t for t in tokens if t not in stop and len(t) > 1]


def sentence_score(sent: str, idx: int, freq: dict[str, int], title_tokens: set[str]) -> float:
    stoks = tokenize_for_score(sent)
    if not stoks:
        return -999
    score = sum(min(freq.get(t, 0), 8) for t in stoks) / max(10, len(stoks))
    score += max(0, 3.0 - idx * 0.18)  # lead thường quan trọng nhất trong báo
    score += 1.2 * len(title_tokens.intersection(stoks))
    if re.search(r"\d", sent):
        score += 0.45
    if re.search(r"[A-ZÀ-Ỹ][a-zà-ỹ]+\s+[A-ZÀ-Ỹ][a-zà-ỹ]+", sent):
        score += 0.25
    if 90 <= len(sent) <= 360:
        score += 0.7
    if len(sent) > 430:
        score -= 0.9
    low = sent.lower()
    score -= 4.0 * sum(low.count(x) for x in NOISE_PHRASES)
    return score


def pick_important_sentences(title: str, text: str, count: int = 5) -> list[str]:
    sentences = split_sentences(text)
    if not sentences:
        return []
    tokens = tokenize_for_score(text)
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    title_tokens = set(tokenize_for_score(title))
    scored = [(sentence_score(s, i, freq, title_tokens), i, s) for i, s in enumerate(sentences)]
    scored = [x for x in scored if x[0] > -100]
    picked = sorted(scored, reverse=True)[:count]
    picked = [s for _, _, s in sorted(picked, key=lambda x: x[1])]

    final = []
    seen = set()
    for sent in picked:
        sent = normalize_text_block(sent)
        key = re.sub(r"\W+", "", sent.lower())[:150]
        if key and key not in seen and not is_noise_paragraph(sent):
            final.append(sent)
            seen.add(key)
    return final


def make_readable_summary(title: str, source: str, points: list[str], style: str) -> str:
    if not points:
        return "Không lấy được đủ nội dung sạch để tóm tắt. Anh nên mở bài gốc để đọc trực tiếp."

    # Không ghi lộ thuật toán/miễn phí trong phần người dùng đọc.
    intro = f"Tóm tắt nhanh — {source}" if source else "Tóm tắt nhanh"
    lines = [intro]
    if title:
        lines.append(f"Bài viết: {title}")
    lines.append("")

    if style == "5w1h":
        lines.append("Các ý chính cần nắm:")
    elif style == "language_learning":
        lines.append("Nội dung chính:")
    else:
        lines.append("Nội dung chính:")

    # Viết thành các gạch đầu dòng sạch, có liên từ mở đầu nhẹ để đọc đỡ rời rạc.
    connectors = ["Trước hết", "Đồng thời", "Điểm đáng chú ý là", "Bên cạnh đó", "Cuối cùng"]
    for i, p in enumerate(points[:5]):
        prefix = connectors[i] if i < len(connectors) else "Ngoài ra"
        # Không ép biến câu thành văn AI; chỉ nối bằng cụm dẫn để dễ đọc hơn.
        if len(p) < 120:
            lines.append(f"- {prefix}, {p[0].lower() + p[1:] if len(p) > 1 else p}")
        else:
            lines.append(f"- {prefix}, {p}")

    if style == "5w1h":
        joined = " ".join(points)
        nums = re.findall(r"[^.?!。！？]{0,45}\d[^.?!。！？]{0,45}", joined)
        nums = [normalize_text_block(x) for x in nums if not is_noise_paragraph(x)]
        if nums:
            lines.append("")
            lines.append("Số liệu/mốc thời gian nổi bật:")
            for n in nums[:4]:
                lines.append(f"- {n}")

    if style == "language_learning":
        toks = tokenize_for_score(" ".join(points))
        freq: dict[str, int] = {}
        for t in toks:
            freq[t] = freq.get(t, 0) + 1
        vocab = [w for w, c in sorted(freq.items(), key=lambda x: (-x[1], x[0])) if len(w) >= 4][:10]
        if vocab:
            lines.append("")
            lines.append("Từ/cụm từ nổi bật trong bài:")
            for w in vocab:
                lines.append(f"- {w}")

    return "\n".join(lines).strip()


def extractive_summary(article: dict[str, Any], style: str = "normal") -> str:
    title = article.get("title", "") or ""
    source = article.get("source_name", "") or ""
    description = article.get("description", "") or ""
    content = article.get("content", "") or description
    text = normalize_text_block(f"{description}\n\n{content}")
    # Phòng trường hợp nội dung cũ còn dính rác từ bản trước.
    text = re.split(r"(?:Nạp thêm|Tặng sao|Hoàn thành Tặng sao|Quay lại bài viết|Bình luận\s*\(|Được quan tâm nhất)", text, flags=re.IGNORECASE)[0]
    points = pick_important_sentences(title, text, count=6 if style in {"5w1h", "language_learning"} else 5)
    return make_readable_summary(title, source, points, style)

@app.post("/api/articles/{article_id}/summarize")
def summarize_article(article_id: int, payload: SummarizeIn):
    article = get_article(article_id)
    cached_summary = article.get("summary") or ""
    cached_ok = (
        cached_summary
        and article.get("summary_style") == payload.style
        and article.get("summary_model") == SUMMARY_MODEL_VERSION
        and "Ghi chú:" not in cached_summary
        and "Tặng sao" not in cached_summary
        and "Nạp thêm" not in cached_summary
    )
    if cached_ok and not payload.force:
        return {"article_id": article_id, "summary": cached_summary, "cached": True, "style": payload.style}
    if not article.get("content"):
        raise HTTPException(status_code=422, detail="Không có nội dung bài để tóm tắt")
    summary = extractive_summary(article, payload.style)
    with db() as conn:
        conn.execute(
            "UPDATE articles SET summary=?, summary_style=?, summary_model=?, summary_at=? WHERE id=?",
            (summary, payload.style, SUMMARY_MODEL_VERSION, now_iso(), article_id),
        )
    return {"article_id": article_id, "summary": summary, "cached": False, "style": payload.style}


@app.delete("/api/articles")
def clear_articles(days_keep: int = Query(30, ge=1, le=365)):
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_keep)).replace(microsecond=0).isoformat()
    with db() as conn:
        cur = conn.execute("DELETE FROM articles WHERE is_saved=0 AND fetched_at < ?", (cutoff,))
    return {"ok": True, "deleted": cur.rowcount, "kept_days": days_keep}
