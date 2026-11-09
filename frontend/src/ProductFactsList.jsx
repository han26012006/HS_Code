import React from 'react';
import {CheckCircle2, AlertCircle, RefreshCw, Trash2, Link2} from 'lucide-react';
import {groupFacts, factGroupStatus} from './factReview.js';

export default function ProductFactsList({facts, documents, labels, Badge, onReview, onDelete, onDocument}) {
  return <div className="facts-list">{groupFacts(facts).map(group => {
    const label=labels[group.field]||group.field;
    return <div className="fact-row" data-field={group.field} key={group.facts[0].id}>
      <div className="fact-type"><span>{label}</span><Badge value={factGroupStatus(group)}/></div>
      <div className="fact-content">
        <p>{group.value}{group.facts[0].unit && <small> {group.facts[0].unit}</small>}</p>
        <details><summary><Link2 size={12}/> {group.facts.length} nguồn · Xem đối chiếu</summary>
          {group.facts.map(f=><div className="fact-source" key={f.id} style={{marginTop:8,paddingLeft:10,borderLeft:'2px solid #dbe4ee'}}>
            <small>{f.document_id?<button className="link" onClick={()=>onDocument(f.document_id)}>{documents.find(d=>d.id===f.document_id)?.name||'Chứng từ'} · đơn vị {f.page_number}</button>:'Xác nhận / ghi chép trực tiếp'}{f.reviewer&&<> · {f.reviewer}</>}</small>
            <p>Giá trị nguồn: {f.value}{f.unit?' '+f.unit:''} · <Badge value={f.document_scope_mismatch?'unverified':f.status}/></p>
            {f.quote&&<blockquote>{f.quote}</blockquote>}
            {!!f.document_scope_mismatch&&<small>Nguồn cần kiểm tra lại phạm vi sử dụng.</small>}
          </div>)}
        </details>
      </div>
      <div className="fact-actions">
        <button className="icon-btn" title="Xác minh các nguồn của thuộc tính" aria-label={'Xác minh '+label} onClick={()=>onReview(group,'verified')}><CheckCircle2 size={18}/></button>
        <button className="icon-btn" title="Đánh dấu mâu thuẫn" aria-label={'Đánh dấu mâu thuẫn '+label} onClick={()=>onReview(group,'conflict')}><AlertCircle size={18}/></button>
        <button className="icon-btn" title="Đưa về chưa kiểm tra" aria-label={'Đưa về chưa kiểm tra '+label} onClick={()=>onReview(group,'unverified')}><RefreshCw size={15}/></button>
        <button className="icon-btn danger" title="Xóa thuộc tính và các nguồn đang gộp" aria-label={'Xóa '+label} onClick={()=>onDelete(group)}><Trash2 size={15}/></button>
      </div>
    </div>;
  })}</div>;
}
