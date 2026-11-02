import React, {useEffect, useState} from 'react';
import {AlertCircle, ArrowRight, BookOpen, Download, Info, Search, ShieldCheck} from 'lucide-react';
import {formatDate, todayVN} from './format.js';

const field = (label, child) => <label className="field"><span>{label}</span>{child}</label>;
const notice = text => <div className="notice amber"><Info size={17}/><div>{text}</div></div>;
const money = value => {
  if (value == null) return 'Chưa xác định';
  const negative=String(value).startsWith('-');
  const [whole, fraction] = String(value).replace(/^-/, '').split('.');
  return (negative?'-':'')+new Intl.NumberFormat('vi-VN').format(BigInt(whole)) + (fraction ? ','+fraction.padEnd(2, '0') : '')+' ₫';
};
const policies = {
  unknown: 'Chưa đối chiếu', none_identified: 'Chưa phát hiện yêu cầu trong phạm vi đã kiểm tra',
  requirement_identified: 'Có giấy phép / kiểm tra / điều kiện', prohibited: 'Có căn cứ về diện cấm',
};
const initialRow = (code, trade) => ({code, scheme: trade==='export'?'EXPORT':'MFN', duty_rate_percent: '',
  duty_rate_source: '', rate_checked: false, policy_status: 'unknown', policy_source: '', policy_note: '',
  policy_checked: false, distinguishing_attributes: '', co_checked: false, origin_rule_checked: false,
  transport_rule_checked: false, schedule_checked: false});

