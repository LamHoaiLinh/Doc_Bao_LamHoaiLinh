const API_BASE = (window.NEWS_RADAR_API_BASE || "http://localhost:8000").replace(/\/$/, "");

const state = {
  tab: "feed",
  page: 1,
  limit: 20,
  total: 0,
  articles: [],
  sources: [],
  currentArticleId: null,
  currentArticleIndex: -1,
  settings: loadSettings(),
};

const $ = (id) => document.getElementById(id);

function api(path, options = {}) {
  return fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  }).then(async (res) => {
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);
    return data;
  });
}

function showToast(message, ms = 2600) {
  const el = $("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => el.classList.add("hidden"), ms);
}

function scrollTopSmooth() {
  window.scrollTo({ top: 0, behavior: "smooth" });
  const reader = $("reader");
  if (!reader.classList.contains("hidden")) reader.scrollTo({ top: 0, behavior: "smooth" });
}

function fmtDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(d);
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function hostname(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}

function loadSettings() {
  const defaults = {
    fontSize: 17,
    lineHeight: 1.7,
    textColor: "#111827",
    bgColor: "#f5f7fb",
    imageMode: "large",
    fontFamily: "system",
  };
  try { return { ...defaults, ...JSON.parse(localStorage.getItem("newsRadarSettings") || "{}") }; }
  catch { return defaults; }
}

function saveSettings() {
  localStorage.setItem("newsRadarSettings", JSON.stringify(state.settings));
}

function applySettings() {
  const s = state.settings;
  const root = document.documentElement;
  root.style.setProperty("--font-size", `${s.fontSize}px`);
  root.style.setProperty("--line-height", s.lineHeight);
  root.style.setProperty("--text", s.textColor);
  root.style.setProperty("--bg", s.bgColor);
  const fam = {
    system: 'system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
    serif: 'Georgia,"Times New Roman",serif',
    mono: 'ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace',
  }[s.fontFamily] || s.fontFamily;
  root.style.setProperty("--font-family", fam);
  document.body.classList.toggle("image-small", s.imageMode === "small");
  document.body.classList.toggle("image-hide", s.imageMode === "hide");
  $("fontSize").value = s.fontSize;
  $("lineHeight").value = s.lineHeight;
  $("textColor").value = s.textColor;
  $("bgColor").value = s.bgColor;
  $("imageMode").value = s.imageMode;
  $("fontFamily").value = s.fontFamily;
}

async function loadSources() {
  state.sources = await api("/api/sources");
  renderSourceFilter();
  renderSources();
}

function renderSourceFilter() {
  const select = $("sourceFilter");
  const current = select.value;
  select.innerHTML = `<option value="">Tất cả nguồn</option>` + state.sources
    .map(s => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("");
  select.value = current;
}

async function loadArticles(savedOnly = false) {
  const q = encodeURIComponent($("searchInput").value.trim());
  const sourceId = $("sourceFilter").value;
  const unread = $("unreadOnly").checked;
  const params = new URLSearchParams({ page: state.page, limit: state.limit });
  if (q) params.set("q", q);
  if (sourceId) params.set("source_id", sourceId);
  if (unread) params.set("unread", "true");
  if (savedOnly) params.set("saved", "true");
  const data = await api(`/api/articles?${params.toString()}`);
  state.total = data.total;
  state.articles = data.items || [];
  if (savedOnly) renderArticles($("savedList"), state.articles);
  else renderArticles($("articleList"), state.articles);
  renderPager();
}

function renderPager() {
  const maxPage = Math.max(1, Math.ceil(state.total / state.limit));
  $("pageInfo").textContent = `Trang ${state.page}/${maxPage} • ${state.total} tin`;
  $("prevPage").disabled = state.page <= 1;
  $("nextPage").disabled = state.page >= maxPage;
}

function renderArticles(container, articles) {
  if (!articles.length) {
    container.innerHTML = `<div class="note-box">Chưa có tin phù hợp. Bấm “↻” để quét tin mới hoặc thêm nguồn RSS.</div>`;
    return;
  }
  container.innerHTML = articles.map((a, idx) => {
    const img = a.image_url ? `<img class="card-image" src="${escapeHtml(a.image_url)}" loading="lazy" alt="" onerror="this.style.display='none'"/>` : "";
    return `<article class="article-card ${a.is_read ? "read" : ""}" data-id="${a.id}" data-index="${idx}">
      <div class="card-body">
        ${img}
        <div class="card-main">
          <div class="card-meta">
            <span>${escapeHtml(a.source_name || hostname(a.url))}</span>
            <span>${escapeHtml(a.source_category || "")}</span>
            <span>${fmtDate(a.published_at || a.fetched_at)}</span>
            ${a.summary_at ? `<span>Đã tóm tắt</span>` : ""}
          </div>
          <h2 class="card-title">${escapeHtml(a.title)}</h2>
          <p class="card-desc">${escapeHtml(a.description || "")}</p>
        </div>
      </div>
      <div class="card-actions">
        <button class="btn" data-action="read">Đọc</button>
        <button class="btn secondary" data-action="summary">Tóm tắt</button>
        <button class="btn secondary" data-action="save">${a.is_saved ? "Bỏ lưu" : "Lưu"}</button>
        <button class="btn secondary" data-action="original">Báo gốc</button>
      </div>
    </article>`;
  }).join("");
}

function renderSources() {
  const box = $("sourceList");
  if (!state.sources.length) {
    box.innerHTML = `<div class="note-box">Chưa có nguồn báo.</div>`;
    return;
  }
  box.innerHTML = state.sources.map(s => `<div class="source-item">
    <div class="source-head">
      <div>
        <div class="source-name">${escapeHtml(s.name)}</div>
        <div class="source-url">${escapeHtml(s.url)}</div>
        <div class="source-tags">${escapeHtml(s.category || "Chưa phân nhóm")} • ${escapeHtml(s.language || "ngôn ngữ chưa đặt")} • ${s.enabled ? "Đang bật" : "Đang tắt"}</div>
        <div class="source-tags">Lần quét: ${s.last_fetch ? fmtDate(s.last_fetch) : "chưa có"} ${s.last_status ? "• " + escapeHtml(s.last_status) : ""}</div>
        ${s.last_error ? `<div class="source-tags">Lỗi: ${escapeHtml(s.last_error)}</div>` : ""}
      </div>
    </div>
    <div class="source-actions">
      <button class="btn secondary" data-source-action="toggle" data-id="${s.id}">${s.enabled ? "Tắt" : "Bật"}</button>
      <button class="btn danger" data-source-action="delete" data-id="${s.id}">Xóa</button>
    </div>
  </div>`).join("");
}

async function fetchNews() {
  $("feedStatus").textContent = "Đang quét RSS từ các nguồn báo...";
  $("btnRefresh").disabled = true;
  try {
    const res = await api("/api/fetch", { method: "POST" });
    const count = (res.results || []).reduce((sum, r) => sum + (r.inserted || 0), 0);
    showToast(`Đã quét xong: thêm ${count} tin mới.`);
    await loadSources();
    state.page = 1;
    await loadArticles(false);
  } catch (e) {
    showToast(e.message, 5000);
  } finally {
    $("feedStatus").textContent = "Sẵn sàng.";
    $("btnRefresh").disabled = false;
  }
}

async function openArticle(articleId, index = -1, autoSummary = false) {
  state.currentArticleId = articleId;
  state.currentArticleIndex = index;
  $("reader").classList.remove("hidden");
  $("readerMeta").textContent = "Đang tải bài...";
  $("readerTitle").textContent = "";
  $("readerContent").textContent = "";
  $("summaryBox").classList.add("hidden");
  scrollTopSmooth();
  try {
    const article = await api(`/api/articles/${articleId}`);
    await api(`/api/articles/${articleId}/read?is_read=true`, { method: "POST" });
    $("readerMeta").textContent = `${article.source_name || hostname(article.url)} • ${fmtDate(article.published_at || article.fetched_at)}`;
    $("readerTitle").textContent = article.title || "Không có tiêu đề";
    $("readerImage").src = article.image_url || "";
    $("readerContent").textContent = article.content || article.description || "Không lấy được nội dung đầy đủ. Anh có thể bấm mở báo gốc.";
    $("readerOpenOriginal").onclick = () => window.open(article.url, "_blank", "noopener,noreferrer");
    $("readerSave").textContent = article.is_saved ? "Bỏ lưu" : "Lưu";
    $("readerSave").onclick = async () => {
      await api(`/api/articles/${articleId}/save?is_saved=${!article.is_saved}`, { method: "POST" });
      showToast(!article.is_saved ? "Đã lưu bài." : "Đã bỏ lưu.");
      await loadArticles(state.tab === "saved");
    };
    $("readerSummary").onclick = () => summarizeCurrent();
    if (article.summary && !article.summary.includes("Ghi chú:") && !article.summary.includes("Tặng sao") && !article.summary.includes("Nạp thêm")) {
      $("summaryBox").textContent = article.summary;
      $("summaryBox").classList.remove("hidden");
    }
    if (autoSummary) await summarizeCurrent();
  } catch (e) {
    $("readerMeta").textContent = "Lỗi";
    $("readerContent").textContent = e.message;
  }
}

async function summarizeCurrent() {
  if (!state.currentArticleId) return;
  const style = $("summaryStyle").value;
  $("summaryBox").classList.remove("hidden");
  $("summaryBox").textContent = "Đang tạo bản tóm tắt sạch...";
  try {
    const res = await api(`/api/articles/${state.currentArticleId}/summarize`, {
      method: "POST",
      body: JSON.stringify({ style, force: true }),
    });
    $("summaryBox").textContent = res.summary;
    showToast(res.cached ? "Đã mở tóm tắt đã lưu." : "Đã tóm tắt xong.");
    await loadArticles(state.tab === "saved");
  } catch (e) {
    $("summaryBox").textContent = e.message;
  }
}

function openNeighbor(delta) {
  const nextIndex = state.currentArticleIndex + delta;
  if (nextIndex < 0 || nextIndex >= state.articles.length) {
    showToast("Hết bài trong trang hiện tại. Anh bấm Trang sau để tải thêm.");
    return;
  }
  const article = state.articles[nextIndex];
  openArticle(article.id, nextIndex, false);
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
      document.querySelectorAll(".panel").forEach(x => x.classList.remove("active"));
      btn.classList.add("active");
      state.tab = btn.dataset.tab;
      $(state.tab).classList.add("active");
      scrollTopSmooth();
      if (state.tab === "saved") {
        state.page = 1;
        await loadArticles(true);
      }
      if (state.tab === "sources") await loadSources();
    });
  });

  $("btnRefresh").addEventListener("click", fetchNews);
  $("searchInput").addEventListener("input", debounce(async () => { state.page = 1; await loadArticles(false); }, 450));
  $("sourceFilter").addEventListener("change", async () => { state.page = 1; await loadArticles(false); scrollTopSmooth(); });
  $("unreadOnly").addEventListener("change", async () => { state.page = 1; await loadArticles(false); scrollTopSmooth(); });
  $("prevPage").addEventListener("click", async () => { if (state.page > 1) { state.page--; await loadArticles(false); scrollTopSmooth(); } });
  $("nextPage").addEventListener("click", async () => { const max = Math.ceil(state.total / state.limit); if (state.page < max) { state.page++; await loadArticles(false); scrollTopSmooth(); } });

  document.addEventListener("click", async (e) => {
    const action = e.target.dataset.action;
    if (action) {
      const card = e.target.closest(".article-card");
      const id = Number(card.dataset.id);
      const index = Number(card.dataset.index);
      const article = state.articles[index];
      if (action === "read") openArticle(id, index, false);
      if (action === "summary") openArticle(id, index, true);
      if (action === "original") window.open(article.url, "_blank", "noopener,noreferrer");
      if (action === "save") {
        await api(`/api/articles/${id}/save?is_saved=${!article.is_saved}`, { method: "POST" });
        showToast(!article.is_saved ? "Đã lưu bài." : "Đã bỏ lưu.");
        await loadArticles(state.tab === "saved");
      }
    }

    const sourceAction = e.target.dataset.sourceAction;
    if (sourceAction) {
      const id = Number(e.target.dataset.id);
      const source = state.sources.find(s => s.id === id);
      if (!source) return;
      if (sourceAction === "toggle") {
        await api(`/api/sources/${id}`, { method: "PATCH", body: JSON.stringify({ enabled: !source.enabled }) });
        await loadSources();
      }
      if (sourceAction === "delete") {
        if (!confirm("Xóa nguồn này? Tin đã lấy cũ vẫn còn trong kho.")) return;
        await api(`/api/sources/${id}`, { method: "DELETE" });
        await loadSources();
      }
    }
  });

  $("sourceForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      name: $("sourceName").value.trim(),
      url: $("sourceUrl").value.trim(),
      category: $("sourceCategory").value.trim(),
      language: $("sourceLanguage").value.trim(),
      enabled: true,
      priority: 5,
    };
    try {
      await api("/api/sources", { method: "POST", body: JSON.stringify(payload) });
      e.target.reset();
      await loadSources();
      showToast("Đã thêm nguồn báo.");
    } catch (err) { showToast(err.message, 5000); }
  });

  $("closeReader").addEventListener("click", () => { $("reader").classList.add("hidden"); loadArticles(state.tab === "saved"); });
  $("prevArticle").addEventListener("click", () => openNeighbor(-1));
  $("nextArticle").addEventListener("click", () => openNeighbor(1));

  ["fontSize", "lineHeight", "textColor", "bgColor", "imageMode", "fontFamily"].forEach(id => {
    $(id).addEventListener("input", () => {
      state.settings[id] = id === "fontSize" ? Number($(id).value) : $(id).value;
      if (id === "lineHeight") state.settings[id] = Number($(id).value);
      saveSettings(); applySettings();
    });
  });
  $("resetSettings").addEventListener("click", () => { localStorage.removeItem("newsRadarSettings"); state.settings = loadSettings(); applySettings(); });
}

function debounce(fn, wait) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
}

async function boot() {
  applySettings();
  bindEvents();
  try {
    await loadSources();
    await loadArticles(false);
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  } catch (e) {
    showToast(`Không kết nối được backend: ${e.message}`, 6000);
    $("articleList").innerHTML = `<div class="note-box">Không kết nối được backend. Kiểm tra API_BASE trong file config.js: <b>${escapeHtml(API_BASE)}</b></div>`;
  }
}

boot();
