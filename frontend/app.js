(() => {
  const API_HOST = window.location.hostname || "localhost";
  const API_BASE = `http://${API_HOST}:8001/api/v1`;

  const $ = (id) => document.getElementById(id);

  const apiBaseEl = $("apiBase");
  apiBaseEl.textContent = API_BASE;

  const tokenKey = "kb_token";
  let token = localStorage.getItem(tokenKey) || "";
  let lastUploadedId = null;

  const decodeJwtPayload = (jwt) => {
    if (!jwt) return null;
    const parts = jwt.split(".");
    if (parts.length < 2) return null;
    let b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    try {
      return JSON.parse(atob(b64));
    } catch {
      return null;
    }
  };

  const syncAuthUi = () => {
    const payload = decodeJwtPayload(token);
    const username = payload?.sub;
    const role = payload?.role;
    $("userStatus").textContent = username ? `${username} (${role || "user"})` : "未登录";
    $("tokenStatus").textContent = token ? token.slice(0, 16) + "..." : "-";

    const reviewTab = document.querySelector('.tab[data-page="review"]');
    const isAdmin = role === "admin";
    if (reviewTab) reviewTab.disabled = !isAdmin;

    const activePage = document.querySelector(".tab.active")?.dataset?.page;
    if (activePage === "review" && !isAdmin) {
      document.querySelector('.tab[data-page="upload"]')?.click();
    }
  };

  const setToken = (value) => {
    token = value || "";
    if (token) localStorage.setItem(tokenKey, token);
    else localStorage.removeItem(tokenKey);
    syncAuthUi();
  };

  setToken(token);
  syncAuthUi();

  let availableModels = [];
  let defaultModel = "qwen2.5:32b";

  const setModels = (models) => {
    const select = $("modelSelect");
    select.innerHTML = "";
    const list = Array.isArray(models) ? models.filter(Boolean) : [];
    availableModels = list.length ? list : ["qwen2.5:32b"];
    defaultModel = availableModels[0] || "qwen2.5:32b";

    availableModels.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
    if (!list.length) {
      $("modelHint").textContent = "Ollama 未安装模型：请先执行 `docker compose exec ollama ollama pull qwen2.5:32b`";
    } else {
      $("modelHint").textContent = `已检测到 Ollama 模型：${list.join(", ")}`;
    }
  };

  // Load health (model list) without auth
  fetch(`${API_BASE}/health`)
    .then((r) => r.json())
    .then((data) => setModels(data?.details?.ollama_models))
    .catch(() => setModels([]));

  const apiFetch = async (path, options = {}) => {
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(`${API_BASE}${path}`, { ...options, headers });
  };

  const requireLogin = () => {
    if (!token) {
      $("authStatus").textContent = "请先登录或注册";
      return false;
    }
    return true;
  };

  const showRegister = (show) => {
    $("registerBox").classList.toggle("hidden", !show);
    $("registerStatus").textContent = "";
    if (show) {
      $("regUsername").value = $("username").value.trim();
      $("regPassword").value = "";
      $("regPassword2").value = "";
      $("regUsername").focus();
    }
  };

  // Tabs
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const page = btn.dataset.page;
      ["upload", "review", "query"].forEach((p) => {
        $(`page-${p}`).classList.toggle("hidden", p !== page);
      });
    });
  });

  // Login / logout
  $("loginBtn").addEventListener("click", async () => {
    $("authStatus").textContent = "";
    try {
      const username = $("username").value.trim();
      const password = $("password").value;
      if (!username || !password) {
        throw new Error("请输入用户名和密码");
      }
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setToken(data.access_token);
      $("authStatus").textContent = "登录成功";
    } catch (e) {
      setToken("");
      $("authStatus").textContent = `登录失败：${e}`;
    }
  });

  $("logoutBtn").addEventListener("click", () => {
    setToken("");
    $("authStatus").textContent = "已退出";
  });

  $("showRegisterBtn").addEventListener("click", () => {
    showRegister(true);
  });

  $("cancelRegisterBtn").addEventListener("click", () => {
    showRegister(false);
  });

  $("registerBtn").addEventListener("click", async () => {
    $("registerStatus").textContent = "";
    try {
      const username = $("regUsername").value.trim();
      const password = $("regPassword").value;
      const password2 = $("regPassword2").value;

      if (!username) throw new Error("用户名不能为空");
      if (password.length < 6) throw new Error("密码至少6位");
      if (password !== password2) throw new Error("两次输入的密码不一致");

      const resp = await fetch(`${API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const txt = await resp.text();
      if (!resp.ok) throw new Error(txt);
      const data = JSON.parse(txt);
      setToken(data.access_token);
      $("username").value = username;
      $("password").value = password;
      $("authStatus").textContent = "注册成功，已自动登录";
      showRegister(false);
    } catch (e) {
      $("registerStatus").textContent = `注册失败：${e}`;
    }
  });

  // Upload
  $("uploadBtn").addEventListener("click", async () => {
    $("uploadStatus").textContent = "";
    $("previewBox").textContent = "";
    $("confirmBtn").disabled = true;
    lastUploadedId = null;

    if (!requireLogin()) return;
    const file = $("fileInput").files?.[0];
    if (!file) return alert("请选择PDF或DOCX文件");
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await apiFetch("/documents/upload", { method: "POST", body: form });
      const txt = await resp.text();
      if (!resp.ok) throw new Error(txt);
      const data = JSON.parse(txt);
      lastUploadedId = data.document_id;
      $("uploadStatus").textContent = `上传成功：document_id=${data.document_id}，status=${data.status}`;
      $("previewBox").textContent = data.preview || "(无预览内容)";
      $("confirmBtn").disabled = false;
    } catch (e) {
      $("uploadStatus").textContent = `上传失败：${e}`;
    }
  });

  $("confirmBtn").addEventListener("click", async () => {
    if (!lastUploadedId) return;
    if (!requireLogin()) return;
    try {
      const resp = await apiFetch(`/documents/confirm/${lastUploadedId}`, { method: "POST" });
      const txt = await resp.text();
      if (!resp.ok) throw new Error(txt);
      const data = JSON.parse(txt);
      $("uploadStatus").textContent = `已提交审核：document_id=${data.document_id}，status=${data.status}`;
      $("confirmBtn").disabled = true;
    } catch (e) {
      $("uploadStatus").textContent = `提交失败：${e}`;
    }
  });

  // Review
  const renderPending = (docs) => {
    const root = $("pendingList");
    root.innerHTML = "";
    if (!docs?.length) {
      root.innerHTML = `<div class="muted">暂无待审核文档</div>`;
      return;
    }
    docs.forEach((doc) => {
      const el = document.createElement("div");
      el.className = "doc-item";
      el.innerHTML = `
        <div class="doc-title">#${doc.id} ${doc.document_name}</div>
        <div class="muted small">状态：${doc.status}</div>
        <pre class="preview">${(doc.preview || "").slice(0, 600) || "(无预览)"}</pre>
        <div class="doc-actions">
          <button data-action="approve">审核通过</button>
          <button class="secondary" data-action="reject">审核拒绝</button>
        </div>
      `;
      el.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const action = btn.dataset.action;
          try {
            if (action === "approve") {
              const resp = await apiFetch(`/review/approve/${doc.id}`, { method: "POST" });
              const txt = await resp.text();
              if (!resp.ok) throw new Error(txt);
              $("reviewStatus").textContent = `已通过并索引：#${doc.id}`;
            } else {
              const reason = prompt("请输入拒绝原因：", "内容不符合要求") || "";
              if (!reason.trim()) return;
              const resp = await apiFetch(`/review/reject/${doc.id}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reason }),
              });
              const txt = await resp.text();
              if (!resp.ok) throw new Error(txt);
              $("reviewStatus").textContent = `已拒绝：#${doc.id}`;
            }
            await refreshPending();
          } catch (e) {
            $("reviewStatus").textContent = `操作失败：${e}`;
          }
        });
      });
      root.appendChild(el);
    });
  };

  const refreshPending = async () => {
    $("reviewStatus").textContent = "加载中...";
    if (!requireLogin()) {
      $("reviewStatus").textContent = "请先用管理员账号登录";
      return;
    }
    try {
      const resp = await apiFetch("/review/pending", { method: "GET" });
      const txt = await resp.text();
      if (!resp.ok) throw new Error(txt);
      const data = JSON.parse(txt);
      renderPending(data.documents || []);
      $("reviewStatus").textContent = "";
    } catch (e) {
      $("reviewStatus").textContent = `加载失败：${e}`;
    }
  };

  $("refreshPendingBtn").addEventListener("click", refreshPending);

  // Query
  $("queryBtn").addEventListener("click", async () => {
    $("queryStatus").textContent = "";
    $("answerBox").textContent = "";
    $("sourcesBox").innerHTML = "";
    const query = $("queryInput").value.trim();
    if (!query) return;
    if (!requireLogin()) return;
    try {
      $("queryStatus").textContent = "查询中...";
      const topK = Number($("topKInput").value || 5);
      const temperature = Number($("temperatureInput").value || 0.7);
      const model = $("modelSelect").value || defaultModel;
      const resp = await apiFetch("/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: topK, model, temperature }),
      });
      const txt = await resp.text();
      if (!resp.ok) throw new Error(txt);
      const data = JSON.parse(txt);
      $("answerBox").textContent = data.answer || "";
      const sources = data.sources || [];
      const box = document.createElement("div");
      box.className = "sources";
      box.innerHTML =
        `<div class="muted small">来源（confidence=${data.confidence ?? 0}）：</div>` +
        sources
          .map(
            (s) =>
              `<div><code>${s.document_name}</code> · chunk=${s.chunk_index} · score=${Number(s.relevance).toFixed(
                4
              )}</div>`
          )
          .join("");
      $("sourcesBox").appendChild(box);
      $("queryStatus").textContent = "";
    } catch (e) {
      $("queryStatus").textContent = `查询失败：${e}`;
    }
  });
})();
