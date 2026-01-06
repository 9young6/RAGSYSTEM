// app.js - Main application logic
(function () {
  const $ = Utils.$;

  const user = API.getCurrentUser();
  if (!user) {
    window.location.href = "./login.html";
    return;
  }

  document.title = "知识库管理系统";
  $("currentUser").textContent = user.sub || "未知用户";
  const roleText = user.role === "admin" ? "管理员" : "普通用户";
  $("userRole").textContent = roleText;

  const isAdmin = API.isAdmin();
  document.querySelectorAll(".admin-only").forEach((el) => {
    el.classList.toggle("hidden", !isAdmin);
  });

  $("logoutBtn").addEventListener("click", () => {
    if (confirm("确定要退出登录吗？")) {
      API.auth.logout();
      window.location.href = "./login.html";
    }
  });

  const navItems = document.querySelectorAll(".nav-item");
  const pages = document.querySelectorAll(".page");

  function showPage(pageName) {
    navItems.forEach((item) => {
      item.classList.toggle("active", item.dataset.page === pageName);
    });

    pages.forEach((page) => {
      if (page.id === `page-${pageName}`) {
        page.classList.remove("hidden");
        page.classList.add("active");
      } else {
        page.classList.add("hidden");
        page.classList.remove("active");
      }
    });

    const event = new CustomEvent("pageshow", { detail: { page: pageName } });
    window.dispatchEvent(event);
    sessionStorage.setItem("kb_active_page", pageName);
  }

  navItems.forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      const pageName = item.dataset.page;
      if (pageName === "review" && !isAdmin) return;
      showPage(pageName);
    });
  });

  // Load Ollama models for query/settings pages
  async function loadModels() {
    try {
      const health = await API.health();
      const models = Array.isArray(health?.details?.ollama_models) ? health.details.ollama_models : [];
      if (window.QueryPage) {
        window.QueryPage.setModels(models);
      }
      if (window.AcceptancePage) {
        window.AcceptancePage.setModels(models);
      }
      if (window.SettingsPage) {
        window.SettingsPage.setModels(models, health?.details || {});
      }
    } catch (error) {
      console.error("加载模型列表失败:", error);
      if (window.SettingsPage) {
        window.SettingsPage.setModels([], {});
        Utils.showMessage("settingsMessage", "无法获取 Ollama 模型列表，请稍后再试", "warning");
      }
    }
  }

  // Initial page selection
  const storedPage = sessionStorage.getItem("kb_active_page") || "documents";
  const initialPage = storedPage === "review" && !isAdmin ? "documents" : storedPage;
  showPage(initialPage);

  loadModels();
})();
