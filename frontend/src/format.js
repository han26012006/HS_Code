const ZONE='Asia/Ho_Chi_Minh';
export function formatDate(value){
 if(!value)return '—';
 if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value.split('-').reverse().join('/');
 const d=new Date(value);if(Number.isNaN(d.getTime()))return '—';
 return d.toLocaleDateString('vi-VN',{timeZone:ZONE,day:'2-digit',month:'2-digit',year:'numeric'});
}
export function formatTime(value){return value?new Date(value).toLocaleString('vi-VN',{timeZone:ZONE,hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'}):'';}
export function todayVN(value=new Date()){
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:ZONE,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value).map(x=>[x.type,x.value]));
 return `${p.year}-${p.month}-${p.day}`;
}
