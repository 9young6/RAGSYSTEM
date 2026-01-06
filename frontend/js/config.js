// Global configuration
const CONFIG = {
  API_HOST: window.location.hostname || "localhost",
  API_PORT: "8001",
  TOKEN_KEY: "kb_token",
  API_BASE_OVERRIDE_KEY: "kb_api_base_override",
};

// Computed API base URL
const computedApiBase = `http://${CONFIG.API_HOST}:${CONFIG.API_PORT}/api/v1`;
const override = localStorage.getItem(CONFIG.API_BASE_OVERRIDE_KEY) || "";
CONFIG.API_BASE = override.trim() || computedApiBase;

// Export for use in other modules
window.CONFIG = CONFIG;
