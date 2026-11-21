(() => {
  "use strict";
  const root=document.getElementById("kart-devices"), message=document.getElementById("kart-device-message"), statuses=document.getElementById("kart-device-status");
  if(!root)return;
  let context=window.kartdashContext||{pilots:[]},data={devices:[],drivers:[]},fetching=false,applying=false,signature="";
  const queued=new Map();
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const key=p=>`${context.trackId}:${p.identity}`;
  const driver=p=>data.drivers.find(d=>d.session_id===context.sessionId&&d.activity===context.activity&&d.identity===p.identity);
  const csrf=()=>document.querySelector('[name=csrfmiddlewaretoken]')?.value||"";
  const state=d=>({online:"Online",delayed:"Verbinding vertraagd",offline:"Offline"}[d.connection_status]||"Offline");
  async function assign(deviceId,driverId){
    const res=await fetch(`/live/api/devices/${encodeURIComponent(deviceId)}/assign/`,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},body:JSON.stringify({driver_id:driverId})});
    const result=await res.json();if(!res.ok)throw Error(result.error||"Koppelen mislukt");
    const d=data.devices.find(d=>d.device_id===deviceId);if(d)d.assigned_driver_id=driverId;
  }
  async function apply(){
    if(applying)return;applying=true;
    try{
      for(const pilot of context.pilots){
        const k=key(pilot),target=driver(pilot);if(!queued.has(k)||!target)continue;
        const desired=queued.get(k),previous=data.devices.filter(d=>d.assigned_driver_id===target.id);
        if(desired)await assign(desired,target.id);
        for(const old of previous)if(old.device_id!==desired)await assign(old.device_id,null);
        queued.delete(k);signature="";message.textContent=desired?`${pilot.name} is gekoppeld aan ${data.devices.find(d=>d.device_id===desired)?.label||desired}.`:`Dashboard voor ${pilot.name} losgekoppeld.`;
      }
    }catch(error){queued.clear();signature="";message.textContent=error.message;}
    finally{applying=false;render();}
  }
  function render(){
    statuses.replaceChildren();
    for(const d of data.devices){const line=el("div",`${d.label}: ${state(d)}${d.receipt_age_ms==null?"":` · heartbeat ${Math.floor(d.receipt_age_ms/1000)}s geleden`}`);line.className=`device-status ${d.connection_status}`;statuses.append(line);}
    if(!data.devices.length)statuses.textContent="Geen dashboard geregistreerd voor je account.";
    if(root.contains(document.activeElement)&&document.activeElement.tagName==="SELECT")return;
    const sig=JSON.stringify([context,data.devices.map(d=>[d.device_id,d.label,d.connection_status,d.assigned_driver_id]),data.drivers,[...queued]]);
    if(signature===sig)return;signature=sig;root.replaceChildren();
    if(!context.pilots.length){root.append(el("p","Kies eerst een piloot uit de lijst hierboven."));return;}
    for(const pilot of context.pilots){
      const row=el("div");row.className="kart-device";row.dataset.identity=pilot.identity;
      row.append(el("strong",`${pilot.name} · kart #${pilot.kart||"—"}`));
      const target=driver(pilot),current=data.devices.find(d=>d.assigned_driver_id===target?.id),k=key(pilot);
      const select=el("select");select.setAttribute("aria-label",`Dashboard voor ${pilot.name}`);
      const none=el("option","Geen dashboard");none.value="";select.append(none);
      for(const d of data.devices){const other=data.drivers.find(p=>p.id===d.assigned_driver_id);const option=el("option",`${d.label} · ${state(d)}${other&&other.id!==target?.id?` · nu bij ${other.name}`:""}`);option.value=d.device_id;option.disabled=(!d.online&&d.device_id!==current?.device_id)||[...queued].some(([other,value])=>other!==k&&value===d.device_id);select.append(option);}
      select.value=queued.has(k)?queued.get(k):(current?.device_id||"");select.disabled=applying;
      const hint=el("small",queued.has(k)?"Gekozen · koppelt bij Start volgsessie of Update piloten.":current?`Gekoppeld aan ${current.label}`:target?"Kies een online dashboard om deze piloot te koppelen.":"Je dashboardkeuze wordt actief bij Start volgsessie.");
      select.addEventListener("change",()=>{queued.set(k,select.value);signature="";select.blur();hint.textContent=target?"Koppeling opslaan…":"Gekozen · koppelt bij Start volgsessie of Update piloten.";if(target)apply();else render();});
      row.append(select,hint);root.append(row);
    }
  }
  async function refresh(){
    if(fetching)return;fetching=true;
    try{const response=await fetch("/live/api/devices/",{credentials:"same-origin",cache:"no-store"});if(!response.ok)throw Error("Dashboards kunnen niet geladen worden.");data=await response.json();render();await apply();}
    catch(error){message.textContent=error.message;}finally{fetching=false;}
  }
  window.addEventListener('coach:dashboard-context',event=>{context=event.detail;const keep=new Set(context.pilots.map(key));for(const k of queued.keys())if(!keep.has(k))queued.delete(k);render();apply();});
  refresh();setInterval(refresh,2000);
})();
