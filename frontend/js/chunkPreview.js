// chunkPreview.js - 文档切分预览功能
(function () {
  const $ = Utils.$;

  let currentDocumentId = null;
  let currentText = null;
  let chartInstance = null;

  // 打开切分预览模态框
  function showPreview(documentId) {
    currentDocumentId = documentId;
    currentText = null;

    Utils.showMessage("chunkPreviewMessage", "", "info");
    Utils.showModal("chunkPreviewModal");

    // 加载文档信息
    loadDocumentInfo(documentId);

    // 自动运行预览
    runPreview();
  }

  // 打开切分预览模态框（直接文本）
  function showPreviewWithText(text, documentName) {
    currentDocumentId = null;
    currentText = text;

    Utils.showMessage("chunkPreviewMessage", "", "info");
    Utils.showModal("chunkPreviewModal");

    // 设置文档信息
    $("chunkPreviewDocMeta").textContent = documentName || "文本预览";

    // 自动运行预览
    runPreview();
  }

  // 加载文档信息
  async function loadDocumentInfo(documentId) {
    try {
      const response = await API.fetch(`/documents/${documentId}`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "加载文档失败");
      }

      const doc = data;
      $("chunkPreviewDocMeta").textContent = `${doc.filename} (ID: ${doc.id})`;
    } catch (error) {
      console.error("加载文档信息失败:", error);
      $("chunkPreviewDocMeta").textContent = `文档 #${documentId}`;
    }
  }

  // 运行预览
  async function runPreview() {
    try {
      Utils.showMessage("chunkPreviewMessage", "正在切分...", "info");

      const strategy = $("previewStrategy").value;
      const chunkSize = parseInt($("previewChunkSize").value) || 512;
      const overlapPercent = parseInt($("previewOverlapPercent").value) || 20;
      const delimiters = $("previewDelimiters").value || null;

      const payload = {
        strategy,
        chunk_size: chunkSize,
        overlap_percent: overlapPercent,
        delimiters,
      };

      if (currentDocumentId) {
        payload.document_id = currentDocumentId;
      } else if (currentText) {
        payload.text = currentText;
      } else {
        throw new Error("缺少文档ID或文本内容");
      }

      const response = await API.fetch("/chunks/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "预览失败");
      }

      // 更新统计信息
      updateStats(data);

      // 更新图表
      updateChart(data.chunks);

      // 更新 Chunk 列表
      updateChunkList(data.chunks);

      Utils.showMessage("chunkPreviewMessage", `切分完成，共 ${data.total_chunks} 个 chunks`, "success");
    } catch (error) {
      console.error("切分预览失败:", error);
      Utils.showMessage("chunkPreviewMessage", `预览失败: ${error.message}`, "error");
    }
  }

  // 更新统计信息
  function updateStats(data) {
    $("previewStatStrategy").textContent = data.strategy;
    $("previewStatTotalChunks").textContent = data.total_chunks;
    $("previewStatTotalChars").textContent = data.total_chars.toLocaleString();
    $("previewStatTotalTokens").textContent = data.total_tokens ? data.total_tokens.toLocaleString() : "N/A";
    $("previewStatAvgSize").textContent = Math.round(data.avg_chunk_size);
    $("previewStatMinSize").textContent = data.min_chunk_size;
    $("previewStatMaxSize").textContent = data.max_chunk_size;
  }

  // 更新图表
  function updateChart(chunks) {
    const canvas = $("chunkSizeChart");
    if (!canvas) return;

    // 销毁旧图表
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }

    // 准备数据
    const sizes = chunks.map((c) => c.char_count);
    const labels = chunks.map((c, i) => `#${i + 1}`);

    // 创建新图表
    try {
      const ctx = canvas.getContext("2d");
      chartInstance = new Chart(ctx, {
        type: "bar",
        data: {
          labels: labels,
          datasets: [
            {
              label: "字符数",
              data: sizes,
              backgroundColor: "rgba(59, 130, 246, 0.6)",
              borderColor: "rgba(59, 130, 246, 1)",
              borderWidth: 1,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false,
            },
            tooltip: {
              callbacks: {
                title: (items) => `Chunk ${items[0].label}`,
                label: (item) => {
                  const chunk = chunks[item.dataIndex];
                  const tokenInfo = chunk.token_count ? ` | ${chunk.token_count} tokens` : "";
                  return `${item.raw} 字符${tokenInfo}`;
                },
              },
            },
          },
          scales: {
            x: {
              display: chunks.length <= 50,
              title: {
                display: true,
                text: "Chunk Index",
              },
            },
            y: {
              beginAtZero: true,
              title: {
                display: true,
                text: "字符数",
              },
            },
          },
        },
      });
    } catch (error) {
      console.error("创建图表失败:", error);
      // Chart.js 可能未加载，显示简单文本统计
      canvas.parentElement.innerHTML = `<div class="muted">图表加载失败（Chart.js 未引入）<br>大小范围：${Math.min(...sizes)} - ${Math.max(...sizes)} 字符</div>`;
    }
  }

  // 更新 Chunk 列表
  function updateChunkList(chunks) {
    const container = $("chunkPreviewList");
    const maxChunks = parseInt($("previewMaxChunks").value) || 10;
    const displayChunks = chunks.slice(0, maxChunks);

    if (!chunks.length) {
      container.innerHTML = `<div class="muted">没有生成 chunks</div>`;
      return;
    }

    container.innerHTML = displayChunks
      .map(
        (chunk) => `
      <div class="card flat" style="margin-bottom:12px;">
        <div class="chunk-preview-header">
          <strong>Chunk #${chunk.chunk_index + 1}</strong>
          <span class="pill">${chunk.char_count} 字符</span>
          ${chunk.token_count ? `<span class="pill">${chunk.token_count} tokens</span>` : ""}
        </div>
        <pre class="chunk-preview-content">${Utils.escapeHtml(chunk.content)}</pre>
      </div>
    `
      )
      .join("");

    if (chunks.length > maxChunks) {
      container.innerHTML += `<div class="muted" style="text-align:center; margin-top:8px;">还有 ${chunks.length - maxChunks} 个 chunks 未显示</div>`;
    }
  }

  // 重置参数
  function resetParams() {
    $("previewStrategy").value = "recursive";
    $("previewChunkSize").value = "512";
    $("previewOverlapPercent").value = "20";
    $("previewDelimiters").value = "";
    Utils.showMessage("chunkPreviewMessage", "参数已重置", "info");
  }

  // 页面初始化
  function init() {
    // 绑定事件
    $("runPreviewBtn").addEventListener("click", runPreview);
    $("resetPreviewParamsBtn").addEventListener("click", resetParams);
    $("closeChunkPreviewModalBtn").addEventListener("click", () => Utils.hideModal("chunkPreviewModal"));
    $("chunkPreviewModalBackdrop").addEventListener("click", () => Utils.hideModal("chunkPreviewModal"));

    // 参数变更时自动重新预览（防抖）
    let debounceTimer;
    const autoPreview = () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(runPreview, 500);
    };

    $("previewStrategy").addEventListener("change", autoPreview);
    $("previewChunkSize").addEventListener("change", autoPreview);
    $("previewOverlapPercent").addEventListener("change", autoPreview);
    $("previewDelimiters").addEventListener("change", autoPreview);
    $("previewMaxChunks").addEventListener("change", () => {
      // 重新渲染列表（不重新请求）
      const currentData = {
        total_chunks: parseInt($("previewStatTotalChunks").textContent) || 0,
        total_chars: parseInt($("previewStatTotalChars").textContent?.replace(/,/g, "")) || 0,
        avg_chunk_size: parseFloat($("previewStatAvgSize").textContent) || 0,
        min_chunk_size: parseInt($("previewStatMinSize").textContent) || 0,
        max_chunk_size: parseInt($("previewStatMaxSize").textContent) || 0,
        chunks: window.lastPreviewChunks || [],
      };
      if (currentData.chunks.length) {
        updateChunkList(currentData.chunks);
      }
    });
  }

  // 导出全局方法
  window.ChunkPreview = {
    init,
    showPreview,
    showPreviewWithText,
    runPreview,
  };

  // 初始化
  init();
})();