export function ConsequenceComparison({sku, current, request}) {
  const [rows, setRows] = useState([]), [reviewer, setReviewer] = useState('');
  const [value, setValue] = useState(''), [origin, setOrigin] = useState('');
  const [result, setResult] = useState(null), [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    const codes = sku.analysis?.heading_candidates?.map(x=>x.example_code) || [];
    for (const c of sku.analysis?.candidates || []) if (codes.length<3 && !codes.includes(c.code)) codes.push(c.code);
    setRows((codes.length>=2?codes.slice(0,3):['','']).map(c=>initialRow(c,current.trade_type)));
    setResult(null); setError(''); setValue(''); setOrigin(''); setReviewer(''); setHistory([]);
    let active=true;
    request('/skus/'+sku.id+'/comparisons').then(x=>active&&setHistory(x)).catch(e=>active&&setError(e.message));
    return ()=>{active=false};
  }, [sku.id, sku.revision, sku.analysis_id, current.trade_type]);
  const edit = (i, key, value) => {setResult(null);setRows(rows.map((r,j)=>j===i?{...r,[key]:value}:r));};
  async function save(e) {
    e.preventDefault();setBusy(true);setError('');setResult(null);
    const body={expected_revision:sku.revision,expected_analysis_id:sku.analysis_id||null,
      customs_value_vnd:value||null,origin_country:origin,reviewer,
      candidates:rows.map(r=>({...r,duty_rate_percent:r.duty_rate_percent||null,
        eligibility:{co_status:r.co_checked?'verified':'not_checked',origin_rule_checked:r.origin_rule_checked,
          transport_rule_checked:r.transport_rule_checked,schedule_checked:r.schedule_checked}}))};
    try {
      const r=await request('/skus/'+sku.id+'/comparisons',{method:'POST',body:JSON.stringify(body)});
      setResult(r);setHistory(await request('/skus/'+sku.id+'/comparisons'));
    } catch(e) {setError(e.message)} finally {setBusy(false)}
  }
  return <section className="card decision-support-card">
    <div className="card-head"><div><h2>So sánh hệ quả giữa các mã</h2><p>Cùng SKU, ngày giao dịch và trị giá; giữ rõ phần đã kiểm tra và phần chưa biết.</p></div><ShieldCheck size={22}/></div>
    {notice('Chênh lệch thuế không xác định mã đúng hoặc xác suất bị kiểm tra. Chỉ tính thuế XNK theo kịch bản đã đối chiếu; các khoản VAT, TTĐB, BVMT và phòng vệ thương mại cần tra riêng.')}
    <form onSubmit={save} onChange={()=>setResult(null)}><div className="card-body"><div className="form-grid">
      {field('Trị giá hải quan chung (VND, tùy chọn)',<input type="number" min="0.01" step="any" value={value} onChange={e=>setValue(e.target.value)}/>)}
      {field('Nước xuất xứ (cần cho kịch bản FTA)',<input value={origin} maxLength={100} onChange={e=>setOrigin(e.target.value)}/>)}
      {field('Người đối chiếu',<input required minLength={2} maxLength={100} value={reviewer} onChange={e=>setReviewer(e.target.value)}/>)}
      <p className="muted">Ngày {formatDate(current.classification_date)} · {current.trade_type==='import'?'Nhập khẩu':'Xuất khẩu'} · SKU bản {sku.revision}</p>
    </div></div>
    <div className="compare-grid consequences-grid" style={{gridTemplateColumns:`repeat(${rows.length},minmax(0,1fr))`}}>{rows.map((r,i)=>{
      const fta=!['MFN','ordinary','EXPORT'].includes(r.scheme);
      return <div key={i}>
        <h3>Phương án {i+1}</h3>
        {field('Mã HS8',<input required pattern="[0-9]{8}" maxLength={8} value={r.code} onChange={e=>edit(i,'code',e.target.value)}/>)}
        {field('Thuộc tính / điều kiện phân biệt',<textarea rows={3} maxLength={4000} value={r.distinguishing_attributes} onChange={e=>edit(i,'distinguishing_attributes',e.target.value)} placeholder="Điều kiện nào khiến mã này phù hợp hoặc bị loại?"/>)}
        {field('Chế độ thuế',<select value={r.scheme} onChange={e=>edit(i,'scheme',e.target.value)}>{(current.trade_type==='export'?['EXPORT','EXPORT_CPTPP','EXPORT_EVFTA','EXPORT_UKVFTA']:['MFN','ordinary','ATIGA','ACFTA','AJCEP','VJEPA','AKFTA','AANZFTA','AIFTA','VKFTA','VCFTA','VN-EAEU','CPTPP','AHKFTA','VNCU','EVFTA','UKVFTA','VN-LAO','VN-CAM','VIFTA','RCEP']).map(s=><option key={s}>{s}</option>)}</select>)}
        {field('Thuế suất XNK đã đối chiếu (%, tùy chọn)',<input type="number" min="0" max="2000" step="any" value={r.duty_rate_percent} onChange={e=>edit(i,'duty_rate_percent',e.target.value)}/>)}
        {field('Căn cứ mức thuế tại ngày giao dịch',<input maxLength={2000} value={r.duty_rate_source} onChange={e=>edit(i,'duty_rate_source',e.target.value)}/>)}
        <label className="checkbox-row"><input type="checkbox" checked={r.rate_checked} onChange={e=>edit(i,'rate_checked',e.target.checked)}/><span>Đã đối chiếu mức thuế và phạm vi áp dụng.</span></label>
        {fta&&<div className="fta-checks"><small>Điều kiện {r.scheme}</small>{[['co_checked','Đã xác minh chứng từ xuất xứ'],['origin_rule_checked','Đã đối chiếu quy tắc xuất xứ'],['transport_rule_checked','Đã đối chiếu điều kiện vận chuyển'],['schedule_checked','Đã đối chiếu biểu, thời kỳ và phạm vi']].map(([k,t])=><label key={k} className="checkbox-row"><input type="checkbox" checked={r[k]} onChange={e=>edit(i,k,e.target.checked)}/><span>{t}</span></label>)}</div>}
        {field('Chính sách quản lý',<select value={r.policy_status} onChange={e=>edit(i,'policy_status',e.target.value)}>{Object.entries(policies).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>)}
        {field('Phạm vi và điều kiện đã kiểm tra',<textarea rows={2} maxLength={4000} value={r.policy_note} onChange={e=>edit(i,'policy_note',e.target.value)}/>)}
        {field('Văn bản / điều khoản chính sách',<input maxLength={2000} value={r.policy_source} onChange={e=>edit(i,'policy_source',e.target.value)}/>)}
        <label className="checkbox-row"><input type="checkbox" checked={r.policy_checked} onChange={e=>edit(i,'policy_checked',e.target.checked)}/><span>Đã đối chiếu chính sách cho đúng hàng, luồng và ngày.</span></label>
      </div>})}</div>
    <div className="card-body button-row"><button className="btn" type="button" disabled={rows.length>=3} onClick={()=>{setRows([...rows,initialRow('',current.trade_type)]);setResult(null)}}>Thêm phương án</button>{rows.length>2&&<button className="btn" type="button" onClick={()=>{setRows(rows.slice(0,-1));setResult(null)}}>Bỏ phương án cuối</button>}<button className="btn primary" disabled={busy}>{busy?'Đang lưu…':'So sánh và lưu hệ quả'}</button></div></form>
    {error&&<div className="notice red" role="alert"><AlertCircle size={17}/>{error}</div>}
    {result&&<div className="card-body comparison-result"><div className="table-wrap"><table><thead><tr><th>Mã</th><th>Thuế XNK kịch bản</th><th>Chính sách</th><th>FTA</th></tr></thead><tbody>{result.rows.map(r=><tr key={r.code}><td className="mono">{r.code}</td><td>{money(r.duty_vnd)}</td><td>{r.policy_label}</td><td>{r.fta_eligibility==='operator_checked'?'Người dùng đã kiểm tra':r.fta_eligibility==='not_established'?'Chưa đủ điều kiện':'Không dùng FTA'}</td></tr>)}</tbody></table></div>
      {result.pairs.map(p=><p key={p.code_a+p.code_b}>Chênh thuế XNK {p.code_b} − {p.code_a}: <b>{money(p.duty_difference_b_minus_a_vnd)}</b></p>)}
      {result.escalation.reasons.map(x=><p key={x} className="error-text">{x}</p>)}
      {notice(result.escalation.advance_ruling_option)}<small>{result.scope}</small></div>}
    {history.length>0&&<details className="analysis-input"><summary>{history.length} bản so sánh đã lưu</summary>{history.map(h=><p key={h.id}>{h.rows.map(x=>x.code).join(' / ')} · {h.reviewer} · SKU bản {h.sku_revision}{h.stale?' · dữ liệu/phân tích đã thay đổi':''}</p>)}</details>}
  </section>;
}

