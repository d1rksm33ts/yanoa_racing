(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const emptyFeedback = $('driver-cards').firstElementChild.cloneNode(true);
  let tracks = [], recordings = [], simulations = [], activeFollowSessions = [], selected = [], session = null, stream = null, connected = false, busy = false, replayTrackId = null;
  const node = (tag, content, cls) => { const el = document.createElement(tag); if (content !== undefined) el.textContent = content; if (cls) el.className = cls; return el; };
  const currentTrack = () => tracks.find(t => replayTrackId !== null ? t.id === replayTrackId : String(t.id) === $('track').value);
  const openInfo = new Set();
  function info(key, label, content) {
    const details=node('details',undefined,'info'), summary=node('summary','ⓘ');
    summary.setAttribute('aria-label',label);details.append(summary,node('div',content,'info-content'));
    details.open=openInfo.has(key);
    details.addEventListener('toggle',()=>{if(details.open)openInfo.add(key);else openInfo.delete(key);});
    return details;
  }
  const error = message => { $('error').textContent = message; $('error').hidden = !message; };
  async function api(path, data) {
    const options = {credentials:'same-origin', headers:{'Accept':'application/json'}};
    if (data) Object.assign(options, {method:'POST', headers:{...options.headers, 'Content-Type':'application/json', 'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value}, body:JSON.stringify(data)});
    const response = await fetch('/live/api/' + path, options);
    if (response.redirected) throw new Error('Je sessie is verlopen. Meld je opnieuw aan.');
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.error || 'De server kon de aanvraag niet uitvoeren.'); }
    return response.json();
  }
  const duration = ms => ms == null ? '—' : `${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;
  const timingClass = value => ({purple:'purple',green:'faster',orange:'slower'}[value?.color] || (value?.deltaMs < 0 ? 'faster' : value?.deltaMs > 0 ? 'slower' : ''));
  const rank = value => value.best === value.worst ? `P${value.best}` : `P${value.best}–P${value.worst}`;
  const age = value => value ? Math.max(0, Math.floor((Date.now()-Date.parse(value))/1000)) : null;
  function updateStart() {
    const track = currentTrack();
    for (const input of $('pilots').querySelectorAll('input')) input.disabled = busy;
    for (const input of $('driver-cards').querySelectorAll('.driver-pit-control input')) input.disabled = busy || session?.state !== 'active';
    for (const button of $('active-sessions').querySelectorAll('button')) button.disabled = busy;
    $('connect').textContent = busy ? 'Bezig…' : currentSimulation() ? 'Simulatie geladen' : track?.subscribed ? 'Verbinding verbreken' : 'Verbinden';
    $('connect').disabled = busy || !track || !!currentSimulation();
    $('pilot-count').textContent = `${selected.length} gekozen`;
    $('start').disabled = busy || !selected.length || !track?.subscribed || !track.workerActive || track.connection !== 'connected' || !track.capabilities.laps;
    const editing = session?.state === 'active' && session.track.id === track?.id;
    const current = session?.drivers.map(d => d.identity) || [];
    const changed = selected.length !== current.length || selected.some(id => !current.includes(id)) || selected[0] !== current[0];
    $('start').hidden = editing;
    $('update-pilots').hidden = !editing;
    $('update-pilots').disabled = busy || !selected.length || !changed;
    $('selection-status').textContent = editing ? changed ? 'Selectie gewijzigd' : '' : '';
    showSimulation();
  }
  function showTrack() {
    const track = currentTrack();
    if (!track) return;
    const present = new Set(track.entrants.map(e => e.identity));
    selected = selected.filter(id => present.has(id));
    $('source-status').textContent = !track.subscribed ? 'Niet verbonden · druk op Verbinden' : !track.workerActive ? 'Baanfeed niet beschikbaar · probeer later opnieuw' : track.connection === 'reconnecting' ? 'Opnieuw verbinden met de baanfeed…' : track.connection !== 'connected' ? 'Verbinden · wachten op de baanfeed…' : !track.capabilities.laps ? 'Verbonden · wachten op timingdata' : track.mode === 'replay' ? 'Simulatie verbonden · opgenomen timing' : 'Verbonden · rondefeedback beschikbaar';
    const seconds = age(track.timingAt);
    $('track-session').textContent = [track.title, seconds == null ? 'Nog geen timingtabel ontvangen' : `Laatste timingupdate ${seconds}s geleden`, track.mode === 'replay' ? 'REPLAY · geen live baan' : ''].filter(Boolean).join(' · ');
    const list = $('pilots');
    // Preserve checkbox focus during automatic status refreshes.
    const signature = JSON.stringify(track.entrants);
    if (list.dataset.signature !== signature) {
      list.dataset.signature = signature;
      list.replaceChildren();
      for (const entrant of track.entrants) {
        const label = node('label', undefined, 'pilot-option'), input = node('input');
        input.type = 'checkbox'; input.value = entrant.identity; input.checked = selected.includes(entrant.identity);
        input.addEventListener('change', () => {
          if (input.checked && selected.length >= 12) { input.checked = false; error('Selecteer maximaal 12 piloten.'); return; }
          selected = input.checked ? [...selected, input.value] : selected.filter(id => id !== input.value);
          updateStart();
          showStandings();
        });
        label.append(input, node('span', entrant.name), node('span', `#${entrant.kart || '—'}`, 'kart')); list.append(label);
      }
      if (!track.entrants.length) list.append(node('p','Nog geen actuele deelnemerslijst.','muted small'));
    }
    updateStart();
    showSimulation();
    showStandings();
  }
  function drawSession(state) {
    if (session?.id === state.id) {
      const identities = new Map(session.drivers.map(old => [old.identity,state.drivers.find(d => d.id === old.id)?.identity || old.identity]));
      selected = selected.map(identity => identities.get(identity) || identity);
    }
    session = state;
    if (state.simulation) simulations = [...simulations.filter(s => s.id !== state.simulation.id), state.simulation];
    document.body.classList.add('has-session');
    $('active-name').textContent = state.name;
    $('session-badge').textContent = state.state === 'active' ? (state.track.mode === 'replay' ? 'REPLAY' : 'ACTIEF') : 'BEWAARD';
    $('session-badge').className = 'badge' + (state.state === 'active' ? ' active' : '');
    $('session-controls').hidden = false;
    $('pit-settings-panel').hidden = false;
    if (!$('pit-settings-form').contains(document.activeElement) && !document.querySelector('#pit-settings-form [data-dirty]')) {
      $('pit-duration').value = state.pitSettings.durationSeconds;
      $('pit-stops').value = state.pitSettings.requiredStops;
      $('pit-net-loss').value = state.pitSettings.netLossSeconds ?? '';
    }
    $('pit-settings-save').disabled = state.state !== 'active' || busy;
    $('stop').hidden = $('discard').hidden = $('reset').hidden = state.state !== 'active';
    $('export').href = `/live/api/sessions/${state.id}/export/`;
    updateConnection();
    const records=$('session-records');records.replaceChildren();
    for(const metric of ['lap',...(state.track.capabilities.sectorIds || [])]) {
      const record=state.track.sessionRecords?.[metric],cell=node('div',undefined,'session-record');
      cell.append(node('span',metric==='lap'?'Ronde':metric),node('strong',duration(record?.timeMs),'purple'),node('small',record?.drivers?.map(d=>d.name).join(' · ') || '—'));
      records.append(cell);
    }
    $('session-record-panel').hidden=false;
    const cards = $('driver-cards'); cards.replaceChildren();
    for (const driver of state.drivers) {
      const card = node('article', undefined, 'panel driver-card' + (!driver.present && state.state === 'active' ? ' stale' : ''));
      card.dataset.driverId=driver.id;
      const top = node('div', undefined, 'driver-top');
      const identity=node('div',undefined,'driver-identity'), positions=node('div',undefined,'position-stack');
      identity.append(node('h3',driver.name));
      positions.append(node('strong', `P${driver.position ?? '—'}`, 'driver-position'));
      if(driver.pitEnabled) {
        const projected=node('div',undefined,'projected-position');projected.append(node('small','Na stops'),node('strong',driver.pit?.expectedCorrectedPosition ? `≈P${driver.pit.expectedCorrectedPosition}` : driver.pit?.correctedPosition ? `≈${rank(driver.pit.correctedPosition)}` : '—'));positions.append(projected);
        const finish=node('div',undefined,'finish-position');finish.append(node('small','Einde'),node('strong',driver.pit?.expectedEndPosition ? `≈P${driver.pit.expectedEndPosition}` : driver.pit?.endPosition ? `≈${rank(driver.pit.endPosition)}` : '—'));positions.append(finish);
      }
      top.append(identity,positions);
      const karts=node('div',undefined,'driver-karts');
      karts.append(node('strong',`Kart #${driver.kart || '—'}`));
      for(const old of [...(driver.kartHistory || [])].reverse()) {
        const label=node('span',`← #${old.kart}`,'previous-kart');
        if(old.best?.lap)label.append(node('small',duration(old.best.lap)));
        karts.append(label);
      }
      identity.append(karts);
      if(driver.lastPitMs!=null)identity.append(node('div',`Pit uit ${(driver.lastPitMs/1000).toFixed(3)}s`,'pit-exit'));
      card.append(top);
      if (driver.finished) card.append(node('div','🏁 FINISH','driver-finish'));
      if (!driver.present && state.state === 'active') card.append(node('p','Niet meer in deze baansessie','warning'));
      const last = driver.last;
      card.append(node('div', last.metric === 'lap' ? `${last.lapCountKnown ? 'Ronde' : 'Waargenomen passage'} ${last.lap}` : last.metric ? `${last.metric} · ${last.lapCountKnown ? 'ronde' : 'passage'} ${last.lap}` : 'Wacht op passage', 'metric'));
      const seconds = age(last.receivedAt);
      const ageLabel = node('div', seconds == null ? '—' : `${seconds}s${last.gap ? ' · ontbrekende rondes' : ''}`, 'small muted');
      if (last.receivedAt) { ageLabel.dataset.receivedAt = last.receivedAt; ageLabel.dataset.gap = last.gap ? 'yes' : ''; }
      card.append(ageLabel);
      const details = node('div', undefined, 'driver-detail');
      const lastLap = last.byMetric?.lap || (last.metric === 'lap' ? last : {});
      for (const [title, value] of [['Laatste ronde', lastLap.timeMs], ['Beste ronde', driver.best.lap]]) {
        const field = node('div'); field.append(node('span',title), node('strong',duration(value),title==='Laatste ronde'?timingClass(lastLap):driver.bestColors?.lap==='purple'?'purple':'')); details.append(field);
      }
      const lapDelta = node('div',undefined,'lap-delta');
      lapDelta.append(node('span','Ronde Δ'),node('strong',lastLap.deltaText || (lastLap.pitLap ? 'Pitronde' : lastLap.timeMs ? 'Ref.' : '—'),timingClass(lastLap)));
      details.append(lapDelta);card.append(details);
      if (state.track.capabilities.sectors) {
        const sectors = node('div', undefined, 'sector-strip');
        sectors.style.gridTemplateColumns = `repeat(${(state.track.capabilities.sectorIds || ['S1','S2','S3']).length},minmax(0,1fr))`;
        for (const metric of (state.track.capabilities.sectorIds || ['S1','S2','S3'])) {
          const passage = last.byMetric?.[metric], cell = node('div');
          cell.append(node('span', metric), node('strong', duration(passage?.timeMs),timingClass(passage)), node('small', passage?.deltaText || (passage ? 'Ref.' : '—'), 'sector-delta '+timingClass(passage)));
          const best=node('div',undefined,'sector-best');best.append(node('span','Beste'),node('b',duration(driver.best[metric]),driver.bestColors?.[metric]==='purple'?'purple':''));cell.append(best);
          sectors.append(cell);
        }
        card.append(sectors);
      }
      const pitControl=node('div',undefined,'driver-pit-control'), pitLabel=node('label'), pitToggle=node('input');
      pitToggle.type='checkbox';pitToggle.checked=driver.pitEnabled;pitToggle.disabled=state.state!=='active' || busy;
      pitToggle.addEventListener('change',()=>action('driver-pit',{driverId:driver.id,enabled:pitToggle.checked}));
      pitLabel.append(pitToggle,node('span','Pitvoorspelling'));pitControl.append(pitLabel);
      pitControl.append(info(`pit-${driver.id}`,'Uitleg pitvoorspelling',[
        driver.pit?.message,driver.pit?.basis,driver.pit?.strategy,
        'Tempo is de mediaan van de recente schone rondes. Het advies is gebaseerd op volhouden van het tempo, niet op één uitzonderlijk snelle ronde.',
        driver.pit?.correctedPosition ? `Na stops: bereik ${rank(driver.pit.correctedPosition)}.` : '',
        driver.pit?.endPosition ? `Einde: bereik ${rank(driver.pit.endPosition)}. De enkele positie gebruikt het gemiddelde aangenomen tempo en pitverlies; de range toont onzekerheid.` : '',
        driver.pit?.horizonLaps ? `Raming tot finish: ${driver.pit.horizonLaps.min}–${driver.pit.horizonLaps.max} ronden volgens de APEX-raceklok/rondeteller.` : '',
        driver.pit?.paceProvisional ? 'Tempo voorlopig: minder dan 3 schone ronden met deze kart. Voor de positie wordt het vorige karttempo of de beschikbare nieuwe rondetijd gebruikt met ruimere marges.' : '',
        driver.pit?.coaching?.limitedData ? 'Sommige achterstanden of tempi zijn onbekend/voorlopig. Een tempo-instructie is een voorwaardelijke raming, geen garantie.' : '',
        driver.pit?.trendText ? `Baantrend ${driver.pit.trendText} · ${driver.pit.trendDrivers} rijders` : '',
        'Nu pitten: tijdelijke positie. Na stops: met de nog verplichte stops van andere rijders. Een range geeft onzekerheid aan. Pitduur loopt van ingang tot uitgang. Baantrend is een aanwijzing; weer, verkeer en tempo van een andere kart worden niet voorspeld.'
      ].filter(Boolean).join('\n\n')));
      card.append(pitControl);
      if (driver.pitEnabled && driver.pit) {
        card.append(pitCard(driver.pit));
        if(driver.pit.coaching) {
          const coach=driver.pit.coaching,box=node('div',undefined,'pace-advice'+(coach.neededGainMs>0?' slower':''));
          box.append(node('strong',coach.text));
          if(coach.neededGainMs>0 && coach.targetLapMs>0)box.append(node('span',`Tempo ${duration(driver.pit.paceMs)} · doel ${duration(coach.targetLapMs)}`));
          const threat=coach.threats?.[0];
          if(threat)box.append(node('span',threat.catchLaps!=null && threat.endMarginMs<=0 ? `${threat.name}: ${threat.remainingStops?'na pit ':''}aansluiting in ≈${threat.catchLaps} ronden` : `${threat.name}: na stops ≈${(threat.marginAfterStopsMs/1000).toFixed(1)}s`));
          card.append(box);
        }
      }
      if (state.state === 'active') {
        const reset = node('button','Reset','button secondary'); reset.type = 'button';
        reset.addEventListener('click', () => resetReferences(driver)); card.append(reset);
      }
      cards.append(card);
    }
    const history = $('history'); history.replaceChildren();
    for (const event of [...state.events].reverse()) {
      const item = node('li'); item.append(node('span',event.payload.name || 'Sessie'), node('strong',event.payload.message || event.kind)); history.append(item);
    }
    showSimulation();
    updateStart();
    showStandings();
  }
  function showComments() {
    const track=session?.track || currentTrack(), panel=$('race-comments-panel');
    panel.hidden=!track;
    const comments=track?.comments || [],list=$('race-comments'),signature=JSON.stringify([track?.id,comments]);
    if(list.dataset.signature===signature)return;
    list.dataset.signature=signature;list.replaceChildren();
    $('race-comment-count').textContent=`(${comments.length})`;
    const labels={penalty:'Penalty',warning:'Waarschuwing',chequered:'Finish',green:'Start',msg:'Info'};
    for(const comment of comments){
      const row=node('li'),head=node('div',undefined,'comment-meta');
      head.append(node('time',comment.time),node('span',labels[comment.kind] || 'Info','comment-kind'+(comment.kind==='penalty'?' slower':'')));
      if(comment.kart)head.append(node('strong',`#${comment.kart}`));
      row.append(head,node('div',comment.message));list.append(row);
    }
    if(!comments.length)list.append(node('li','Nog geen officiële meldingen.','muted'));
  }
  function showRaceClock() {
    showComments();
    const track=session?.track || currentTrack();
    $('race-clock-panel').hidden=!track;
    if(!track)return;
    $('race-title').textContent=track.title || track.name;
    const race=track.race || {}, running=session?.state!=='saved' && (!session || session.state==='active');
    const elapsed=running && (!session || connected) && race.rate ? Math.max(0,Date.now()-Date.parse(race.asOf))*race.rate : 0;
    const ms=race.remainingMs==null?null:Math.max(0,race.remainingMs-elapsed);
    const seconds=ms==null?null:Math.ceil(ms/1000);
    $('race-clock').textContent=race.finished?'🏁 FINISH':seconds!=null?`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`:race.currentLap!=null && race.totalLaps?`${race.currentLap}/${race.totalLaps}`:race.remainingLaps!=null?`${race.remainingLaps} ronden`:'—';
    $('race-clock-label').textContent=race.finished?'Sessie afgelopen':!connected && session?.state==='active'?'Laatste stand':track.mode==='replay' && race.rate===0 && !race.finished?'Gepauzeerd':ms===0?'Wachten op finish':race.remainingMs==null && race.remainingLaps==null?'Geen klok beschikbaar':race.currentLap!=null && race.totalLaps?'Ronde':'Resterend';
  }
  function updateConnection() {
    showRaceClock();
    if (!session) return;
    for (const label of document.querySelectorAll('[data-received-at]')) {
      label.textContent = `${age(label.dataset.receivedAt)}s${label.dataset.gap ? ' · ontbrekende rondes' : ''}`;
    }
    const status = $('live-status');
    if (session.state !== 'active') { status.textContent = 'Gestopt en bewaard'; return; }
    if (session.simulation?.state === 'finished') { status.textContent = 'Simulatie afgelopen'; return; }
    if (session.simulation?.state === 'paused') { status.textContent = 'Simulatie gepauzeerd'; return; }
    if (session.track.finished) { status.textContent = '🏁 Finish'; return; }
    if (!connected) { status.textContent = 'Verbinding onderbroken'; return; }
    if (!session.track.workerActive || session.track.connection !== 'connected') { status.textContent = 'Baanfeed niet verbonden'; return; }
    const seconds = age(session.track.timingAt);
    status.textContent = `Live verbonden · ${seconds == null ? 'wachten op timingdata' : `laatste timingupdate ${seconds}s geleden`}`;
  }
  function follow(state) {
    $('active-sessions-details').open = false;
    if (stream) stream.close();
    connected = false;
    if (tracks.some(t => t.id === state.track.id)) {
      replayTrackId=state.track.mode==='replay'?state.track.id:null;
      $('track').value = replayTrackId===null?String(state.track.id):'';
      selected = state.drivers.map(d => d.identity);
      delete $('pilots').dataset.signature;
      showTrack();
    }
    drawSession(state);
    stream = new EventSource(`/live/api/sessions/${state.id}/events/`);
    stream.addEventListener('snapshot', event => { connected = true; drawSession(JSON.parse(event.data)); });
    stream.addEventListener('revoked', () => { stream.close(); connected = false; error('Je toegang is verlopen. Meld je opnieuw aan.'); updateConnection(); });
    stream.onerror = () => { connected = false; updateConnection(); };
  }
  async function refresh() {
    const data = await api(''); tracks = data.tracks; recordings = data.recordings || []; simulations = data.simulations || [];
    activeFollowSessions=data.activeSessions || [];
    showActiveSessions(activeFollowSessions);
    showRecordings();
    showActiveSimulations();
    const select = $('track'), old = select.value;
    const circuits=tracks.filter(t=>t.mode!=='replay');
    if (JSON.stringify(circuits.map(t=>[t.id,t.name])) !== select.dataset.signature) {
      select.dataset.signature = JSON.stringify(circuits.map(t=>[t.id,t.name])); select.replaceChildren();
      const placeholder=node('option','Kies een circuit');placeholder.value='';placeholder.disabled=true;select.append(placeholder);
      for (const track of circuits) { const option = node('option',track.name); option.value = track.id; select.append(option); }
      select.value=replayTrackId!==null?'':circuits.some(t=>String(t.id)===old)?old:String(circuits[0]?.id || '');
    }
    if(session){const latest=tracks.find(t=>t.id===session.track.id);if(latest)session.track=latest;}
    showTrack();showRaceClock();
    const list = $('sessions'); list.replaceChildren();
    for (const saved of data.sessions) {
      const button = node('button',undefined,'saved-session'); button.type='button';
      button.append(node('strong',saved.name), node('span',`${saved.track} · ${saved.state === 'active' ? 'actief' : 'bewaard'}`));
      button.addEventListener('click', () => api(`sessions/${saved.id}/`).then(follow).catch(e=>error(e.message))); list.append(button);
    }
    if (!data.sessions.length) list.append(node('p','Je eerste volgsessie verschijnt hier.','muted'));
  }
  function showActiveSessions(items) {
    $('active-sessions-panel').hidden = !items.length;
    $('active-session-count').textContent = `${items.length} / 5`;
    const list = $('active-sessions'); list.replaceChildren();
    for (const saved of items) {
      const row=node('article',undefined,'active-session-row');row.dataset.sessionId=saved.id;
      const info=node('div');info.append(node('strong',saved.name));
      const started=new Intl.DateTimeFormat('nl-BE',{timeZone:'Europe/Brussels',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(saved.startedAt));
      info.append(node('small',`${saved.track} · ${started} · ${saved.drivers.join(', ') || 'Geen piloten'}`));
      const controls=node('div',undefined,'active-session-controls');
      const open=node('button','Bekijken','button secondary');open.type='button';open.disabled=busy;
      open.addEventListener('click',()=>api(`sessions/${saved.id}/`).then(follow).catch(e=>error(e.message)));
      const stop=node('button','Stop & bewaar','button');stop.type='button';stop.disabled=busy;
      stop.addEventListener('click',async()=>{
        if(busy)return;busy=true;updateStart();error('');
        try {
          const state=await api(`sessions/${saved.id}/action/`,{action:'stop',requestId:crypto.randomUUID()});
          if(session?.id===saved.id)drawSession(state);
          await refresh();
        }catch(e){error(e.message);}finally{busy=false;updateStart();}
      });
      const discard=node('button','Stop zonder bewaren','button danger');discard.type='button';discard.disabled=busy;
      discard.addEventListener('click',()=>discardSession(saved.id,saved.name));
      controls.append(open,stop,discard);row.append(info,controls);list.append(row);
    }
  }
  async function discardSession(identity,name) {
    if(busy || !confirm(`Stop zonder bewaren? De volgsessie “${name}” en haar tijden worden verwijderd. Dit kan niet ongedaan worden gemaakt.`))return;
    busy=true;updateStart();error('');
    const current=session?.id===identity;
    if(current && stream){stream.close();stream=null;connected=false;}
    try {
      await api(`sessions/${identity}/discard/`,{});
      if(current){
        session=null;document.body.classList.remove('has-session');
        $('driver-cards').replaceChildren(emptyFeedback.cloneNode(true));$('session-record-panel').hidden=true;
        $('active-name').textContent='Klaar voor de start';$('session-badge').textContent='STAND-BY';$('session-badge').className='badge';
        $('session-controls').hidden=true;$('finish-banner').hidden=true;$('pit-settings-panel').hidden=true;
        $('live-status').textContent='Volgsessie verwijderd. Kies piloten om opnieuw te volgen.';
        $('history').replaceChildren(node('li','Geen bewaarde feedback voor de verwijderde sessie.','muted'));
        $('active-sessions-details').open=true;
      }
      await refresh();
    }catch(e){
      error(e.message);
      if(current)try{follow(await api(`sessions/${identity}/`));}catch(_){}
    }finally{busy=false;updateStart();showStandings();}
  }
  function showRecordings() {
    const picker = $('recording'), old = picker.value;
    const signature = JSON.stringify(recordings);
    if (picker.dataset.signature === signature) return;
    picker.dataset.signature = signature; picker.replaceChildren();
    for (const recording of recordings) { const option = node('option', recording.name); option.value = recording.id; picker.append(option); }
    if (recordings.some(r => String(r.id) === old)) picker.value = old;
    if (!recordings.length) picker.append(node('option', 'Nog geen opnames beschikbaar'));
    showSegments();
  }
  function showSegments() {
    const recording = recordings.find(r => String(r.id) === $('recording').value);
    const picker = $('recording-segment');
    const previous = picker.dataset.recording === $('recording').value ? picker.value : null;
    picker.dataset.recording = $('recording').value;
    picker.replaceChildren();
    for (const segment of recording?.segments || []) {
      const option = node('option', `${segment.title} · ${Math.round(segment.durationMs / 60000)} min${segment.drivers.some(n => /noah/i.test(n)) ? ' · Noah' : ''}`);
      option.value = segment.index; $('recording-segment').append(option);
    }
    if (previous !== null && [...picker.options].some(option => option.value === previous)) picker.value = previous;
    $('load-simulation').disabled = busy || !recording?.segments.length;
  }
  function showActiveSimulations() {
    const list = $('active-simulations'); list.replaceChildren();
    const active = simulations.filter(sim => ['paused','playing'].includes(sim.state));
    if (!active.length) return;
    list.append(node('p',`Actieve simulaties: ${active.length} / 3`,'small muted'));
    for (const sim of active) {
      const row = node('div',undefined,'simulation-list-row');
      row.append(node('strong',sim.title),node('small',`${sim.recording} · ${sim.state === 'paused' ? 'gepauzeerd' : 'speelt af'}`,'muted'));
      const open=node('button','Open simulatie','button secondary');open.type='button';open.disabled=busy;
      open.addEventListener('click',async()=>{
        if(busy)return;
        const existing=activeFollowSessions.find(item=>item.trackId===sim.trackId);
        if(existing){try{follow(await api(`sessions/${existing.id}/`));}catch(e){error(e.message);}return;}
        replayTrackId=sim.trackId;$('track').value='';selected=[];delete $('pilots').dataset.signature;showTrack();
      });
      row.append(open);
      const button = node('button','Stop deze simulatie','button secondary'); button.type='button';button.disabled=busy;
      button.addEventListener('click',async()=>{
        if(busy)return;busy=true;showActiveSimulations();error('');
        try {
          await api(`simulations/${sim.id}/action/`,{action:'stop'});
          if(session?.track.id===sim.trackId)drawSession(await api(`sessions/${session.id}/`));
          await refresh();
        }catch(e){error(e.message);}finally{busy=false;showActiveSimulations();updateStart();}
      });
      row.append(button);list.append(row);
    }
  }
  function currentSimulation() { return simulations.find(s => s.trackId === currentTrack()?.id); }
  function showStandings() {
    const track = session?.track || currentTrack();
    const rows = track?.standings || [], following = session?.drivers || [];
    const focus = new Map(following.map(d => [d.identity,d]));
    if (!session) for (const id of selected) focus.set(id,{});
    $('finish-banner').hidden = !track?.finished;
    const seconds = age(track?.timingAt);
    $('standings-status').textContent = !track ? 'Verbind met een baan om de actuele stand te zien.' : `${track.name} · ${track.title || 'wachten op timing'} · ${rows.length} rijders${track.finished ? ' · 🏁 FINISH' : ''}${!track.workerActive || !['connected','finished'].includes(track.connection) ? ' · bron niet verbonden, laatste bekende stand' : ''}${seconds == null ? '' : ` · update ${seconds}s geleden`}${session?.state === 'stopped' ? ' · opvolging gestopt; deltas worden niet meer bijgewerkt' : ''}`;
    const body = $('standings'); body.replaceChildren();
    for (const row of rows) {
      const driver = focus.get(row.identity), chosen = focus.has(row.identity);
      if ($('only-selected').checked && !chosen) continue;
      const tr = node('article',undefined,'standing-row'+(chosen?' selected-driver':'')); tr.dataset.identity=row.identity;
      const name=node('div',undefined,'standing-name');
      name.append(node('strong',`${row.position || '—'}. ${row.name}`),node('small',`#${row.kart || '—'}${chosen?' · GEVOLGD':''}${row.inPit?' · IN PIT':''}${row.finished?' · 🏁 FINISH':''}`));tr.append(name);
      const times=node('div',undefined,'standing-times');
      const field=(label,value,feedback)=>{const cell=node('div');cell.append(node('span',label),node('strong',value,timingClass(feedback)));if(feedback)cell.append(node('small',feedback.deltaText || (feedback.pitLap?'Pitronde':'Ref.'),timingClass(feedback)));times.append(cell);};
      for (const metric of (track.capabilities.sectorIds || ['S1','S2','S3'])) {
        const passage=driver?.last?.byMetric?.[metric];field(metric,duration(passage?.timeMs ?? row.sectors?.[metric]),passage);
      }
      const lap=driver?.last?.byMetric?.lap;
      field('Ronde',duration(lap?.timeMs ?? row.lastLapMs),lap);
      field('Beste',duration(driver?.best?.lap ?? row.bestLapMs));
      field('Ronden',row.laps == null ? (row.observedPassages ? `${row.observedPassages}*`:'—') : String(row.laps));
      tr.append(times);body.append(tr);
    }
    if(!body.children.length)body.append(node('p',rows.length?'Geen geselecteerde piloten in deze stand.':'Nog geen baanstand beschikbaar.','muted small'));
  }
  function pitCard(pit) {
    const box=node('div',undefined,'pit-card');
    const field=(label,value)=>{const cell=node('div');cell.append(node('span',label),node('strong',value));box.append(cell);};
    if(pit.inPit)field('IN PIT',`${(pit.pitRemainingMs/1000).toFixed(1)}s resterend`);
    if(pit.temporaryPosition)field('Nu pitten',rank(pit.temporaryPosition));

    if(pit.lossMinMs!=null)field('Netto verlies',pit.lossMinMs===pit.lossMaxMs?`${(pit.lossMinMs/1000).toFixed(1)}s`:`${(pit.lossMinMs/1000).toFixed(1)}–${(pit.lossMaxMs/1000).toFixed(1)}s`);
    if(!pit.inPit && !pit.temporaryPosition) {
      const labels={disabled:'Geen verplichte stop',uncalibrated:'Wacht op pitdata',complete:'Stops voltooid','unknown-gap':'Achterstand onbekend',finished:'Finish'};
      box.append(node('span',labels[pit.status] || 'Geen voorspelling','small muted'));
    }
    return box;
  }

  function showSimulation() {
    const sim = currentSimulation(); $('simulation-panel').hidden = !sim;
    if (!sim) return;
    $('simulation-title').textContent = `${sim.recording} · ${sim.title}`;
    const labels = {paused:'Gepauzeerd',playing:'Speelt af',finished:'Afgelopen',stopped:'Gestopt',error:'Fout'};
    const clock = ms => `${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}`;
    $('simulation-status').textContent = `${labels[sim.state] || sim.state} · ${clock(sim.positionMs)} / ${clock(sim.durationMs)} · ${sim.speed}×${sim.error ? ' · '+sim.error : ''}`;
    $('simulation-progress').max = sim.durationMs || 1; $('simulation-progress').value = sim.positionMs;
    $('sim-play').disabled = busy || sim.state !== 'paused' || session?.state !== 'active' || session?.track.id !== sim.trackId;
    $('sim-pause').disabled = busy || sim.state !== 'playing';
    $('sim-restart').disabled = busy;
    $('sim-stop').disabled = busy || ['stopped','finished','error'].includes(sim.state);
    $('sim-speed').disabled = busy || !['paused','playing'].includes(sim.state);
    if (document.activeElement !== $('sim-speed')) $('sim-speed').value = String(sim.speed);
  }
  async function simulationAction(action, extra={}) {
    const sim = currentSimulation(); if (!sim || busy) return;
    busy=true;showSimulation();error('');
    try {
      const result = await api(`simulations/${sim.id}/action/`, {action,...extra});
      simulations = simulations.map(s => s.id === result.id ? result : s);
      if (session?.track.id === sim.trackId) drawSession(await api(`sessions/${session.id}/`));
      await refresh();
    } catch(e) { error(e.message); }
    finally { busy=false;showSimulation();updateStart(); }
  }
  async function action(kind, extra={}) {
    if (!session || busy) return;
    busy=true; updateStart(); error('');
    try { drawSession(await api(`sessions/${session.id}/action/`, {action:kind,requestId:crypto.randomUUID(),...extra})); await refresh(); }
    catch(e) { error(e.message); }
    finally { busy=false; updateStart(); }
  }
  function resetReferences(driver) {
    if (confirm(`Nieuwe referentie starten voor ${driver ? driver.name : 'alle geselecteerde piloten'}? Alle eerdere tijden blijven bewaard.`)) action('reset',driver ? {driverId:driver.id} : {});
  }
  for(const input of $('pit-settings-form').querySelectorAll('input'))input.addEventListener('input',()=>{input.dataset.dirty='yes';});
  $('pit-settings-form').addEventListener('submit',async event=>{
    event.preventDefault();
    await action('pit',{settings:{durationSeconds:Number($('pit-duration').value),requiredStops:Number($('pit-stops').value),netLossSeconds:$('pit-net-loss').value===''?null:Number($('pit-net-loss').value)}});
    for(const input of $('pit-settings-form').querySelectorAll('input'))delete input.dataset.dirty;
  });
  $('track').addEventListener('change',()=>{replayTrackId=null;selected=[];delete $('pilots').dataset.signature;showTrack();});
  $('connect').addEventListener('click', async()=>{
    if(busy)return; const track=currentTrack(); if(!track)return;
    busy=true;showTrack();error('');
    try { await api('connect/', {trackId:track.id,action:track.subscribed?'disconnect':'connect'}); await refresh(); }
    catch(e){error(e.message);} finally {busy=false;showTrack();}
  });
  $('recording').addEventListener('change',showSegments);
  $('load-simulation').addEventListener('click',async()=>{
    if(busy)return;
    const recordingId=Number($('recording').value),segment=Number($('recording-segment').value);
    busy=true;showSegments();error('');
    try {
      const sim=await api('simulate/',{recordingId,segment,requestId:crypto.randomUUID()});
      await refresh();replayTrackId=sim.trackId;$('track').value='';selected=[];delete $('pilots').dataset.signature;showTrack();
    }catch(e){error(e.message);}finally{busy=false;showSegments();showTrack();}
  });
  $('sim-play').addEventListener('click',()=>simulationAction('play'));
  $('sim-pause').addEventListener('click',()=>simulationAction('pause'));
  $('sim-stop').addEventListener('click',()=>simulationAction('stop'));
  $('sim-restart').addEventListener('click',()=>{if(confirm('Vanaf het begin afspelen en de referenties opnieuw opbouwen? Eerdere feedback blijft bewaard.'))simulationAction('restart');});
  $('sim-speed').addEventListener('change',()=>simulationAction('speed',{speed:Number($('sim-speed').value)}));
  $('only-selected').addEventListener('change',showStandings);
  $('update-pilots').addEventListener('click',async()=>{
    await action('drivers',{drivers:selected});
    if(session) {selected=session.drivers.map(d=>d.identity);delete $('pilots').dataset.signature;showTrack();}
  });
  $('start-form').addEventListener('submit',async event=>{
    event.preventDefault();
    if (!$('update-pilots').hidden) { $('update-pilots').click(); return; }
    if (busy || $('start').disabled) return;
    busy=true;updateStart();error('');
    try { follow(await api('start/',{trackId:currentTrack()?.id,drivers:selected,name:$('session-name').value,requestId:crypto.randomUUID()})); await refresh(); }
    catch(e) { error(e.message); }
    finally { busy=false;updateStart(); }
  });
  $('stop').addEventListener('click',()=>action('stop'));
  $('discard').addEventListener('click',()=>{if(session)discardSession(session.id,session.name);});
  $('reset').addEventListener('click',()=>resetReferences());
  $('rename').addEventListener('click',()=>{const name=prompt('Sessienaam',session?.name);if(name?.trim())action('save',{name});});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){refresh().catch(e=>error(e.message));updateConnection();}});
  async function poll() { try { await refresh(); } catch(e) { error(e.message); } finally { setTimeout(poll,5000); } }
  poll();
  setInterval(updateConnection,1000);
})();
