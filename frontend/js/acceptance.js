// acceptance.js - Acceptance/audit workflow UI
(function () {
  const $ = Utils.$;

  const allowedExts = [".pdf", ".docx", ".xlsx", ".csv", ".md", ".markdown", ".txt", ".json"];

  let currentReportId = null;
  let currentReportName = null;
  let pollTimer = null;
  let lastMarkdownStatus = null;
  let lastReportMarkdown = null;

  let availableModels = [];
  let preferredModel = null;
  let preferredProvider = "ollama";

  const AcceptancePage = {
    init() {
      const uploadBox = $("acceptanceUploadBox");
      const fileInput = $("acceptanceFileInput");

      uploadBox?.addEventListener("click", () => fileInput?.click());
      fileInput?.addEventListener("change", (e) => {
        const file = e.target.files?.[0];
        if (file) this.uploadReport(file);
      });

      uploadBox?.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadBox.classList.add("drag-over");
      });
      uploadBox?.addEventListener("dragleave", () => uploadBox.classList.remove("drag-over"));
      uploadBox?.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadBox.classList.remove("drag-over");
        const file = e.dataTransfer.files?.[0];
        if (file) this.uploadReport(file);
      });

      $("acceptanceConvertMarkdownBtn")?.addEventListener("click", () => this.convertMarkdown());
      $("acceptanceDownloadMarkdownBtn")?.addEventListener("click", () => this.downloadMarkdown());
      $("acceptanceRunBtn")?.addEventListener("click", () => this.runAcceptance());
      $("acceptanceDownloadReportBtn")?.addEventListener("click", () => this.downloadReport());
      $("acceptanceProviderSelect")?.addEventListener("change", () => this.syncLlmUi());

      if (API.isAdmin()) {
        this.loadOwners();
      }

      window.addEventListener("pageshow", (e) => {
        if (e.detail?.page === "acceptance") {
          this.applyDefaultsFromSettings();
          if (currentReportId) this.startPolling();
        } else {
          this.stopPolling();
        }
      });

      window.addEventListener("userSettingsUpdated", (e) => {
        const s = e.detail || {};
        preferredModel = s.default_llm_model || preferredModel;
        preferredProvider = s.default_llm_provider || preferredProvider;
        this.applyDefaults(s);
      });

      this.applyDefaultsFromSettings();
    },

    setModels(models) {
      const select = $("acceptanceModelSelect");
      if (!select) return;

      availableModels = Array.isArray(models) && models.length ? models : [];
      const list = availableModels.length ? availableModels : ["qwen3:latest", "qwen2.5:32b"];

      select.innerHTML = "";
      list.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        select.appendChild(opt);
      });

      if (preferredModel && list.includes(preferredModel)) {
        select.value = preferredModel;
      }

      this.syncLlmUi();
    },

    applyDefaultsFromSettings() {
      const user = API.getCurrentUser();
      const cached = Utils.loadUserPrefs(user?.sub || "anonymous");
      if (cached && Object.keys(cached).length) {
        preferredModel = cached.default_llm_model || preferredModel;
        preferredProvider = cached.default_llm_provider || preferredProvider;
        this.applyDefaults(cached);
        return;
      }

      API.settings
        .getMe()
        .then((s) => {
          Utils.saveUserPrefs(user?.sub || "anonymous", s);
          preferredModel = s.default_llm_model || preferredModel;
          preferredProvider = s.default_llm_provider || preferredProvider;
          this.applyDefaults(s);
        })
        .catch(() => {
          // ignore
        });
    },

    applyDefaults(s) {
      if (!s || typeof s !== "object") return;
      if ($("acceptanceProviderSelect")) $("acceptanceProviderSelect").value = s.default_llm_provider || "ollama";
      if ($("acceptanceTopKInput")) $("acceptanceTopKInput").value = String(s.default_top_k ?? $("acceptanceTopKInput").value);
      if ($("acceptanceTemperatureInput")) $("acceptanceTemperatureInput").value = String(s.default_temperature ?? $("acceptanceTemperatureInput").value);
      if (preferredModel && $("acceptanceModelSelect")) {
        const select = $("acceptanceModelSelect");
        if (Array.from(select.options).some((o) => o.value === preferredModel)) {
          select.value = preferredModel;
        }
      }
      if ($("acceptanceModelInput")) $("acceptanceModelInput").value = preferredModel || $("acceptanceModelInput").value || "";
      this.syncLlmUi();
    },

    syncLlmUi() {
      const provider = ($("acceptanceProviderSelect")?.value || preferredProvider || "ollama").toLowerCase();
      const select = $("acceptanceModelSelect");
      const input = $("acceptanceModelInput");
      if (!select || !input) return;

      if (provider === "ollama") {
        select.classList.remove("hidden");
        input.classList.add("hidden");
        const typed = (input.value || "").trim();
        if (typed && !Array.from(select.options).some((o) => o.value === typed)) {
          const opt = document.createElement("option");
          opt.value = typed;
          opt.textContent = typed;
          select.prepend(opt);
        }
        if (typed) select.value = typed;
        else if (preferredModel && Array.isArray(availableModels) && availableModels.includes(preferredModel)) select.value = preferredModel;
      } else {
        select.classList.add("hidden");
        input.classList.remove("hidden");
        if (!input.value.trim()) input.value = preferredModel || select.value || "gpt-4o-mini";
      }
    },

    async loadOwners() {
      const el = $("acceptanceScopeUserSelect");
      if (!el) return;
      try {
        const data = await API.admin.listUsers();
        const users = Array.isArray(data?.users) ? data.users : [];
        el.innerHTML = '<option value="">请选择</option>';
        users
          .filter((u) => u && u.is_active)
          .forEach((u) => {
            const opt = document.createElement("option");
            opt.value = String(u.id);
            opt.textContent = `${u.username} (id=${u.id}${u.role === "admin" ? ", admin" : ""})`;
            el.appendChild(opt);
          });
      } catch (error) {
        console.warn("Failed to load users:", error);
      }
    },

    async uploadReport(file) {
      Utils.clearMessage("acceptanceUploadStatus");
      Utils.clearMessage("acceptanceMessage");
      this.stopPolling();
      this.resetResult();

      const fileExt = "." + (file.name.split(".").pop() || "").toLowerCase();
      if (!allowedExts.includes(fileExt)) {
        Utils.showMessage("acceptanceUploadStatus", "支持 PDF / DOCX / XLSX / CSV / MD / TXT / JSON", "error");
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        Utils.showMessage("acceptanceUploadStatus", "文件不能超过 50MB", "error");
        return;
      }

      try {
        Utils.showMessage("acceptanceUploadStatus", "上传中...", "info");
        const result = await API.documents.upload(file);
        currentReportId = result.document_id;
        currentReportName = result.document_name || file.name;
        $("acceptanceReportName").textContent = currentReportName || "-";
        $("acceptanceReportId").textContent = String(currentReportId ?? "-");
        lastMarkdownStatus = null;
        lastReportMarkdown = null;
        this.updateButtons();
        Utils.showMessage("acceptanceUploadStatus", "上传成功，正在转换 Markdown...", "success");
        this.startPolling();
      } catch (error) {
        Utils.showMessage("acceptanceUploadStatus", `上传失败：${error.message}`, "error");
      }
    },

    startPolling() {
      this.stopPolling();
      this.checkMarkdownStatus();
      pollTimer = setInterval(() => this.checkMarkdownStatus(), 2500);
    },

    stopPolling() {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    },

    updateButtons() {
      const hasReport = !!currentReportId;
      $("acceptanceConvertMarkdownBtn").disabled = !hasReport;
      $("acceptanceDownloadMarkdownBtn").disabled = !hasReport || lastMarkdownStatus !== "markdown_ready";
      $("acceptanceRunBtn").disabled = !hasReport;
    },

    async checkMarkdownStatus() {
      if (!currentReportId) return;
      try {
        const res = await API.documents.getMarkdownStatus(currentReportId);
        const status = res.markdown_status || "pending";
        lastMarkdownStatus = status;
        $("acceptanceReportMarkdownStatus").textContent = Utils.getMarkdownStatusBadge(status).text;
        this.updateButtons();

        if (status === "markdown_ready") {
          this.stopPolling();
          Utils.showMessage("acceptanceUploadStatus", "Markdown 转换完成，可下载或直接生成审查报告。", "success");
        } else if (status === "failed") {
          this.stopPolling();
          Utils.showMessage(
            "acceptanceUploadStatus",
            `Markdown 转换失败：${res.markdown_error || "未知错误"}（可点击“开始/重试转换”，或直接生成审查报告）`,
            "warning"
          );
        }
      } catch (error) {
        console.debug("Failed to check markdown status:", error);
      }
    },

    async convertMarkdown() {
      if (!currentReportId) return;
      try {
        Utils.showMessage("acceptanceUploadStatus", "已提交转换任务，请稍候...", "info");
        await API.documents.convertMarkdown(currentReportId);
        this.startPolling();
      } catch (error) {
        Utils.showMessage("acceptanceUploadStatus", `触发转换失败：${error.message}`, "error");
      }
    },

    async downloadMarkdown() {
      if (!currentReportId) return;
      try {
        const blob = await API.documents.downloadMarkdown(currentReportId);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `report_${currentReportId}.md`;
        a.click();
        URL.revokeObjectURL(url);
        Utils.showMessage("acceptanceUploadStatus", "Markdown 已下载", "success");
      } catch (error) {
        Utils.showMessage("acceptanceUploadStatus", `下载失败：${error.message}`, "error");
      }
    },

    async runAcceptance() {
      Utils.clearMessage("acceptanceMessage");
      this.resetResult();

      if (!currentReportId) {
        Utils.showMessage("acceptanceMessage", "请先上传验收报告", "warning");
        return;
      }

      const provider = ($("acceptanceProviderSelect")?.value || preferredProvider || "ollama").toLowerCase();
      const model =
        provider === "ollama"
          ? $("acceptanceModelSelect")?.value || preferredModel || "qwen3:latest"
          : ($("acceptanceModelInput")?.value || "").trim() || preferredModel || "gpt-4o-mini";
      const topK = parseInt($("acceptanceTopKInput")?.value, 10) || 12;
      const temperature = parseFloat($("acceptanceTemperatureInput")?.value) || 0.2;

      const isAdmin = API.isAdmin();
      const scope = isAdmin ? ($("acceptanceScopeSelect")?.value || "all") : "self";
      const scopeUser = isAdmin ? ($("acceptanceScopeUserSelect")?.value || "").trim() : "";
      const scopeUserId = scope === "user" ? (scopeUser ? parseInt(scopeUser, 10) : null) : null;
      if (isAdmin && scope === "user" && !scopeUserId) {
        Utils.showMessage("acceptanceMessage", "请选择要审查的用户", "warning");
        return;
      }

      try {
        Utils.showMessage("acceptanceMessage", "生成中...（可能需要几十秒）", "info");
        const result = await API.acceptance.run({
          report_document_id: currentReportId,
          provider,
          model,
          top_k: Math.max(1, Math.min(30, topK)),
          temperature,
          scope,
          scope_user_id: scopeUserId,
        });

        lastReportMarkdown = result.report_markdown || "";
        $("acceptanceReportOutput").textContent = lastReportMarkdown || "(无输出)";
        $("acceptanceVerdict").textContent = result.verdict || "-";
        $("acceptancePassed").textContent =
          result.passed === true ? "合格" : result.passed === false ? "不合格" : "需补充材料/未知";

        const sourcesBox = $("acceptanceSourcesBox");
        const sources = Array.isArray(result.sources) ? result.sources : [];
        if (!sources.length) {
          sourcesBox.innerHTML = '<div class="empty-state">无来源</div>';
        } else {
          sourcesBox.innerHTML = sources
            .map((s, idx) => {
              const name = Utils.escapeHtml(s.document_name || "-");
              const relevance = typeof s.relevance === "number" ? s.relevance : 0;
              return `
                <div class="source-item">
                  <div class="source-header">
                    <span class="source-index">#${idx + 1}</span>
                    <span class="source-doc">${name}</span>
                    <span class="source-meta">文档ID: ${s.document_id} · 分段: ${s.chunk_index} · 相似度 ${(relevance * 100).toFixed(1)}%</span>
                  </div>
                </div>
              `;
            })
            .join("");
        }

        $("acceptanceResultCard").classList.remove("hidden");
        $("acceptanceDownloadReportBtn").disabled = !lastReportMarkdown;
        Utils.showMessage("acceptanceMessage", "已生成审查报告", "success");
      } catch (error) {
        Utils.showMessage("acceptanceMessage", `生成失败：${error.message}`, "error");
      }
    },

    downloadReport() {
      if (!lastReportMarkdown) return;
      const blob = new Blob([lastReportMarkdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `acceptance_report_${currentReportId || "unknown"}.md`;
      a.click();
      URL.revokeObjectURL(url);
    },

    resetResult() {
      $("acceptanceResultCard")?.classList.add("hidden");
      $("acceptanceDownloadReportBtn").disabled = true;
      $("acceptanceVerdict").textContent = "-";
      $("acceptancePassed").textContent = "-";
      $("acceptanceReportOutput").textContent = "";
      $("acceptanceSourcesBox").innerHTML = "";
    },
  };

  AcceptancePage.init();
  window.AcceptancePage = AcceptancePage;
})();
