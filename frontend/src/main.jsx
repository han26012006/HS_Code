import React, {useState,useEffect,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {LayoutDashboard,FolderOpen,Search,Files,BookOpen,BarChart3,Settings,Plus,ArrowUpRight,ArrowRight,ArrowLeft,ChevronRight,ChevronDown,Check,CheckCircle2,Clock,AlertCircle,ShieldCheck,FileText,Upload,Download,X,Layers,SlidersHorizontal,RefreshCw,ExternalLink,MoreHorizontal,ChevronLeft,Menu,Loader2,ClipboardCheck,MessageSquare,ScanText,Package,Link2,Info,LogOut,Calculator,Trash2} from 'lucide-react';
import './style.css';
import TaxPage from './TaxPage.jsx';
import ProjectKnowledgePanel from './ProjectKnowledgePanel.jsx';
import ProductFactsList from './ProductFactsList.jsx';
import ReviewFields from './ReviewFields.jsx';
import {reviewCandidateState} from './reviewCandidates.js';
import {performFactGroupAction} from './factReview.js';
import {ConsequenceComparison, VietnamReferences, LegalStatusPanel, FrozenDossier} from './DecisionSupportPanel.jsx';
import {formatDate as fmtDate,formatTime as fmtTime,todayVN} from './format.js';

let accessKey='';
const BASE='/api/v2';
const labels={name:'Tên và bản chất hàng',function:'Công dụng chính',material:'Vật liệu / thành phần',construction:'Cấu tạo / nguyên lý',manufacturing:'Quy trình sản xuất',specifications:'Thông số và kích thước',condition:'Trạng thái khi XNK',packaging:'Quy cách đóng gói',model:'Model / SKU',part_number:'Part number',quantity:'Số lượng',unit:'Đơn vị',unit_price:'Đơn giá',amount:'Thành tiền',currency:'Tiền tệ',gross_weight:'Trọng lượng cả bì',net_weight:'Trọng lượng tịnh',packages:'Số kiện',origin:'Xuất xứ',declared_code:'HS khai báo trên nguồn'};
const statuses={draft:'Mới tạo',collecting:'Đang bổ sung',in_review:'Chờ đối chiếu',approved:'Đã duyệt nội bộ',returned:'Yêu cầu bổ sung',unverified:'Chưa kiểm tra',verified:'Đã kiểm tra',conflict:'Mâu thuẫn',queued:'Đang xếp hàng',processing:'Đang trích xuất',needs_review:'Cần kiểm tra bản trích',error:'Xử lý lỗi',failed:'Xử lý lỗi',active:'Còn hiệu lực',not_checked:'Chưa đối chiếu',withdrawn:'Đã hủy',superseded:'Đã thay thế'};
const roles={reference:'Tham khảo',supports:'Căn cứ áp dụng',excludes:'Điều khoản loại trừ',not_applicable:'Không áp dụng',conflict:'Mâu thuẫn'};
const kinds={tariff:'Danh mục / biểu thuế',chapter_note:'Chú giải chương',section_note:'Chú giải phần',ruling:'Thông báo / quyết định',technical:'Hồ sơ kỹ thuật',other:'Nguồn khác'};
const family={general:'Hàng hóa khác',steel:'Sắt thép',feed:'Thức ăn chăn nuôi',laser:'Thiết bị laser',machine:'Máy móc',electronic:'Điện / điện tử',chemical:'Hóa chất',food:'Thực phẩm'};
function errorText(d){if(typeof d==='string')return d;if(Array.isArray(d))return d.map(x=>`${x.loc?.slice(-1)}: ${x.msg}`).join('; ');return 'Không thể thực hiện thao tác.';}
async function request(path,options={}){const r=await fetch(path.startsWith('/health')?path:BASE+path,{...options,headers:{...(options.body instanceof FormData?{}:options.body?{'Content-Type':'application/json'}:{}),...(accessKey?{'X-API-Key':accessKey}:{}),...options.headers}});if(!r.ok){let d;try{d=await r.json()}catch{d={detail:r.statusText}};const e=new Error(errorText(d.detail));e.status=r.status;throw e;}return options.blob?r.blob():r.json();}
const post=(p,v)=>request(p,{method:'POST',body:JSON.stringify(v)});const patch=(p,v)=>request(p,{method:'PATCH',body:JSON.stringify(v)});
function saveBlob(blob,name){const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),5000);}
function csvFile(rows,name){const esc=v=>'"'+String(v??'').replace(/^[=+@\-]/,"'$&").replaceAll('"','""')+'"';saveBlob(new Blob(['\ufeff'+rows.map(r=>r.map(esc).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}),name);}
function Badge({value,children}){return <span className={'badge '+(value||'')}>{children||statuses[value]||value}</span>}
function Button({children,icon:Icon,variant='',className='',...props}){return <button className={'btn '+variant+' '+className} {...props}>{Icon&&<Icon size={16}/ >}{children}</button>}
function Empty({icon:Icon=FolderOpen,title,children,action}){return <div className="empty"><div className="empty-icon"><Icon size={27}/></div><h3>{title}</h3><p>{children}</p>{action}</div>}
function Field({label,children,hint,wide}){return <label className={'field '+(wide?'wide':'')}><span>{label}</span>{children}{hint&&<small>{hint}</small>}</label>}
function Notice({children,tone='amber',icon:Icon=Info}){return <div className={'notice '+tone}><Icon size={17}/><div>{children}</div></div>}
function Modal({title,subtitle,children,onClose,wide=false}){const ref=useRef();useEffect(()=>{const old=document.activeElement;ref.current?.focus();const f=e=>{if(e.key==='Escape')onClose();if(e.key==='Tab'){const a=[...ref.current.querySelectorAll('button,input,textarea,select,a[href]')].filter(x=>!x.disabled);if(!a.length)return;if(e.shiftKey&&document.activeElement===a[0]){e.preventDefault();a.at(-1).focus()}else if(!e.shiftKey&&document.activeElement===a.at(-1)){e.preventDefault();a[0].focus()}}};document.addEventListener('keydown',f);return()=>{document.removeEventListener('keydown',f);old?.focus()}},[]);return <div className="modal-overlay" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section className={'modal '+(wide?'modal-wide':'')} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}><div className="modal-head"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="icon-btn" aria-label="Đóng" onClick={onClose}><X size={20}/></button></div>{children}</section></div>}
function FormModal({title,subtitle,onClose,onSubmit,children,submit='Lưu',wide=false,submitDisabled=false}){const [busy,setBusy]=useState(false),[err,setErr]=useState('');return <Modal {...{title,subtitle,onClose,wide}}><form onSubmit={async e=>{e.preventDefault();setBusy(true);setErr('');try{await onSubmit(new FormData(e.currentTarget));}catch(x){setErr(x.message)}finally{setBusy(false)}}}><div className="modal-body">{children}{err&&<Notice tone="red">{err}</Notice>}</div><div className="modal-foot"><Button type="button" onClick={onClose}>Hủy</Button><Button variant="primary" disabled={busy||submitDisabled}>{busy?<Loader2 className="spin" size={16}/>:null}{busy?'Đang xử lý…':submit}</Button></div></form></Modal>}
const getValues=f=>Object.fromEntries(f.entries());
function App(){
 const [route,setRoute]=useState(location.hash.slice(1)||'overview'),[status,setStatus]=useState(null),[summary,setSummary]=useState(null),[cases,setCases]=useState([]),[current,setCurrent]=useState(null),[sku,setSku]=useState(null),[tab,setTab]=useState('documents'),[modal,setModal]=useState(null),[toast,setToast]=useState(null),[fatal,setFatal]=useState(''),[busy,setBusy]=useState(false),[menu,setMenu]=useState(false),[apiLogin,setApiLogin]=useState(false);
 const nav=r=>{location.hash=r;setMenu(false)};
 useEffect(()=>{const f=()=>{setRoute(location.hash.slice(1)||'overview');setMenu(false)};window.addEventListener('hashchange',f);return()=>window.removeEventListener('hashchange',f)},[]);
 const say=(message,error=false)=>{setToast({message,error});setTimeout(()=>setToast(null),5000)};
 const run=async(fn,success)=>{setBusy(true);try{const r=await fn();if(success)say(success);return r}catch(e){if(e.status===401)setApiLogin(true);say(e.message,true);return null}finally{setBusy(false)}};
 async function refresh(){try{const [s,a,c]=await Promise.all([request('/status'),request('/summary'),request('/cases')]);setStatus(s);setSummary(a);setCases(c);setFatal('')}catch(e){if(e.status===401)setApiLogin(true);else setFatal(e.message)}}
 useEffect(()=>{refresh()},[]);
 async function loadCase(id,selected){const c=await request('/cases/'+id);setCurrent(c);const sid=selected||c.skus[0]?.id;if(sid)setSku(await request('/skus/'+sid));else setSku(null);return c;}
 useEffect(()=>{if(route.startsWith('case/')){setCurrent(null);setSku(null);run(()=>loadCase(route.split('/')[1]));setTab('documents')}},[route]);
 async function afterSKU(next){setSku(next);await loadCase(next.case_id,next.id);await refresh();}
 async function exportCase(kind){await run(async()=>{const blob=await request(`/cases/${current.id}/export/${kind}`,{blob:true});saveBlob(blob,`${current.reference}.${kind}`)},'Đã xuất hồ sơ');}
 async function demo(){await run(async()=>{const r=await post('/demo',{});await refresh();if(r.cases[0])nav('case/'+r.cases[0].id)},'Đã mở hồ sơ mẫu — các thuộc tính cần được kiểm tra');}
 const openCase=c=>nav('case/'+c.id);
 const openFact=(prefill={})=>setModal({type:'fact',prefill});
 const factReview=(group,state)=>setModal({type:'factReview',fact:group.facts[0],facts:group.facts,status:state});
 const reloadFacts=async()=>{await loadCase(current.id,sku.id);await refresh();};
 const delFact=group=>setModal({type:'confirm',title:'Xóa thuộc tính',message:`Xóa thuộc tính "${labels[group.field]||group.field}" và ${group.facts.length} nguồn đang gộp? Phiên bản SKU sẽ được cập nhật.`,confirmText:'Xác nhận xóa',onConfirm:async()=>{const result=await run(()=>performFactGroupAction(group.facts,id=>request('/skus/'+sku.id+'/facts/'+id,{method:'DELETE'}),reloadFacts));if(result!==null)say('Đã xóa thuộc tính và các nguồn đang gộp')}});
 const delEvidence=e=>setModal({type:'confirm',title:'Xóa căn cứ',message:`Bạn có chắc chắn muốn xóa căn cứ "${e.title}"?`,confirmText:'Xác nhận xóa',onConfirm:async()=>{const next=await request('/skus/'+sku.id+'/evidence/'+e.id,{method:'DELETE'});await afterSKU(next);say('Đã xóa căn cứ')}});
 const delCase=c=>setModal({type:'confirm',title:'Xóa hồ sơ',message:`Bạn có chắc chắn muốn xóa hồ sơ "${c.title}" (${c.reference})? Toàn bộ SKU, chứng từ và quyết định liên quan sẽ bị xóa vĩnh viễn.`,confirmText:'Xác nhận xóa hồ sơ',onConfirm:async()=>{await request('/cases/'+c.id,{method:'DELETE'});await refresh();if(route.startsWith('case/'))nav('cases');say('Đã xóa hồ sơ thành công')}});
 const delSku=s=>setModal({type:'confirm',title:'Xóa mặt hàng (SKU)',message:`Bạn có chắc chắn muốn xóa SKU "${s.sku_code} — ${s.name}"?`,confirmText:'Xác nhận xóa SKU',onConfirm:async()=>{await request('/skus/'+s.id,{method:'DELETE'});await loadCase(current.id);await refresh();say('Đã xóa SKU')}});
 const navs=[['overview','Tổng quan',LayoutDashboard],['cases','Hồ sơ phân loại',FolderOpen],['catalogue','Tra cứu mã HS',Search],['audit','Rà soát danh mục',Files],['knowledge','Thư viện căn cứ',BookOpen],['tax','Biểu thuế & kịch bản',Calculator],['system','Hệ thống & Vận hành',Settings]];
 const pageTitle=route.startsWith('case/')?'Hồ sơ phân loại':{overview:'Tổng quan',cases:'Hồ sơ phân loại',catalogue:'Tra cứu mã HS',audit:'Rà soát danh mục',knowledge:'Thư viện căn cứ',tax:'Biểu thuế & kịch bản',quality:'Hệ thống & Vận hành',settings:'Hệ thống & Vận hành',system:'Hệ thống & Vận hành'}[route]||'Tổng quan';
 const createCase=()=>setModal({type:'case'});
 return <div className="app-shell"><aside className={'sidebar '+(menu?'open':'')}><a className="brand" href="#overview"><span className="brand-mark"><img src="/assets/images/mascot.png?v=2" alt="HS Workspace Mascot"/></span><span>HS Workspace<small>PHÂN LOẠI CÓ CĂN CỨ</small></span></a><div className="workspace-label"><span className="tiny-avatar">N8</span><div>Không gian dự án<small>Nhóm 8 · Việt Nam</small></div><ChevronDown size={14}/></div><div className="nav-label">KHÔNG GIAN LÀM VIỆC</div><nav>{navs.map(([id,title,Icon])=><a href={'#'+id} key={id} className={(route===id||(id==='cases'&&route.startsWith('case/'))||(id==='system'&&(route==='quality'||route==='settings'||route==='system')))?'active':''}><Icon size={19}/><span>{title}</span>{id==='cases'&&summary?.cases>0&&<b>{summary.cases}</b>}</a>)}</nav><div className="sidebar-bottom"><div className="jurisdiction"><span className="country-dot"/>Việt Nam<small>AHTN 2022 · HS 8 số</small></div><div className="user"><span className="avatar">N8</span><div>Nhóm dự án 8<small>Không gian nội bộ</small></div><span className="online-dot"/></div></div></aside>{menu&&<div className="nav-scrim" onClick={()=>setMenu(false)}/>}
 <div className="main-shell"><header className="topbar"><div className="crumb"><button className="icon-btn mobile-toggle" aria-label="Mở điều hướng" onClick={()=>setMenu(!menu)}><Menu size={22}/></button><span>Không gian làm việc</span><ChevronRight size={14}/><strong>{pageTitle}</strong></div><div className="top-actions"><span className="local-badge"><span className="online-dot"/>Dữ liệu trong không gian</span><a className="icon-btn" href="#settings" aria-label="Cài đặt"><Settings size={18}/></a><span className="avatar small">N8</span></div></header>
 <main className="content">{fatal&&<Notice tone="red">Không kết nối được ứng dụng: {fatal}. <button className="link" onClick={refresh}>Thử lại</button></Notice>}
 {route==='overview'&&summary&&<><div className="page-heading"><div><div className="eyebrow">KHÔNG GIAN PHÂN LOẠI</div><h1>Mỗi mã HS, một bộ căn cứ.</h1><p>Từ chứng từ hàng hóa đến quyết định được kiểm tra và lưu vết.</p></div><Button variant="primary" icon={Plus} onClick={createCase}>Tạo hồ sơ mới</Button></div><div className="stats-grid">{[[FolderOpen,'Hồ sơ đang quản lý',summary?.cases??0,'Từng lô hàng, từng SKU'],[Package,'SKU cần xử lý',(summary?.skus??0)-(summary?.approved??0),'Chưa có quyết định được duyệt'],[ClipboardCheck,'SKU đã duyệt nội bộ',summary?.approved??0,'Có người duyệt và căn cứ'],[ScanText,'Thuộc tính cần kiểm tra',summary?.unverified_facts??0,'Đối chiếu trước khi phân tích']].map(([Icon,label,value,note],i)=><div className="stat" key={label}><div className="stat-top"><span>{label}</span><span className={'stat-icon s'+i}><Icon size={18}/></span></div><strong>{value}</strong><small>{note}</small></div>)}</div>
 <div className="overview-grid"><section className="card"><div className="card-head"><div><h2>Hàng đợi hồ sơ</h2><p>Tiếp tục đối chiếu các mặt hàng đang xử lý.</p></div><a className="text-link" href="#cases">Tất cả hồ sơ <ArrowUpRight size={15}/></a></div><CaseTable cases={cases.slice(0,5)} onOpen={openCase} onDelete={delCase} emptyAction={<Button icon={Plus} onClick={createCase}>Tạo hồ sơ đầu tiên</Button>}/></section><section className="guide-card"><div className="guide-icon"><ShieldCheck size={26}/></div><h2>Kiểm tra trước khi kết luận</h2><p>Xác minh thuộc tính quyết định, đối chiếu chú giải và hiệu lực nguồn, sau đó chuyển người duyệt.</p><div className="guide-steps">{['Một hồ sơ, nhiều SKU độc lập','Mỗi thuộc tính có nguồn trích','Mỗi quyết định có người đối chiếu'].map((t,i)=><div key={t}><span>{i+1}</span>{t}</div>)}</div><Button onClick={demo} icon={ArrowRight} disabled={busy}>Khám phá hồ sơ mẫu</Button><small>Mẫu từ chứng từ dự án; chưa thẩm định mã.</small></section></div>
 <div className="overview-grid bottom-grid"><section className="card"><div className="card-head"><div><h2>Hoạt động gần đây</h2><p>Thay đổi được lưu cùng thời gian và người thao tác.</p></div><Clock size={18} className="muted"/></div><Events events={summary?.events||[]}/></section><section className="card quick-card"><div className="card-head"><h2>Công cụ tra cứu</h2></div>{[[Search,'Tra cứu danh mục Việt Nam',`${(status?.catalogue_rows||11414).toLocaleString('vi-VN')} dòng HS8 · tìm theo mã hoặc mô tả`,'catalogue'],[Files,'Rà soát danh mục SKU','Tìm các mô tả gần nhau đang khai khác mã','audit'],[BookOpen,'Chú giải và nguồn pháp lý','Đối chiếu phạm vi, thời điểm và vai trò nguồn','knowledge']].map(([Icon,title,sub,id])=><a className="quick-link" href={'#'+id} key={id}><span><Icon size={20}/></span><div><strong>{title}</strong><small>{sub}</small></div><ChevronRight size={18}/></a>)}</section></div></>}
 {route==='overview'&&!summary&&!fatal&&<div className="loading-view"><Loader2 size={25} className="spin"/><p>Đang mở không gian làm việc…</p></div>}
 {route==='cases'&&<CasesPage {...{cases,openCase,createCase,demo,busy,onDelete:delCase}}/>}
 {route.startsWith('case/')&&current&&<><div className="back-line"><a href="#cases"><ArrowLeft size={14}/>Danh sách hồ sơ</a><span>{current.reference}</span>{!!current.is_demo&&<Badge value="demo">Hồ sơ mẫu</Badge>}</div><div className="page-heading case-heading"><div><div className="heading-inline"><h1>{current.title}</h1><Badge value={current.status}/></div><p>{current.trade_type==='import'?'Nhập khẩu':'Xuất khẩu'} <span className="sep">/</span> Ngày phân loại {fmtDate(current.classification_date)} <span className="sep">/</span> {current.owner}</p></div><div className="button-row"><Button icon={SlidersHorizontal} onClick={()=>setModal({type:'case',edit:current})}>Thông tin</Button><div className="dropdown"><Button icon={Download} onClick={()=>setModal({type:'export'})}>Xuất hồ sơ</Button></div><Button variant="danger" icon={Trash2} onClick={()=>delCase(current)}>Xóa hồ sơ</Button></div></div>
 <ExtractedShipmentFields current={current}/>
 <div className="sku-bar"><div className="sku-switch"><Package size={19}/><select aria-label="Chọn SKU" value={sku?.id||''} onChange={e=>run(async()=>setSku(await request('/skus/'+e.target.value)))}>{!sku&&<option value="">Chưa có SKU</option>}{current.skus.map(x=><option value={x.id} key={x.id}>{x.sku_code} — {x.name}</option>)}</select></div><div className="sku-bar-meta">{sku&&<><Badge value={sku.status}/><span className="mono">Bản {sku.revision}</span><button className="link" onClick={()=>setModal({type:'sku',edit:sku})}>Sửa SKU</button><button className="link danger" onClick={()=>delSku(sku)}>Xóa SKU</button></>}<Button icon={Plus} variant="subtle" onClick={()=>setModal({type:'sku'})}>Thêm SKU</Button></div></div>
 {!sku?<section className="card"><Empty icon={Package} title="Thêm mặt hàng cần phân loại" action={<Button variant="primary" icon={Plus} onClick={()=>setModal({type:'sku'})}>Thêm SKU đầu tiên</Button>}>Mỗi SKU có thuộc tính, phân tích và quyết định riêng.</Empty></section>:<><div className="workflow-tabs">{[['documents','Chứng từ',Files],['facts','Thông tin hàng',Package],['analysis','So sánh mã HS',Layers],['evidence','Căn cứ',BookOpen],['review','Duyệt & lịch sử',ClipboardCheck]].map(([id,t,Icon],i)=><button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}><span className="step-number">{i+1}</span><Icon size={16}/>{t}{id==='documents'&&<small>{current.documents.length}</small>}</button>)}</div><div className="case-layout"><div className="case-main">
 {tab==='documents'&&<DocumentsPanel {...{current,sku,run,say}} onRefresh={()=>loadCase(current.id,sku.id)} onOpen={id=>setModal({type:'document',id})} onAutofill={f=>setModal(f)}/>}
 {tab==='facts'&&<section className="card"><div className="card-head"><div><h2>Hồ sơ thuộc tính hàng hóa</h2><p>Chỉ thuộc tính đã kiểm tra được đưa vào phân tích.</p></div><Button icon={Plus} onClick={()=>openFact()}>Thêm thuộc tính</Button></div>{sku.declared_code&&<div className="inset-notice"><Info size={16}/><span>Mã ghi trên chứng từ / đang khai: <b className="mono">{sku.declared_code}</b>. Đây là mã quan sát, chưa phải nhãn đúng.</span></div>}{sku.facts.length?<ProductFactsList facts={sku.facts} documents={current.documents} labels={labels} Badge={Badge} onReview={factReview} onDelete={delFact} onDocument={id=>setModal({type:'document',id})}/>:<Empty icon={Package} title="Chưa có thuộc tính được ghi nhận">Tải chứng từ hoặc thêm thông tin từ xác nhận kỹ thuật.</Empty>}<div className="card-footer"><span><Info size={14}/>Không đưa mã HS có sẵn vào thuộc tính sản phẩm.</span><Button variant="subtle" icon={ArrowRight} onClick={()=>setTab('analysis')}>Đối chiếu mã HS</Button></div></section>}
 {tab==='analysis'&&<><AnalysisPanel {...{sku,status,run}} onAnalyze={async (engine,allow_paid_api)=>{const next=await run(()=>post('/skus/'+sku.id+'/analyze',{engine,allow_paid_api}),'Đã tạo danh sách để đối chiếu');if(next)afterSKU(next)}} onAddEvidence={row=>setModal({type:'evidence',prefill:{title:'Dòng danh mục '+row.code,kind:'tariff',quote:row.path,role:'reference',target_codes:[row.code]}})} onCatalog={code=>setModal({type:'catalogDetail',code})}/><VietnamReferences key={'refs-'+sku.id} {...{sku,current,request}} onUse={prefill=>setModal({type:'evidence',prefill})}/><ConsequenceComparison key={'compare-'+sku.id} {...{sku,current,request}}/></>}
 {tab==='evidence'&&<section className="card"><div className="card-head"><div><h2>Căn cứ phân loại</h2><p>Ghi rõ nguồn đang hỗ trợ, loại trừ hay chỉ được tham khảo.</p></div><Button icon={Plus} onClick={()=>setModal({type:'evidence'})}>Thêm căn cứ</Button></div><Notice>Kiểm tra văn bản thay thế, hủy và phạm vi theo đúng ngày phân loại. Mã xuất hiện trong điều khoản loại trừ không phải mã được áp dụng.</Notice>{sku.evidence.length?<div className="evidence-list">{sku.evidence.map(e=><article className="evidence-item" key={e.id}><div className="heading-inline"><span className="doc-icon"><BookOpen size={19}/></span><div><h3>{e.title}</h3><small>{kinds[e.kind]} · {e.jurisdiction} · {e.nomenclature}</small></div><Badge value={e.role}>{roles[e.role]}</Badge><button className="icon-btn danger" title="Xóa căn cứ" aria-label="Xóa căn cứ" onClick={()=>delEvidence(e)}><Trash2 size={15}/></button></div><blockquote>{e.quote}</blockquote><div className="evidence-meta"><Badge value={e.lifecycle}/><span>{e.reviewer?'Đã đối chiếu: '+e.reviewer:'Chưa có người đối chiếu'}</span><span>{e.effective_from||'Chưa ghi ngày bắt đầu'} → {e.effective_to||'Chưa ghi ngày kết thúc'}</span>{e.target_codes?.length>0&&<span>Mã/phạm vi: {e.target_codes.join(', ')}</span>}{e.source_url&&<a href={e.source_url} target="_blank" rel="noreferrer">Mở nguồn <ExternalLink size={12}/></a>}<button className="link" onClick={()=>setModal({type:'evidenceReview',evidence:e})}>Đối chiếu lại vai trò / hiệu lực</button></div></article>)}</div>:<Empty icon={BookOpen} title="Chưa ghi nhận căn cứ">Thêm dòng danh mục, chú giải và tài liệu phân biệt các mã đang xem.</Empty>}</section>}
 {tab==='review'&&<><FrozenDossier {...{sku,current,request,saveBlob}}/><section className="card"><div className="card-head"><div><h2>Quyết định phân loại nội bộ</h2><p>Lưu lựa chọn, lập luận và người kiểm tra độc lập.</p></div><ShieldCheck size={21} className="teal"/></div>{sku.decision?<div className="decision-box"><Badge value="approved"/><h2 className="mono">{sku.decision.code}</h2><p>{sku.decision.reason}</p><small>Người lập: {sku.decision.preparer} · Người duyệt: {sku.decision.reviewer} · {fmtTime(sku.decision.created_at)}</small></div>:<div className="review-summary"><h3>{sku.analysis?'Kết quả đang chờ đối chiếu':'Chưa đủ hồ sơ để duyệt'}</h3><p>Người duyệt cần kiểm tra thuộc tính, tiêu chí phân biệt và các căn cứ áp dụng cho đúng SKU.</p><div className="button-row"><Button icon={ClipboardCheck} variant="primary" onClick={()=>setModal({type:'review',action:'approve'})}>Lập phiếu duyệt</Button><Button icon={MessageSquare} onClick={()=>setModal({type:'review',action:'return'})}>Yêu cầu bổ sung</Button></div></div>}<div className="inset-notice"><Info size={16}/>Quyết định nội bộ chưa tự trở thành nhãn gold và không thay thế kết luận của Hải quan. Khi hồ sơ thay đổi, quyết định cũ được đánh dấu cần xem lại.</div></section><section className="card"><div className="card-head"><h2>Lịch sử hồ sơ</h2><Badge value="neutral">{current.events.length} sự kiện gần nhất</Badge></div><Events events={current.events}/></section></>}
 </div><aside className="readiness card"><div className="readiness-title"><ShieldCheck size={19}/><h3>Kiểm tra hồ sơ</h3></div><p>Thuộc tính bắt buộc đã xác minh</p><div className="readiness-count"><strong>{sku.readiness.required_fields.length-sku.readiness.missing_fields.length}<span>/{sku.readiness.required_fields.length}</span></strong><span>thuộc tính</span></div><div className="progress"><i style={{width:((1-sku.readiness.missing_fields.length/sku.readiness.required_fields.length)*100)+'%'}}/></div><ul className="checks">{sku.readiness.required_fields.map(f=><li className={sku.readiness.verified_fields.includes(f)?'done':''} key={f}>{sku.readiness.verified_fields.includes(f)?<CheckCircle2 size={16}/>:<span className="check-ring"/>}{labels[f]}</li>)}</ul><div className="readiness-divider"/><div className="mini-check"><BookOpen size={16}/><span>{sku.evidence.filter(e=>e.reviewer&&e.lifecycle==='active').length} căn cứ đã đối chiếu</span></div><div className="mini-check"><Layers size={16}/><span>{sku.analysis?'Có phân tích ở bản hiện tại':'Chưa phân tích ở bản hiện tại'}</span></div><Button variant="primary" icon={ArrowRight} disabled={!sku.readiness.can_analyze||busy} onClick={()=>setTab('analysis')}>Đối chiếu mã HS</Button><small className="readiness-note">Mức hoàn thiện hồ sơ không phải độ chính xác của model.</small>{sku.analysis?.questions.filter(q=>q.status==='missing').map((q,i)=><div className="question-note" key={i}><MessageSquare size={14}/><p>{q.question}</p></div>)}</aside></div></>}
 </>}
 {route==='catalogue'&&<CataloguePage {...{run}} onDetail={code=>setModal({type:'catalogDetail',code})}/>}
 {route==='knowledge'&&<KnowledgePage {...{run}}/>}
 {route==='audit'&&<AuditPage {...{run,say}}/>}
 {route.startsWith('case/')&&sku&&<div className="tax-case-shortcut"><span>Thuế theo SKU <b>{sku.sku_code}</b> và ngày hồ sơ</span><Button icon={Calculator} onClick={()=>nav('tax')}>Mở kịch bản thuế</Button></div>}
 {route==='tax'&&<TaxPage request={request} cases={cases} saveBlob={saveBlob} initialSku={sku} initialCase={current}/>}
 {route==='knowledge'&&<><LegalStatusPanel request={request}/><ProjectKnowledgePanel request={request}/></>}
 {(route==='quality'||route==='settings'||route==='system')&&<UnifiedSystemPage route={route} run={run} status={status} onRefresh={refresh} onKey={()=>setApiLogin(true)}/>}
 </main><footer className="app-footer"><span>HS Workspace <span className="muted">/</span> Việt Nam · AHTN 2022</span><span>Hỗ trợ quyết định có người kiểm tra</span></footer></div>
 {toast&&<div className={'toast '+(toast.error?'toast-error':'')} role="status">{toast.error?<AlertCircle size={18}/>:<CheckCircle2 size={18}/>}<span>{toast.message}</span><button className="icon-btn" onClick={()=>setToast(null)} aria-label="Đóng thông báo"><X size={15}/></button></div>}
 {apiLogin&&<FormModal title="Khóa truy cập không gian" subtitle="Nhập khóa HS_API_KEY đã cấu hình trên máy chủ. Khóa chỉ giữ trong bộ nhớ của thẻ này." onClose={()=>setApiLogin(false)} onSubmit={async f=>{accessKey=f.get('key');await request('/status');setApiLogin(false);refresh()}} submit="Kết nối"><Field label="Khóa truy cập"><input name="key" type="password" required autoComplete="off"/></Field></FormModal>}
 {modal?.type==='case'&&(modal.edit?<FormModal title="Thông tin hồ sơ" subtitle="Một hồ sơ có thể gồm nhiều SKU được phân loại độc lập." onClose={()=>setModal(null)} submit="Lưu thay đổi" onSubmit={async f=>{const v=getValues(f);v.legal_hold=f.has('legal_hold');v.declaration_registered_date=v.declaration_registered_date||null;const c=await patch('/cases/'+modal.edit.id,v);setModal(null);await refresh();loadCase(c.id,sku?.id);}}><div className="form-grid"><Field label="Tên hồ sơ" wide><input name="title" required minLength={3} maxLength={250} defaultValue={modal.edit?.title} placeholder="Ví dụ: Lô nguyên liệu thép tháng 11"/></Field><Field label="Người phụ trách"><input name="owner" required minLength={2} defaultValue={modal.edit?.owner||'Nhóm 8'}/></Field><Field label="Luồng hàng"><select name="trade_type" defaultValue={modal.edit?.trade_type||'import'}><option value="import">Nhập khẩu</option><option value="export">Xuất khẩu</option></select></Field><Field label="Ngày phân loại" hint="Đối chiếu hiệu lực văn bản theo ngày này."><input type="date" name="classification_date" required defaultValue={modal.edit?.classification_date||todayVN()}/></Field><Field label="Phạm vi"><input value="Việt Nam · AHTN 2022" disabled/></Field><Field label="Số tờ khai (nếu đã đăng ký)"><input name="declaration_number" maxLength={100} defaultValue={modal.edit?.declaration_number||''}/></Field><Field label="Ngày đăng ký tờ khai" hint="Dùng để tính mốc lưu hồ sơ; có thể để trống trước khi khai."><input name="declaration_registered_date" type="date" defaultValue={modal.edit?.declaration_registered_date||''}/></Field><label className="checkbox-row wide"><input type="checkbox" name="legal_hold" defaultChecked={!!modal.edit?.legal_hold}/><span>Tiếp tục giữ hồ sơ vì kiểm tra, tranh chấp hoặc yêu cầu riêng.</span></label><Field label="Ghi chú" wide><textarea name="notes" defaultValue={modal.edit?.notes} rows={3}/></Field></div><Notice>Đổi ngày phân loại sẽ yêu cầu xem lại phân tích và quyết định của các SKU trong hồ sơ.</Notice></FormModal>:<CreateCaseModal onClose={()=>setModal(null)} onStartDraft={df=>setModal({type:'autofill_review',draft:df})} onSubmitManual={async f=>{const v=getValues(f);v.legal_hold=f.has('legal_hold');v.declaration_registered_date=v.declaration_registered_date||null;const c=await post('/cases',v);setModal(null);await refresh();nav('case/'+c.id)}}/>)}
 {modal?.type==='autofill_review'&&<AutofillReviewWorkspaceModal draft={modal.draft} onClose={()=>setModal(null)} onCommit={async pl=>{const nc=await post('/autofill/draft/'+modal.draft.draft_id+'/commit',pl);setModal(null);await refresh();nav('case/'+nc.id);say('Đã tạo hồ sơ từ bộ chứng từ thành công')}}/>}
 {modal?.type==='case_autofill_review'&&<CaseAutofillReviewModal data={modal.data} case_id={modal.case_id} onClose={()=>setModal(null)} onApply={async pl=>{await post('/cases/'+modal.case_id+'/autofill/apply',pl);setModal(null);await loadCase(modal.case_id,sku?.id);say('Đã tự điền thuộc tính từ chứng từ vào hồ sơ thành công')}}/>}
 {modal?.type==='sku'&&<FormModal title={modal.edit?'Sửa mặt hàng':'Thêm SKU'} onClose={()=>setModal(null)} onSubmit={async f=>{const v=getValues(f);const s=modal.edit?await patch('/skus/'+sku.id,v):await post('/cases/'+current.id+'/skus',v);setModal(null);await afterSKU(s);setTab('facts')}}><div className="form-grid"><Field label="Mã SKU"><input name="sku_code" required defaultValue={modal.edit?.sku_code} placeholder="SKU-001"/></Field><Field label="Nhóm hàng để gợi ý thuộc tính"><select name="product_family" defaultValue={modal.edit?.product_family||'general'}>{Object.entries(family).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></Field><Field label="Tên hàng" wide><input name="name" required minLength={3} defaultValue={modal.edit?.name} placeholder="Tên kỹ thuật, không kèm kết luận HS"/></Field><Field label="Mô tả ban đầu" wide><textarea name="description" rows={3} defaultValue={modal.edit?.description}/></Field><Field label="Mã đang khai / quan sát" wide hint="Không dùng trường này làm nhãn đúng hoặc đầu vào model."><input name="declared_code" className="mono" maxLength={30} defaultValue={modal.edit?.declared_code||''}/></Field></div></FormModal>}
 {modal?.type==='fact'&&<FactModal {...{current,labels}} prefill={modal.prefill} onClose={()=>setModal(null)} onSubmit={async v=>{const next=await post('/skus/'+sku.id+'/facts',v);setModal(null);await afterSKU(next);say('Đã lưu thuộc tính và cập nhật phiên bản hồ sơ')}}/>}
 {modal?.type==='factReview'&&<FormModal title={modal.status==='verified'?'Xác minh thuộc tính':'Cập nhật trạng thái thuộc tính'} onClose={()=>setModal(null)} onSubmit={async f=>{await performFactGroupAction(modal.facts,id=>patch('/skus/'+sku.id+'/facts/'+id,{status:modal.status,reviewer:f.get('reviewer')}),reloadFacts);setModal(null);}}><Badge value={modal.status}/><h3>{labels[modal.fact.field]||modal.fact.field}</h3><p>{modal.fact.value}</p><p>Thao tác áp dụng cho {modal.facts.length} nguồn đang gộp. Đối chiếu từng nguồn trước khi xác nhận.</p>{modal.facts.map(f=><div key={f.id}><small>{f.document_id?(current.documents.find(d=>d.id===f.document_id)?.name||'Chứng từ')+' · đơn vị '+f.page_number:'Xác nhận / ghi chép trực tiếp'} · {f.value}{f.unit?' '+f.unit:''}</small><blockquote>{f.quote||'Chưa có trích đoạn nguồn. Hãy ghi nhận lại thuộc tính với nguồn xác minh.'}</blockquote></div>)}<Field label="Người kiểm tra" hint="Chỉ xác nhận sau khi đã đối chiếu các chứng từ / xác nhận kỹ thuật."><input name="reviewer" required minLength={2} placeholder="Họ tên người thực hiện"/></Field></FormModal>}
 {modal?.type==='document'&&<DocumentModal id={modal.id} {...{run}} onRetry={async()=>{await post('/documents/'+modal.id+'/retry',{});setModal(null);await loadCase(current.id,sku?.id);say('Đang trích xuất lại. Thuộc tính/căn cứ liên quan cần được kiểm tra lại.')}} onClose={()=>setModal(null)} onFact={v=>openFact(v)}/>}
 {modal?.type==='evidence'&&<EvidenceModal prefill={modal.prefill||{}} current={current} onClose={()=>setModal(null)} onSubmit={async v=>{const s=await post('/skus/'+sku.id+'/evidence',v);setModal(null);afterSKU(s);say('Đã lưu căn cứ. Cần phân tích lại với phiên bản hồ sơ hiện tại.')}}/>}
 {modal?.type==='evidenceReview'&&<FormModal title="Đối chiếu lại căn cứ" subtitle={modal.evidence.title} onClose={()=>setModal(null)} onSubmit={async f=>{const v=getValues(f);v.target_codes=(v.target_codes||'').split(/[ ,;]+/).filter(Boolean);const next=await patch('/skus/'+sku.id+'/evidence/'+modal.evidence.id,v);setModal(null);await afterSKU(next);say('Đã ghi lý do đối chiếu; cần phân tích và duyệt lại')}}><div className="form-grid"><Field label="Vai trò"><select name="role" defaultValue={modal.evidence.role}>{Object.entries(roles).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></Field><Field label="Hiệu lực đã đối chiếu"><select name="lifecycle" defaultValue={modal.evidence.lifecycle}>{['not_checked','active','withdrawn','superseded'].map(k=><option key={k} value={k}>{statuses[k]}</option>)}</select></Field><Field label="Mã/phạm vi hỗ trợ hoặc loại trừ" wide><input name="target_codes" defaultValue={(modal.evidence.target_codes||[]).join(', ')}/></Field><Field label="Người đối chiếu"><input name="reviewer" required minLength={2} maxLength={100}/></Field><Field label="Lý do và căn cứ xử lý mâu thuẫn / thay đổi" wide><textarea name="resolution_note" required minLength={10} maxLength={4000} rows={4}/></Field></div><Notice>Nội dung nguồn gốc được giữ nguyên. Lịch sử ghi lại vai trò cũ, vai trò mới và lý do xử lý.</Notice></FormModal>}
 {modal?.type==='review'&&<FormModal title={modal.action==='return'?'Yêu cầu bổ sung hồ sơ':'Lập phiếu duyệt nội bộ'} subtitle={'SKU '+sku.sku_code+' · phiên bản '+sku.revision} wide={modal.action==='approve'} onClose={()=>setModal(null)} submit={modal.action==='return'?'Lưu yêu cầu':'Lưu quyết định nội bộ'} submitDisabled={modal.action==='approve'&&!reviewCandidateState(sku).hasCurrentAnalysis} onSubmit={async f=>{const v=getValues(f);v.evidence_ids=f.getAll('evidence_ids');v.expected_revision=sku.revision;v.expected_analysis_id=sku.analysis_id;v.classification_basis_confirmed=f.has('classification_basis_confirmed');v.action=modal.action;const s=await post('/skus/'+sku.id+'/review',v);setModal(null);afterSKU(s);say('Đã lưu phiếu và nhật ký')}}><ReviewFields sku={sku} current={current} action={modal.action} Field={Field} Notice={Notice} roles={roles} statuses={statuses} onRefreshAnalysis={async()=>{const next=await post('/skus/'+sku.id+'/analyze',{engine:'catalogue'});await afterSKU(next);say('Đã cập nhật danh sách mã; nội dung phiếu được giữ nguyên')}}/></FormModal>}
 {modal?.type==='export'&&<Modal title="Xuất hồ sơ phân loại" subtitle="Chọn gói có bản gốc hoặc bản đọc/tổng hợp để giải trình." onClose={()=>setModal(null)}><div className="modal-body export-options">{[['zip','Gói bằng chứng ZIP','Chứng từ gốc, bản chụp quyết định và manifest SHA256'],['pdf','Bản đọc PDF','Phiếu tổng hợp, nguồn trích và lịch sử'],['xlsx','Bảng dữ liệu Excel','Các sheet SKU, thuộc tính, căn cứ và tài liệu'],['json','Hồ sơ máy đọc JSON','Giữ cấu trúc, ID, phiên bản và toàn bộ nội dung']].map(([kind,title,sub])=><button key={kind} onClick={()=>exportCase(kind)}><span className="doc-icon"><FileText size={23}/></span><span><strong>{title}</strong><small>{sub}</small></span><Download size={19}/></button>)}</div></Modal>}
 {modal?.type==='catalogDetail'&&<CatalogueDetail code={modal.code} onClose={()=>setModal(null)} {...{run}}/>}
  {modal?.type==='confirm'&&<Modal title={modal.title} onClose={()=>setModal(null)}><div className="modal-body"><p>{modal.message}</p></div><div className="modal-foot"><Button type="button" onClick={()=>setModal(null)}>Hủy</Button><Button variant="primary danger" onClick={async()=>{setModal(null);await modal.onConfirm()}}>{modal.confirmText||'Xóa'}</Button></div></Modal>}
 </div>;
}
function CaseTable({cases,onOpen,emptyAction,onDelete}){return cases.length?<div className="table-wrap"><table className="case-table"><thead><tr><th>Hồ sơ</th><th>Trạng thái</th><th>SKU</th><th>Cập nhật</th><th/>{onDelete&&<th/>}</tr></thead><tbody>{cases.map(c=><tr key={c.id} onClick={()=>onOpen(c)}><td><button className="table-title" onClick={e=>{e.stopPropagation();onOpen(c)}}>{c.title}</button><small>{c.reference}{!!c.is_demo&&' · Hồ sơ mẫu'}</small></td><td><Badge value={c.status}/></td><td className="sku-cell"><strong className="sku-num">{c.approved_skus}/{c.sku_count}</strong> <span className="sku-sub">đã duyệt</span></td><td className="date-cell">{fmtDate(c.updated_at)}</td><td><ChevronRight size={17}/></td>{onDelete&&<td><button className="icon-btn danger" title="Xóa hồ sơ" onClick={e=>{e.stopPropagation();onDelete(c)}}><Trash2 size={16}/></button></td>}</tr>)}</tbody></table></div>:<Empty title="Chưa có hồ sơ phân loại" action={emptyAction}>Bắt đầu bằng một lô hàng và thêm các SKU cần phân loại.</Empty>}
function CasesPage({cases,openCase,createCase,demo,busy,onDelete}){const [q,setQ]=useState(''),[filter,setFilter]=useState('');const items=cases.filter(c=>(c.title+' '+c.reference).toLowerCase().includes(q.toLowerCase())&&(!filter||c.status===filter));return <><div className="page-heading"><div><div className="eyebrow">QUẢN LÝ HỒ SƠ</div><h1>Hồ sơ phân loại</h1><p>Tập trung chứng từ, thuộc tính và quyết định của từng SKU.</p></div><Button variant="primary" icon={Plus} onClick={createCase}>Tạo hồ sơ mới</Button></div><section className="card"><div className="toolbar"><div className="search-field"><Search size={17}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Tìm tên hoặc số hồ sơ…"/></div><select aria-label="Lọc trạng thái" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">Tất cả trạng thái</option>{['draft','collecting','in_review','approved'].map(s=><option key={s} value={s}>{statuses[s]}</option>)}</select><span className="muted">{items.length} hồ sơ</span></div><CaseTable cases={items} onOpen={openCase} onDelete={onDelete} emptyAction={<Button onClick={createCase} icon={Plus}>Tạo hồ sơ</Button>}/></section><div className="sample-link"><span>Cần xem cách ứng dụng vận hành?</span><button className="link" disabled={busy} onClick={demo}>Mở hồ sơ mẫu từ chứng từ dự án <ArrowRight size={14}/></button></div></>}
function Events({events}){const names={case_created:'Tạo hồ sơ',sku_created:'Thêm mặt hàng',evidence_changed:'Cập nhật dữ liệu SKU',analysis_completed:'Hoàn thành phân tích',decision_approved:'Duyệt mã nội bộ',returned:'Yêu cầu bổ sung',case_updated:'Cập nhật hồ sơ',document_uploaded:'Thêm chứng từ',document_processed:'Trích xuất chứng từ',document_extracted:'Trích xuất chứng từ'};return events.length?<div className="events">{events.map(e=><div className="event" key={e.id}><span className={'event-dot '+(e.action==='decision_approved'?'green':'')}/><div><strong>{names[e.action]||e.action}</strong><p>{e.payload.title||e.payload.reason||e.payload.name||e.payload.sku_code||e.payload.code||e.payload.engine||'Đã lưu thay đổi'}</p><small>{e.actor} <span>·</span> {fmtTime(e.created_at)}</small></div></div>)}</div>:<div className="quiet-empty">Chưa có hoạt động. Các thao tác sẽ được ghi nhận tại đây.</div>}
function DocumentsPanel({current,sku,run,say,onRefresh,onOpen,onAutofill}){const input=useRef(),[uploading,setUploading]=useState(false),[drag,setDrag]=useState(false);async function delDoc(d){if(!window.confirm())return;await run(()=>request("/documents/"+d.id,{method:"DELETE"}));say("Đã xóa chứng từ");onRefresh();}const pending=current.documents.some(d=>['queued','processing'].includes(d.status));useEffect(()=>{if(!pending)return;const t=setInterval(onRefresh,2500);return()=>clearInterval(t)},[pending,current.id]);async function upload(files){if(!files.length)return;setUploading(true);const f=new FormData();[...files].forEach(x=>f.append('files',x));f.append('sku_id',sku.id);const r=await run(()=>request('/cases/'+current.id+'/documents',{method:'POST',body:f}));if(r){say(`${r.added} tệp đã thêm; ${r.skipped.length} tệp bỏ qua / trùng.`);onRefresh()}setUploading(false);if(input.current)input.current.value='';}
 return <section className="card"><div className="card-head"><div><h2>Chứng từ của hồ sơ</h2><p>Trích xuất toàn bộ trang; người dùng kiểm tra nội dung trước khi sử dụng.</p></div><div style={{display:'flex',gap:'8px',alignItems:'center'}}><Button variant="primary" onClick={async()=>{try{const res=await run(()=>request('/cases/'+current.id+'/autofill',{method:'POST'}));if(!res.skus.length&&!Object.keys(res.dossier_fields||{}).length){say('Chưa có chứng từ hoặc không tìm thấy trường mới để tự điền.',true);return;}onAutofill&&onAutofill({type:'case_autofill_review',data:res,case_id:current.id});}catch(x){say(x.message||'Lỗi trích xuất chứng từ',true);}}}>⚡ Trích xuất & Tự điền từ chứng từ</Button><Button icon={RefreshCw} variant="subtle" onClick={onRefresh}>Làm mới</Button></div></div><div className={'upload-zone '+(drag?'drag':'')} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);upload(e.dataTransfer.files)}}><span className="upload-icon">{uploading?<Loader2 className="spin" size={24}/>:<Upload size={24}/>}</span><h3>{uploading?'Đang tải chứng từ…':'Kéo thả chứng từ vào đây'}</h3><p>PDF, ảnh, Word, Excel, CSV, TXT hoặc gói ZIP / RAR · tối đa 128 MB / tệp</p><input ref={input} type="file" multiple hidden accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx,.pptx,.csv,.txt,.zip,.rar" onChange={e=>upload(e.target.files)}/><Button icon={Plus} disabled={uploading} onClick={()=>input.current.click()}>Chọn tệp từ máy</Button></div><div className="documents-list">{current.documents.map(d=><div className="document-row" key={d.id}><span className="doc-icon"><FileText size={22}/></span><div className="doc-row-main"><button className="table-title" onClick={()=>onOpen(d.id)}>{d.name}</button><small>{d.processed_pages}{d.total_pages?'/'+d.total_pages:''} trang / đơn vị · SHA256 {d.sha256.slice(0,10)}{d.source_archive&&' · Từ gói nén'}</small>{d.error&&<p className="error-text">{d.error}</p>}</div><Badge value={d.status}/>{!['queued','processing'].includes(d.status)?<button className="icon-btn" title="Trích xuất lại · các xác minh liên quan sẽ cần rà soát" onClick={()=>run(async()=>{await post('/documents/'+d.id+'/retry',{});onRefresh()})}><RefreshCw size={17}/></button>:<button className="icon-btn" aria-label={'Mở '+d.name} onClick={()=>onOpen(d.id)}><ArrowUpRight size={18}/></button>}<button className="icon-btn danger" title="Xóa chứng từ" aria-label={'Xóa '+d.name} onClick={()=>delDoc(d)}><Trash2 size={16}/></button></div>)}</div><div className="card-footer"><span><ScanText size={15}/>OCR tiếng Việt cần Tesseract vie+eng. Thiếu công cụ được báo rõ trong từng tệp.</span></div></section>}
