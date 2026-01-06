// documents.js - Document management page
(function () {
  const $ = Utils.$;
  const isAdmin = API.isAdmin();

  let currentPage = 1;
  let currentFilter = "";
  let currentOwnerId = "";
  let selectedDocIds = new Set();
  const docCache = new Map();

  let chunkDoc = null;
  let chunkPage = 1;
  const chunkPageSize = 50;

  const DocumentsPage = {
    init() {
      $("refreshDocsBtn").addEventListener("click", () => {
        this.loadDocuments();
      });

      $("batchDeleteBtn").addEventListener("click", () => {
        this.batchDelete();
      });

      $("statusFilter").addEventListener("change", (e) => {
        currentFilter = e.target.value;
        currentPage = 1;
        this.loadDocuments();
      });

      if (isAdmin) {
        const ownerFilter = $("ownerFilter");
        if (ownerFilter) {
          ownerFilter.addEventListener("change", (e) => {
            currentOwnerId = (e.target.value || "").trim();
            currentPage = 1;
            this.loadDocuments();
          });
        }
        this.loadOwners();
      }

      this.initChunkModal();

      window.addEventListener("pageshow", (e) => {
        if (e.detail?.page === "documents") {
          this.loadDocuments();
        }
      });
    },

    async loadDocuments() {
      Utils.clearMessage("docsMessage");
      try {
        const ownerId = isAdmin && currentOwnerId ? parseInt(currentOwnerId, 10) : null;
        const data = await API.documents.list(currentPage, 20, currentFilter, ownerId);
        this.renderDocuments(data.documents || []);
        this.renderPagination(data.page, data.page_size, data.total);
        $("totalDocs").textContent = data.total ?? 0;
      } catch (error) {
        Utils.showMessage("docsMessage", `加载失败：${error.message}`, "error");
      }
    },

    renderDocuments(documents) {
      const listEl = $("documentList");
      selectedDocIds.clear();
      docCache.clear();
      this.updateBatchDeleteButton();

      if (!documents.length) {
        listEl.innerHTML = '<div class="empty-state">暂无文档</div>';
        $("pagination").innerHTML = "";
        return;
      }

      const headerOwner = isAdmin ? '<th width="110">所属用户</th>' : "";
      const rows = documents
        .map((doc) => {
          docCache.set(Number(doc.id), doc);
          const statusBadge = Utils.getStatusBadge(doc.status);
          const mdBadge = Utils.getMarkdownStatusBadge(doc.markdown_status);
          const safeName = Utils.escapeHtml(doc.document_name || "");
          const ownerCell = isAdmin ? `<td><span class="pill">user_${doc.owner_id}</span></td>` : "";
          const mdAction =
            doc.markdown_status === "markdown_ready"
              ? `<button class="btn btn-sm btn-secondary" onclick="DocumentsPage.downloadMarkdown(${doc.id})">下载 MD</button>`
              : "";
          const uploadMdAction =
            doc.markdown_status === "markdown_ready"
              ? `<button class="btn btn-sm btn-secondary" onclick="DocumentsPage.uploadMarkdown(${doc.id})">上传 MD</button>`
              : "";
          const confirmAction =
            doc.status === "uploaded"
              ? `<button class="btn btn-sm btn-primary" onclick="DocumentsPage.confirmDocument(${doc.id})">确认</button>`
              : "";

          const chunksAction = `<button class="btn btn-sm btn-secondary" onclick="DocumentsPage.openChunks(${doc.id})">Chunks</button>`;

          return `
            <tr data-doc-id="${doc.id}">
              <td>
                <input type="checkbox" class="doc-checkbox" data-id="${doc.id}" />
              </td>
              <td>${doc.id}</td>
              <td class="doc-name" title="${safeName}">${safeName}</td>
              ${ownerCell}
              <td>
                <span class="badge ${statusBadge.class}">${statusBadge.text}</span>
              </td>
              <td>
                <span class="badge ${mdBadge.class}">${mdBadge.text}</span>
              </td>
              <td>${Utils.formatFileSize(doc.size_bytes)}</td>
              <td class="text-small">${Utils.formatDate(doc.created_at)}</td>
              <td class="doc-actions">
                ${mdAction}
                ${uploadMdAction}
                ${confirmAction}
                ${chunksAction}
                <button class="btn btn-sm btn-danger" onclick="DocumentsPage.deleteDocument(${doc.id})">删除</button>
              </td>
            </tr>
          `;
        })
        .join("");

      listEl.innerHTML = `
        <div class="card flat">
          <table class="doc-table">
            <thead>
              <tr>
                <th width="40">
                  <input type="checkbox" id="selectAll" />
                </th>
                <th width="60">ID</th>
                <th>文档名称</th>
                ${headerOwner}
                <th width="100">状态</th>
                <th width="130">Markdown</th>
                <th width="120">大小</th>
                <th width="160">创建时间</th>
                <th width="200">操作</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
      `;

      const selectAllCb = document.getElementById("selectAll");
      if (selectAllCb) {
        selectAllCb.addEventListener("change", (e) => {
          const checkboxes = document.querySelectorAll(".doc-checkbox");
          checkboxes.forEach((cb) => {
            cb.checked = e.target.checked;
            const docId = parseInt(cb.dataset.id, 10);
            if (e.target.checked) {
              selectedDocIds.add(docId);
            } else {
              selectedDocIds.delete(docId);
            }
          });
          this.updateBatchDeleteButton();
        });
      }

      document.querySelectorAll(".doc-checkbox").forEach((cb) => {
        cb.addEventListener("change", (e) => {
          const docId = parseInt(e.target.dataset.id, 10);
          if (e.target.checked) {
            selectedDocIds.add(docId);
          } else {
            selectedDocIds.delete(docId);
          }
          this.updateBatchDeleteButton();
        });
      });
    },

    renderPagination(page, pageSize, total) {
      const paginationEl = $("pagination");
      const totalPages = Math.ceil(total / pageSize);

      if (totalPages <= 1) {
        paginationEl.innerHTML = "";
        return;
      }

      let html = '<div class="pagination-controls">';
      if (page > 1) {
        html += `<button class="btn btn-sm" onclick="DocumentsPage.goToPage(${page - 1})">上一页</button>`;
      }

      html += `<span class="pagination-info">第 ${page} / ${totalPages} 页</span>`;

      if (page < totalPages) {
        html += `<button class="btn btn-sm" onclick="DocumentsPage.goToPage(${page + 1})">下一页</button>`;
      }

      html += "</div>";
      paginationEl.innerHTML = html;
    },

    goToPage(page) {
      currentPage = page;
      this.loadDocuments();
    },

    updateBatchDeleteButton() {
      const btn = $("batchDeleteBtn");
      btn.disabled = selectedDocIds.size === 0;
      btn.textContent = selectedDocIds.size > 0 ? `批量删除 (${selectedDocIds.size})` : "批量删除";
    },

    async deleteDocument(id) {
      if (!confirm("确定要删除此文档吗？该操作不可恢复。")) {
        return;
      }

      try {
        await API.documents.delete(id);
        Utils.showMessage("docsMessage", "删除成功", "success");
        this.loadDocuments();
      } catch (error) {
        Utils.showMessage("docsMessage", `删除失败：${error.message}`, "error");
      }
    },

    async batchDelete() {
      if (selectedDocIds.size === 0) return;

      if (!confirm(`确定要删除选中的 ${selectedDocIds.size} 个文档吗？该操作不可恢复。`)) {
        return;
      }

      try {
        const result = await API.documents.batchDelete(Array.from(selectedDocIds));
        Utils.showMessage("docsMessage", result.message, result.failed_ids.length > 0 ? "warning" : "success");
        selectedDocIds.clear();
        this.loadDocuments();
      } catch (error) {
        Utils.showMessage("docsMessage", `批量删除失败：${error.message}`, "error");
      }
    },

    async downloadMarkdown(id) {
      try {
        const blob = await API.documents.downloadMarkdown(id);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `document_${id}.md`;
        a.click();
        URL.revokeObjectURL(url);
        Utils.showMessage("docsMessage", "Markdown 下载成功", "success");
      } catch (error) {
        Utils.showMessage("docsMessage", `下载失败：${error.message}`, "error");
      }
    },

    async uploadMarkdown(id) {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".md,.markdown,text/markdown";
      input.onchange = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        try {
          Utils.showMessage("docsMessage", "正在上传 Markdown...", "info");
          await API.documents.uploadMarkdown(id, file);
          Utils.showMessage("docsMessage", "Markdown 上传成功", "success");
          this.loadDocuments();
        } catch (error) {
          Utils.showMessage("docsMessage", `上传失败：${error.message}`, "error");
        }
      };
      input.click();
    },

    async confirmDocument(id) {
      if (!confirm("确认提交此文档进入审核流程吗？")) {
        return;
      }
      try {
        await API.documents.confirm(id);
        Utils.showMessage("docsMessage", "已提交审核", "success");
        this.loadDocuments();
      } catch (error) {
        Utils.showMessage("docsMessage", `提交失败：${error.message}`, "error");
      }
    },

    async loadOwners() {
      const ownerFilter = $("ownerFilter");
      if (!ownerFilter) return;

      try {
        const data = await API.admin.listUsers();
        const users = Array.isArray(data?.users) ? data.users : [];

        ownerFilter.innerHTML = '<option value="">全部用户</option>';
        users
          .filter((u) => u && u.is_active)
          .forEach((u) => {
            const opt = document.createElement("option");
            opt.value = String(u.id);
            opt.textContent = `${u.username} (id=${u.id}${u.role === "admin" ? ", admin" : ""})`;
            ownerFilter.appendChild(opt);
          });
      } catch (error) {
        console.warn("Failed to load users:", error);
      }
    },

    initChunkModal() {
      const modal = $("chunkModal");
      if (!modal) return;

      const close = () => {
        modal.classList.add("hidden");
        modal.setAttribute("aria-hidden", "true");
        chunkDoc = null;
        chunkPage = 1;
        Utils.clearMessage("chunkMessage");
        $("chunkList").innerHTML = "";
        $("chunkPagination").innerHTML = "";
        $("chunkAddBox").classList.add("hidden");
        $("newChunkContent").value = "";
      };

      $("chunkModalClose")?.addEventListener("click", close);
      $("chunkModalBackdrop")?.addEventListener("click", close);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !modal.classList.contains("hidden")) close();
      });

      $("toggleAddChunkBtn")?.addEventListener("click", () => {
        $("chunkAddBox").classList.toggle("hidden");
        $("newChunkContent").focus();
      });
      $("cancelAddChunkBtn")?.addEventListener("click", () => {
        $("chunkAddBox").classList.add("hidden");
        $("newChunkContent").value = "";
      });

      $("addChunkBtn")?.addEventListener("click", async () => {
        if (!chunkDoc) return;
        const content = ($("newChunkContent").value || "").trim();
        if (!content) return alert("Chunk 内容不能为空");
        Utils.clearMessage("chunkMessage");
        try {
          Utils.showMessage("chunkMessage", "正在添加 Chunk...", "info");
          await API.chunks.create(chunkDoc.id, content);
          $("newChunkContent").value = "";
          $("chunkAddBox").classList.add("hidden");
          await this.loadChunks();
          Utils.showMessage("chunkMessage", "Chunk 已添加", "success");
        } catch (error) {
          Utils.showMessage("chunkMessage", `添加失败：${error.message}`, "error");
        }
      });

      $("reembedChunksBtn")?.addEventListener("click", async () => {
        if (!chunkDoc) return;
        if (!confirm("将删除该文档在 Milvus 的向量并按当前 Chunk 重建，确定继续？")) return;
        Utils.clearMessage("chunkMessage");
        try {
          Utils.showMessage("chunkMessage", "正在重建向量（可能需要一些时间）...", "info");
          const result = await API.chunks.reembed(chunkDoc.id);
          Utils.showMessage("chunkMessage", `重建完成：${result.reembedded_chunks} 个 Chunk`, "success");
          await this.loadChunks();
        } catch (error) {
          Utils.showMessage("chunkMessage", `重建失败：${error.message}`, "error");
        }
      });

      window.DocumentsPage = DocumentsPage;
      window.DocumentsPage.closeChunks = close;
    },

    async openChunks(documentId) {
      const modal = $("chunkModal");
      if (!modal) return;

      const doc = docCache.get(Number(documentId));
      if (!doc) {
        Utils.showMessage("docsMessage", "无法打开 Chunk：未找到文档信息，请先刷新列表", "warning");
        return;
      }

      await this.openChunksFromDoc(doc);
    },

    async openChunksFromDoc(doc) {
      const modal = $("chunkModal");
      if (!modal) return;

      chunkDoc = doc;
      chunkPage = 1;
      $("chunkDocMeta").textContent = `document_id=${doc.id} · ${doc.document_name || ""} · owner_id=${doc.owner_id}`;
      $("chunkVectorHint").textContent =
        doc.status === "indexed"
          ? "可编辑/新增/删除 chunk，并可同步 Milvus 向量；支持勾选“入库”控制是否参与检索"
          : "文档未入库：可查看/编辑 chunk，并勾选“入库”用于管理员审批时部分入库";

      const reembedBtn = $("reembedChunksBtn");
      if (reembedBtn) reembedBtn.disabled = doc.status !== "indexed";

      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
      await this.loadChunks();
    },

    async loadChunks() {
      if (!chunkDoc) return;
      Utils.clearMessage("chunkMessage");
      try {
        const data = await API.chunks.list(chunkDoc.id, chunkPage, chunkPageSize);
        this.renderChunks(data.chunks || [], data.total ?? 0, data.page ?? chunkPage, data.page_size ?? chunkPageSize);
      } catch (error) {
        Utils.showMessage("chunkMessage", `加载 Chunk 失败：${error.message}`, "error");
      }
    },

    renderChunks(chunks, total, page, pageSize) {
      const listEl = $("chunkList");
      if (!chunks.length) {
        listEl.innerHTML = '<div class="empty-state">暂无 Chunk</div>';
        $("chunkPagination").innerHTML = "";
        return;
      }

      const isIndexed = chunkDoc?.status === "indexed";
      const rows = chunks
        .map((c) => {
          const safe = Utils.escapeHtml(c.content || "");
          const included = c.included !== false;
          return `
            <tr data-chunk-id="${c.id}" data-chunk-index="${c.chunk_index}">
              <td width="70" class="muted mono">#${c.chunk_index}</td>
              <td>
                <label class="chunk-sync">
                  <input type="checkbox" class="include-chunk" ${included ? "checked" : ""} />
                  入库
                </label>
                <div class="chunk-content chunk-view">${safe}</div>
                <textarea class="chunk-edit hidden" rows="6"></textarea>
                <label class="chunk-sync sync-wrap ${isIndexed ? "hidden" : "hidden"}">
                  <input type="checkbox" class="sync-vector" checked />
                  同步向量（仅已入库文档）
                </label>
              </td>
              <td width="220">
                <div class="chunk-actions">
                  <button class="btn btn-sm btn-secondary edit-btn" type="button">编辑</button>
                  <button class="btn btn-sm btn-primary save-btn hidden" type="button">保存</button>
                  <button class="btn btn-sm btn-secondary cancel-btn hidden" type="button">取消</button>
                  <button class="btn btn-sm btn-danger delete-btn" type="button">删除</button>
                </div>
              </td>
            </tr>
          `;
        })
        .join("");

      listEl.innerHTML = `
        <div class="card flat">
          <table class="chunk-table">
            <thead>
              <tr>
                <th width="70">Index</th>
                <th>Content</th>
                <th width="220">Actions</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
      `;

      this.bindChunkRowEvents();
      this.renderChunkPagination(page, pageSize, total);
    },

    bindChunkRowEvents() {
      if (!chunkDoc) return;
      const isIndexed = chunkDoc.status === "indexed";

      document.querySelectorAll("#chunkList tr[data-chunk-id]").forEach((row) => {
        const chunkId = parseInt(row.dataset.chunkId, 10);
        const viewEl = row.querySelector(".chunk-view");
        const editEl = row.querySelector(".chunk-edit");
        const includeCb = row.querySelector(".include-chunk");
        const syncWrap = row.querySelector(".sync-wrap");
        const syncCb = row.querySelector(".sync-vector");
        const editBtn = row.querySelector(".edit-btn");
        const saveBtn = row.querySelector(".save-btn");
        const cancelBtn = row.querySelector(".cancel-btn");
        const delBtn = row.querySelector(".delete-btn");

        if (includeCb) {
          includeCb.addEventListener("change", async () => {
            try {
              Utils.showMessage("chunkMessage", "正在更新入库状态...", "info");
              await API.chunks.update(chunkDoc.id, chunkId, null, false, !!includeCb.checked);
              Utils.showMessage("chunkMessage", "已更新", "success");
            } catch (error) {
              includeCb.checked = !includeCb.checked;
              Utils.showMessage("chunkMessage", `更新失败：${error.message}`, "error");
            }
          });
        }

        const enterEdit = () => {
          editEl.value = (viewEl.textContent || "").trimEnd();
          viewEl.classList.add("hidden");
          editEl.classList.remove("hidden");
          if (isIndexed && syncWrap) syncWrap.classList.remove("hidden");
          editBtn.classList.add("hidden");
          saveBtn.classList.remove("hidden");
          cancelBtn.classList.remove("hidden");
          editEl.focus();
        };

        const exitEdit = () => {
          viewEl.classList.remove("hidden");
          editEl.classList.add("hidden");
          if (syncWrap) syncWrap.classList.add("hidden");
          editBtn.classList.remove("hidden");
          saveBtn.classList.add("hidden");
          cancelBtn.classList.add("hidden");
        };

        editBtn.addEventListener("click", enterEdit);
        cancelBtn.addEventListener("click", exitEdit);

        saveBtn.addEventListener("click", async () => {
          const newContent = (editEl.value || "").trim();
          if (!newContent) return alert("Chunk 内容不能为空");
          try {
            Utils.showMessage("chunkMessage", "正在保存...", "info");
            await API.chunks.update(chunkDoc.id, chunkId, newContent, isIndexed ? !!syncCb.checked : false, includeCb ? !!includeCb.checked : null);
            await this.loadChunks();
            Utils.showMessage("chunkMessage", "已保存", "success");
          } catch (error) {
            Utils.showMessage("chunkMessage", `保存失败：${error.message}`, "error");
          }
        });

        delBtn.addEventListener("click", async () => {
          if (!confirm("确定要删除这个 Chunk 吗？")) return;
          try {
            Utils.showMessage("chunkMessage", "正在删除...", "info");
            await API.chunks.delete(chunkDoc.id, chunkId);
            await this.loadChunks();
            Utils.showMessage("chunkMessage", "已删除", "success");
          } catch (error) {
            Utils.showMessage("chunkMessage", `删除失败：${error.message}`, "error");
          }
        });
      });
    },

    renderChunkPagination(page, pageSize, total) {
      const paginationEl = $("chunkPagination");
      const totalPages = Math.ceil(total / pageSize);
      if (totalPages <= 1) {
        paginationEl.innerHTML = "";
        return;
      }

      let html = '<div class="pagination-controls">';
      if (page > 1) {
        html += `<button class="btn btn-sm" onclick="DocumentsPage.goToChunkPage(${page - 1})">上一页</button>`;
      }

      html += `<span class="pagination-info">第 ${page} / ${totalPages} 页</span>`;

      if (page < totalPages) {
        html += `<button class="btn btn-sm" onclick="DocumentsPage.goToChunkPage(${page + 1})">下一页</button>`;
      }

      html += "</div>";
      paginationEl.innerHTML = html;
    },

    goToChunkPage(page) {
      chunkPage = page;
      this.loadChunks();
    },
  };

  DocumentsPage.init();
  window.DocumentsPage = DocumentsPage;
})();
