// auth.js - Login & register logic
(function () {
  const $ = Utils.$;

  const loginForm = $("loginForm");
  const registerForm = $("registerForm");
  const tabBtns = document.querySelectorAll(".tab-btn");

  // Show API base for quick troubleshooting
  const apiBaseEl = $("apiBase");
  if (apiBaseEl) {
    apiBaseEl.textContent = CONFIG.API_BASE;
  }

  const switchTab = (tab) => {
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    loginForm.classList.toggle("hidden", tab !== "login");
    registerForm.classList.toggle("hidden", tab !== "register");
    Utils.clearMessage("authMessage");
  };

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    Utils.clearMessage("authMessage");

    const username = $("loginUsername").value.trim();
    const password = $("loginPassword").value;

    if (!username || !password) {
      Utils.showMessage("authMessage", "请输入用户名和密码", "error");
      return;
    }

    try {
      await API.auth.login(username, password);
      Utils.showMessage("authMessage", "登录成功，正在跳转...", "success");
      setTimeout(() => {
        window.location.href = "./app.html";
      }, 400);
    } catch (error) {
      Utils.showMessage("authMessage", `登录失败：${error.message || "请重试"}`, "error");
    }
  });

  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    Utils.clearMessage("authMessage");

    const username = $("regUsername").value.trim();
    const password = $("regPassword").value;
    const password2 = $("regPassword2").value;

    if (!username) {
      Utils.showMessage("authMessage", "请输入用户名", "error");
      return;
    }
    if (password.length < 6) {
      Utils.showMessage("authMessage", "密码至少 6 位", "error");
      return;
    }
    if (password !== password2) {
      Utils.showMessage("authMessage", "两次输入的密码不一致", "error");
      return;
    }

    try {
      await API.auth.register(username, password);
      Utils.showMessage("authMessage", "注册成功，正在跳转...", "success");
      setTimeout(() => {
        window.location.href = "./app.html";
      }, 400);
    } catch (error) {
      Utils.showMessage("authMessage", `注册失败：${error.message || "请重试"}`, "error");
    }
  });

  // Already logged in? Jump to app
  const user = API.getCurrentUser();
  if (user) {
    window.location.href = "./app.html";
  }
})();