function DocumentModal({id,onClose,onFact,onRetry,run}){const [doc,setDoc]=useState(null),[page,setPage]=useState(0),[url,setUrl]=useState(''),[selected,setSelected]=useState('');const text=useRef();useEffect(()=>{let active=true,u;run(async()=>{const [d,b]=await Promise.all([request('/documents/'+id),request('/documents/'+id+'/file',{blob:true})]);if(!active)return;setDoc(d);u=URL.createObjectURL(b);setUrl(u)});return()=>{active=false;if(u)URL.revokeObjectURL(u)}},[id]);return <Modal title={doc?.name||'Đang mở chứng từ…'} subtitle="Đối chiếu bản gốc và nội dung trích xuất. Chọn đúng đoạn làm nguồn thuộc tính." {...{onClose}} wide><div className="document-view"><div className="original-preview">{doc&&url&&(doc.mime==='application/pdf'?<iframe title="Chứng từ gốc" src={url+'#toolbar=1'}/>:doc.mime.startsWith('image/')?<img src={url} alt="Chứng từ gốc"/>:<div className="empty"><FileText size={40}/><h3>Bản gốc {doc.name.split('.').at(-1).toUpperCase()}</h3><p>Mở tệp trên máy để đối chiếu định dạng.</p><a className="btn" href={url} download={doc.name}><Download size={16}/>Tải bản gốc</a></div>)}</div><div className="extracted-panel"><div className="extract-head"><h3>Nội dung trích xuất</h3><button className="icon-btn" title="Trích xuất lại và yêu cầu kiểm tra nguồn liên quan" aria-label="Trích xuất lại chứng từ" onClick={()=>run(onRetry)}><RefreshCw size={15}/></button><select aria-label="Trang / đơn vị trích xuất" value={page} onChange={e=>{setPage(+e.target.value);setSelected('')}}>{doc?.pages.map((p,i)=><option key={p.id} value={i}>Trang / đơn vị {p.number} · {p.method}</option>)}</select></div><Notice>Đoạn OCR có thể sai số, đơn vị hoặc thứ tự bảng. Đối chiếu bản gốc trước khi xác minh.</Notice><textarea ref={text} className="extract-text" value={doc?.pages[page]?.text||'Chưa có nội dung. Tệp có thể đang được xử lý.'} readOnly onSelect={e=>setSelected(e.target.value.slice(e.target.selectionStart,e.target.selectionEnd))}/><div className="extract-actions"><small>{selected.length?`Đã chọn ${selected.length} ký tự`:'Bôi chọn đoạn văn bản để ghi nguồn.'}</small><Button variant="primary" icon={Plus} disabled={!selected.trim()} onClick={()=>onFact({document_id:id,page_number:doc.pages[page].number,quote:selected,source_kind:'document'})}>Tạo thuộc tính từ đoạn chọn</Button></div></div></div></Modal>}
function FactModal({current,prefill,onClose,onSubmit}){const [source,setSource]=useState(prefill.document_id?'document':'manual_declaration');return <FormModal title="Ghi nhận thuộc tính" subtitle="Giá trị mô tả sản phẩm cần tách khỏi kết luận phân loại HS." {...{onClose}} onSubmit={async f=>{const v=getValues(f);v.source_kind=source;v.document_id=v.document_id||null;v.page_number=v.page_number?+v.page_number:null;v.reviewer=v.reviewer||null;await onSubmit(v)}}><div className="form-grid"><Field label="Thuộc tính"><select name="field" defaultValue={prefill.field||'name'}>{Object.entries(labels).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></Field><Field label="Loại nguồn"><select value={source} onChange={e=>setSource(e.target.value)}><option value="manual_declaration">Xác nhận kỹ thuật trực tiếp</option><option value="document">Trích từ chứng từ</option></select></Field><Field label="Giá trị thuộc tính" wide><textarea name="value" rows={3} required minLength={2} placeholder="Ghi giá trị đúng như đã kiểm tra; giữ số và đơn vị."/></Field>{source==='document'&&<><Field label="Chứng từ"><select name="document_id" required defaultValue={prefill.document_id||''}><option value="">Chọn chứng từ</option>{current.documents.map(d=><option value={d.id} key={d.id}>{d.name}</option>)}</select></Field><Field label="Trang / đơn vị"><input type="number" min={1} required name="page_number" defaultValue={prefill.page_number||1}/></Field></>}<Field label={source==='document'?'Trích đoạn nguyên văn':'Căn cứ xác nhận kỹ thuật'} wide hint={source==='document'?'Hệ thống kiểm tra đoạn trích có trong đúng trang đã chọn.':'Ghi rõ ai xác nhận, tài liệu được đối chiếu và thông tin kỹ thuật.'}><textarea name="quote" rows={4} required minLength={source==='document'?1:10} defaultValue={prefill.quote}/></Field><Field label="Trạng thái"><select name="status" defaultValue="unverified"><option value="unverified">Chưa kiểm tra</option><option value="verified">Đã kiểm tra</option><option value="conflict">Mâu thuẫn</option></select></Field><Field label="Người kiểm tra (nếu đã xác minh)"><input name="reviewer" minLength={2}/></Field></div></FormModal>}
function AnalysisPanel({sku,status,run,onAnalyze,onAddEvidence,onCatalog}){const [engine,setEngine]=useState('catalogue'),[selected,setSelected]=useState([]),[running,setRunning]=useState(false),[consent,setConsent]=useState(false);const a=sku.analysis;useEffect(()=>{setConsent(false);setSelected([])},[sku.id,sku.revision,engine]);async function analyze(){setRunning(true);try{await onAnalyze(engine,consent);setSelected([])}finally{setConsent(false);setRunning(false)}}const rows=a?.candidates.filter(x=>selected.includes(x.code))||[];return <><section className="card"><div className="card-head"><div><h2>Đối chiếu các mã có thể phù hợp</h2><p>Danh sách truy hồi để kiểm tra cùng cấu trúc danh mục và chú giải.</p></div><Layers size={21} className="teal"/></div><div className="analysis-controls"><Field label="Phương pháp"><select value={engine} onChange={e=>setEngine(e.target.value)}><option value="catalogue">Danh mục · BM25</option><option value="model" disabled={!status?.model_artifacts_available}>Model dự án {status?.model_artifacts_available?'':'· chưa cấu hình artifact'}</option><option value="qwen" disabled={!status?.qwen_enabled}>Qwen 4B · notebook 07 · {status?.qwen_enabled?'thử nghiệm':'chưa bật'}</option><option value="openai" disabled={!status?.openai_enabled}>OpenAI · notebook 07 · {status?.openai_enabled?'cần xác nhận gửi dữ liệu':'chưa cấu hình'}</option></select></Field><Button variant="primary" icon={running?Loader2:RefreshCw} disabled={!sku.readiness.can_analyze||running||(engine==='openai'&&!consent)} onClick={analyze}>{running?'Đang phân tích…':a?'Phân tích lại':'Tạo danh sách đối chiếu'}</Button></div>{engine==='openai'&&<div className="paid-consent"><label className="checkbox-row"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>Cho phép gửi các thuộc tính đã xác minh và cây ứng viên tới OpenAI cho lượt này.<small>Có phí. Giới hạn máy chủ: {status?.api_max_calls} yêu cầu / ngân sách ước tính ${status?.api_max_usd_estimate}. Chưa hiệu chuẩn độ chính xác; không gửi toàn bộ chứng từ.</small></span></label></div>}{!sku.readiness.can_analyze&&<div className="inset-notice"><AlertCircle size={17}/>Xác minh tên/bản chất hàng và công dụng trước khi chạy.</div>}{a?<><div className="analysis-meta"><Badge value="neutral">{a.engine_label}</Badge><span className="mono">{a.model_version?.slice(0,12)}</span><span>{a.candidates.length} dòng danh mục</span><span>{a.elapsed_ms} ms</span></div><div className="table-wrap"><table className="candidate-table"><thead><tr><th>So sánh</th><th>Mã HS8</th><th>Mô tả và cấu trúc</th><th/></tr></thead><tbody>{a.candidates.map((r,i)=><tr key={r.code}><td><input type="checkbox" aria-label={'So sánh '+r.code} checked={selected.includes(r.code)} disabled={!selected.includes(r.code)&&selected.length>=3} onChange={e=>setSelected(e.target.checked?[...selected,r.code]:selected.filter(c=>c!==r.code))}/></td><td><button className="code-link" onClick={()=>onCatalog(r.code)}>{r.code}</button><small>Thứ hạng {i+1}</small></td><td><p>{r.description}</p><small className="path">{r.path}</small></td><td><button className="icon-btn" aria-label={'Ghi căn cứ '+r.code} title="Ghi nhận căn cứ để kiểm tra" onClick={()=>onAddEvidence(r)}><Plus size={17}/></button></td></tr>)}</tbody></table></div>{!a.candidates.length&&<Empty icon={Search} title="Chưa tìm được dòng phù hợp">Bổ sung thông tin kỹ thuật hoặc tra cứu thêm từ nguồn chính thức.</Empty>}<div className="card-footer"><span><Info size={15}/>Thứ hạng và điểm truy hồi chưa phải xác suất đúng HS8.</span><span>Chọn tối đa 3 dòng để so sánh</span></div></>:<Empty icon={Layers} title="Chưa có danh sách đối chiếu">Phân tích sử dụng các thuộc tính đã xác minh của đúng SKU này.</Empty>}</section>{rows.length>0&&<section className="card"><div className="card-head"><h2>So sánh cấu trúc danh mục</h2><span className="muted">{rows.length}/3 dòng</span></div><div className="compare-grid" style={{gridTemplateColumns:`repeat(${rows.length},minmax(0,1fr))`}}>{rows.map(r=><div key={r.code}><h3 className="mono">{r.code}</h3><small>Chương {r.chapter} · Nhóm {r.heading} · HS6 {r.code.slice(0,6)}</small><p>{r.path}</p><Button icon={BookOpen} onClick={()=>onCatalog(r.code)}>Xem dòng cùng HS6</Button></div>)}</div></section>}{a&&<section className="card"><div className="card-head"><h2>Câu hỏi và điều kiện cần đối chiếu</h2></div><div className="question-list">{a.questions.map((q,i)=><div key={i}><span className="question-icon"><MessageSquare size={17}/></span><p>{q.question}</p></div>)}</div>{a.warnings.map((w,i)=><div className="inset-notice" key={i}><Info size={16}/>{w}</div>)}<details className="analysis-input"><summary>Đầu vào thực tế đã gửi cho phương pháp</summary><pre>{a.input_text}</pre><small className="mono">SHA256 {a.input_hash}</small></details></section>}</>}
function EvidenceModal({current,prefill,onClose,onSubmit}){const [doc,setDoc]=useState('');return <FormModal title="Ghi nhận căn cứ phân loại" subtitle="Vai trò nguồn và hiệu lực phải được người có nghiệp vụ đối chiếu." {...{onClose}} wide onSubmit={async f=>{const v=getValues(f);for(const k of ['document_id','effective_from','effective_to','reviewer'])v[k]=v[k]||null;v.page_number=v.page_number?+v.page_number:null;v.target_codes=(v.target_codes||'').split(/[ ,;]+/).filter(Boolean);await onSubmit(v)}}><div className="form-grid"><Field label="Tên văn bản / căn cứ" wide><input name="title" required minLength={3} defaultValue={prefill.title}/></Field><Field label="Loại căn cứ"><select name="kind" defaultValue={prefill.kind||'ruling'}>{Object.entries(kinds).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></Field><Field label="Vai trò đối với SKU"><select name="role" defaultValue={prefill.role||'reference'}>{Object.entries(roles).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></Field><Field label="Đường dẫn nguồn" wide><input type="url" name="source_url" placeholder="https://…" defaultValue={prefill.source_url||''}/></Field><Field label="Hoặc trích từ chứng từ"><select name="document_id" value={doc} onChange={e=>setDoc(e.target.value)}><option value="">Không chọn tệp</option>{current.documents.map(d=><option value={d.id} key={d.id}>{d.name}</option>)}</select></Field><Field label="Trang / đơn vị"><input type="number" name="page_number" min={1} required={!!doc}/></Field><Field label="Trích đoạn và điều kiện áp dụng" wide><textarea name="quote" required minLength={5} rows={4} defaultValue={prefill.quote}/></Field><Field label="Mã / phạm vi căn cứ hỗ trợ hoặc loại trừ" wide hint="Nhập mã 2/4/6/8 số, cách nhau bằng dấu phẩy. Người duyệt phải kiểm tra điều kiện áp dụng."><input name="target_codes" defaultValue={(prefill.target_codes||[]).join(', ')} placeholder="Ví dụ: 85163100"/></Field><Field label="Quốc gia / phạm vi"><input name="jurisdiction" defaultValue="VN" required/></Field><Field label="Phiên bản danh mục"><input name="nomenclature" defaultValue="AHTN2022" required/></Field><Field label="Hiệu lực từ ngày"><input type="date" name="effective_from"/></Field><Field label="Hiệu lực đến ngày (nếu có)"><input type="date" name="effective_to"/></Field><Field label="Trạng thái đã đối chiếu"><select name="lifecycle" defaultValue="not_checked">{['not_checked','active','withdrawn','superseded'].map(x=><option value={x} key={x}>{statuses[x]}</option>)}</select></Field><Field label="Người đối chiếu nguồn"><input name="reviewer" minLength={2}/></Field></div><Notice>Bản danh mục đóng gói trong ứng dụng là bản tổng hợp của dự án. Ghi nguồn chính thức và kiểm tra hiệu lực trước khi sử dụng để duyệt.</Notice></FormModal>}
function CataloguePage({run,onDetail}){const [q,setQ]=useState(''),[chapter,setChapter]=useState(''),[rows,setRows]=useState([]),[loading,setLoading]=useState(true);async function search(){setLoading(true);const r=await run(()=>request('/catalogue?q='+encodeURIComponent(q)+'&chapter='+chapter+'&limit=50'));if(r)setRows(r.rows);setLoading(false)}useEffect(()=>{search()},[]);return <><div className="page-heading"><div><div className="eyebrow">DANH MỤC VIỆT NAM</div><h1>Tra cứu mã HS</h1><p>Tìm trong 11.414 dòng danh mục, xem cấu trúc và các dòng cùng HS6.</p></div><Badge value="neutral">VN · AHTN 2022</Badge></div><section className="card"><form className="catalogue-search" onSubmit={e=>{e.preventDefault();search()}}><div className="search-field"><Search size={20}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Nhập mã HS hoặc mô tả hàng hóa, ví dụ: thép không gỉ cán nguội"/></div><select value={chapter} onChange={e=>setChapter(e.target.value)} aria-label="Chương HS"><option value="">Tất cả chương</option>{Array.from({length:97},(_,i)=>String(i+1).padStart(2,'0')).filter(x=>x!=='77').map(x=><option key={x} value={x}>Chương {x}</option>)}</select><Button variant="primary" icon={Search} disabled={loading}>Tra cứu</Button></form><div className="results-meta"><span>{loading?'Đang tra cứu…':`${rows.length} kết quả hiển thị`}</span><span>Chưa xác minh toàn bộ hiệu lực pháp lý</span></div><div className="catalogue-results">{rows.map(r=><button key={r.code} onClick={()=>onDetail(r.code)}><span className="code-pill">{r.code}</span><div><h3>{r.description}</h3><p>{r.path}</p><small>Chương {r.chapter} · Nhóm {r.heading} · HS6 {r.code.slice(0,6)}</small></div><ArrowUpRight size={18}/></button>)}</div>{!loading&&!rows.length&&<Empty icon={Search} title="Không có kết quả">Thử tên kỹ thuật, từ khóa khác hoặc tìm theo phần đầu của mã.</Empty>}</section></>}
function CatalogueDetail({code,onClose,run}){const [r,setR]=useState(null);useEffect(()=>{run(async()=>setR(await request('/catalogue/'+code)))},[code]);return <Modal title={'Dòng danh mục '+code} subtitle="Kiểm tra toàn bộ cấu trúc và chú giải trước khi chọn mã." {...{onClose}} wide><div className="modal-body">{r?<><div className="catalog-detail-title"><span className="code-pill">{r.code}</span><h2>{r.description}</h2></div><div className="hierarchy">{r.path.split(' > ').map((v,i)=><div key={i} style={{paddingLeft:i*12}}><ChevronRight size={14}/>{v}</div>)}</div><Notice>Danh mục dự án · {r.nomenclature}. Trạng thái đối chiếu văn bản chính thức: chưa xác nhận.</Notice><h3>Các dòng cùng HS6 {code.slice(0,6)}</h3><div className="sibling-list">{r.siblings.map(x=><div key={x.code} className={x.code===code?'selected':''}><span className="mono">{x.code}</span><p>{x.description}</p></div>)}</div><h3>Chú giải liên quan để kiểm tra</h3>{r.notes.map(n=><details className="note-detail" key={n.id}><summary>{n.title}</summary><pre>{n.text}</pre></details>)}</>:<p>Đang mở dòng danh mục…</p>}</div></Modal>}
function KnowledgePage({run}){const [q,setQ]=useState(''),[data,setData]=useState(null);const search=()=>run(async()=>setData(await request('/knowledge?q='+encodeURIComponent(q))));useEffect(()=>{search()},[]);return <><div className="page-heading"><div><div className="eyebrow">TRA CỨU NGUỒN VÀ CHÚ GIẢI</div><h1>Thư viện căn cứ</h1><p>Dùng tài liệu theo đúng quốc gia, phiên bản, thời điểm và phạm vi.</p></div><BookOpen size={28} className="teal"/></div><div className="knowledge-layout"><section className="card"><form className="toolbar" onSubmit={e=>{e.preventDefault();search()}}><div className="search-field"><Search size={18}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Tìm nội dung chú giải…"/></div><Button variant="primary">Tìm kiếm</Button></form><div className="note-list">{data?.notes.map(n=><details key={n.id} className="note-detail"><summary><BookOpen size={17}/><span>{n.title}<small>{n.kind==='chapter_notes'?'Chú giải chương':'Chú giải phần'} · {n.scope}</small></span><ChevronDown size={16}/></summary><pre>{n.text}</pre><small className="muted">Bản tổng hợp của dự án; cần đối chiếu nguyên bản và hiệu lực.</small></details>)}</div></section><aside className="card source-panel"><div className="card-head"><div><h2>Nguồn pháp lý tham chiếu</h2><p>Mốc kiểm tra: 01/11/2026</p></div></div>{data?.legal_sources.rules.map(s=><div className="legal-source" key={s.id}><h3>{s.id}</h3><small>{s.effective_from?'Hiệu lực ghi nhận: '+fmtDate(s.effective_from):'Cần đối chiếu điều khoản hiệu lực'}</small>{s.source?<a href={s.source} target="_blank" rel="noreferrer">Mở nguồn <ExternalLink size={13}/></a>:<Badge value="unverified">Chưa có bản ký chính thức</Badge>}{s.packaged_official_pdf&&<button className="link" onClick={()=>run(async()=>{const b=await request('/legal-document/'+s.id.replaceAll('/','_'),{blob:true});saveBlob(b,s.local_file)})}>Tải bản ký đã lưu <Download size={12}/></button>}<p>{s.role.includes('secondary')?'Bản sao thứ cấp, chưa xác minh với bản ký.':'Nguồn quy trình và biểu mẫu. Không tự tạo nhãn đúng cho sản phẩm.'}</p></div>)}<div className="inset-notice"><Info size={16}/>Thư viện hiện có 102 phạm vi chú giải. Chưa phải bộ văn bản hợp nhất, cập nhật tự động.</div></aside></div></>}
function AuditPage({run,say}){const input=useRef(),[data,setData]=useState(null),[map,setMap]=useState({id:'',description:'',code:''}),[threshold,setThreshold]=useState(.85),[result,setResult]=useState(null),[running,setRunning]=useState(false);async function upload(file){const f=new FormData();f.append('file',file);const r=await run(()=>request('/catalog-import',{method:'POST',body:f}));if(r){setData(r);setResult(null);setMap({id:r.columns.find(c=>/sku|\bid\b/i.test(c))||r.columns[0],description:r.columns.find(c=>/description|mo.?ta|mô tả|tên hàng/i.test(c))||r.columns[1]||r.columns[0],code:r.columns.find(c=>/hs|code|mã/i.test(c)&&!/sku/i.test(c))||r.columns.at(-1)})}}async function audit(){setRunning(true);const r=await run(()=>post('/catalog-audit',{items:data.rows.map((x,i)=>({id:x[map.id]||String(i+1),description:x[map.description],code:x[map.code]})),threshold}));if(r)setResult(r);setRunning(false)}return <><div className="page-heading"><div><div className="eyebrow">KIỂM TRA DANH MỤC DOANH NGHIỆP</div><h1>Rà soát danh mục SKU</h1><p>Phát hiện mã chưa khớp danh mục và mô tả tương tự đang khai khác mã.</p></div><Button icon={Download} onClick={()=>csvFile([['sku','description','hs_code'],['SKU-001','Mô tả kỹ thuật của sản phẩm','01012100']], 'mau_danh_muc_SKU.csv')}>Tải mẫu CSV</Button></div><section className="card"><div className="card-head"><h2>Nhập danh mục</h2><Badge value="neutral">CSV / XLSX · tối đa 5.000 dòng</Badge></div><div className="audit-import"><input hidden ref={input} type="file" accept=".csv,.xlsx" onChange={e=>e.target.files[0]&&upload(e.target.files[0])}/><Button icon={Upload} onClick={()=>input.current.click()}>Chọn danh mục từ máy</Button><span className="muted">Giữ nguyên mã dưới dạng chuỗi, bao gồm số 0 ở đầu.</span></div>{data&&<><div className="audit-map">{[['id','Cột mã SKU'],['description','Cột mô tả hàng'],['code','Cột mã HS hiện tại']].map(([k,v])=><Field label={v} key={k}><select value={map[k]} onChange={e=>setMap({...map,[k]:e.target.value})}>{data.columns.map(c=><option key={c}>{c}</option>)}</select></Field>)}<Field label={'Ngưỡng tương đồng: '+Math.round(threshold*100)+'%'}><input type="range" min="0.5" max="1" step="0.01" value={threshold} onChange={e=>setThreshold(+e.target.value)}/></Field></div><div className="toolbar"><span>{data.rows.length} dòng đã đọc</span><Button variant="primary" icon={running?Loader2:Files} disabled={running||data.rows.length<2} onClick={audit}>{running?'Đang rà soát…':'Rà soát danh mục'}</Button></div></> }</section>{result&&<><div className="stats-grid three"><div className="stat"><span>Dòng đã kiểm tra</span><strong>{result.items}</strong></div><div className="stat"><span>Cặp mô tả cần đối chiếu</span><strong>{result.pairs.length}</strong></div><div className="stat"><span>Mã chưa khớp danh mục</span><strong>{result.invalid_or_unmapped_codes.length}</strong></div></div><Notice>Độ giống mô tả chỉ dùng để đưa vào hàng đợi kiểm tra. Các mã khác nhau có thể đúng do thành phần, kích thước, nguyên lý hoặc trạng thái hàng khác nhau.</Notice><section className="card"><div className="card-head"><h2>Các cặp cần đối chiếu</h2><Button icon={Download} onClick={()=>csvFile([['sku_a','mo_ta_a','hs_a','sku_b','mo_ta_b','hs_b','tuong_dong'],...result.pairs.map(p=>[p.id_a,p.description_a,p.code_a,p.id_b,p.description_b,p.code_b,p.similarity])],'ket_qua_ra_soat.csv')}>Xuất kết quả</Button></div><div className="table-wrap"><table><thead><tr><th>SKU thứ nhất</th><th>SKU thứ hai</th><th>Tương đồng</th></tr></thead><tbody>{result.pairs.slice(0,300).map((p,i)=><tr key={i}><td><b>{p.id_a}</b><p>{p.description_a}</p><span className="mono">{p.code_a}</span></td><td><b>{p.id_b}</b><p>{p.description_b}</p><span className="mono">{p.code_b}</span></td><td>{(p.similarity*100).toFixed(1)}%<small>Cần kiểm tra</small></td></tr>)}</tbody></table></div>{!result.pairs.length&&<div className="quiet-empty">Không tìm thấy cặp khác mã vượt ngưỡng đã chọn.</div>}</section>{result.invalid_or_unmapped_codes.length>0&&<section className="card"><div className="card-head"><h2>Mã chưa có trong danh mục đã nạp</h2><Button icon={Download} onClick={()=>csvFile([['dong','ma_hien_tai'],...result.invalid_or_unmapped_codes.map(x=>[x.row,x.code])],'ma_chua_khop.csv')}>Xuất danh sách</Button></div><div className="invalid-list">{result.invalid_or_unmapped_codes.slice(0,100).map(x=><span key={x.row}>Dòng {x.row}: <b className="mono">{x.code||'(trống)'}</b></span>)}</div></section>}</>}</>}
function UnifiedSystemPage({route, run, status, onRefresh, onKey}) {
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

    <div className="system-tabs">
      <button type="button" className={tab === 'quality' ? 'active' : ''} onClick={() => setTab('quality')}>
        Chất lượng & Đo lường
      </button>
      <button type="button" className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}>
        Cấu hình & Nguồn dữ liệu
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
}

function CreateCaseModal({onClose, onStartDraft, onSubmitManual}) {
  const [tab, setTab] = useState('doc');
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState('');
  const fileInputRef = useRef(null);

  const handleFiles = (fl) => setFiles(prev => [...prev, ...Array.from(fl)]);
  const removeFile = (idx) => setFiles(prev => prev.filter((_, i) => i !== idx));

  const handleProcess = async () => {
    if (!files.length) { setErr('Vui lòng chọn ít nhất một chứng từ.'); return; }
    setUploading(true); setErr('');
    try {
      const fd = new FormData();
      files.forEach(f => fd.append('files', f));
      const res = await request('/autofill/draft', { method: 'POST', body: fd });
      onStartDraft(res);
    } catch (e) {
      setErr(e.message || 'Lỗi xử lý chứng từ.');
    } finally {
      setUploading(false);
    }
  };

  return <Modal title="Tạo hồ sơ phân loại HS" subtitle="Khởi tạo nhanh từ bộ chứng từ hàng hóa hoặc nhập thủ công." onClose={onClose} wide>
    <div className="modal-body">
      <div className="docfirst-tabs">
        <button type="button" className={'docfirst-tab ' + (tab === 'doc' ? 'active' : '')} onClick={() => setTab('doc')}>
          <FileText size={16}/><span>Phương án A — Tạo từ chứng từ</span><span className="docfirst-badge-rec">Khuyến nghị</span>
        </button>
        <button type="button" className={'docfirst-tab ' + (tab === 'manual' ? 'active' : '')} onClick={() => setTab('manual')}>
          <FolderOpen size={16}/><span>Phương án B — Nhập thủ công</span>
        </button>
      </div>
      {tab === 'doc' ? <div>
        <div className="doc-dropzone" onClick={() => fileInputRef.current && fileInputRef.current.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}>
          <input type="file" multiple ref={fileInputRef} style={{ display: 'none' }} accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.csv,.txt,.zip,.rar" onChange={e => handleFiles(e.target.files)}/>
          <div style={{ marginBottom: '12px' }}><Upload size={36} style={{ color: '#0284C7' }}/></div>
          <h3 style={{ margin: '0 0 6px 0', fontSize: '15px', fontWeight: '700' }}>Kéo thả bộ chứng từ vào đây hoặc chọn tệp từ máy</h3>
          <p style={{ margin: 0, color: '#64748B', fontSize: '12.5px' }}>Hỗ trợ PDF (text/scan), Word (.docx), Excel (.xlsx), ảnh (PNG/JPG), TXT, ZIP · Tối đa 128 MB/tệp</p>
        </div>
        {files.length > 0 && <div style={{ marginTop: '16px' }}>
          <h4 style={{ fontSize: '13px', fontWeight: '700', marginBottom: '8px' }}>Danh sách chứng từ đã chọn ({files.length} tệp):</h4>
          {files.map((f, i) => <div key={i} className="doc-file-chip">
            <span className="chip-name"><FileText size={16} style={{ color: '#0284C7' }}/><span>{f.name}</span><small style={{ color: '#94A3B8' }}>({(f.size / 1024).toFixed(1)} KB)</small></span>
            <button type="button" className="icon-btn danger" onClick={() => removeFile(i)}><X size={14}/></button>
          </div>)}
        </div>}
        {err && <div style={{ marginTop: '14px' }}><Notice tone="red">{err}</Notice></div>}
        <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <Button type="button" onClick={onClose}>Hủy</Button>
          <Button variant="primary" disabled={uploading || files.length === 0} onClick={handleProcess}>
            {uploading ? <Loader2 className="spin" size={16}/> : <Plus size={16}/>}{uploading ? 'Đang xử lý & trích xuất…' : 'Xử lý chứng từ & Tự điền'}
          </Button>
        </div>
      </div> : <form onSubmit={async e => { e.preventDefault(); await onSubmitManual(new FormData(e.currentTarget)); }}>
        <div className="form-grid">
          <Field label="Tên hồ sơ" wide><input name="title" required minLength={3} maxLength={250} placeholder="Ví dụ: Lô máy sấy tóc gia dụng tháng 11"/></Field>
          <Field label="Người phụ trách"><input name="owner" required minLength={2} defaultValue="Nhóm 8"/></Field>
          <Field label="Luồng hàng"><select name="trade_type" defaultValue="import"><option value="import">Nhập khẩu</option><option value="export">Xuất khẩu</option></select></Field>
          <Field label="Ngày phân loại" hint="Đối chiếu hiệu lực văn bản theo ngày này."><input type="date" name="classification_date" required defaultValue={todayVN()}/></Field>
          <Field label="Phạm vi"><input value="Việt Nam · AHTN 2022" disabled/></Field>
          <Field label="Số tờ khai (nếu đã đăng ký)"><input name="declaration_number" maxLength={100} defaultValue=""/></Field>
          <Field label="Ngày đăng ký tờ khai" hint="Dùng để tính mốc lưu hồ sơ; có thể để trống trước khi khai."><input name="declaration_registered_date" type="date" defaultValue=""/></Field>
          <label className="checkbox-row wide"><input type="checkbox" name="legal_hold"/><span>Tiếp tục giữ hồ sơ vì kiểm tra, tranh chấp hoặc yêu cầu riêng.</span></label>
          <Field label="Ghi chú" wide><textarea name="notes" rows={3}/></Field>
        </div>
        <div className="modal-foot" style={{ marginTop: '18px' }}>
          <Button type="button" onClick={onClose}>Hủy</Button>
          <Button variant="primary" type="submit">Tạo hồ sơ thủ công</Button>
        </div>
      </form>}
    </div>
  </Modal>;
}

function AutofillReviewWorkspaceModal({draft, onClose, onCommit}) {
  const [activeDoc, setActiveDoc] = useState(0);
  const [activePage, setActivePage] = useState(0);
  const [dossier, setDossier] = useState(draft.dossier_fields || {});
  const [skus, setSkus] = useState(draft.skus || []);
  const [title, setTitle] = useState(
    (dossier.importer?.value ? 'Hồ sơ nhập khẩu — ' + dossier.importer.value : '') ||
    (dossier.invoice_number?.value ? 'Hồ sơ Invoice ' + dossier.invoice_number.value : '') ||
    (draft.documents?.[0] ? 'Hồ sơ từ chứng từ ' + draft.documents[0].name : 'Hồ sơ phân loại từ chứng từ')
  );
  const [owner, setOwner] = useState('Nhóm 8');
  const [tradeType, setTradeType] = useState('import');
  const [classDate, setClassDate] = useState(todayVN());
  const [notes, setNotes] = useState('Khởi tạo qua luồng Document-First & Tự động điền thông tin.');
  const [committing, setCommitting] = useState(false);
  const [err, setErr] = useState('');

  const currentDoc = draft.documents?.[activeDoc] || draft.documents?.[0];
  const pages = currentDoc ? currentDoc.pages || [] : [];
  const currentPage = pages[activePage] || pages[0];

  const updateFactStatus = (sIdx, fIdx, st) => {
    setSkus(prev => {
      const copy = JSON.parse(JSON.stringify(prev));
      copy[sIdx].facts[fIdx].status = st;
      return copy;
    });
  };

  const updateFactValue = (sIdx, fIdx, val) => {
    setSkus(prev => {
      const copy = JSON.parse(JSON.stringify(prev));
      copy[sIdx].facts[fIdx].value = val;
      copy[sIdx].facts[fIdx].source_kind = 'user_input';
      copy[sIdx].facts[fIdx].status = 'unverified';
      return copy;
    });
  };

  const handleCommit = async () => {
    setCommitting(true); setErr('');
    try {
      await onCommit({ title, owner, trade_type: tradeType, classification_date: classDate, declaration_number: dossier.declaration_number?.value || '', dossier_fields: dossier, notes, skus });
    } catch (e) {
      setErr(e.message || 'Lỗi lưu hồ sơ.');
    } finally {
      setCommitting(false);
    }
  };

  const docTypeLabels = {
    commercial_invoice: 'Commercial Invoice (Hóa đơn thương mại)',
    packing_list: 'Packing List (Bảng kê đóng gói)',
    bill_of_lading: 'Bill of Lading (Vận đơn đường biển)',
    air_waybill: 'Air Waybill (Vận đơn hàng không)',
    certificate_of_quality: 'C/Q (Chứng nhận chất lượng)',
    certificate_of_origin: 'C/O (Chứng nhận xuất xứ)',
    technical_spec: 'Technical Spec / Datasheet',
    product_catalogue: 'Product Catalogue',
    customs_declaration: 'Customs Declaration (Tờ khai hải quan)',
    mill_test: 'Mill Test Certificate (Chứng chỉ xuất xưởng)',
    sales_contract: 'Sales Contract (Hợp đồng)',
    regulatory_permit: 'Giấy phép chuyên ngành',
    legal_reference: 'Tài liệu pháp lý tham chiếu',
    other: 'Chứng từ khác'
  };

  return <Modal title="Không gian kiểm tra & đối chiếu chứng từ (Review Workspace)" subtitle="Đối chiếu tài liệu gốc bên trái với các trường thông tin tự động trích xuất bên phải trước khi lưu." onClose={onClose} wide>
    <div className="modal-body" style={{ padding: '16px 20px' }}>
      <div className="review-workspace-container">
        <div className="review-left-pane">
          <div className="review-doc-nav">
            {(draft.documents || []).map((d, i) => <button key={i} type="button" className={'review-doc-tab ' + (activeDoc === i ? 'active' : '')} onClick={() => { setActiveDoc(i); setActivePage(0); }}>
              <FileText size={14}/>{d.name}
            </button>)}
          </div>
          {currentDoc && <div className="review-doc-type-badge">
            <span><strong>Loại nhận diện: </strong>{currentDoc.detected_type?.label || docTypeLabels[currentDoc.kind] || currentDoc.kind}</span>
            <select value={currentDoc.kind || 'other'} onChange={e => { currentDoc.kind = e.target.value; }}>
              {Object.entries(docTypeLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>}
          {pages.length > 1 && <div style={{ padding: '6px 14px', background: '#F1F5F9', borderBottom: '1px solid #E2E8F0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
            <span>Trang {activePage + 1} / {pages.length}</span>
            <div style={{ display: 'flex', gap: '4px' }}>
              <Button disabled={activePage <= 0} onClick={() => setActivePage(p => p - 1)} style={{ padding: '2px 8px', fontSize: '11px' }}>‹ Trước</Button>
              <Button disabled={activePage >= pages.length - 1} onClick={() => setActivePage(p => p + 1)} style={{ padding: '2px 8px', fontSize: '11px' }}>Sau ›</Button>
            </div>
          </div>}
          <div className="review-doc-preview">{currentPage ? currentPage.text : 'Chưa có nội dung văn bản.'}</div>
        </div>

        <div className="review-right-pane">
          <div className="review-card">
            <div className="review-card-title"><span>Thông tin hồ sơ lô hàng</span><Badge value="neutral">Tự động trích xuất</Badge></div>
            <div className="form-grid">
              <Field label="Tên hồ sơ" wide><input value={title} onChange={e => setTitle(e.target.value)} required/></Field>
              <Field label="Người phụ trách"><input value={owner} onChange={e => setOwner(e.target.value)} required/></Field>
              <Field label="Luồng hàng"><select value={tradeType} onChange={e => setTradeType(e.target.value)}><option value="import">Nhập khẩu</option><option value="export">Xuất khẩu</option></select></Field>
              <Field label="Ngày phân loại"><input type="date" value={classDate} onChange={e => setClassDate(e.target.value)} required/></Field>
              {Object.entries(dossier).map(([field,f]) => <Field key={field} label={field.replaceAll('_',' ')} wide>
                <input value={f.value || ''} onChange={e => setDossier({...dossier,[field]:{...f,value:e.target.value,source_kind:'user_input'}})}/>
                <small>{f.status === 'conflicting' ? 'Mâu thuẫn · cần chọn giá trị' : f.source_kind === 'user_input' ? 'Người dùng chỉnh sửa · cần kiểm tra' : 'Có nguồn · chưa xác minh'}</small>
                {(f.sources || f.alternatives || [f]).map((source,i) => <div key={i} className="field-provenance-quote">{source.source_document_name} · Tr.{source.source_page}: “{source.source_quote || source.source_excerpt}”</div>)}
              </Field>)}
            </div>
          </div>

          {draft.reconciliations && draft.reconciliations.length > 0 && <div className="review-card">
            <div className="review-card-title"><span>Đối chiếu chéo giữa các chứng từ</span><Badge value={draft.reconciliations.some(r => r.status === 'conflict') ? 'conflict' : draft.reconciliations.every(r => r.status === 'match') ? 'verified' : 'unverified'}>{draft.reconciliations.some(r => r.status === 'conflict') ? 'Phát hiện mâu thuẫn' : draft.reconciliations.every(r => r.status === 'match') ? 'Khớp dữ liệu' : 'Thiếu dữ liệu · cần kiểm tra'}</Badge></div>
            {draft.reconciliations.map((r, i) => <div key={i} className={'reconcile-card ' + (r.status === 'match' ? 'match' : 'conflict')}>
              {r.status === 'match' ? <Check size={18}/> : <AlertCircle size={18}/>}
              <div><strong>{r.label}</strong><p style={{ margin: '2px 0 0 0' }}>{r.description}</p></div>
            </div>)}
          </div>}

          <div className="review-card">
            <div className="review-card-title"><span>Mặt hàng (SKU) đề xuất ({skus.length} SKU)</span><Badge value="neutral">Tự động phân tách</Badge></div>
            {skus.length === 0 && <Notice>Chưa xác định được SKU. Cần rà soát chứng từ; tài liệu pháp lý chỉ dùng tham chiếu.</Notice>}
            {skus.map((s, sIdx) => <div key={sIdx} style={{ border: '1px solid #E2E8F0', borderRadius: '12px', padding: '14px', marginBottom: '14px', background: '#F8FAFC' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <strong style={{ fontSize: '14px' }}>{s.sku_code}</strong><span style={{ color: '#64748B' }}>—</span><span style={{ fontWeight: '600' }}>{s.name}</span>
                </div>
                {s.declared_code && <span className="status-pill-unverified" title="Mã khai báo trên chứng từ; hệ thống KHÔNG tự động duyệt mã này">Mã quan sát: {s.declared_code} (Chưa duyệt)</span>}
              </div>
              {(s.matching || []).filter(l => l.status === 'needs_review' && skus.some(other => other.id === l.candidate_id)).map((l,i) => <div key={i}><small>Cần xác nhận quan hệ sản phẩm: {l.reasons.join(', ')}</small><Button onClick={async () => {try {const result=await patch('/autofill/draft/'+draft.draft_id,{skus,dossier_fields:dossier,match_confirmations:[{target_sku_id:s.id,source_sku_id:l.candidate_id,confirmed:true}]});setSkus(result.skus);} catch(e) {setErr(e.message);}}}>Xác nhận cùng sản phẩm</Button></div>)}
              {s.missing_fields?.length > 0 && (
                <div className="missing-fields-alert" style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: '8px', padding: '8px 12px', marginBottom: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: '600', color: '#92400E' }}>
                    <span>⚠️ Thuộc tính cần bổ sung:</span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {s.missing_fields.map(f => <span key={f} style={{ background: '#FEF3C7', color: '#92400E', fontSize: '11px', fontWeight: '600', padding: '2px 8px', borderRadius: '6px', border: '1px solid #FCD34D' }}>{labels[f] || f}</span>)}
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {(s.facts || []).map((f, fIdx) => <div key={fIdx} style={{ background: '#FFFFFF', padding: '10px', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <strong style={{ fontSize: '12.5px', color: '#1E293B' }}>{labels[f.field] || f.field}</strong>
                      <span className="provenance-pill">{`${f.document_name || 'chứng từ'} · Tr.${f.page_number || 1}`}</span>
                    </div>
                    <button type="button" className={f.status === 'verified' ? 'status-pill-verified' : 'status-pill-unverified'} disabled={f.extraction_status === 'conflicting' || f.source_kind === 'user_input'} style={{ border: 'none', cursor: 'pointer' }} onClick={() => updateFactStatus(sIdx, fIdx, f.status === 'verified' ? 'unverified' : 'verified')}>
                      {f.extraction_status === 'conflicting' ? 'Mâu thuẫn · cần giải quyết' : f.source_kind === 'user_input' ? 'Người dùng chỉnh sửa' : f.status === 'verified' ? '✓ Đã xác minh' : '○ Chưa kiểm tra'}
                    </button>
                  </div>
                  <input style={{ width: '100%', padding: '6px 8px', fontSize: '13px', borderRadius: '6px', border: '1px solid #CBD5E1', marginTop: '4px' }} value={f.value} onChange={e => updateFactValue(sIdx, fIdx, e.target.value)}/>
                  {f.source_row_id && <small>Dòng {f.source_row_id} · Cột {f.source_header}</small>}
                  {f.quote && <div className="field-provenance-quote">"{f.quote}"</div>}
                </div>)}
              </div>
            </div>)}
          </div>
        </div>
      </div>
      {err && <div style={{ marginTop: '14px' }}><Notice tone="red">{err}</Notice></div>}
      <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
        <Button type="button" onClick={onClose}>Hủy</Button>
        <Button variant="primary" disabled={committing} onClick={handleCommit}>
          {committing ? <Loader2 className="spin" size={16}/> : <Check size={16}/>}{committing ? 'Đang lưu hồ sơ…' : 'Xác nhận & Hoàn tất tạo hồ sơ'}
        </Button>
      </div>
    </div>
  </Modal>;
}

function CaseAutofillReviewModal({data, case_id, onClose, onApply}) {
  const [skus, setSkus] = useState(data.skus || []);
  const [applying, setApplying] = useState(false);
  const [err, setErr] = useState('');

  const handleApply = async () => {
    setApplying(true); setErr('');
    try {
      await onApply({ skus });
    } catch (e) {
      setErr(e.message || 'Lỗi áp dụng dữ liệu.');
    } finally {
      setApplying(false);
    }
  };

  return <Modal title="Trích xuất & Tự điền từ chứng từ hồ sơ" subtitle="Hệ thống trích xuất thông tin kỹ thuật từ chứng từ đã tải lên. Các thuộc tính đã xác minh được giữ nguyên." onClose={onClose} wide>
    <div className="modal-body">
      {data.reconciliations && data.reconciliations.length > 0 && <div style={{ marginBottom: '16px' }}>
        {data.reconciliations.map((r, i) => <div key={i} className={'reconcile-card ' + (r.status === 'match' ? 'match' : 'conflict')}>
          {r.status === 'match' ? <Check size={18}/> : <AlertCircle size={18}/>}
          <div><strong>{r.label}</strong><p style={{ margin: '2px 0 0 0' }}>{r.description}</p></div>
        </div>)}
      </div>}
      <div>
        {skus.length === 0 && <Notice>Chưa xác định được SKU. Cần rà soát chứng từ; tài liệu pháp lý chỉ dùng tham chiếu.</Notice>}
            {skus.map((s, sIdx) => <div key={sIdx} style={{ border: '1px solid #E2E8F0', borderRadius: '12px', padding: '14px', marginBottom: '14px', background: '#F8FAFC' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <div><strong style={{ fontSize: '14px' }}>{s.sku_code}</strong><span style={{ color: '#64748B', margin: '0 6px' }}>—</span><span style={{ fontWeight: '600' }}>{s.name}</span></div>
            {s.existing_sku_id ? <Badge value="neutral">Khớp SKU hiện có</Badge> : <Badge value="collecting">SKU mới đề xuất</Badge>}
          </div>
          {(s.facts || []).map((f, fIdx) => <div key={fIdx} style={{ background: '#FFFFFF', padding: '10px', borderRadius: '8px', border: '1px solid #E2E8F0', marginBottom: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <strong style={{ fontSize: '12.5px' }}>{labels[f.field] || f.field}</strong>
                <span className="provenance-pill">{`${f.document_name || 'chứng từ'} · Tr.${f.page_number || 1}`}</span>
              </div>
              {f.skip_overwrite ? <span className="status-pill-verified">Đã xác minh (Giữ nguyên)</span> : <span className="status-pill-unverified">Sẽ bổ sung</span>}
            </div>
            <div style={{ fontSize: '13px', color: '#1E293B', marginTop: '4px' }}>{f.value}</div>
            {f.quote && <div className="field-provenance-quote">"{f.quote}"</div>}
          </div>)}
        </div>)}
      </div>
      {err && <div style={{ marginTop: '14px' }}><Notice tone="red">{err}</Notice></div>}
      <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
        <Button type="button" onClick={onClose}>Hủy</Button>
        <Button variant="primary" disabled={applying} onClick={handleApply}>
          {applying ? <Loader2 className="spin" size={16}/> : <Check size={16}/>}{applying ? 'Đang áp dụng…' : 'Áp dụng vào hồ sơ'}
        </Button>
      </div>
    </div>
  </Modal>;
}

createRoot(document.getElementById('root')).render(<App/>);

function ExtractedShipmentFields({current}) {
  if (!current.extracted_fields?.length) return null;
  return <details className="card"><summary>Thông tin giao dịch đã lưu · {current.extracted_fields.length} giá trị nguồn</summary>
    {current.extracted_fields.map(f => <div key={f.id} style={{padding:'10px 16px'}}><strong>{f.field.replaceAll('_',' ')}: {f.value}</strong><small> · {f.status === 'conflict' ? 'Mâu thuẫn' : f.value_origin === 'user_input' ? 'Người dùng chỉnh sửa · cần kiểm tra' : 'Có nguồn · chưa xác minh'}</small><p>{f.source_document_name} · Trang {f.page_number}</p><blockquote>{f.quote}</blockquote></div>)}
  </details>;
}