export function VietnamReferences({sku, current, request, onUse}) {
  const [query,setQuery]=useState(''),[heading,setHeading]=useState(''),[rows,setRows]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{setRows([]);setHeading('');setQuery(sku.facts.filter(f=>f.status==='verified'&&['name','function'].includes(f.field)).map(f=>f.value).join(' '));setError('')},[sku.id,sku.revision]);
  async function search(e){e.preventDefault();setBusy(true);setError('');setRows([]);try{const r=await request('/precedents?q='+encodeURIComponent(query)+'&as_of='+current.classification_date+(heading?'&heading='+heading:''));setRows(r.rows)}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <section className="card decision-support-card"><div className="card-head"><div><h2>Căn cứ và tiền lệ Việt Nam để kiểm tra</h2><p>Truy hồi độc lập trên bản OCR dự án; không biến mã trong thông báo thành kết luận cho SKU hiện tại.</p></div><BookOpen size={21}/></div>
    {sku.analysis?.decision_support_state&&notice(sku.analysis.decision_support_state==='needs_information'?'Còn thông tin bắt buộc hoặc mâu thuẫn. Danh sách bên trên chỉ dùng để tiếp tục kiểm tra.':sku.analysis.decision_support_state==='model_abstained_retrieval_only'?'Model đã từ chối/không có gợi ý hợp lệ. Các mã còn hiển thị là kết quả truy hồi.':'Các mã đang hiển thị cần được người có nghiệp vụ đối chiếu; chưa có xác suất đúng HS8 được hiệu chuẩn.')}
    {sku.analysis?.heading_candidates?.length>0&&<div className="card-body"><h3>Tối đa ba nhóm khác nhau trong danh sách truy hồi</h3><p className="muted">Nhóm lấy từ các dòng HS8 đã truy hồi; không đồng nhất với chỉ số HS4 Top-3 của model lịch sử.</p>{sku.analysis.heading_candidates.map(h=><details key={h.heading}><summary>Nhóm {h.heading} · {h.path.split(' > ')[0]}</summary>{h.notes.map(n=><div key={n.id}><strong>{n.title}</strong><pre className="source-excerpt">{n.text}</pre></div>)}</details>)}</div>}
    <form className="card-body" onSubmit={search}><div className="form-grid">{field('Từ khóa thuộc tính hàng hóa',<textarea required maxLength={15000} rows={2} value={query} onChange={e=>setQuery(e.target.value)}/>)}{field('Giới hạn nhóm HS4 (tùy chọn)',<input pattern="[0-9]{4}" maxLength={4} value={heading} onChange={e=>setHeading(e.target.value)}/>)}</div><button className="btn" disabled={busy}><Search size={16}/>{busy?'Đang tra…':'Tìm tiền lệ Việt Nam'}</button></form>
    {error&&<div className="notice red" role="alert">{error}</div>}
    <div className="evidence-list">{rows.map(r=><article key={r.id} className="evidence-item"><div className="heading-inline"><h3>{r.source_name}</h3><span className="badge unverified">Chưa xác minh tính áp dụng</span></div><p>Ngày {formatDate(r.notice_date)} · Mã ghi trong nguồn: <b className="mono">{r.reported_hs8}</b></p>{r.more_than_three_years_old&&notice(r.age_warning)}<blockquote>{r.goods_excerpt}</blockquote>{r.excerpt_truncated&&<small>Đoạn xem trước giới hạn 2.500 ký tự; cần đọc bản gốc.</small>}<div className="button-row">{r.source_url&&<a className="btn" href={r.source_url} target="_blank" rel="noreferrer">Mở bản nguồn</a>}<button className="btn" onClick={()=>onUse({kind:'ruling',title:r.source_name,source_url:r.source_url,quote:r.goods_excerpt,role:'reference',target_codes:[r.reported_hs8]})}><ArrowRight size={15}/>Ghi nhận để đối chiếu</button></div></article>)}</div>
    <div className="card-footer"><small>Mặc định chỉ truy hồi tiền lệ train, loại dữ liệu valid/test và thông báo sau ngày hồ sơ. Trạng thái hủy/thay thế vẫn cần đối chiếu nguồn hiện hành.</small></div>
  </section>;
}

