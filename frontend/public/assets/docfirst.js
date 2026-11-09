// Document-First & Intelligent Auto-Fill Module for HS Workspace

(async function() {
  const {groupFacts, requiredFields, missingFields, editFactGroup} = await import('/assets/fact-review.js?v=20261104-1');
  console.log("[DocFirst] Module initialized.");

  // Helper to fetch API with proper headers
  async function api(path, options = {}) {
    const key = localStorage.getItem("hs_api_key");
    const headers = { ...(options.headers || {}) };
    if (key) headers["X-API-Key"] = key;
    
    // Don't set Content-Type if body is FormData
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const res = await fetch("/api/v2" + path, { ...options, headers });
    if (!res.ok) {
      let msg = "HTTP " + res.status;
      try {
        const data = await res.json();
        msg = data.detail || data.error || msg;
      } catch (e) {}
      throw new Error(msg);
    }
    return await res.json();
  }

  // Toast notification
  function showToast(msg, isError = false) {
    const el = document.createElement("div");
    el.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 12px 20px;
      background: ${isError ? "#EF4444" : "#0F172A"};
      color: #FFF;
      border-radius: 10px;
      font-size: 13.5px;
      font-weight: 500;
      box-shadow: 0 4px 16px rgba(0,0,0,0.18);
      z-index: 100000;
      transition: all 0.3s ease;
      display: flex;
      align-items: center;
      gap: 10px;
    `;
    el.innerHTML = (isError ? "⚠️ " : "✓ ") + msg;
    document.body.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 300);
    }, 3500);
  }

  // Escape HTML helper
  function esc(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Format file size
  function fmtSize(bytes) {
    if (!bytes) return "0 B";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  // --- MODAL: Document-First Create Case ---
  function openCreateCaseModal() {
    let activeTab = "docfirst";
    let selectedFiles = [];
    let isProcessing = false;

    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.style.cssText = "z-index: 9999;";

    function render() {
      overlay.innerHTML = `
        <section class="modal modal-wide" role="dialog" aria-modal="true" style="max-width: 680px; z-index: 10000;">
          <div class="modal-head">
            <div>
              <h2>Tạo hồ sơ phân loại mới</h2>
              <p>Chọn phương thức tạo hồ sơ phù hợp với bộ chứng từ bạn có</p>
            </div>
            <button class="icon-btn close-modal-btn" aria-label="Đóng">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
          
          <div class="modal-body" style="padding-top: 10px;">
            <div class="docfirst-tabs">
              <button class="docfirst-tab ${activeTab === 'docfirst' ? 'active' : ''}" data-tab="docfirst">
                <span>📄 Tạo từ chứng từ</span>
                <span class="docfirst-badge-rec">Khuyên dùng</span>
              </button>
              <button class="docfirst-tab ${activeTab === 'manual' ? 'active' : ''}" data-tab="manual">
                <span>✍️ Nhập thủ công</span>
              </button>
            </div>

            ${activeTab === 'docfirst' ? `
              <div class="docfirst-content">
                <div class="doc-dropzone" id="docDropzone">
                  <div style="font-size: 32px; margin-bottom: 8px;">📤</div>
                  <strong style="display:block; font-size: 14.5px; color: #1E293B;">Kéo thả hoặc nhấn để chọn chứng từ</strong>
                  <p style="font-size: 12.5px; color: #64748B; margin: 4px 0 14px;">Hỗ trợ PDF, Word (DOCX), Excel (XLSX), TXT, ảnh (PNG/JPG) hoặc gói ZIP</p>
                  <input type="file" id="docFileInput" multiple style="display: none;" accept=".pdf,.docx,.xlsx,.xls,.txt,.png,.jpg,.jpeg,.zip" />
                  <button type="button" class="btn" id="btnSelectFiles" style="background: #E2E8F0; font-size: 13px;">Chọn tệp từ máy tính</button>
                </div>

                ${selectedFiles.length > 0 ? `
                  <div style="margin-top: 14px;">
                    <div style="font-size: 12px; font-weight: 700; color: #64748B; margin-bottom: 6px; text-transform: uppercase;">Tệp đã chọn (${selectedFiles.length})</div>
                    <div style="max-height: 160px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;">
                      ${selectedFiles.map((f, idx) => `
                        <div class="doc-file-chip">
                          <div class="chip-name">
                            <span>📄</span>
                            <div>
                              <div style="font-weight: 600; font-size: 13px;">${esc(f.name)}</div>
                              <div style="font-size: 11px; color: #64748B;">${fmtSize(f.size)}</div>
                            </div>
                          </div>
                          <button class="icon-btn btn-remove-file" data-idx="${idx}" style="padding: 4px; color: #94A3B8;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                          </button>
                        </div>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}

                <div class="notice amber" style="margin-top: 14px; font-size: 12.5px;">
                  <span>💡</span>
                  <div>Hệ thống sẽ tự động đọc, nhận diện loại chứng từ, trích xuất thông tin doanh nghiệp, lô hàng và các dòng hàng SKU để điền vào hồ sơ. Bạn sẽ được xem và xác nhận trước khi lưu.</div>
                </div>
              </div>
            ` : `
              <form id="manualForm" style="display: flex; flex-direction: column; gap: 14px;">
                <label class="field">
                  <span>Tên hồ sơ phân loại *</span>
                  <input type="text" name="title" required placeholder="VD: Nhập khẩu máy sấy tóc gia dụng" />
                </label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                  <label class="field">
                    <span>Loại hình giao dịch</span>
                    <select name="trade_type">
                      <option value="import">Nhập khẩu</option>
                      <option value="export">Xuất khẩu</option>
                    </select>
                  </label>
                  <label class="field">
                    <span>Ngày phân loại</span>
                    <input type="date" name="classification_date" value="${new Date().toISOString().split('T')[0]}" />
                  </label>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                  <label class="field">
                    <span>Người nhập khẩu / Khai báo</span>
                    <input type="text" name="importer_name" placeholder="Tên công ty nhập khẩu" />
                  </label>
                  <label class="field">
                    <span>Người xuất khẩu / Nhà cung cấp</span>
                    <input type="text" name="exporter_name" placeholder="Tên đối tác nước ngoài" />
                  </label>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                  <label class="field">
                    <span>Số hóa đơn (Invoice No.)</span>
                    <input type="text" name="invoice_number" placeholder="VD: INV-2026-001" />
                  </label>
                  <label class="field">
                    <span>Người lập hồ sơ</span>
                    <input type="text" name="created_by" value="Ngọc Hân" />
                  </label>
                </div>
                <label class="field">
                  <span>Ghi chú ban đầu</span>
                  <textarea name="notes" rows="2" placeholder="Ghi chú nội bộ về lô hàng"></textarea>
                </label>
              </form>
            `}
          </div>

          <div class="modal-foot" style="margin-top: 14px; display: flex; justify-content: flex-end; gap: 10px;">
            <button type="button" class="btn close-modal-btn">Hủy</button>
            ${activeTab === 'docfirst' ? `
              <button type="button" class="btn primary" id="btnProcessDocFirst" ${selectedFiles.length === 0 || isProcessing ? 'disabled' : ''}>
                ${isProcessing ? '⏳ Đang phân tích chứng từ…' : '⚡ Tự động xử lý & Tiếp tục →'}
              </button>
            ` : `
              <button type="button" class="btn primary" id="btnSubmitManual">Tạo hồ sơ</button>
            `}
          </div>
        </section>
      `;

      bindEvents();
    }

    function bindEvents() {
      overlay.querySelectorAll(".close-modal-btn").forEach(btn => {
        btn.onclick = () => overlay.remove();
      });

      overlay.querySelectorAll(".docfirst-tab").forEach(btn => {
        btn.onclick = () => {
          activeTab = btn.getAttribute("data-tab");
          render();
        };
      });

      const dropzone = overlay.querySelector("#docDropzone");
      const fileInput = overlay.querySelector("#docFileInput");
      const btnSelect = overlay.querySelector("#btnSelectFiles");

      if (dropzone && fileInput) {
        dropzone.onclick = (e) => {
          if (e.target.id !== "btnSelectFiles") fileInput.click();
        };
        if (btnSelect) btnSelect.onclick = (e) => { e.stopPropagation(); fileInput.click(); };

        dropzone.ondragover = (e) => { e.preventDefault(); dropzone.classList.add("dragover"); };
        dropzone.ondragleave = () => dropzone.classList.remove("dragover");
        dropzone.ondrop = (e) => {
          e.preventDefault();
          dropzone.classList.remove("dragover");
          if (e.dataTransfer.files) {
            selectedFiles = [...selectedFiles, ...Array.from(e.dataTransfer.files)];
            render();
          }
        };

        fileInput.onchange = () => {
          if (fileInput.files) {
            selectedFiles = [...selectedFiles, ...Array.from(fileInput.files)];
            render();
          }
        };
      }

      overlay.querySelectorAll(".btn-remove-file").forEach(btn => {
        btn.onclick = (e) => {
          e.stopPropagation();
          const idx = parseInt(btn.getAttribute("data-idx"), 10);
          selectedFiles.splice(idx, 1);
          render();
        };
      });

      // Submit Document-First
      const btnProcess = overlay.querySelector("#btnProcessDocFirst");
      if (btnProcess) {
        btnProcess.onclick = async () => {
          if (!selectedFiles.length) return;
          isProcessing = true;
          render();
          try {
            const fd = new FormData();
            selectedFiles.forEach(f => fd.append("files", f));
            const draft = await api("/autofill/draft", { method: "POST", body: fd });
            overlay.remove();
            openReviewWorkspaceModal(draft);
          } catch (err) {
            isProcessing = false;
            render();
            showToast("Lỗi phân tích chứng từ: " + err.message, true);
          }
        };
      }

      // Submit Manual
      const btnManual = overlay.querySelector("#btnSubmitManual");
      if (btnManual) {
        btnManual.onclick = async () => {
          const form = overlay.querySelector("#manualForm");
          if (!form) return;
          if (!form.reportValidity()) return;
          const fd = new FormData(form);
          const payload = Object.fromEntries(fd.entries());
          try {
            const newCase = await api("/cases", { method: "POST", body: JSON.stringify(payload) });
            overlay.remove();
            showToast("Tạo hồ sơ thành công!");
            window.location.hash = "#case/" + newCase.id;
            setTimeout(() => window.location.reload(), 150);
          } catch (err) {
            showToast("Lỗi tạo hồ sơ: " + err.message, true);
          }
        };
      }
    }

    document.body.appendChild(overlay);
    render();
  }

  // --- MODAL: Review Workspace for Auto-fill Draft ---
  // Map friendly Vietnamese labels for technical facts
  const FACT_LABELS = {
    name: "Tên / Bản chất mặt hàng",
    function: "Công dụng / Chức năng sử dụng",
    specifications: "Thông số kỹ thuật (Công suất, Kích thước...)",
    material: "Chất liệu / Thành phần cấu tạo",
    construction: "Cấu tạo / Nguyên lý hoạt động",
    manufacturing: "Quy trình sản xuất / Chế biến",
    condition: "Tình trạng hàng hóa",
    packaging: "Quy cách đóng gói", model: "Model / SKU", part_number: "Part number",
    quantity: "Số lượng", unit: "Đơn vị", unit_price: "Đơn giá", amount: "Thành tiền",
    currency: "Tiền tệ", origin: "Xuất xứ", net_weight: "Khối lượng tịnh",
    gross_weight: "Khối lượng cả bì", packages: "Số kiện", declared_code: "HS khai báo trên nguồn"
  };

  const PRODUCT_FAMILIES = {
    general: "Hàng thông thường / Đa dụng",
    electronic: "Điện tử / Thiết bị điện gia dụng",
    machine: "Máy móc / Thiết bị cơ khí công nghiệp",
    steel: "Thép / Kim loại / Hợp kim",
    food: "Thực phẩm / Muối / Nông sản",
    feed: "Thức ăn chăn nuôi / Cám chiết xuất",
    chemical: "Hóa chất / Dung môi / Hợp chất",
    laser: "Thiết bị quang học / Diode Laser"
  };

  const SHIPMENT_FIELDS = new Set(['quantity','unit','unit_price','amount','currency','origin','net_weight','gross_weight','packages','declared_code']);

  function renderSources(group, showValue = false) {
    const seen = new Set();
    const sources = group.facts.filter(f => {
      if (!f.quote) return false;
      const key = JSON.stringify([f.document_id, f.page_number, f.source_row_id, f.source_header, f.quote, f.value]);
      if (seen.has(key)) return false;
      seen.add(key); return true;
    });
    if (!sources.length) return '';
    return `<details class="fact-source-list" style="margin-top:6px"><summary style="cursor:pointer;font-size:12px;color:#64748B">${showValue ? 'Tên trên chứng từ · ' : 'Đối chiếu · '}${sources.length} nguồn</summary>${sources.map(f => `<div style="font-size:12px;color:#64748B;margin-top:6px;padding:6px 8px;border-left:2px solid #0284C7;background:#FFF">
      <strong>${esc(f.document_name || 'Chứng từ')} · Trang ${esc(f.page_number || 1)}</strong>
      ${f.source_row_id ? ' · Dòng ' + esc(f.source_row_id) : ''}${f.source_header ? ' · Cột ' + esc(f.source_header) : ''}
      <div>Giá trị trên nguồn: ${esc(f.value)}${f.unit ? ' ' + esc(f.unit) : ''}</div><div>“${esc(f.quote)}”</div></div>`).join('')}</details>`;
  }

  function renderFactSection(sku, sIdx, shipment) {
    const required = requiredFields(sku.product_family);
    const groups = groupFacts(sku.facts).filter(g => g.field !== 'name' && SHIPMENT_FIELDS.has(g.field) === shipment && (g.value.trim() || required.includes(g.field)));
    if (!groups.length) return '';
    return `<div style="background:#FFF;border:1px solid #E2E8F0;border-radius:8px;padding:12px;margin-top:10px">
      <div style="font-size:12px;font-weight:700;color:#64748B;margin-bottom:8px">${shipment ? 'SỐ LƯỢNG, TRỊ GIÁ & THÔNG TIN LÔ HÀNG' : 'THUỘC TÍNH PHÂN LOẠI HS'}</div>
      <div style="display:flex;flex-direction:column;gap:8px">${groups.map(group => {
        const conflict = group.facts.some(f => f.status === 'conflict' || f.extraction_status === 'conflicting');
        const edited = group.facts.some(f => f.source_kind === 'user_input');
        const hasSource = group.facts.some(f => f.quote);
        const label = conflict ? 'Mâu thuẫn · cần giải quyết' : edited ? 'Người dùng nhập · cần kiểm tra' : hasSource ? 'Có nguồn · cần kiểm tra' : 'Cần bổ sung';
        return `<div class="review-fact-group" data-field="${esc(group.field)}" style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:8px 10px">
          <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px"><label for="fact-${sIdx}-${group.indices[0]}" style="font-size:13px;font-weight:600;color:#0284C7">${esc(FACT_LABELS[group.field] || group.field)}${group.facts[0].unit ? ' · ' + esc(group.facts[0].unit) : ''}</label><span style="font-size:12px;color:${conflict ? '#DC2626' : '#64748B'}">${label}</span></div>
          <textarea id="fact-${sIdx}-${group.indices[0]}" class="sku-fact-value-input" data-sidx="${sIdx}" data-findices="${esc(JSON.stringify(group.indices))}" data-original-value="${esc(group.value)}" rows="${shipment ? 1 : 2}" style="width:100%;padding:6px 10px;border:1px solid #CBD5E1;border-radius:4px;resize:vertical">${esc(group.value)}</textarea>
          ${renderSources(group)}</div>`;
      }).join('')}</div></div>`;
  }

  // --- MODAL: Document-First Review & Confirmation Workspace ---
  function openReviewWorkspaceModal(draft) {
    let currentDocIdx = 0;
    let currentPageIdx = 0;
    let isSaving = false;

    // Working state
    const docs = draft.documents || [];
    const caseData = { ...(draft.extracted_case || {}) };
    const dossier = JSON.parse(JSON.stringify(draft.dossier_fields || {}));
    
    // Fallback if title is missing
    if (!caseData.title) {
      if (draft.dossier_fields?.title?.value) {
        caseData.title = draft.dossier_fields.title.value;
      } else if (draft.dossier_fields?.importer?.value) {
        caseData.title = "Hồ sơ nhập khẩu " + draft.dossier_fields.importer.value;
      } else if (draft.dossier_fields?.exporter?.value) {
        caseData.title = "Hồ sơ xuất khẩu " + draft.dossier_fields.exporter.value;
      } else if (docs.length > 0) {
        const rawName = docs[0].name || docs[0].filename || "chứng từ";
        const cleanName = rawName.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
        caseData.title = "Hồ sơ " + cleanName;
      } else {
        caseData.title = "Hồ sơ phân loại từ chứng từ";
      }
    }

    if (!caseData.trade_type) caseData.trade_type = "import";
    if (!caseData.owner) caseData.owner = "Nhóm 8";
    if (!caseData.classification_date) {
      caseData.classification_date = new Date().toLocaleDateString("en-CA", {timeZone: "Asia/Ho_Chi_Minh"});
    }
    if (!caseData.declaration_number) {
      caseData.declaration_number = draft.dossier_fields?.declaration_number?.value || "";
    }
    if (!caseData.notes) {
      caseData.notes = `Tự động trích xuất từ bộ chứng từ (${docs.length} tệp) của cùng lô hàng.`;
    }

    let reconciliation = draft.reconciliation || draft.reconciliations || [];
    let skus = [...(draft.proposed_skus || draft.skus || [])];

    const REQUIRED_FIELDS = requiredFields('general');
    function ensureRequiredFacts(sku) {
      sku.facts ||= [];
      for (const field of requiredFields(sku.product_family)) {
        if (!sku.facts.some(f => f.field === field)) sku.facts.push({field, value:'', source_kind:'user_input', extraction_status:'missing', quote:'', status:'unverified'});
      }
    }

    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.style.cssText = "z-index: 10000;";

    function render() {
      skus.forEach(ensureRequiredFacts);
      const activeDoc = docs[currentDocIdx] || null;
      let activeDocText = "";
      if (activeDoc) {
        activeDocText = activeDoc.pages?.[currentPageIdx]?.text || activeDoc.text_content || activeDoc.text || '';
      }

      overlay.innerHTML = `
        <section class="modal modal-wide" role="dialog" aria-modal="true" style="width: 95vw; max-width: 1280px; height: 92vh; display: flex; flex-direction: column;">
          <div class="modal-head" style="flex-shrink: 0; padding: 14px 24px; border-bottom: 1px solid #E2E8F0;">
            <div>
              <div style="display: flex; align-items: center; gap: 10px;">
                <h2 style="margin: 0; font-size: 18px; font-weight: 700; color: #0F172A;">Trích xuất & Tự động điền hồ sơ từ chứng từ</h2>
                <span class="status-pill-verified" style="background: #E0F2FE; color: #0369A1; font-weight: 600;">Document-First Auto-Fill</span>
              </div>
              <p style="margin: 4px 0 0; color: #64748B; font-size: 13px;">Đối chiếu giá trị, trang nguồn và cảnh báo trước khi xác nhận hồ sơ (${docs.length} chứng từ).</p>
            </div>
            <button class="icon-btn close-modal-btn" aria-label="Đóng">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>

          <div class="review-workspace-container" style="flex: 1; display: flex; overflow: hidden; padding: 16px 24px; gap: 20px; background: #F8FAFC;">
            <!-- LEFT PANE: Documents list & Text Preview -->
            <div class="review-left-pane" style="width: 38%; display: flex; flex-direction: column; background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 14px; overflow: hidden;">
              <div style="font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; margin-bottom: 8px; display: flex; justify-content: space-between;">
                <span>Bộ chứng từ lô hàng (${docs.length})</span>
                <span style="font-weight: 500; color: #0284C7;">Cùng 1 hồ sơ</span>
              </div>
              <div class="review-doc-nav" style="display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 10px; border-bottom: 1px solid #F1F5F9;">
                ${docs.map((d, idx) => `
                  <button type="button" class="review-doc-tab ${idx === currentDocIdx ? 'active' : ''}" data-idx="${idx}" style="font-size: 12.5px; padding: 6px 12px; border-radius: 6px; border: 1px solid ${idx === currentDocIdx ? '#0284C7' : '#E2E8F0'}; background: ${idx === currentDocIdx ? '#EFF6FF' : '#FFF'}; color:#0F172A; font-weight: ${idx === currentDocIdx ? '600' : '500'}; white-space: nowrap; cursor: pointer;">
                    📄 ${esc(d.name || d.filename || ('Chứng từ ' + (idx + 1)))}
                  </button>
                `).join('')}
              </div>

              ${activeDoc ? `
                <div style="background: #F1F5F9; padding: 8px 12px; border-radius: 8px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; font-size: 12px;">
                  <div>
                    <span style="color: #64748B;">Loại chứng từ:</span>
                    <strong style="color: #0369A1; margin-left: 4px;">${esc(activeDoc.document_type_name || activeDoc.kind || 'Chứng từ')}</strong>
                  </div>
                  <span style="color: #64748B;">${activeDoc.pages ? activeDoc.pages.length + ' trang' : ''}</span>
                  ${activeDoc.pages?.length > 1 ? `<select id="reviewPageSelect" aria-label="Trang nguồn">${activeDoc.pages.map((p,i) => `<option value="${i}" ${i === currentPageIdx ? 'selected' : ''}>Trang ${p.number || i+1}</option>`).join('')}</select>` : ''}
                </div>
                <div style="flex: 1; overflow-y: auto; background: #FAFAFA; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 12px; line-height: 1.5; color: #334155; white-space: pre-wrap;">${esc(activeDocText || 'Không có nội dung văn bản sau trích xuất.')}</div>
              ` : '<div style="padding: 20px; color: #94A3B8;">Chưa có chứng từ nào được tải lên.</div>'}
            </div>

            <!-- RIGHT PANE: Extracted Case & SKU Facts Form -->
            <div class="review-right-pane" style="flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding-right: 4px;">
              <!-- 1. Case Header Form (Identical to Manual Case Creation) -->
              <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 16px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #F1F5F9;">
                  <span style="font-size: 16px;">🏢</span>
                  <strong style="font-size: 14.5px; color: #0F172A;">1. Thông tin Hồ sơ Lô hàng</strong>
                  <span style="font-size: 12px; color: #10B981; margin-left: auto;">Cần kiểm tra · gồm mặc định hệ thống</span>
                </div>

                <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 12px;">
                  <label class="field" style="grid-column: 1 / -1;">
                    <span style="font-weight: 600; font-size: 13px; color: #1E293B; margin-bottom: 4px; display: block;">Tên hồ sơ phân loại *</span>
                    <input type="text" id="caseTitle" value="${esc(caseData.title || '')}" style="width: 100%; padding: 8px 12px; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13.5px; font-weight: 600;" placeholder="Ví dụ: Lô hàng máy sấy tóc cầm tay 1200W" />
                  </label>

                  <label class="field">
                    <span style="font-weight: 600; font-size: 13px; color: #1E293B; margin-bottom: 4px; display: block;">Luồng hàng</span>
                    <select id="caseTradeType" style="width: 100%; padding: 8px 12px; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px;">
                      <option value="import" ${caseData.trade_type === 'import' ? 'selected' : ''}>Nhập khẩu</option>
                      <option value="export" ${caseData.trade_type === 'export' ? 'selected' : ''}>Xuất khẩu</option>
                    </select>
                  </label>

                  <label class="field">
                    <span style="font-weight: 600; font-size: 13px; color: #1E293B; margin-bottom: 4px; display: block;">Ngày phân loại</span>
                    <input type="date" id="caseClassDate" value="${esc(caseData.classification_date || '')}" style="width: 100%; padding: 8px 12px; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px;" />
                  </label>

                  <label class="field">
                    <span style="font-weight: 600; font-size: 13px; color: #1E293B; margin-bottom: 4px; display: block;">Số tờ khai (nếu có)</span>
                    <input type="text" id="caseDeclNum" value="${esc(caseData.declaration_number || '')}" style="width: 100%; padding: 8px 12px; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px;" placeholder="Ví dụ: 105829103920" />
                  </label>

                  <label class="field">
                    <span style="font-weight: 600; font-size: 13px; color: #1E293B; margin-bottom: 4px; display: block;">Người phụ trách</span>
                    <input type="text" id="caseOwner" value="${esc(caseData.owner || 'Nhóm 8')}" style="width: 100%; padding: 8px 12px; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px;" />
                  </label>

                  <label class="field" style="grid-column: 1 / -1;">
                    <span style="font-weight: 600; font-size: 13px; color: #1E293B; margin-bottom: 4px; display: block;">Ghi chú hồ sơ</span>
                    <input type="text" id="caseNotes" value="${esc(caseData.notes || '')}" style="width: 100%; padding: 8px 12px; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px;" placeholder="Ghi chú thêm về lô hàng..." />
                  </label>
                </div>
              </div>

              <div style="background:#fff;padding:14px;border:1px solid #CBD5E1;border-radius:8px;margin-bottom:12px">
                <strong>Thông tin chứng từ · cần kiểm tra</strong>
                ${Object.entries(dossier).map(([field,f]) => `<label style="display:block;margin-top:8px">${esc(field.replaceAll('_',' '))}
                  <input class="dossier-value-input" data-field="${esc(field)}" value="${esc(f.value || '')}" style="width:100%"/>
                  <small>${f.status === 'conflicting' ? 'Mâu thuẫn · cần chọn giá trị' : f.source_kind === 'user_input' ? 'Người dùng chỉnh sửa' : 'Có nguồn · chưa xác minh'}</small>
                  ${(f.sources || f.alternatives || [f]).map(source => `<div class="field-provenance-quote">${esc(source.source_document_name)} · Trang ${esc(source.source_page)}: “${esc(source.source_quote || source.source_excerpt)}”</div>`).join('')}
                </label>`).join('')}
              </div>

              ${reconciliation.length ? `<details style="background:#fff;padding:12px"><summary>Đối chiếu: ${reconciliation.filter(r => r.status === 'conflict').length} mâu thuẫn · ${reconciliation.filter(r => r.status === 'missing').length} thiếu dữ liệu · ${reconciliation.filter(r => r.status === 'match').length} khớp</summary>${reconciliation.map(r => `<p><strong>${esc(r.label)}</strong> — ${esc(r.status === 'match' ? 'Khớp' : r.status === 'conflict' ? 'Mâu thuẫn' : 'Thiếu dữ liệu / cần kiểm tra')}<br>${esc(r.description)}</p>`).join('')}</details>` : ''}
              <!-- 2. SKUs and Technical Facts (The Core HS Classification Input) -->
              <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 16px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #F1F5F9;">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 16px;">📦</span>
                    <strong style="font-size: 14.5px; color: #0F172A;">2. Mặt hàng (SKU) & Thuộc tính phân loại HS</strong>
                    <span style="background: #EFF6FF; color: #0284C7; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 12px;">${skus.length} SKU</span>
                  </div>
                  <button type="button" class="btn" id="btnAddSkuRow" style="font-size: 12px; padding: 4px 10px; background: #F1F5F9; border: 1px solid #CBD5E1;">+ Thêm dòng hàng</button>
                </div>

                ${(draft.warnings || []).map(w => `<p style="color:#92400E">Cần rà soát trang ${esc(w.page)}: ${esc(w.message)}</p>`).join("")}
                ${skus.length === 0 ? "<p>Cần rà soát: chưa xác định được SKU từ chứng từ.</p>" : ""}
                ${skus.map((sku, sIdx) => `
                  <div style="border: 1px solid #CBD5E1; border-radius: 10px; padding: 14px; margin-bottom: 16px; background: #F8FAFC;">
                    ${missingFields(sku).length ? `<p>Cần bổ sung: ${missingFields(sku).map(f => esc(FACT_LABELS[f] || f)).join(", ")}</p>` : ""}
                    ${(sku.matching || []).filter(l => l.status === 'needs_review' && skus.some(s => s.id === l.candidate_id)).filter((l, i, links) => links.findIndex(x => x.candidate_id === l.candidate_id) === i).map(l => `<p>Cần xác nhận ghép sản phẩm: ${esc(l.reasons.join(', '))} <button type="button" class="confirm-product-match" data-target="${esc(sku.id)}" data-source="${esc(l.candidate_id)}">Xác nhận cùng sản phẩm</button></p>`).join('')}
                    <!-- SKU Header Line -->
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #E2E8F0;">
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="background: #0284C7; color: #FFF; font-weight: 700; font-size: 11px; padding: 2px 6px; border-radius: 4px;">SKU #${sIdx + 1}</span>
                        <input type="text" class="sku-code-input" data-sidx="${sIdx}" value="${esc(sku.sku_code || 'SKU-' + (sIdx + 1))}" style="width: 110px; font-weight: 600; font-size: 12.5px; padding: 4px 8px; border: 1px solid #CBD5E1; border-radius: 4px;" placeholder="Mã SKU" />
                        <select class="sku-family-select" data-sidx="${sIdx}" style="padding: 4px 8px; font-size: 12.5px; border: 1px solid #CBD5E1; border-radius: 4px;">
                          ${Object.entries(PRODUCT_FAMILIES).map(([k, v]) => `
                            <option value="${k}" ${sku.product_family === k ? 'selected' : ''}>${v}</option>
                          `).join('')}
                        </select>
                      </div>
                      <div style="display: flex; align-items: center; gap: 10px;">
                        <label style="font-size: 12px; color: #64748B; display: flex; align-items: center; gap: 4px;">
                          <span>Mã HS quan sát:</span>
                          <input type="text" class="sku-declared-code-input" data-sidx="${sIdx}" value="${esc(sku.declared_code || '')}" style="width: 100px; padding: 4px 8px; font-size: 12px; font-family: monospace; border: 1px solid #CBD5E1; border-radius: 4px;" placeholder="8 số / 6 số" />
                        </label>
                        ${skus.length > 1 ? `
                          <button type="button" class="icon-btn btn-remove-sku" data-sidx="${sIdx}" style="color: #EF4444; padding: 4px;" title="Xóa mặt hàng này">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                          </button>
                        ` : ''}
                      </div>
                    </div>

                    <!-- SKU Main Name -->
                    <div style="margin-bottom: 12px;">
                      <label style="display: block; font-size: 12.5px; font-weight: 600; color: #334155; margin-bottom: 4px;">Tên hàng hóa / Bản chất mặt hàng *</label>
                      <input type="text" class="sku-name-input" data-sidx="${sIdx}" value="${esc(sku.name || '')}" style="width: 100%; padding: 8px 12px; font-size: 13.5px; border: 1px solid #CBD5E1; border-radius: 6px; font-weight: 600;" placeholder="Nhập tên kỹ thuật của hàng hóa..." />
                    </div>

                    ${groupFacts(sku.facts).filter(g => g.field === 'name' && g.value.trim()).map(g => renderSources(g, true)).join('')}
                    ${renderFactSection(sku, sIdx, false)}
                    ${renderFactSection(sku, sIdx, true)}
                  </div>
                `).join('')}
              </div>
            </div>
          </div>

          <!-- FOOTER ACTIONS -->
          <div class="modal-foot" style="flex-shrink: 0; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; background: #FFFFFF; border-top: 1px solid #E2E8F0;">
            <button type="button" class="btn close-modal-btn">Hủy</button>
            <div style="display: flex; gap: 12px; align-items: center;">
              <span style="font-size: 12.5px; color: #64748B;">Hồ sơ và chứng từ sẽ được lưu đầy đủ vào không gian làm việc.</span>
              <button type="button" class="btn primary" id="btnCommitCase" ${isSaving ? 'disabled' : ''} style="padding: 10px 22px; font-weight: 700; font-size: 13.5px; background: #0284C7;">
                ${isSaving ? '⏳ Đang tạo hồ sơ…' : '✓ Xác nhận & Tạo hồ sơ phân loại'}
              </button>
            </div>
          </div>
        </section>
      `;

      bindEvents();
    }

    function syncInputs() {
      const getVal = id => {
        const el = overlay.querySelector(id);
        return el ? el.value : "";
      };
      caseData.title = getVal("#caseTitle");
      caseData.trade_type = getVal("#caseTradeType") || "import";
      caseData.classification_date = getVal("#caseClassDate") || new Date().toISOString().split("T")[0];
      caseData.owner = getVal("#caseOwner") || "Nhóm 8";
      caseData.declaration_number = getVal("#caseDeclNum");
      caseData.notes = getVal("#caseNotes");

      overlay.querySelectorAll('.dossier-value-input').forEach(el => { const field=el.getAttribute('data-field'); if (dossier[field].value !== el.value) dossier[field]={...dossier[field],value:el.value,source_kind:'user_input'}; });
      // Sync SKUs
      skus.forEach((s, sIdx) => {
        const codeEl = overlay.querySelector(`.sku-code-input[data-sidx="${sIdx}"]`);
        if (codeEl) s.sku_code = codeEl.value;
        const familyEl = overlay.querySelector(`.sku-family-select[data-sidx="${sIdx}"]`);
        if (familyEl) s.product_family = familyEl.value;
        const nameEl = overlay.querySelector(`.sku-name-input[data-sidx="${sIdx}"]`);
        if (nameEl) s.name = nameEl.value;
        const declEl = overlay.querySelector(`.sku-declared-code-input[data-sidx="${sIdx}"]`);
        if (declEl) s.declared_code = declEl.value;

        // One editor updates the represented source records; original quotes stay intact.
        overlay.querySelectorAll(`.sku-fact-value-input[data-sidx="${sIdx}"]`).forEach(el => {
          if (el.value !== el.getAttribute('data-original-value')) {
            editFactGroup(s, JSON.parse(el.getAttribute('data-findices')), el.value);
          }
        });
      });
    }

    function bindEvents() {
      overlay.querySelectorAll(".close-modal-btn").forEach(btn => {
        btn.onclick = () => overlay.remove();
      });

      overlay.querySelectorAll(".review-doc-tab").forEach(tab => {
        tab.onclick = () => {
          syncInputs();
          currentDocIdx = parseInt(tab.getAttribute("data-idx") || "0", 10);currentPageIdx=0;
          render();
        };
      });

      overlay.querySelectorAll('.confirm-product-match').forEach(button => {
        button.onclick=async () => { syncInputs();try {const result=await api('/autofill/draft/'+draft.draft_id,{method:'PATCH',body:JSON.stringify({skus,dossier_fields:dossier,match_confirmations:[{target_sku_id:button.getAttribute('data-target'),source_sku_id:button.getAttribute('data-source'),confirmed:true}]})});skus=result.skus;reconciliation=result.reconciliations || [];render();}catch(error){showToast(error.message,true);}};
      });
      const pageSelect=overlay.querySelector('#reviewPageSelect');if(pageSelect)pageSelect.onchange=()=>{syncInputs();currentPageIdx=Number(pageSelect.value);render();};
      overlay.querySelectorAll('.sku-family-select').forEach(select => {
        select.onchange = () => { syncInputs(); render(); };
      });
      const btnAddSku = overlay.querySelector("#btnAddSkuRow");
      if (btnAddSku) {
        btnAddSku.onclick = () => {
          syncInputs();
          const nextIdx = skus.length + 1;
          skus.push({
            id: "cand_" + Math.random().toString(16).slice(2, 10),
            sku_code: "SKU-" + String(nextIdx).padStart(3, "0"),
            name: "Mặt hàng mới " + nextIdx,
            product_family: "general",
            declared_code: "",
            facts: REQUIRED_FIELDS.map(fld => ({
              field: fld,
              value: "",
              source_kind: "user_input",
              quote: "",
              status: "unverified"
            }))
          });
          render();
        };
      }

      overlay.querySelectorAll(".btn-remove-sku").forEach(btn => {
        btn.onclick = () => {
          syncInputs();
          const sIdx = parseInt(btn.getAttribute("data-sidx"), 10);
          if (skus.length > 1) {
            skus.splice(sIdx, 1);
            render();
          }
        };
      });

      const btnCommit = overlay.querySelector("#btnCommitCase");
      if (btnCommit) {
        btnCommit.onclick = async () => {
          syncInputs();
          if (!caseData.title || caseData.title.trim().length < 2) {
            showToast("Vui lòng nhập tên hồ sơ phân loại.", true);
            return;
          }

          isSaving = true;
          render();

          try {
            const payload = {
              title: caseData.title.trim(),
              owner: caseData.owner || "Nhóm 8",
              trade_type: caseData.trade_type || "import",
              classification_date: caseData.classification_date || new Date().toISOString().split("T")[0],
              declaration_number: caseData.declaration_number || "",
              notes: caseData.notes || "",
              skus: skus,
              dossier_fields: dossier
            };

            const res = await api(`/autofill/draft/${draft.draft_id}/commit`, {
              method: "POST",
              body: JSON.stringify(payload)
            });

            overlay.remove();
            showToast("Đã tạo hồ sơ và tự điền thuộc tính thành công!");
            window.location.hash = "#case/" + (res.id || res.case_id);
            setTimeout(() => window.location.reload(), 250);
          } catch (err) {
            isSaving = false;
            render();
            showToast("Lỗi khi lưu hồ sơ: " + err.message, true);
          }
        };
      }
    }

    document.body.appendChild(overlay);
    render();
  }


    // --- MODAL: Auto-fill For Existing Case Documents ---
  async function triggerCaseAutofill(caseId) {
    try {
      showToast("Đang phân tích chứng từ trong hồ sơ…");
      const data = await api(`/cases/${caseId}/autofill`);
      openCaseAutofillModal(caseId, data);
    } catch (err) {
      showToast("Lỗi phân tích: " + err.message, true);
    }
  }

  function openCaseAutofillModal(caseId, data) {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.style.cssText = "z-index: 10000;";

    const fields = (data.skus || []).flatMap(s => (s.facts || []).map(f => ({...f, label: s.sku_code + " · " + (FACT_LABELS[f.field] || f.field), is_verified: f.skip_overwrite})));
    let isApplying = false;

    function render() {
      overlay.innerHTML = `
        <section class="modal modal-wide" role="dialog" aria-modal="true" style="max-width: 720px; z-index: 10000;">
          <div class="modal-head">
            <div>
              <h2>Trích xuất & Tự điền từ chứng từ hồ sơ</h2>
              <p>Phát hiện ${fields.length} trường thông tin từ ${data.summary?.total_documents || 0} tài liệu</p>
            </div>
            <button class="icon-btn close-modal-btn" aria-label="Đóng">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>

          <div class="modal-body" style="max-height: 60vh; overflow-y: auto;">
            <div style="font-size: 12px; font-weight: 700; color: #64748B; margin-bottom: 8px; text-transform: uppercase;">Các trường thông tin tìm thấy</div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              ${fields.map(f => `
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 12px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="font-size: 13px; color: #0F172A;">${esc(f.label || f.field)}</strong>
                    <span class="${f.is_verified ? 'status-pill-verified' : 'status-pill-unverified'}">
                      ${f.is_verified ? 'Đã xác minh (Giữ nguyên)' : f.extraction_status === 'conflicting' ? 'Mâu thuẫn' : 'Cần kiểm tra'}
                    </span>
                  </div>
                  <div style="font-size: 13.5px; color: #1E293B; margin-top: 4px;">${esc(f.value)}</div>
                  ${f.quote ? `<div class="field-provenance-quote">"${esc(f.quote)}"</div>` : ''}
                </div>
              `).join('')}
            </div>

            <div style="margin-top: 14px; background: #FFFBEB; border: 1px solid #FCD34D; border-radius: 8px; padding: 10px 14px; font-size: 12.5px; color: #92400E;">
              ⚠️ Những trường đã được thẩm định xác minh sẽ được giữ nguyên nếu bạn chọn bảo lưu.
            </div>
          </div>

          <div class="modal-foot" style="margin-top: 14px; display: flex; justify-content: space-between; align-items: center;">
            <label style="display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer;">
              <input type="checkbox" id="chkCasePreserve" checked />
              <span>Bảo lưu các thuộc tính đã xác minh</span>
            </label>
            <div style="display: flex; gap: 10px;">
              <button type="button" class="btn close-modal-btn">Hủy</button>
              <button type="button" class="btn primary" id="btnApplyAutofill" ${isApplying ? 'disabled' : ''}>
                ${isApplying ? '⏳ Đang áp dụng…' : 'Áp dụng vào hồ sơ'}
              </button>
            </div>
          </div>
        </section>
      `;

      overlay.querySelectorAll(".close-modal-btn").forEach(btn => {
        btn.onclick = () => overlay.remove();
      });

      const btnApply = overlay.querySelector("#btnApplyAutofill");
      if (btnApply) {
        btnApply.onclick = async () => {
          isApplying = true;
          render();
          try {
            const preserve = overlay.querySelector("#chkCasePreserve")?.checked ?? true;
            await api(`/cases/${caseId}/autofill/apply`, {
              method: "POST",
              body: JSON.stringify({ preserve_verified: preserve, skus: data.skus || [] })
            });
            overlay.remove();
            showToast("Đã áp dụng thông tin trích xuất vào hồ sơ!");
            setTimeout(() => window.location.reload(), 200);
          } catch (err) {
            isApplying = false;
            render();
            showToast("Lỗi khi áp dụng: " + err.message, true);
          }
        };
      }
    }

    document.body.appendChild(overlay);
    render();
  }

  // --- INTERCEPTORS & DOM OBSERVER ---
  function setupDOMObservers() {
    // Intercept clicks on "+ Tạo hồ sơ mới" button
    document.addEventListener("click", function(e) {
      const btn = e.target.closest("button");
      if (!btn) return;
      const text = btn.innerText || btn.textContent || "";
      if (text.includes("Tạo hồ sơ mới") || text.includes("Tạo hồ sơ") && !btn.closest(".modal")) {
        // Prevent default React modal if user wants our Document-First flow
        e.preventDefault();
        e.stopPropagation();
        openCreateCaseModal();
      }
    }, true);

    // Periodically check if we are in a case's "Chứng từ" panel and inject the Auto-fill button if not present
    setInterval(() => {
      const hash = window.location.hash;
      if (!hash.startsWith("#case/")) return;
      const caseId = hash.split("/")[1];
      if (!caseId) return;

      // Check if we are on the documents tab or documents list is visible
      const docHeader = document.querySelector(".card-header");
      if (docHeader && (docHeader.textContent.includes("Chứng từ của hồ sơ") || docHeader.textContent.includes("Chứng từ"))) {
        if (!document.getElementById("btnTriggerAutofill")) {
          const btn = document.createElement("button");
          btn.id = "btnTriggerAutofill";
          btn.className = "btn";
          btn.style.cssText = "margin-left: 12px; background: #0284C7; color: #FFF; font-weight: 600; font-size: 13px; display: inline-flex; align-items: center; gap: 6px;";
          btn.innerHTML = "⚡ Trích xuất & Tự điền từ chứng từ";
          btn.onclick = () => triggerCaseAutofill(caseId);

          const actionArea = docHeader.querySelector("button") || docHeader;
          if (actionArea && actionArea.parentElement) {
            actionArea.parentElement.appendChild(btn);
          }
        }
      }
    }, 800);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupDOMObservers);
  } else {
    setupDOMObservers();
  }
})();

