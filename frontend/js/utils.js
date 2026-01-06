// Utility functions
const Utils = {
  // DOM helper
  $: (id) => document.getElementById(id),

  // JWT token decoder
  decodeJwtPayload: (jwt) => {
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
  },

  // Format date
  formatDate: (dateString) => {
    if (!dateString) return "-";
    const date = new Date(dateString);
    return date.toLocaleString("zh-CN");
  },

  // Format file size
  formatFileSize: (bytes) => {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    return `${size.toFixed(2)} ${units[unitIndex]}`;
  },

  // Get status badge class
  getStatusBadge: (status) => {
    const badges = {
      uploaded: { text: "已上传", class: "badge-info" },
      confirmed: { text: "已确认", class: "badge-primary" },
      approved: { text: "已审批", class: "badge-warning" },
      indexed: { text: "已索引", class: "badge-success" },
      rejected: { text: "已拒绝", class: "badge-danger" },
    };
    return badges[status] || { text: status || "-", class: "badge-default" };
  },

  // Get markdown status badge
  getMarkdownStatusBadge: (status) => {
    const badges = {
      pending: { text: "待转换", class: "badge-secondary" },
      processing: { text: "转换中", class: "badge-info" },
      markdown_ready: { text: "转换完成", class: "badge-success" },
      failed: { text: "转换失败", class: "badge-danger" },
    };
    return badges[status] || { text: "-", class: "badge-default" };
  },

  // Show message
  showMessage: (elementId, message, type = "info") => {
    const el = Utils.$(elementId);
    if (!el) return;
    el.textContent = message;
    el.className = `message message-${type}`;
    el.style.display = message ? "block" : "none";
  },

  // Clear message
  clearMessage: (elementId) => {
    const el = Utils.$(elementId);
    if (!el) return;
    el.textContent = "";
    el.style.display = "none";
  },

  // Simple HTML escape for user content
  escapeHtml: (text) =>
    (text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;"),

  // Debounce function
  debounce: (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  // User-scoped preferences stored in localStorage (fallback if backend settings unavailable)
  getPrefsKey: (username) => `kb_user_prefs_${username || "anonymous"}`,

  loadUserPrefs: (username) => {
    const key = Utils.getPrefsKey(username);
    const raw = localStorage.getItem(key) || "";
    if (!raw) return {};
    try {
      const obj = JSON.parse(raw);
      return obj && typeof obj === "object" ? obj : {};
    } catch {
      return {};
    }
  },

  saveUserPrefs: (username, prefs) => {
    const key = Utils.getPrefsKey(username);
    localStorage.setItem(key, JSON.stringify(prefs || {}));
  },
};

window.Utils = Utils;
