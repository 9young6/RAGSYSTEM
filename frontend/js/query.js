// query.js - Knowledge base query page
(function () {
  const $ = Utils.$;

  let availableModels = [];
  let defaultModel = "qwen2.5:32b";
  let preferredModel = null;
  let preferredProvider = "ollama";

  const QueryPage = {
    init() {
      $("queryBtn").addEventListener("click", () => this.performQuery());
      $("queryInput").addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          this.performQuery();
        }
      });

      $("rerankEnable")?.addEventListener("change", () => this.syncRerankUi());
      $("rerankProvider")?.addEventListener("change", () => this.syncRerankUi());
      $("queryProviderSelect")?.addEventListener("change", () => this.syncLlmUi());

      window.addEventListener("pageshow", (e) => {
        if (e.detail?.page === "query") {
          Utils.clearMessage("queryMessage");
          this.loadDefaultsFromSettings();
        }
      });

      window.addEventListener("userSettingsUpdated", (e) => {
        const s = e.detail || {};
        preferredModel = s.default_llm_model || preferredModel;
        preferredProvider = s.default_llm_provider || preferredProvider;
        this.applyDefaults(s);
      });

      this.loadDefaultsFromSettings();
      this.syncRerankUi();
      this.syncLlmUi();
      this.loadAdminUsers();
    },

    setModels(models) {
      const select = $("modelSelect");
      select.innerHTML = "";

      availableModels = Array.isArray(models) && models.length > 0 ? models : ["qwen2.5:32b"];
      defaultModel = availableModels[0] || "qwen2.5:32b";
      const count = Array.isArray(models) ? models.length : 0;

      availableModels.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      });

      const provider = ($("queryProviderSelect")?.value || preferredProvider || "ollama").toLowerCase();
      if (provider !== "ollama") {
        Utils.showMessage("modelHint", `当前 Provider: ${provider}（模型支持手动输入）`, "info");
      } else if (!Array.isArray(models) || models.length === 0) {
        Utils.showMessage(
          "modelHint",
          "未检测到 Ollama 模型：可执行 docker compose exec ollama ollama pull qwen2.5:32b",
          "warning"
        );
      } else {
        Utils.showMessage("modelHint", `已检测到 ${count} 个 Ollama 模型`, "success");
      }

      // Apply preferred selection if available
      if (preferredModel && availableModels.includes(preferredModel)) {
        select.value = preferredModel;
      }

      this.syncLlmUi();
    },

    async loadAdminUsers() {
      if (!API.isAdmin()) return;
      const select = $("adminUserSelect");
      if (!select) return;

      try {
        const res = await API.admin.listUsers();
        const users = Array.isArray(res?.users) ? res.users : [];
        select.innerHTML = '<option value="">（请选择用户）</option>';
        users.forEach((u) => {
          const id = u?.id;
          if (!id) return;
          const opt = document.createElement("option");
          opt.value = String(id);
          opt.textContent = `${u?.username || "user"} (id:${id}${u?.role ? `, ${u.role}` : ""})`;
          select.appendChild(opt);
        });

        // Keep manual input in sync
        select.addEventListener("change", () => {
          const v = (select.value || "").trim();
          const input = $("adminUserId");
          if (input) input.value = v;
        });
      } catch {
        select.innerHTML = '<option value="">（用户列表加载失败，可手动输入 ID）</option>';
      }
    },

    async loadDefaultsFromSettings() {
      const user = API.getCurrentUser();
      const cached = Utils.loadUserPrefs(user?.sub || "anonymous");
      if (cached && Object.keys(cached).length) {
        preferredModel = cached.default_llm_model || preferredModel;
        preferredProvider = cached.default_llm_provider || preferredProvider;
        this.applyDefaults(cached);
        return;
      }

      try {
        const s = await API.settings.getMe();
        Utils.saveUserPrefs(user?.sub || "anonymous", s);
        preferredModel = s.default_llm_model || preferredModel;
        preferredProvider = s.default_llm_provider || preferredProvider;
        this.applyDefaults(s);
      } catch {
        // ignore
      }
    },

    applyDefaults(s) {
      if (!s || typeof s !== "object") return;

      if ($("queryProviderSelect")) {
        $("queryProviderSelect").value = s.default_llm_provider || $("queryProviderSelect").value || "ollama";
      }
      if ($("topKInput")) $("topKInput").value = String(s.default_top_k ?? $("topKInput").value);
      if ($("temperatureInput")) $("temperatureInput").value = String(s.default_temperature ?? $("temperatureInput").value);
      if (preferredModel && $("modelSelect") && availableModels.includes(preferredModel)) {
        $("modelSelect").value = preferredModel;
      }
      if ($("modelInput")) {
        $("modelInput").value = preferredModel || $("modelInput").value || "";
      }

      if ($("rerankEnable")) $("rerankEnable").checked = !!s.enable_rerank;
      if ($("rerankProvider")) $("rerankProvider").value = s.rerank_provider || "none";
      if ($("rerankModel")) $("rerankModel").value = s.rerank_model || "";
      this.syncRerankUi();
      this.syncLlmUi();
    },

    syncLlmUi() {
      const provider = ($("queryProviderSelect")?.value || preferredProvider || "ollama").toLowerCase();
      const select = $("modelSelect");
      const input = $("modelInput");
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
        else if (preferredModel && availableModels.includes(preferredModel)) select.value = preferredModel;
      } else {
        select.classList.add("hidden");
        input.classList.remove("hidden");
        if (!input.value.trim()) {
          input.value = preferredModel || select.value || "gpt-4o-mini";
        }
      }
    },

    syncRerankUi() {
      const enabled = !!$("rerankEnable")?.checked;
      const provider = $("rerankProvider")?.value || "none";
      const modelEl = $("rerankModel");
      if (modelEl) modelEl.disabled = !(enabled && provider !== "none");
    },

    async performQuery() {
      const query = $("queryInput").value.trim();
      if (!query) {
        Utils.showMessage("queryMessage", "请输入查询问题", "warning");
        return;
      }

      Utils.clearMessage("queryMessage");
      $("queryResult").classList.add("hidden");

      try {
        Utils.showMessage("queryMessage", "查询中...", "info");

        const topK = parseInt($("topKInput").value, 10) || 5;
        const temperature = parseFloat($("temperatureInput").value) || 0.7;
        const provider = ($("queryProviderSelect")?.value || preferredProvider || "ollama").toLowerCase();
        const model =
          provider === "ollama"
            ? $("modelSelect").value || defaultModel
            : ($("modelInput")?.value || "").trim() || preferredModel || "gpt-4o-mini";

        const rerankEnabled = !!$("rerankEnable")?.checked;
        const rerankProvider = $("rerankProvider")?.value || "none";
        const rerankModel = ($("rerankModel")?.value || "").trim();
        const useRerank = rerankEnabled && rerankProvider !== "none" && !!rerankModel;

        const isAdmin = API.isAdmin();
        const scope = isAdmin ? ($("adminScope")?.value || "all") : "self";
        const userIdRaw = isAdmin ? ($("adminUserId")?.value || "").trim() : "";
        const selectedUser = isAdmin ? (($("adminUserSelect")?.value || "").trim() || "") : "";
        const userId = (selectedUser ? parseInt(selectedUser, 10) : null) || (userIdRaw ? parseInt(userIdRaw, 10) : null);

        let result;
        if (isAdmin && scope !== "self") {
          if (scope === "user" && !userId) {
            Utils.showMessage("queryMessage", "请输入要查询的用户 ID，或将范围改为“全库”", "warning");
            return;
          }
          result = await API.query.adminSearch(
            query,
            topK,
            provider,
            model,
            temperature,
            scope === "user" ? userId : null,
            useRerank,
            rerankProvider,
            rerankModel
          );
        } else {
          result = await API.query.search(query, topK, provider, model, temperature, useRerank, rerankProvider, rerankModel);
        }

        this.renderResult(result);
        Utils.clearMessage("queryMessage");
      } catch (error) {
        Utils.showMessage("queryMessage", `查询失败：${error.message}`, "error");
      }
    },

    renderResult(result) {
      $("answerBox").textContent = result.answer || "(无答案)";

      const sourcesBox = $("sourcesBox");
      if (!result.sources || result.sources.length === 0) {
        sourcesBox.innerHTML = '<div class="empty-state">无相关来源</div>';
      } else {
        sourcesBox.innerHTML = result.sources
          .map((source, index) => {
            const name = Utils.escapeHtml(source.document_name || "-");
            const relevance = typeof source.relevance === "number" ? source.relevance : 0;
            return `
              <div class="source-item">
                <div class="source-header">
                  <span class="source-index">#${index + 1}</span>
                  <span class="source-doc">${name}</span>
                  <span class="source-meta">
                    文档ID: ${source.document_id} · 分段: ${source.chunk_index} · 相似度 ${(relevance * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            `;
          })
          .join("");
      }

      const confidence = typeof result.confidence === "number" ? result.confidence : 0;
      const confidenceText = `置信度 ${(confidence * 100).toFixed(1)}%`;
      const confidenceClass = confidence > 0.7 ? "success" : confidence > 0.4 ? "warning" : "error";
      $("answerBox").setAttribute("data-confidence", confidenceText);
      $("answerBox").className = `answer-box confidence-${confidenceClass}`;

      $("queryResult").classList.remove("hidden");
    },
  };

  QueryPage.init();
  window.QueryPage = QueryPage;
})();
