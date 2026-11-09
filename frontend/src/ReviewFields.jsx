import React,{useEffect,useState} from 'react';
import {reviewCandidateState} from './reviewCandidates.js';

export default function ReviewFields({sku,current,action,Field,Notice,roles,statuses,onRefreshAnalysis}) {
  const [code,setCode]=useState(''),[alternative,setAlternative]=useState('');
  const [loading,setLoading]=useState(false),[error,setError]=useState('');
  const state=reviewCandidateState(sku,code);
  useEffect(()=>{
    if(alternative&&!state.alternatives.some(row=>String(row.code)===alternative))setAlternative('');
  },[sku.analysis_id,sku.revision,code,alternative]);
  async function refresh(){
    setLoading(true);setError('');
    try{await onRefreshAnalysis();}catch(e){setError(e.message);}finally{setLoading(false);}
  }
  return <>
    <div className="form-grid">
      <Field label="Người lập"><input name="preparer" required minLength={2} defaultValue={current.owner}/></Field>
      <Field label="Người duyệt / yêu cầu"><input name="reviewer" required minLength={2}/></Field>
    </div>
    {action==='approve'&&<>
      {!state.hasCurrentAnalysis&&<Notice tone="blue">{state.status==='stale'?'Hồ sơ đã thay đổi sau lần phân tích.':'Chưa có danh sách mã cho phiên bản hồ sơ hiện tại.'} Cập nhật danh sách ngay bên dưới để chọn phương án đối chiếu. Nội dung phiếu đang nhập được giữ lại.</Notice>}
      <div className="button-row" style={{margin:'12px 0'}}>
        <button type="button" className="btn" disabled={loading||!sku.readiness?.can_analyze} onClick={refresh}>{loading?'Đang cập nhật…':'Cập nhật danh sách mã · BM25'}</button>
      </div>
      {!sku.readiness?.can_analyze&&<Notice>Xác minh tên, công dụng và xử lý thuộc tính mâu thuẫn trước khi cập nhật danh sách mã.</Notice>}
      {error&&<Notice tone="red">{error}</Notice>}
      <Field label="Mã HS8 đề nghị duyệt" wide>
        <input name="code" className="mono" required pattern="[0-9]{8}" maxLength={8} list="candidate-codes" value={code} onChange={e=>setCode(e.target.value)} placeholder="Nhập đủ 8 chữ số hoặc chọn từ danh sách bên dưới"/>
        <datalist id="candidate-codes">{state.candidates.map(row=><option value={row.code} key={row.code} label={row.description}/>)}</datalist>
        {state.candidates.length>0&&<select aria-label="Chọn nhanh mã HS8 đề nghị duyệt" style={{marginTop:8}} className="mono" value={state.candidates.some(row=>String(row.code)===code)?code:''} onChange={e=>setCode(e.target.value)}>
          <option value="">Chọn từ danh sách phân tích ({state.candidates.length} mã)</option>
          {state.candidates.map(row=><option value={row.code} key={row.code}>{row.code} — {row.description}</option>)}
        </select>}
      </Field>
    </>}
    <Field label={action==='return'?'Thông tin cần bổ sung':'Lập luận và tiêu chí phân biệt'} wide><textarea name="reason" required minLength={action==='return'?5:30} rows={4} placeholder="Đặc tính hàng → dòng danh mục → chú giải / quy tắc áp dụng → lý do loại các mã khác"/></Field>
    {action==='approve'&&<>
      <div className="form-grid">
        <Field label="Một mã khác đã xem xét" hint={!state.hasCurrentAnalysis?'Cập nhật danh sách mã để chọn.':!state.alternatives.length?'Danh sách hiện tại chưa có phương án khác để chọn.':`${state.alternatives.length} phương án khác mã đề nghị duyệt.`}>
          <select name="alternative_code" aria-label="Một mã khác đã xem xét" required={state.requiresAlternative} disabled={loading||!state.alternatives.length} value={alternative} onChange={e=>setAlternative(e.target.value)}>
            <option value="">{!state.hasCurrentAnalysis?'Cần cập nhật danh sách mã':!state.alternatives.length?'Chưa có phương án khác':'Chọn mã để nêu lý do loại'}</option>
            {state.alternatives.map(row=><option value={row.code} key={row.code}>{row.code} — {row.description}{row.path?` (${row.path})`:''}</option>)}
          </select>
        </Field>
        <Field label="Lý do không chọn phương án đó" wide><textarea name="alternative_reason" required={state.requiresAlternative} minLength={state.requiresAlternative?20:undefined} maxLength={4000} rows={3} placeholder="Thuộc tính cụ thể và căn cứ nào loại trừ phương án này?"/></Field>
      </div>
      <label className="checkbox-row"><input name="classification_basis_confirmed" type="checkbox" required/><span>Đã đối chiếu bản chất hàng và căn cứ phân loại, độc lập với lợi ích thuế của phương án.</span></label>
      <h4>Căn cứ sử dụng</h4>
      {sku.evidence.length?sku.evidence.map(e=><label className="checkbox-row" key={e.id}><input type="checkbox" name="evidence_ids" value={e.id}/><span>{e.title}<small>{roles[e.role]} · {statuses[e.lifecycle]} · {e.reviewer||'Chưa đối chiếu'}</small></span></label>):<Notice>Chưa có căn cứ. Thêm và đối chiếu nguồn trước khi duyệt.</Notice>}
      <Notice tone="blue">Hệ thống kiểm tra thuộc tính, phiên bản phân tích, người duyệt và căn cứ trước khi lưu. Tên người thao tác là bản ghi nội bộ, chưa phải chữ ký điện tử.</Notice>
    </>}
  </>;
}
