// milvus-dashboard.js - 知识库向量浏览
(function () {
  const $ = Utils.$;

  const MilvusDashboard = {
    chunks: [],
    vectors3D: [],
    selectedChunkId: null,
    currentPage: 1,
    pageSize: 50,

    init() {
      const token = API.getToken();
      if (!token) {
        alert("请先登录");
        window.location.href = "./app.html";
        return;
      }

      $("refreshBtn").addEventListener("click", () => this.loadAllData());
      $("applyFilter").addEventListener("click", () => this.loadAllData());
      $("searchInput").addEventListener("input", (e) => this.filterChunks(e.target.value));
      $("pageSize").addEventListener("change", () => this.loadAllData());

      this.loadAllData();
    },

    async loadAllData() {
      Utils.clearMessage();
      this.pageSize = parseInt($("pageSize").value);
      this.currentPage = 1;

      await Promise.all([
        this.loadChunkList(),
        this.loadDocuments(),
      ]);

      // Load visualization after chunks are loaded
      await this.loadVisualization();
    },

    async loadDocuments() {
      try {
        const data = await API.documents.list(1, 1000, "indexed");
        const select = $("documentFilter");
        select.innerHTML = '<option value="">全部文档</option>';

        data.documents.forEach(doc => {
          const option = document.createElement("option");
          option.value = doc.id;
          option.textContent = `${doc.filename} (${doc.total_chunks || 0} chunks)`;
          select.appendChild(option);
        });

        select.addEventListener("change", () => {
          this.loadChunkList().then(() => this.loadVisualization());
        });
      } catch (error) {
        console.error("Failed to load documents:", error);
      }
    },

    async loadChunkList() {
      try {
        const docFilter = $("documentFilter").value;
        const data = await API.documents.list(1, 1000, "indexed");

        let allChunks = [];
        for (const doc of data.documents) {
          if (docFilter && doc.id != docFilter) continue;

          try {
            const chunksData = await API.chunks.list(doc.id, 1, 1000);
            allChunks = allChunks.concat(chunksData.chunks.map(c => ({
              ...c,
              document_name: doc.filename,
              document_id: doc.id,
            })));
          } catch (e) {
            console.error(`Failed to load chunks for doc ${doc.id}:`, e);
          }
        }

        this.chunks = allChunks;
        this.renderChunkList();
      } catch (error) {
        console.error("Failed to load chunk list:", error);
        $("chunkList").innerHTML = `<p class="error">加载失败：${error.message}</p>`;
      }
    },

    renderChunkList(filteredChunks = null) {
      const chunks = filteredChunks || this.chunks;
      const start = (this.currentPage - 1) * this.pageSize;
      const end = start + this.pageSize;
      const pageChunks = chunks.slice(start, end);

      if (pageChunks.length === 0) {
        $("chunkList").innerHTML = '<p style="text-align: center; color: rgba(255,255,255,0.5); padding: 20px;">暂无chunk数据</p>';
        $("listStats").textContent = `共 0 个chunk`;
        return;
      }

      $("chunkList").innerHTML = pageChunks.map(chunk => `
        <div class="chunk-item" data-chunk-id="${chunk.id}" data-chunk-index="${chunk.chunk_index}">
          <div class="chunk-meta">
            📄 ${chunk.document_name} · 分段 #${chunk.chunk_index}
            · ${chunk.char_count || chunk.content?.length || 0} 字符
          </div>
          <div class="chunk-preview">${this.escapeHtml(chunk.content?.substring(0, 150) || '')}...</div>
        </div>
      `).join("");

      $("chunkList").querySelectorAll(".chunk-item").forEach(item => {
        item.addEventListener("click", () => {
          const chunkId = parseInt(item.dataset.chunkId);
          this.selectChunk(chunkId);
        });
      });

      $("listStats").textContent = `显示 ${start + 1}-${Math.min(end, chunks.length)} / 共 ${chunks.length} 个chunk`;
    },

    async loadVisualization() {
      const method = $("methodSelect").value;
      const limit = Math.min(this.chunks.length, 500);

      if (limit === 0) {
        $("vizStats").textContent = "暂无数据";
        $("vectorScatterPlot").innerHTML = '';
        return;
      }

      try {
        $("loadingStatus").textContent = "生成3D可视化中...";

        const data = await API.milvus.getEmbeddingVisualization(limit, method);

        // For 3D, we need 3 dimensions. If we only have 2, add a third dimension
        let vectors3D = data.vectors_2d;
        if (data.vectors_2d && data.vectors_2d.length > 0) {
          // Check if we have 2D or 3D data
          if (data.vectors_2d[0].z === undefined) {
            // Add 3rd dimension using a simple projection
            vectors3D = data.vectors_2d.map((v, i) => ({
              x: v.x,
              y: v.y,
              z: v.x * 0.5 + v.y * 0.5, // Simple 3rd dimension
              metadata: v.metadata
            }));
          }
        }

        this.vectors3D = vectors3D;
        this.render3DScatterPlot(vectors3D);

        $("vizStats").textContent = `方法: ${method === 'pca' ? 'PCA' : 't-SNE'} · 点数: ${data.total} · 3D可拖动旋转`;
        $("loadingStatus").textContent = "";
      } catch (error) {
        console.error("Visualization failed:", error);
        $("vizStats").innerHTML = `<span style="color: #ff6b6b">可视化失败: ${error.message}</span>`;
        $("loadingStatus").textContent = "";
      }
    },

    render3DScatterPlot(vectors) {
      if (!vectors || vectors.length === 0) {
        $("vectorScatterPlot").innerHTML = '<p style="text-align: center; color: rgba(255,255,255,0.5); padding: 50px;">暂无向量数据</p>';
        return;
      }

      // Map vectors to chunks and assign colors by document
      const colors = [
        '#64c8ff', '#ff6b9d', '#51cf66', '#ffd43b',
        '#cc5de8', '#ff922b', '#20c997', '#339af0'
      ];

      const pointsWithChunks = vectors.map((v, i) => {
        const chunk = this.chunks.find(c =>
          c.document_id === v.metadata.document_id &&
          c.chunk_index === v.metadata.chunk_index
        );
        const docId = chunk?.document_id || 0;
        return {
          x: v.x,
          y: v.y,
          z: v.z || 0,
          chunk: chunk,
          metadata: v.metadata,
          color: colors[docId % colors.length],
          name: chunk ? `${chunk.document_name} #${chunk.chunk_index}` : `Chunk ${i}`
        };
      });

      // Separate data by document for legend
      const traces = {};
      pointsWithChunks.forEach(p => {
        const docName = p.chunk?.document_name || 'Unknown';
        if (!traces[docName]) {
          traces[docName] = {
            x: [], y: [], z: [],
            text: [],
            mode: 'markers',
            type: 'scatter3d',
            name: docName,
            marker: {
              size: 5,
              color: p.color,
              line: {
                color: p.color,
                width: 0.5
              },
              opacity: 0.8
            },
            hovertemplate: '%{text}<extra></extra>'
          };
        }
        traces[docName].x.push(p.x);
        traces[docName].y.push(p.y);
        traces[docName].z.push(p.z);
        traces[docName].text.push(
          p.chunk ?
            `文档: ${p.chunk.document_name}<br>分段: #${p.chunk.chunk_index}<br>内容: ${p.chunk.content?.substring(0, 50) || ''}...` :
            `Unknown chunk`
        );
      });

      const plotData = Object.values(traces);

      const layout = {
        title: {
          text: '向量空间3D分布 (可拖动旋转)',
          font: { color: 'rgba(255,255,255,0.9)' }
        },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        scene: {
          xaxis: {
            title: '维度 1',
            backgroundcolor: 'rgba(0,0,0,0)',
            gridcolor: 'rgba(255,255,255,0.1)',
            showbackground: true,
            titlefont: { color: 'rgba(255,255,255,0.7)' },
            tickfont: { color: 'rgba(255,255,255,0.5)' },
            zerolinecolor: 'rgba(255,255,255,0.2)'
          },
          yaxis: {
            title: '维度 2',
            backgroundcolor: 'rgba(0,0,0,0)',
            gridcolor: 'rgba(255,255,255,0.1)',
            showbackground: true,
            titlefont: { color: 'rgba(255,255,255,0.7)' },
            tickfont: { color: 'rgba(255,255,255,0.5)' },
            zerolinecolor: 'rgba(255,255,255,0.2)'
          },
          zaxis: {
            title: '维度 3',
            backgroundcolor: 'rgba(0,0,0,0)',
            gridcolor: 'rgba(255,255,255,0.1)',
            showbackground: true,
            titlefont: { color: 'rgba(255,255,255,0.7)' },
            tickfont: { color: 'rgba(255,255,255,0.5)' },
            zerolinecolor: 'rgba(255,255,255,0.2)'
          },
          camera: {
            eye: { x: 1.5, y: 1.5, z: 1.5 }
          }
        },
        margin: { l: 0, r: 0, b: 0, t: 40 },
        showlegend: true,
        legend: {
          font: { color: 'rgba(255,255,255,0.8)' },
          bgcolor: 'rgba(0,0,0,0.3)',
          bordercolor: 'rgba(255,255,255,0.1)',
          borderwidth: 1
        },
        hovermode: 'closest'
      };

      const config = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d']
      };

      Plotly.newPlot('vectorScatterPlot', plotData, layout, config);

      // Add click handler
      $('vectorScatterPlot').on('plotly_click', (data) => {
        const point = data.points[0];
        const chunk = this.chunks.find(c =>
          c.document_id === point.data.customdata?.[point.pointIndex]?.document_id &&
          c.chunk_index === point.data.customdata?.[point.pointIndex]?.chunk_index
        );

        if (chunk) {
          this.selectChunk(chunk.id);
        }
      });
    },

    selectChunk(chunkId) {
      document.querySelectorAll(".chunk-item").forEach(el => el.classList.remove("active"));

      const chunkItem = document.querySelector(`.chunk-item[data-chunk-id="${chunkId}"]`);
      if (chunkItem) {
        chunkItem.classList.add("active");
        chunkItem.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      const chunk = this.chunks.find(c => c.id === chunkId);
      if (!chunk) return;

      $("chunkDetail").innerHTML = `
        <div style="margin-bottom: 10px;">
          <strong>📄 文档:</strong> ${chunk.document_name}<br>
          <strong>🔢 分段索引:</strong> ${chunk.chunk_index}<br>
          <strong>📏 字符数:</strong> ${chunk.char_count || chunk.content?.length || 0}<br>
          ${chunk.included !== undefined ? `<strong>✅ 已索引:</strong> ${chunk.included ? '是' : '否'}<br>` : ''}
        </div>
        <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1);">
          <strong>📝 内容:</strong><br>
          <div style="white-space: pre-wrap; word-wrap: break-word; max-height: 150px; overflow-y: auto; line-height: 1.6;">
            ${this.escapeHtml(chunk.content || '(空)')}
          </div>
        </div>
      `;

      this.selectedChunkId = chunkId;

      // Highlight the point in 3D plot
      if (window.Plotly && this.vectors3D.length > 0) {
        const point = this.vectors3D.find(v =>
          v.metadata.document_id === chunk.document_id &&
          v.metadata.chunk_index === chunk.chunk_index
        );
        if (point) {
          // Could add highlighting logic here
        }
      }
    },

    filterChunks(searchText) {
      if (!searchText) {
        this.renderChunkList();
        return;
      }

      const filtered = this.chunks.filter(chunk =>
        chunk.content?.toLowerCase().includes(searchText.toLowerCase()) ||
        chunk.document_name?.toLowerCase().includes(searchText.toLowerCase())
      );

      this.renderChunkList(filtered);
    },

    escapeHtml(text) {
      if (!text) return '';
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  };

  window.MilvusDashboard = MilvusDashboard;

  document.addEventListener("DOMContentLoaded", () => {
    MilvusDashboard.init();
  });
})();
