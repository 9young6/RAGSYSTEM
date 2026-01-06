// API client module
const API = {
  // Get token from localStorage
  getToken: () => localStorage.getItem(CONFIG.TOKEN_KEY) || "",

  // Set token to localStorage
  setToken: (token) => {
    if (token) {
      localStorage.setItem(CONFIG.TOKEN_KEY, token);
    } else {
      localStorage.removeItem(CONFIG.TOKEN_KEY);
    }
  },

  // Get current user info from token
  getCurrentUser: () => {
    const token = API.getToken();
    return Utils.decodeJwtPayload(token);
  },

  // Check if user is admin
  isAdmin: () => {
    const user = API.getCurrentUser();
    return user?.role === "admin";
  },

  // Generic fetch with auth
  fetch: async (path, options = {}) => {
    const token = API.getToken();
    const headers = new Headers(options.headers || {});

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(`${CONFIG.API_BASE}${path}`, {
      ...options,
      headers,
    });

    return response;
  },

  // Auth APIs
  auth: {
    login: async (username, password) => {
      const response = await fetch(`${CONFIG.API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const data = await response.json();
      API.setToken(data.access_token);
      return data;
    },

    register: async (username, password) => {
      const response = await fetch(`${CONFIG.API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const data = await response.json();
      API.setToken(data.access_token);
      return data;
    },

    logout: () => {
      API.setToken("");
    },
  },

  // Document APIs
  documents: {
    list: async (page = 1, pageSize = 20, statusFilter = "", ownerId = null) => {
      let url = `/documents?page=${page}&page_size=${pageSize}`;
      if (statusFilter) url += `&status_filter=${statusFilter}`;
      if (ownerId) url += `&owner_id=${ownerId}`;

      const response = await API.fetch(url);
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    get: async (id) => {
      const response = await API.fetch(`/documents/${id}`);
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    upload: async (file) => {
      const formData = new FormData();
      formData.append("file", file);

      const response = await API.fetch("/documents/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    confirm: async (id) => {
      const response = await API.fetch(`/documents/confirm/${id}`, {
        method: "POST",
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    delete: async (id) => {
      const response = await API.fetch(`/documents/${id}`, {
        method: "DELETE",
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    batchDelete: async (documentIds) => {
      const response = await API.fetch("/documents/batch-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: documentIds }),
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    getMarkdownStatus: async (id) => {
      const response = await API.fetch(`/documents/${id}/markdown/status`);
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    downloadMarkdown: async (id) => {
      const response = await API.fetch(`/documents/${id}/markdown/download`);
      if (!response.ok) throw new Error(await response.text());
      return await response.blob();
    },

    uploadMarkdown: async (id, file) => {
      const formData = new FormData();
      formData.append("file", file);

      const response = await API.fetch(`/documents/${id}/markdown/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    convertMarkdown: async (id) => {
      const response = await API.fetch(`/documents/${id}/markdown/convert`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // Chunk APIs (Milvus content CRUD via controlled backend)
  chunks: {
    list: async (documentId, page = 1, pageSize = 50) => {
      const response = await API.fetch(`/documents/${documentId}/chunks?page=${page}&page_size=${pageSize}`);
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    create: async (documentId, content) => {
      const response = await API.fetch(`/documents/${documentId}/chunks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    update: async (documentId, chunkId, content = null, syncVector = true, included = null) => {
      const body = { sync_vector: !!syncVector };
      if (content !== null && content !== undefined) body.content = content;
      if (included !== null && included !== undefined) body.included = !!included;
      const response = await API.fetch(`/documents/${documentId}/chunks/${chunkId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    delete: async (documentId, chunkId) => {
      const response = await API.fetch(`/documents/${documentId}/chunks/${chunkId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    reembed: async (documentId, chunkIds = null) => {
      const payload = {};
      if (Array.isArray(chunkIds) && chunkIds.length) payload.chunk_ids = chunkIds;
      const response = await API.fetch(`/documents/${documentId}/chunks/reembed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // Admin-only APIs
  admin: {
    listUsers: async () => {
      const response = await API.fetch("/admin/users");
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // User settings APIs
  settings: {
    getMe: async () => {
      const response = await API.fetch("/settings/me");
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    updateMe: async (payload) => {
      const response = await API.fetch("/settings/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // Diagnostics APIs (connectivity test)
  diagnostics: {
    ollama: async (payload) => {
      const response = await API.fetch("/diagnostics/ollama", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    inference: async (payload) => {
      const response = await API.fetch("/diagnostics/inference", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    rerank: async (payload) => {
      const response = await API.fetch("/diagnostics/rerank", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // Query APIs
  query: {
    search: async (
      query,
      topK,
      provider,
      model,
      temperature,
      rerank = null,
      rerankProvider = null,
      rerankModel = null
    ) => {
      const payload = {
        query,
        top_k: topK,
        provider,
        model,
        temperature,
      };
      if (!provider) delete payload.provider;
      if (rerank !== null && rerank !== undefined) payload.rerank = !!rerank;
      if (rerankProvider) payload.rerank_provider = rerankProvider;
      if (rerankModel) payload.rerank_model = rerankModel;
      const response = await API.fetch("/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    adminSearch: async (
      query,
      topK,
      provider,
      model,
      temperature,
      userId = null,
      rerank = null,
      rerankProvider = null,
      rerankModel = null
    ) => {
      const payload = {
        query,
        top_k: topK,
        provider,
        model,
        temperature,
      };
      if (!provider) delete payload.provider;
      if (userId) payload.user_id = userId;
      if (rerank !== null && rerank !== undefined) payload.rerank = !!rerank;
      if (rerankProvider) payload.rerank_provider = rerankProvider;
      if (rerankModel) payload.rerank_model = rerankModel;

      const response = await API.fetch("/query/admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // Acceptance / audit APIs
  acceptance: {
    run: async (payload) => {
      const response = await API.fetch("/acceptance/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // Review APIs (admin only)
  review: {
    getPending: async () => {
      const response = await API.fetch("/review/pending");
      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    approve: async (id) => {
      const response = await API.fetch(`/review/approve/${id}`, {
        method: "POST",
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },

    reject: async (id, reason) => {
      const response = await API.fetch(`/review/reject/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });

      if (!response.ok) throw new Error(await response.text());
      return await response.json();
    },
  },

  // Health check
  health: async () => {
    const response = await fetch(`${CONFIG.API_BASE}/health`);
    if (!response.ok) throw new Error("Health check failed");
    return await response.json();
  },
};

window.API = API;
