// settings.js - Settings / diagnostics page
(function () {
  const $ = Utils.$;

  let availableModels = [];

  const SettingsPage = {
    init() {
      window.addEventListener("pageshow", (e) => {
        if (e.detail?.page === "settings") {
          this.renderBasic();
          this.loadUserSettings();
        }
      });

      this.renderBasic();
      this.bindActions();
      this.loadUserSettings();
    },

    bindActions() {
      $("settingsSaveBtn")?.addEventListener("click", () => this.saveUserSettings());
      $("settingsTestInferenceBtn")?.addEventListener("click", () => this.testInference());
      $("settingsTestRerankBtn")?.addEventListener("click", () => this.testRerank());

      $("settingsApiBaseSaveBtn")?.addEventListener("click", () => {
        const value = ($("settingsApiBaseOverride")?.value || "").trim();
        if (!value) {
          Utils.showMessage("settingsUserConfigMessage", "请输入要覆盖的 API Base", "warning");
          return;
        }
        localStorage.setItem(CONFIG.API_BASE_OVERRIDE_KEY, value);
        window.location.reload();
      });

      $("settingsApiBaseClearBtn")?.addEventListener("click", () => {
        localStorage.removeItem(CONFIG.API_BASE_OVERRIDE_KEY);
        window.location.reload();
      });

      $("settingsEnableRerank")?.addEventListener("change", () => this.syncRerankUi());
      $("settingsRerankProvider")?.addEventListener("change", () => this.syncRerankUi());
      $("settingsLlmProvider")?.addEventListener("change", () => this.syncLlmUi());
    },

    renderBasic() {
      const user = API.getCurrentUser();
      $("settingsApiBase").textContent = CONFIG.API_BASE;
      $("settingsUser").textContent = user?.sub || "-";
      $("settingsRole").textContent = user?.role || "-";

      const token = API.getToken();
      $("settingsToken").textContent = token ? token.slice(0, 24) + "..." : "-";

      const override = localStorage.getItem(CONFIG.API_BASE_OVERRIDE_KEY) || "";
      const el = $("settingsApiBaseOverride");
      if (el) el.value = override.trim();
    },

    async loadUserSettings() {
      Utils.clearMessage("settingsUserConfigMessage");
      const user = API.getCurrentUser();
      const username = user?.sub || "anonymous";

      try {
        const data = await API.settings.getMe();
        Utils.saveUserPrefs(username, data);
        this.applyUserSettingsToForm(data);
      } catch (error) {
        const cached = Utils.loadUserPrefs(username);
        if (cached && Object.keys(cached).length) {
          this.applyUserSettingsToForm(cached);
          Utils.showMessage("settingsUserConfigMessage", "后端设置接口不可用，已加载本地缓存", "warning");
        } else {
          Utils.showMessage("settingsUserConfigMessage", `加载用户设置失败：${error.message}`, "error");
        }
      }
    },

    applyUserSettingsToForm(data) {
      $("settingsLlmProvider").value = data.default_llm_provider || "ollama";

      this.syncModelSelect(availableModels, data.default_llm_model);
      const modelInput = $("settingsDefaultModelInput");
      if (modelInput) modelInput.value = data.default_llm_model || "";
      this.syncLlmUi();
      $("settingsTopK").value = String(data.default_top_k ?? 5);
      $("settingsTemp").value = String(data.default_temperature ?? 0.7);

      $("settingsEnableRerank").checked = !!data.enable_rerank;
      $("settingsRerankProvider").value = data.rerank_provider || "none";
      $("settingsRerankModel").value = data.rerank_model || "";
      this.syncRerankUi();

      window.dispatchEvent(new CustomEvent("userSettingsUpdated", { detail: data }));
    },

    syncModelSelect(modelNames, preferred) {
      const select = $("settingsDefaultModel");
      if (!select) return;
      const list = Array.isArray(modelNames) ? modelNames.filter(Boolean) : [];
      select.innerHTML = "";
      (list.length ? list : ["qwen3:latest", "qwen2.5:32b"]).forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        select.appendChild(opt);
      });
      if (preferred && Array.from(select.options).some((o) => o.value === preferred)) {
        select.value = preferred;
      }
    },

    syncLlmUi() {
      const provider = ($("settingsLlmProvider")?.value || "ollama").toLowerCase();
      const select = $("settingsDefaultModel");
      const input = $("settingsDefaultModelInput");
      if (!select || !input) return;

      const currentSelectValue = select.value || "";
      const currentInputValue = (input.value || "").trim();

      if (provider === "ollama") {
        select.classList.remove("hidden");
        input.classList.add("hidden");

        // If user typed a model manually, keep it selectable for convenience.
        if (currentInputValue && !Array.from(select.options).some((o) => o.value === currentInputValue)) {
          const opt = document.createElement("option");
          opt.value = currentInputValue;
          opt.textContent = currentInputValue;
          select.prepend(opt);
        }

        if (currentInputValue) select.value = currentInputValue;
        else if (currentSelectValue) select.value = currentSelectValue;
      } else {
        select.classList.add("hidden");
        input.classList.remove("hidden");
        if (!currentInputValue) input.value = currentSelectValue || "gpt-4o-mini";
      }
    },

    syncRerankUi() {
      const enabled = !!$("settingsEnableRerank")?.checked;
      const provider = $("settingsRerankProvider")?.value || "none";
      const modelEl = $("settingsRerankModel");
      if (modelEl) modelEl.disabled = !(enabled && provider !== "none");
    },

    async saveUserSettings() {
      Utils.clearMessage("settingsUserConfigMessage");
      const provider = ($("settingsLlmProvider").value || "ollama").toLowerCase();
      const model = provider === "ollama" ? $("settingsDefaultModel").value : ($("settingsDefaultModelInput")?.value || "").trim();
      if (!model) {
        Utils.showMessage("settingsUserConfigMessage", "请输入默认 LLM 模型", "warning");
        return;
      }
      const payload = {
        default_llm_provider: provider,
        default_llm_model: model,
        default_top_k: parseInt($("settingsTopK").value, 10) || 5,
        default_temperature: parseFloat($("settingsTemp").value) || 0.7,
        enable_rerank: !!$("settingsEnableRerank").checked,
        rerank_provider: $("settingsRerankProvider").value || "none",
        rerank_model: ($("settingsRerankModel").value || "").trim() || null,
      };

      try {
        const data = await API.settings.updateMe(payload);
        const user = API.getCurrentUser();
        Utils.saveUserPrefs(user?.sub || "anonymous", data);
        this.applyUserSettingsToForm(data);
        Utils.showMessage("settingsUserConfigMessage", "已保存", "success");
      } catch (error) {
        Utils.showMessage("settingsUserConfigMessage", `保存失败：${error.message}`, "error");
      }
    },

    async testInference() {
      Utils.clearMessage("settingsUserConfigMessage");
      try {
        const provider = ($("settingsLlmProvider").value || "ollama").toLowerCase();
        const model = provider === "ollama" ? $("settingsDefaultModel").value : ($("settingsDefaultModelInput")?.value || "").trim();
        if (!model) throw new Error("model is required");
        const temperature = parseFloat($("settingsTemp").value) || 0.1;
        const res = await API.diagnostics.inference({ provider, model, prompt: "ping", temperature });
        if (!res.ok) throw new Error(res.error || "unknown");
        Utils.showMessage(
          "settingsUserConfigMessage",
          `LLM OK (${res.provider})\\nbase_url=${res.base_url}\\nmodel=${res.model}\\npreview=${res.preview || ""}`,
          "success"
        );
      } catch (error) {
        Utils.showMessage("settingsUserConfigMessage", `LLM 测试失败：${error.message}`, "error");
      }
    },

    async testRerank() {
      Utils.clearMessage("settingsUserConfigMessage");
      try {
        const enabled = !!$("settingsEnableRerank").checked;
        const provider = $("settingsRerankProvider").value || "none";
        const model = ($("settingsRerankModel").value || "").trim();
        if (!enabled || provider === "none") {
          Utils.showMessage("settingsUserConfigMessage", "Rerank 未启用", "warning");
          return;
        }
        if (!model) {
          Utils.showMessage("settingsUserConfigMessage", "请输入 Rerank 模型名称", "warning");
          return;
        }
        const res = await API.diagnostics.rerank({
          provider,
          model,
          query: "hello",
          documents: ["hello world", "foo bar", "hello foo"],
        });
        if (!res.ok) throw new Error(res.error || "unknown");
        Utils.showMessage("settingsUserConfigMessage", `Rerank OK\\nbase_url=${res.base_url}\\nscores=${(res.scores || []).join(", ")}`, "success");
      } catch (error) {
        Utils.showMessage("settingsUserConfigMessage", `Rerank 测试失败：${error.message}`, "error");
      }
    },

    setModels(models, healthDetails) {
      const list = $("settingsModels");
      list.innerHTML = "";

      const modelNames = Array.isArray(models) ? models : [];
      availableModels = modelNames;
      if (!modelNames.length) {
        list.innerHTML = '<div class="muted">未检测到 Ollama 模型</div>';
      } else {
        list.innerHTML = modelNames.map((m) => `<div class="pill">${Utils.escapeHtml(m)}</div>`).join("");
      }

      // keep default model select in sync
      const user = API.getCurrentUser();
      const cached = Utils.loadUserPrefs(user?.sub || "anonymous");
      this.syncModelSelect(modelNames, cached?.default_llm_model);
      this.syncLlmUi();

      const detailsEl = $("settingsHealth");
      if (!detailsEl) return;
      const details = healthDetails && typeof healthDetails === "object" ? healthDetails : {};
      const entries = Object.entries(details)
        .filter(([k]) => k !== "ollama_models")
        .map(([k, v]) => `<div><span class="pill">${Utils.escapeHtml(k)}</span> ${Utils.escapeHtml(String(v))}</div>`)
        .join("");
      detailsEl.innerHTML = entries || '<div class="muted">暂无健康信息</div>';
    },
  };

  SettingsPage.init();
  window.SettingsPage = SettingsPage;
})();