export function LegalStatusPanel({request}) {
  const [day,setDay]=useState(todayVN()),[data,setData]=useState(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;setData(null);setError('');if(day)request('/legal-status?as_of='+day).then(d=>active&&setData(d)).catch(e=>active&&setError(e.message));return()=>{active=false}},[day]);
  const labels={not_yet_effective:'Chưa có hiệu lực',no_longer_effective:'Đã hết khoảng hiệu lực ghi nhận',in_recorded_effective_period:'Trong khoảng hiệu lực đã ghi',effective_period_not_recorded:'Cần đối chiếu hiệu lực từng điều'};
  return <section className="card decision-support-card"><div className="card-head"><div><h2>Văn bản theo ngày áp dụng</h2><p>Phân biệt văn bản mới ban hành với văn bản đang có hiệu lực.</p></div>{field('Ngày cần đối chiếu',<input type="date" required value={day} onChange={e=>setDay(e.target.value)}/>)}</div>{error&&<p role="alert">{error}</p>}{data&&<><div className="table-wrap"><table><thead><tr><th>Văn bản</th><th>Hiệu lực từ</th><th>Trạng thái theo registry</th></tr></thead><tbody>{data.sources.map(s=><tr key={s.id}><td>{s.source?<a href={s.source} target="_blank" rel="noreferrer">{s.id}</a>:s.id}{s.note&&<small className="block">{s.note}</small>}</td><td>{s.effective_from?formatDate(s.effective_from):'Đọc nguyên bản'}</td><td>{labels[s.status_on_date]}</td></tr>)}</tbody></table></div>{notice(data.warning+' Registry được đối chiếu ngày '+formatDate(data.registry_checked_on)+'.')}</>}</section>;
}

export function FrozenDossier({sku,current,request,saveBlob}) {
  const [check,setCheck]=useState(null),[error,setError]=useState('');
  useEffect(()=>{setCheck(null);setError('')},[sku.id,sku.revision,sku.decision?.id]);
  async function snapshot(){try{const d=await request('/decisions/'+sku.decision.id+'/snapshot');if(!d.integrity_matches)throw new Error('Bản chụp không khớp SHA256; cần kiểm tra dữ liệu.');saveBlob(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}),'quyet-dinh-'+sku.decision.id+'.json')}catch(e){setError(e.message)}}
  const retention=current.retention;
  return <section className="card decision-support-card"><div className="card-head"><h2>Bằng chứng tại thời điểm duyệt</h2><ShieldCheck size={21}/></div><div className="card-body">
    {sku.decision?.snapshot?<><p className="mono snapshot-hash">SHA256 {sku.decision.snapshot.snapshot_sha256}</p><button className="btn" onClick={snapshot}><Download size={16}/>Tải bản chụp quyết định</button></>:<p>Chưa có bản chụp ở quyết định hiện tại. Quyết định cũ trước bản 2.2 cần được đối chiếu lại để tạo bản chụp.</p>}
    <p>{retention?.minimum_reference_until?'Mốc lưu tham chiếu: '+formatDate(retention.minimum_reference_until)+' · tính từ ngày đăng ký tờ khai.':'Chưa ghi ngày đăng ký tờ khai; chưa tính được mốc lưu 5 năm.'}</p>{retention?.legal_hold&&notice('Hồ sơ đang được đánh dấu cần tiếp tục giữ vì kiểm tra/tranh chấp.')}
    <p className="muted">{retention?.note}</p><button className="btn" onClick={async()=>{try{setCheck(await request('/audit-integrity'))}catch(e){setError(e.message)}}}>Kiểm tra chuỗi nhật ký</button>
    {check&&<p>{check.integrity_matches?'Chuỗi hash khớp':'Phát hiện chuỗi hash không khớp'} · {check.events_checked} sự kiện. Chưa có dấu thời gian độc lập hoặc chữ ký số.</p>}{error&&<p className="error-text" role="alert">{error}</p>}
    {notice('Xuất gói ZIP để giữ cả chứng từ gốc, bản chụp và manifest hash. Đoạn trích/URL chưa thay thế bản gốc chưa được tải vào hồ sơ. Sao lưu riêng và thử phục hồi; ứng dụng không tự bảo đảm lưu bền vững 5 năm.')}
  </div></section>;
}
