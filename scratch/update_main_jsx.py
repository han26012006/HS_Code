def update():
    with open('frontend/src/main.jsx', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find line where QualityPage starts
    q_line = -1
    s_line = -1
    for i, l in enumerate(lines):
        if l.startswith('function QualityPage('):
            q_line = i
        if l.startswith('function SettingsPage('):
            s_line = i

    print(f'q_line: {q_line}, s_line: {s_line}')
    assert q_line != -1 and s_line != -1

    new_func = '''function UnifiedSystemPage({route, run, status, onRefresh, onKey}) {
  const [tab, setTab] = useState(route === 'settings' ? 'settings' : 'quality');
  const [d, setD] = useState(null);
  useEffect(() => {
    if (route === 'settings') setTab('settings');
    else if (route === 'quality' || route === 'system') setTab('quality');
  }, [route]);
  useEffect(() => { run(async () => setD(await request('/quality'))); }, []);

  return <>
    <div className="page-heading">
      <div>
        <div className="eyebrow">HỆ THỐNG & VẬN HÀNH</div>
        <h1>Hệ thống & Vận hành</h1>
        <p>Theo dõi chất lượng model, đo lường độ chính xác và cấu hình nguồn dữ liệu.</p>
      </div>
      <div style={{display: 'flex', gap: '10px', alignItems: 'center'}}>
        <Badge value="unverified">Tự động chốt HS8: tắt</Badge>
        <Button icon={RefreshCw} onClick={onRefresh}>Làm mới trạng thái</Button>
      </div>
    </div>

    <div className="docfirst-tabs" style={{maxWidth: '500px', marginBottom: '22px'}}>
      <button type="button" className={'docfirst-tab ' + (tab === 'quality' ? 'active' : '')} onClick={() => setTab('quality')}>
        📊 Chất lượng & Đo lường model
      </button>
      <button type="button" className={'docfirst-tab ' + (tab === 'settings' ? 'active' : '')} onClick={() => setTab('settings')}>
        ⚙️ Cấu hình & Nguồn dữ liệu
      </button>
    </div>

    {tab === 'quality' ? (
      d ? <>
        <div className="quality-grid">
          <section className="card metric-card">
            <div className="card-head">
              <div>
                <h2>HS8 Top-1 lịch sử</h2>
                <p>{d.historical.label}</p>
              </div>
              <BarChart3 size={23}/>
            </div>
            <div className="big-metric">{(d.historical.hs8_top1*100).toFixed(1).replace('.', ',')}<span>%</span></div>
            <p><b>{d.historical.correct}/{d.historical.n}</b> mẫu khớp nhãn dự án.</p>
            <Notice>Đây là kết quả cũ, nhãn còn tạm thời. Chưa đo hiệu quả của bản ứng dụng hiện tại trên bộ kiểm thử độc lập.</Notice>
            <small>Nguồn: {d.historical.source}</small>
          </section>
          <section className="card">
            <div className="card-head">
              <h2>Điều kiện cần trước phát hành</h2>
              <ShieldCheck size={22} className="teal"/>
            </div>
            <div className="release-checks">
              {['Bộ SKU độc lập, hồ sơ kỹ thuật đủ và nhãn được thẩm định','Chia tập theo nhóm SKU / nhà sản xuất và thời gian','So sánh baseline, retrieval, reranker và model chỉ dẫn','Đo HS8 Top-1, recall ứng viên, sai theo chương và chi phí','Hiệu chuẩn, cơ chế từ chối và kiểm tra citation','Đánh giá thử với người khai và chuyên gia phân loại'].map(x => <div key={x}><span className="check-ring"/>{x}</div>)}
            </div>
          </section>
        </div>
        <section className="card">
          <div className="card-head">
            <div>
              <h2>Chất lượng ở từng tầng</h2>
              <p>{d.multilevel_experiment?.models_evaluated} cấu hình đã đo; chưa có nhánh vượt điều kiện chọn đồng thời trên validation.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Tầng</th><th>Top-1</th><th>Top-3</th><th>Macro F1</th></tr></thead>
              <tbody>
                {[2,4,6,8].map(n => <tr key={n}><td>HS{n}</td>{['top1','top3','macro_f1'].map(k => <td key={k}>{(d.historical[`hs${n}_${k}`]*100).toFixed(1)}%</td>)}</tr>)}
              </tbody>
            </table>
          </div>
          <div className="card-body">
            <p>Recall@200: <b>{(d.historical.recall_at_200*100).toFixed(1)}%</b> · MRR@200: {d.historical.mrr_at_200.toFixed(3)} · HierarchicalF1: {d.historical.hierarchical_f1.toFixed(3)}</p>
            <p className="muted">HS8 với mã chưa có trong train: {d.historical.unseen.hs8_correct}/{d.historical.unseen.n}. Chưa có OCR/citation gold và calibration HS8 độc lập.</p>
          </div>
        </section>
        <section className="card">
          <div className="card-head">
            <h2>Vận hành trong không gian hiện tại</h2>
            <Badge value="neutral">Số liệu thực tế trong ứng dụng</Badge>
          </div>
          <div className="stats-grid three no-gap">
            <div className="stat"><span>Phân tích đã thực hiện</span><strong>{d.operations.analyses}</strong></div>
            <div className="stat"><span>SKU được duyệt nội bộ</span><strong>{d.operations.approved}</strong></div>
            <div className="stat"><span>Tài liệu đang trích xuất</span><strong>{d.operations.processing_documents}</strong></div>
          </div>
          <div className="inset-notice"><Info size={16}/>Tỷ lệ duyệt không phải accuracy. Quyết định nội bộ cần thẩm định riêng trước khi thêm vào dữ liệu huấn luyện.</div>
        </section>
      </> : <div className="empty" style={{padding: '40px'}}>Đang tải số liệu chất lượng và vận hành…</div>
    ) : (
      <>
        <section className="card settings-card">
          <div className="card-head">
            <h2>Model và danh mục</h2>
            <Layers size={21}/>
          </div>
          <dl>
            <dt>Danh mục đang dùng</dt>
            <dd>{status?.catalogue_rows?.toLocaleString('vi-VN')} dòng · Việt Nam / AHTN 2022</dd>
            <dt>Mã phiên bản danh mục</dt>
            <dd className="mono">{status?.catalogue_version||'…'}</dd>
            <dt>Artifact model dự án</dt>
            <dd><Badge value={status?.model_artifacts_available?'verified':'unverified'}>{status?.model_artifacts_available?'Có artifact · '+status.artifact_version:'Chưa cấu hình'}</Badge></dd>
            <dt>Model đã được nạp</dt>
            <dd>{status?.model_loaded?'Đã nạp':'Chưa nạp; chỉ tải khi người dùng chọn model'}</dd>
            <dt>Lỗi model gần nhất</dt>
            <dd>{status?.model_error||'Chưa ghi nhận'}</dd>
            <dt>Tự động chốt HS8</dt>
            <dd>Đã tắt · luôn có bước kiểm tra của con người</dd>
          </dl>
          <Notice tone="blue">Để dùng model dự án, đặt HS_ART tới thư mục artifact đã hoàn tất. Encoder cần có sẵn trong cache; ứng dụng không tự tải trọng số khi khởi động.</Notice>
        </section>
        <section className="card settings-card">
          <div className="card-head">
            <h2>Truy cập và dữ liệu hồ sơ</h2>
            <Settings size={21}/>
          </div>
          <dl>
            <dt>Chế độ truy cập</dt>
            <dd>{status?.authentication_required?'Khóa không gian HS_API_KEY':'Máy cục bộ; chưa cấu hình khóa truy cập'}</dd>
            <dt>Danh tính người duyệt</dt>
            <dd>Tên do người thao tác khai báo; chưa tích hợp SSO / chữ ký số.</dd>
            <dt>Lưu dữ liệu</dt>
            <dd>SQLite và chứng từ trên máy chạy ứng dụng. Sao lưu toàn bộ thư mục runtime.</dd>
            <dt>API trả phí</dt>
            <dd>Luồng mặc định không gọi API. Nhánh OpenAI: {status?.openai_enabled?'đã bật trên máy chủ, cần xác nhận từng lượt':'đang tắt'}. Khóa API đặt trong biến môi trường máy chủ.</dd>
          </dl>
          <div className="settings-actions">
            <Button icon={ShieldCheck} onClick={onKey}>Nhập / đổi khóa truy cập</Button>
          </div>
        </section>
      </>
    )}
  </>;
}\n'''

    lines[q_line:s_line+1] = [new_func]
    with open('frontend/src/main.jsx', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('main.jsx successfully updated!')

if __name__ == '__main__':
    update()

