// libraries.js - 文档库管理页面逻辑
(function () {
  const $ = Utils.$;

  let libraries = [];
  let currentPage = 1;
  const pageSize = 20;

  // 加载文档库列表
  async function loadLibraries() {
    try {
      Utils.showMessage("librariesMessage", "加载中...", "info");
      const response = await API.fetch("/libraries");
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "加载失败");
      }

      libraries = data.libraries;
      renderLibraries();
      Utils.showMessage("librariesMessage", `加载成功，共 ${data.total} 个文档库`, "success");
    } catch (error) {
      console.error("加载文档库失败:", error);
      Utils.showMessage("librariesMessage", `加载失败: ${error.message}`, "error");
    }
  }

  // 渲染文档库列表
  function renderLibraries() {
    const container = $("libraryList");
    if (!libraries.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📚</div>
          <div class="empty-text">还没有文档库</div>
          <button class="btn btn-primary" onclick="LibrariesPage.showCreateModal()">
            创建第一个文档库
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = libraries
      .map(
        (lib) => `
      <div class="library-card card">
        <div class="library-header">
          <h3 class="library-name">${Utils.escapeHtml(lib.name)}</h3>
          <div class="library-actions">
            <button class="btn btn-sm btn-secondary" onclick="LibrariesPage.editLibrary(${lib.id})">编辑</button>
            <button class="btn btn-sm btn-danger" onclick="LibrariesPage.deleteLibrary(${lib.id})">删除</button>
          </div>
        </div>
        <div class="library-body">
          <p class="library-description">${
            lib.description ? Utils.escapeHtml(lib.description) : "<span class='muted'>暂无描述</span>"
          }</p>
          <div class="library-stats">
            <div class="stat-item">
              <span class="stat-icon">📄</span>
              <span class="stat-value">${lib.document_count}</span>
              <span class="stat-label">文档数量</span>
            </div>
            ${lib.embedding_strategy ? `
              <div class="stat-item">
                <span class="stat-icon">🔤</span>
                <span class="stat-value">${Utils.escapeHtml(lib.embedding_strategy)}</span>
                <span class="stat-label">Embedding</span>
              </div>
            ` : ""}
            ${lib.chunking_strategy ? `
              <div class="stat-item">
                <span class="stat-icon">📝</span>
                <span class="stat-value">${Utils.escapeHtml(lib.chunking_strategy)}</span>
                <span class="stat-label">切分策略</span>
              </div>
            ` : ""}
          </div>
          <div class="library-meta">
            <span class="muted">创建时间: ${new Date(lib.created_at).toLocaleString("zh-CN")}</span>
          </div>
        </div>
      </div>
    `
      )
      .join("");
  }

  // 显示创建模态框
  function showCreateModal() {
    $("libraryForm").reset();
    $("libraryModalTitle").textContent = "创建文档库";
    $("libraryId").value = "";
    Utils.showModal("libraryModal");
  }

  // 编辑文档库
  async function editLibrary(id) {
    const lib = libraries.find((l) => l.id === id);
    if (!lib) {
      Utils.showMessage("librariesMessage", "文档库不存在", "error");
      return;
    }

    $("libraryName").value = lib.name;
    $("libraryDescription").value = lib.description || "";
    $("libraryEmbeddingStrategy").value = lib.embedding_strategy || "";
    $("libraryChunkingStrategy").value = lib.chunking_strategy || "";
    $("libraryId").value = id;
    $("libraryModalTitle").textContent = "编辑文档库";
    Utils.showModal("libraryModal");
  }

  // 删除文档库
  async function deleteLibrary(id) {
    const lib = libraries.find((l) => l.id === id);
    if (!lib) return;

    const docCount = lib.document_count || 0;
    if (docCount > 0) {
      if (
        !confirm(
          `文档库"${lib.name}"包含 ${docCount} 个文档，删除库将同时删除所有文档。\n\n确定要删除吗？`
        )
      ) {
        return;
      }
    } else {
      if (!confirm(`确定要删除文档库"${lib.name}"吗？`)) {
        return;
      }
    }

    try {
      Utils.showMessage("librariesMessage", "删除中...", "info");
      const response = await API.fetch(`/libraries/${id}`, { method: "DELETE" });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "删除失败");
      }

      Utils.showMessage("librariesMessage", "删除成功", "success");
      Utils.hideModal("libraryModal");
      await loadLibraries();
    } catch (error) {
      console.error("删除文档库失败:", error);
      Utils.showMessage("librariesMessage", `删除失败: ${error.message}`, "error");
    }
  }

  // 保存文档库
  async function saveLibrary() {
    const id = $("libraryId").value;
    const isEdit = !!id;

    const payload = {
      name: $("libraryName").value.trim(),
      description: $("libraryDescription").value.trim() || null,
      embedding_strategy: $("libraryEmbeddingStrategy").value || null,
      chunking_strategy: $("libraryChunkingStrategy").value || null,
    };

    if (!payload.name) {
      Utils.showMessage("libraryFormMessage", "请输入库名称", "error");
      return;
    }

    try {
      Utils.showMessage("libraryFormMessage", "保存中...", "info");

      const method = isEdit ? "PUT" : "POST";
      const url = isEdit ? `/libraries/${id}` : "/libraries";
      const response = await API.fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "保存失败");
      }

      Utils.showMessage("libraryFormMessage", "", "success");
      Utils.showMessage("librariesMessage", isEdit ? "更新成功" : "创建成功", "success");
      Utils.hideModal("libraryModal");
      await loadLibraries();
    } catch (error) {
      console.error("保存文档库失败:", error);
      Utils.showMessage("libraryFormMessage", `保存失败: ${error.message}`, "error");
    }
  }

  // 页面初始化
  function init() {
    loadLibraries();

    // 绑定事件
    $("createLibraryBtn").addEventListener("click", showCreateModal);
    $("saveLibraryBtn").addEventListener("click", saveLibrary);
    $("cancelLibraryBtn").addEventListener("click", () => Utils.hideModal("libraryModal"));

    // 模态框关闭时清除消息
    $("libraryModal").addEventListener("modal-hidden", () => {
      $("libraryFormMessage").textContent = "";
      $("libraryForm").reset();
    });
  }

  // 导出全局方法
  window.LibrariesPage = {
    init,
    showCreateModal,
    editLibrary,
    deleteLibrary,
    loadLibraries,
  };

  // 初始化
  init();
})();
