(() => {
  'use strict';
  const $=id=>document.getElementById(id), node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;};
  const duration=ms=>ms==null?'—':`${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;
  const delta=ms=>ms==null?'—':`${ms<0?'-':'+'}${(Math.abs(ms)/1000).toFixed(3)}s`;
  const color=ms=>ms==null?'':ms<=0?'faster':'slower';
  let state=null,tracks=[],template=null,reportRequest=null,reportContext=null;
  async function api(path,data){
    const options={credentials:'same-origin',headers:{Accept:'application/json'}};
    if(data)Object.assign(options,{method:'POST',headers:{...options.headers,'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(data)});
    const response=await fetch('/live/api/'+path,options);
    if(response.redirected)throw Error('Meld je opnieuw aan.');
    const result=await response.json();if(!response.ok)throw Error(result.error || 'Opslaan mislukt.');return result;
  }
  const gainText=ms=>ms==null?'—':`${(ms/1000).toFixed(3)}s`;
  function potential(metric){
    const gain=state?.training?.potentialMs?.[metric];
    const line=node('small',null,'ideal-delta');
    line.append(node('span','Te winnen '),node('b',gainText(gain),gain===0?'purple':''));
    line.title=metric==='lap'?'Eigen beste ronde min ideale ronde (som van beste sectoren)':'Eigen beste sector min de ideale beste sector';
    return line;
  }
  const shadeClass=shade=>({purple:'purple',green:'faster',orange:'slower'}[shade] || '');
  function ownDelta(value){const line=node('small',null,'own-delta');line.append(node('span','Δ eigen '),node('b',delta(value?.deltaMs),shadeClass(value?.color)));return line;}
  function render(){
    const training=state?.activity==='training',driver=state?.drivers[0];
    $('training-dashboard').hidden=!training;$('training-fullscreen').hidden=!training;
    if(!training || !driver)return;
    const live=$('training-live');live.replaceChildren();
    const panel=node('article',null,'panel training-pilot');
    const heading=node('div',null,'training-pilot-heading');heading.append(node('h2',driver.name),node('strong',`Kart #${driver.kart || '—'}`));panel.append(heading);
    const pace=state.training?.paceMs;panel.append(node('p',pace?`Pace ${duration(pace)} · ${state.training.paceLaps} schone ronde${state.training.paceLaps===1?'':'n'}`:'Pace · wachten op schone ronden','muted small'));
    if(!driver.present)panel.append(node('p','Piloot niet aanwezig in de actuele baansessie','warning'));
    const times=node('div',null,'training-times');
    for(const metric of [...(state.track.capabilities.sectorIds || []),'lap']){
      const passage=driver.last.byMetric?.[metric] || (driver.last.metric===metric?driver.last:{}), cell=node('div',null,'training-time');
      const latest=state.training?.ownLatest?.[metric],cls=shadeClass(latest?.color),time=latest?.timeMs ?? passage.timeMs;
      cell.dataset.active=String(!!latest?.active);cell.dataset.color=latest?.color || 'neutral';
      cell.append(node('span',metric==='lap'?'Ronde':metric),node('strong',duration(time),cls),node('b',latest?.deltaMs!=null?delta(latest.deltaMs):(time?'Ref.':'—'),cls+(latest?.deltaMs==null?' ref':'')));
      cell.dataset.phase=latest?.phase || 'unknown';
      cell.append(potential(metric),node('small',`Beste ${duration(state.training?.ownBest?.[metric])}`));
      times.append(cell);
    }
    panel.append(times);
    const potentialPanel=node('section',null,'training-potential');potentialPanel.append(node('h3','Nog te winnen'));
    const stats=node('div',null,'training-potential-stats'),bestLap=state.training?.ownBest?.lap,idealLap=state.training?.ideal?.lap;
    for(const [key,label,value,isTime] of [['ownBest','Eigen beste',bestLap,true],['idealLap','Ideale ronde',idealLap,true],['bestToIdeal','Nog te winnen',state.training?.potentialMs?.lap,false]]){
      const field=node('div');field.dataset.stat=key;field.append(node('span',label),node('strong',isTime?duration(value):gainText(value),!isTime && value===0?'faster':''));stats.append(field);
    }
    potentialPanel.append(stats);panel.append(potentialPanel);live.append(panel);
    const comparison=$('training-comparison');comparison.replaceChildren();
    const metrics=[...(state.track.capabilities.sectorIds || []),'lap'];
    const table=node('table',null,'training-table training-rows-table'),head=node('tr');
    head.append(node('th','Pos. / piloot'));
    for(const metric of [...metrics,'best'])head.append(node('th',metric==='lap'?'Ronde':metric==='best'?'Beste ronde':metric));
    const thead=node('thead');thead.append(head);table.append(thead);const tbody=node('tbody');
    for(const item of state.training?.rows || []){
      const row=node('tr',null,item.selected?'followed-training-row':'');row.dataset.identity=item.identity;row.dataset.lapColor=item.latest.lap?.color || 'neutral';
      const identity=node('th',null,'training-row-pilot');identity.scope='row';
      const label=node('div',null,'training-row-name');label.append(node('strong',item.position?`T${item.position}`:'T—','training-pace-position'),node('span',item.name));
      identity.append(label,node('small',`Kart #${item.kart || '—'}`));row.append(identity);
      for(const metric of metrics){
        const value=item.latest[metric],cell=node('td',null,'training-row-time');cell.dataset.label=metric==='lap'?'Ronde':metric;cell.dataset.phase=value?.phase || 'unknown';
        cell.dataset.active=String(!!value?.active);
        cell.append(node('strong',duration(value?.timeMs),shadeClass(value?.color)),ownDelta(value));
        if(item.selected)cell.append(potential(metric));
        row.append(cell);
      }
      const best=node('td',null,'training-row-best');best.dataset.label='Beste ronde';best.append(node('strong',duration(item.best.lap),item.best.lap===state.track.sessionBests?.lap?'purple':''));if(item.selected)best.append(potential('lap'));row.append(best);tbody.append(row);
    }
    const ideal=node('tr',null,'ideal-training-row'),identity=node('th',null,'training-row-pilot');identity.scope='row';identity.append(node('strong','Ideaal'),node('small','Snelste sectoren samen'));ideal.append(identity);
    for(const metric of metrics){
      const cell=node('td');cell.dataset.label=metric==='lap'?'Ideale ronde':metric;
      cell.append(node('strong',duration(state.training?.ideal?.[metric])));
      if(metric!=='lap')cell.append(node('small',state.track.sessionRecords?.[metric]?.drivers?.map(d=>d.name).join(' · ') || '—'));
      ideal.append(cell);
    }
    const empty=node('td');empty.dataset.label='Beste ronde';empty.append(node('span','—'));ideal.append(empty);tbody.append(ideal);
    table.append(tbody);comparison.append(table);
  }

  function circuitOptions(select){
    const circuits=tracks.filter(t=>t.mode==='live' && !t.slug.startsWith('sim-')),old=select.value,preferred=state?.track.mode==='live'?String(state.track.id):old;
    select.replaceChildren();
    const placeholder=node('option','Kies het circuit');placeholder.value='';select.append(placeholder);
    for(const track of circuits){const option=node('option',track.name);option.value=track.id;select.append(option);}
    select.value=circuits.some(t=>String(t.id)===preferred)?preferred:'';
  }
  window.addEventListener('coach:tracks',event=>{tracks=event.detail;});
  window.addEventListener('coach:snapshot',event=>{state=event.detail;render();});
  $('training-provider')?.addEventListener('change',()=>{$('provider-note').hidden=$('training-provider').value==='apex';$('connect').disabled=$('training-provider').value!=='apex';$('start').disabled=true;});
  const area=document.querySelector('.live-area');
  async function leaveFullscreen(){document.body.classList.remove('training-fullscreen');$('training-fullscreen').textContent='Fullscreen training';if(document.fullscreenElement)await document.exitFullscreen();}
  async function enterFullscreen(){
    document.body.classList.add('training-fullscreen');$('training-fullscreen').textContent='Verlaat fullscreen';
    try{await area.requestFullscreen?.();}catch{/* Fixed viewport fallback remains available. */}
  }
  $('training-fullscreen').addEventListener('click',async()=>{if(document.body.classList.contains('training-fullscreen'))await leaveFullscreen();else await enterFullscreen();});
  document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement){document.body.classList.remove('training-fullscreen');$('training-fullscreen').textContent='Fullscreen training';}});
  document.addEventListener('keydown',event=>{if(event.key==='Escape' && !document.fullscreenElement)leaveFullscreen();});
  for(const button of document.querySelectorAll('.close-dialog'))button.addEventListener('click',()=>button.closest('dialog').close());
  $('new-kart-report').addEventListener('click',async()=>{
    if(!state?.drivers.length)return;
    try{
      if(!template)template=(await api('kart-reports/')).template;
      reportContext={sessionId:state.id,driverId:state.drivers[0].id};reportRequest=crypto.randomUUID();
      $('kart-report-form').reset();$('report-status').textContent='';$('report-pilot').textContent=state.drivers[0].name;
      circuitOptions($('report-circuit'));
      $('report-kart').replaceChildren();for(const kart of state.training?.karts || [state.drivers[0].kart]){const option=node('option',`#${kart}`);option.value=kart;$('report-kart').append(option);}
      $('report-kart').value=state.drivers[0].kart;
      $('report-scores').replaceChildren();
      for(const item of template.elements){const label=node('label',item.label),select=node('select');select.dataset.score=item.id;select.setAttribute('aria-label',item.label);const empty=node('option','—');empty.value='';select.append(empty);for(let n=1;n<=5;n++){const option=node('option',String(n));option.value=n;select.append(option);}label.append(select);$('report-scores').append(label);}
      $('kart-dialog').showModal();
    }catch(e){$('error').hidden=false;$('error').textContent=e.message;}
  });
  $('kart-report-form').addEventListener('submit',async event=>{
    event.preventDefault();const scores={};for(const input of $('report-scores').querySelectorAll('select'))if(input.value)scores[input.dataset.score]=Number(input.value);
    if(!Object.keys(scores).length){$('report-status').textContent='Geef minstens één score.';return;}
    $('save-kart-report').disabled=true;
    try{
      await api(`sessions/${reportContext.sessionId}/kart-reports/`,{requestId:reportRequest,driverId:reportContext.driverId,trackId:Number($('report-circuit').value),kart:$('report-kart').value,conditions:$('report-conditions').value,scores,notes:$('report-notes').value});
      $('report-status').textContent='Verslag bewaard.';$('save-kart-report').textContent='Bewaard';
    }catch(e){$('report-status').textContent=e.message;$('save-kart-report').disabled=false;}
  });
  $('kart-dialog').addEventListener('close',()=>{$('save-kart-report').disabled=false;$('save-kart-report').textContent='Verslag bewaren';});
  async function findReports(){
    const list=$('kart-report-list');list.replaceChildren(node('p','Verslagen laden…','muted'));
    try{
      const params=new URLSearchParams();if($('library-circuit').value)params.set('trackId',$('library-circuit').value);if($('library-kart').value.trim())params.set('kart',$('library-kart').value.trim());
      const data=await api('kart-reports/?'+params);template=data.template;list.replaceChildren();
      for(const report of data.reports){
        const card=node('article',null,'kart-report');card.append(node('h3',`Kart #${report.kart} · ${report.track}`),node('p',`${report.pilot} · ${new Date(report.createdAt).toLocaleString('nl-BE')} · ${{dry:'Droog',damp:'Vochtig',wet:'Nat'}[report.conditions]}`,'muted small'));
        const scores=node('div',null,'saved-scores');for(const item of report.template.elements){if(report.scores[item.id]!=null)scores.append(node('span',`${item.label}: ${report.scores[item.id]}/5`));}card.append(scores);
        if(Object.keys(report.timing).length)card.append(node('p',Object.entries(report.timing).map(([metric,value])=>`${metric==='lap'?'Ronde':metric} ${duration(value)}`).join(' · '),'small'));
        card.append(node('p',report.notes),node('small',report.sessionName,'muted'));list.append(card);
      }
      if(!data.reports.length)list.append(node('p','Nog geen kartverslagen voor deze selectie.','muted'));
    }catch(e){list.replaceChildren(node('p',e.message,'warning'));}
  }
  $('open-kart-library').addEventListener('click',async()=>{
    if(document.body.classList.contains('training-fullscreen'))await leaveFullscreen();
    $('kart-library').showModal();$('kart-report-list').replaceChildren(node('p','Verslagen laden…','muted'));
    try{if(!tracks.length)tracks=(await api('')).tracks;circuitOptions($('library-circuit'));await findReports();}
    catch(e){$('kart-report-list').replaceChildren(node('p',e.message,'warning'));}
  });
  $('find-kart-reports').addEventListener('click',findReports);
})();
