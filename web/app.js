const $=id=>document.getElementById(id);
let token='',busy=false,ticket='',lastStatus=null;
const buttons=['upload','loadPath','red','stop','mark'];
function render(){const s=lastStatus;for(const id of buttons)$(id).disabled=busy||!s||(s.pending&&id!=='stop')||(['red','stop','mark'].includes(id)&&!s.available[id]);}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();token=s.token;lastStatus=s;$('connection').textContent=Object.values(s.available).some(Boolean)?'EZCAD2 در دسترس':'EZCAD2 آماده نیست';$('title').textContent=s.title||'—';$('selected').textContent=s.selected||'—';if(!busy)$('message').textContent=s.message;}catch{lastStatus=null;$('connection').textContent='سرویس در دسترس نیست';}render();}
async function post(data){const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Panel-Token':token},body:JSON.stringify({...data,id:crypto.randomUUID()})});const result=await r.json();if(!r.ok||!result.ok)throw Error(result.message||'خطای درخواست');return result;}
async function act(data){if(busy)return;busy=true;render();try{const r=await post(data);$('message').textContent=r.message||'درخواست ثبت شد';return r;}catch(e){$('message').textContent=e.message+' — درخواست را بدون بررسی EZCAD2 تکرار نکنید.';throw e;}finally{busy=false;render();}}
for(const action of ['red','stop'])$(action).onclick=()=>act({action}).catch(()=>{});
$('loadPath').onclick=()=>act({action:'load',path:$('path').value.trim()}).catch(()=>{});
$('upload').onclick=async()=>{const file=$('file').files[0];if(!file||!file.name.toLowerCase().endsWith('.ezd')||file.size===0||file.size>20*1024*1024){$('message').textContent='یک فایل .ezd غیرخالی تا ۲۰ مگابایت انتخاب کنید.';return;}const reader=new FileReader();reader.onload=()=>act({action:'load',name:file.name,content:reader.result.split(',')[1]}).catch(()=>{});reader.onerror=()=>{$('message').textContent='خواندن فایل ممکن نشد';};reader.readAsDataURL(file);};
$('mark').onclick=async()=>{try{const r=await act({action:'prepare_mark'});if(!r)return;ticket=r.ticket;$('confirmTitle').textContent=r.title;$('confirm').showModal();$('cancel').focus();}catch{}};
$('cancel').onclick=()=>{ticket='';$('confirm').close();};
$('confirm').addEventListener('cancel',()=>{ticket='';});
$('confirmMark').onclick=()=>{const current=ticket;ticket='';$('confirm').close();if(current)act({action:'mark',ticket:current}).catch(()=>{});};
render();refresh();setInterval(refresh,2000);
