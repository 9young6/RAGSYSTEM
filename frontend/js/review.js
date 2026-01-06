// review.js - Document review page (Admin only)
(function () {
  const $ = Utils.$;

  const ReviewPage = {
    init() {
      $("refreshReviewBtn").addEventListener("click", () => this.loadPendingReviews());

      window.addEventListener("pageshow", (e) => {
        if (e.detail?.page === "review") {
          if (API.isAdmin()) {
            this.loadPendingReviews();
          } else {
            Utils.showMessage("reviewMessage", "您不是管理员，无法访问此页面", "error");
          }
        }
      });
    },

    async loadPendingReviews() {
      Utils.clearMessage("reviewMessage");

      if (!API.isAdmin()) {
        Utils.showMessage("reviewMessage", "需要管理员权限", "error");
        return;
      }

      try {
        const result = await API.review.getPending();
        this.renderReviews(result.documents || []);
      } catch (error) {
        Utils.showMessage("reviewMessage", `加载失败：${error.message}`, "error");
      }
    },

    renderReviews(documents) {
      const listEl = $("reviewList");
      listEl.innerHTML = "";

      if (!documents.length) {
        listEl.innerHTML = '<div class="empty-state">暂无待审核文档</div>';
        return;
      }

      documents.forEach((doc) => {
        const reviewItem = document.createElement("div");
        const name = Utils.escapeHtml(doc.document_name || "-");
        const statusBadge = Utils.getStatusBadge(doc.status);
        const mdBadge = Utils.getMarkdownStatusBadge(doc.markdown_status);
        const owner = doc.owner_id ? `user_${doc.owner_id}` : "-";
        const chunkCount = typeof doc.chunk_count === "number" ? doc.chunk_count : null;
        const preview = Utils.escapeHtml((doc.preview || "").slice(0, 400));
        const chunksBtnDisabled = doc.markdown_status !== "markdown_ready";

        reviewItem.className = "review-item card";
        reviewItem.innerHTML = `
          <div class="review-header">
            <span class="doc-id">#${doc.id}</span>
            <span class="doc-name" title="${name}">${name}</span>
            <span class="doc-owner muted">Owner: ${owner}</span>
            <span class="doc-status">
              <span class="badge ${statusBadge.class}">${statusBadge.text}</span>
              <span class="badge ${mdBadge.class}">${mdBadge.text}</span>
            </span>
          </div>
          <div class="muted small">Chunks: ${chunkCount === null ? "-" : chunkCount}</div>
          <div class="review-preview">
            <pre>${preview || "(无预览内容)"}</pre>
          </div>
          <div class="review-actions">
            <button class="btn btn-success" onclick="ReviewPage.approveDocument(${doc.id})">审批通过（按入库选择）</button>
            <button class="btn btn-danger" onclick="ReviewPage.rejectDocument(${doc.id})">拒绝</button>
          </div>
        `;
        listEl.appendChild(reviewItem);

        const actions = reviewItem.querySelector(".review-actions");
        if (actions) {
          const btn = document.createElement("button");
          btn.className = "btn btn-secondary";
          btn.textContent = chunksBtnDisabled ? "Chunks（等待转换）" : `Chunks（选择入库）`;
          btn.disabled = !!chunksBtnDisabled;
          btn.addEventListener("click", () => this.openChunks(doc));
          actions.prepend(btn);
        }
      });
    },

    async openChunks(doc) {
      if (!API.isAdmin()) return;
      if (doc.markdown_status !== "markdown_ready") {
        Utils.showMessage("reviewMessage", "Markdown 未完成转换，无法查看 chunks", "warning");
        return;
      }
      if (!window.DocumentsPage?.openChunksFromDoc) {
        Utils.showMessage("reviewMessage", "Chunks 模态框未就绪，请刷新页面后重试", "warning");
        return;
      }
      await window.DocumentsPage.openChunksFromDoc(doc);
    },

    async approveDocument(id) {
      if (!confirm("确定审批通过并索引该文档吗？仅 included=true 的 chunks 会入库。")) return;

      try {
        const result = await API.review.approve(id);
        Utils.showMessage("reviewMessage", `文档 #${id} 已审批（${result.status}）`, "success");
        this.loadPendingReviews();
      } catch (error) {
        Utils.showMessage("reviewMessage", `审批失败：${error.message}`, "error");
      }
    },

    async rejectDocument(id) {
      const reason = prompt("请输入拒绝原因：", "内容不符合要求");
      if (reason === null) return;
      if (!reason.trim()) {
        Utils.showMessage("reviewMessage", "拒绝原因不能为空", "warning");
        return;
      }

      try {
        await API.review.reject(id, reason);
        Utils.showMessage("reviewMessage", `文档 #${id} 已拒绝`, "info");
        this.loadPendingReviews();
      } catch (error) {
        Utils.showMessage("reviewMessage", `拒绝失败：${error.message}`, "error");
      }
    },
  };

  ReviewPage.init();
  window.ReviewPage = ReviewPage;
})();
