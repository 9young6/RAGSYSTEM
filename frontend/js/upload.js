// upload.js - Document upload and Markdown editing
(function () {
  const $ = Utils.$;

  let currentDocId = null;
  let markdownCheckInterval = null;

  const UploadPage = {
    init() {
      const uploadBox = $("uploadBox");
      const fileInput = $("fileInput");

      uploadBox.addEventListener("click", () => fileInput.click());

      fileInput.addEventListener("change", (e) => {
        const file = e.target.files?.[0];
        if (file) this.uploadFile(file);
      });

      uploadBox.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadBox.classList.add("drag-over");
      });
      uploadBox.addEventListener("dragleave", () => uploadBox.classList.remove("drag-over"));
      uploadBox.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadBox.classList.remove("drag-over");
        const file = e.dataTransfer.files?.[0];
        if (file) this.uploadFile(file);
      });

      $("downloadMarkdownBtn").addEventListener("click", () => this.downloadMarkdown());
      $("uploadMarkdownBtn").addEventListener("click", () => this.showMarkdownUploadDialog());
      $("convertMarkdownBtn").addEventListener("click", () => this.convertMarkdown());
      $("confirmDocBtn").addEventListener("click", () => this.confirmDocument());

      window.addEventListener("pageshow", (e) => {
        if (e.detail?.page !== "upload") {
          this.clearMarkdownCheck();
        }
      });
    },

    async uploadFile(file) {
      Utils.clearMessage("uploadStatus");
      $("uploadPreview").classList.add("hidden");
      this.clearMarkdownCheck();

      const fileExt = "." + (file.name.split(".").pop() || "").toLowerCase();
      const allowed = [".pdf", ".docx", ".xlsx", ".csv", ".md", ".markdown", ".txt", ".json"];
      if (!allowed.includes(fileExt)) {
        Utils.showMessage("uploadStatus", "支持 PDF / DOCX / XLSX / CSV / MD / TXT / JSON", "error");
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        Utils.showMessage("uploadStatus", "文件不能超过 50MB", "error");
        return;
      }

      try {
        Utils.showMessage("uploadStatus", "上传中...", "info");
        const result = await API.documents.upload(file);
        currentDocId = result.document_id;
        Utils.showMessage("uploadStatus", "上传成功，正在转换 Markdown...", "success");
        this.showPreview(result);
        this.startMarkdownCheck();
      } catch (error) {
        Utils.showMessage("uploadStatus", `上传失败：${error.message}`, "error");
      }
    },

    showPreview(data) {
      $("previewFilename").textContent = data.document_name || "-";
      $("previewDocId").textContent = String(data.document_id ?? "-");
      $("previewStatus").textContent = data.status || "-";
      $("previewMarkdownStatus").textContent = "转换中";
      $("previewContent").textContent = data.preview || "(无预览内容)";

      $("downloadMarkdownBtn").disabled = true;
      $("uploadMarkdownBtn").disabled = true;
      $("convertMarkdownBtn").disabled = false;

      $("uploadPreview").classList.remove("hidden");
    },

    startMarkdownCheck() {
      this.clearMarkdownCheck();
      this.checkMarkdownStatus();
      markdownCheckInterval = setInterval(() => this.checkMarkdownStatus(), 2500);
    },

    clearMarkdownCheck() {
      if (markdownCheckInterval) {
        clearInterval(markdownCheckInterval);
        markdownCheckInterval = null;
      }
    },

    async checkMarkdownStatus() {
      if (!currentDocId) return;

      try {
        const result = await API.documents.getMarkdownStatus(currentDocId);
        const status = result.markdown_status;

        $("previewMarkdownStatus").textContent = Utils.getMarkdownStatusBadge(status).text;

        if (status === "markdown_ready") {
          this.clearMarkdownCheck();
          $("downloadMarkdownBtn").disabled = false;
          $("uploadMarkdownBtn").disabled = false;
          $("convertMarkdownBtn").disabled = true;
          Utils.showMessage("uploadStatus", "Markdown 转换完成，可下载/编辑后上传。", "success");
        } else if (status === "failed") {
          this.clearMarkdownCheck();
          Utils.showMessage(
            "uploadStatus",
            `Markdown 转换失败：${result.markdown_error || "未知错误"}（可手动上传 Markdown 继续）`,
            "warning"
          );
          $("uploadMarkdownBtn").disabled = false;
          $("convertMarkdownBtn").disabled = false;
        } else {
          // pending/processing
          $("convertMarkdownBtn").disabled = false;
        }
      } catch (error) {
        // Avoid spamming UI for transient errors.
        console.debug("Failed to check markdown status:", error);
      }
    },

    async convertMarkdown() {
      if (!currentDocId) return;
      try {
        Utils.showMessage("uploadStatus", "已提交转换任务，请稍候...", "info");
        await API.documents.convertMarkdown(currentDocId);
        this.startMarkdownCheck();
      } catch (error) {
        Utils.showMessage("uploadStatus", `触发转换失败：${error.message}`, "error");
      }
    },

    async downloadMarkdown() {
      if (!currentDocId) return;
      try {
        const blob = await API.documents.downloadMarkdown(currentDocId);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `document_${currentDocId}.md`;
        a.click();
        URL.revokeObjectURL(url);
        Utils.showMessage("uploadStatus", "Markdown 已下载", "success");
      } catch (error) {
        Utils.showMessage("uploadStatus", `下载失败：${error.message}`, "error");
      }
    },

    showMarkdownUploadDialog() {
      if (!currentDocId) return;
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".md,.markdown,text/markdown";
      input.onchange = async (e) => {
        const file = e.target.files?.[0];
        if (file) await this.uploadMarkdown(file);
      };
      input.click();
    },

    async uploadMarkdown(file) {
      if (!currentDocId) return;
      try {
        Utils.showMessage("uploadStatus", "上传 Markdown 中...", "info");
        await API.documents.uploadMarkdown(currentDocId, file);
        $("previewMarkdownStatus").textContent = "已上传";
        Utils.showMessage("uploadStatus", "Markdown 上传成功，可提交审核。", "success");
      } catch (error) {
        Utils.showMessage("uploadStatus", `上传失败：${error.message}`, "error");
      }
    },

    async confirmDocument() {
      if (!currentDocId) return;
      if (!confirm("确认提交此文档进入审核流程吗？")) return;
      try {
        await API.documents.confirm(currentDocId);
        Utils.showMessage("uploadStatus", "已提交审核，等待管理员审批并索引。", "success");
        this.clearMarkdownCheck();
        setTimeout(() => {
          currentDocId = null;
          $("uploadPreview").classList.add("hidden");
          $("fileInput").value = "";
        }, 1200);
      } catch (error) {
        Utils.showMessage("uploadStatus", `提交失败：${error.message}`, "error");
      }
    },
  };

  UploadPage.init();
  window.UploadPage = UploadPage;
})();
