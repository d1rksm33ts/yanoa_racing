"""Local-only interactive replay rewind proof with an isolated timing worker."""
import json,os,re,secrets,sys,threading,time,uuid
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','server.settings');os.environ.setdefault('DJANGO_DEBUG','true');os.environ.setdefault('DJANGO_SECURE_COOKIES','false');os.environ['DJANGO_ALLOW_ASYNC_UNSAFE']='true'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import OperationalError,close_old_connections
from django.test import Client
from playwright.sync_api import expect,sync_playwright
from www.live_models import FollowSession,TimingTrack,TimingSimulation
from www.live_simulation import index_recording,create_simulation,tick
from www.test_livecoach import GRID,lap,packet
if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':raise SystemExit('Local SQLite only')
root=Path(settings.LIVECOACH_RECORDINGS_DIR);root.mkdir(parents=True,exist_ok=True)
path=root/('rewind-browser-'+secrets.token_hex(5)+'.ndjson')
events=[packet(0,'title2||Rewind browser\ngrid||'+GRID),lap(1,'1:01.400',4),lap(2,'1:00.451',5),lap(3,'1:00.553',6),lap(4,'0:59.000',7),packet(5,'light|lf|'),packet(6,'title2||Next\ngrid||'+GRID)]
for event,offset in zip(events,[0,2000,6000,12000,18000,22000,24000]):event['offsetMs']=offset
path.write_text(''.join(json.dumps(e)+'\n' for e in events));recording=index_recording(path,'Rewind browser '+secrets.token_hex(4))
password=secrets.token_urlsafe(24);user=get_user_model().objects.create_superuser(username='rewind-'+secrets.token_hex(5),password=password)
client=Client();client.force_login(user);results=[];stop=threading.Event();worker_errors=[]
def worker():
 try:
  while not stop.wait(.05):
   try:
    for sid in TimingSimulation.objects.filter(owner_id=user.pk,state__in=['paused','playing','rewinding']).values_list('pk',flat=True):tick(sid)
   except OperationalError:pass
   except Exception as e:worker_errors.append(type(e).__name__+': '+str(e));return
 finally:close_old_connections()
thread=threading.Thread(target=worker,daemon=True);thread.start()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
  try:
   for mobile in [False,True]:
    for slow in [False,True]:
     sim=create_simulation(user,recording,0,uuid.uuid4())
     response=client.post('/live/api/start/',json.dumps({'trackId':sim.track_id,'drivers':[sim.track.entrants[0]['identity']],'requestId':str(uuid.uuid4()),'name':'Rewind browser test','activity':'sprint'}),content_type='application/json');assert response.status_code==201,response.content
     session=FollowSession.objects.get(pk=response.json()['id'])
     ctx=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto('http://127.0.0.1:8216/live/login/?next=/live/sprint/')
     page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password);page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8216/live/sprint/')
     cdp=ctx.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
     if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
     page.goto(f'http://127.0.0.1:8216/live/sprint/?session={session.pk}',wait_until='domcontentloaded')
     expect(page.locator('#driver-cards')).to_contain_text('NOAH SMEETS');expect(page.locator('#sim-rewind')).to_be_disabled()
     page.wait_for_function("performance.getEntriesByName('first-contentful-paint').length>0")
     fcp=page.evaluate("performance.getEntriesByName('first-contentful-paint')[0].startTime");assert fcp<(3000 if slow else 2000),fcp
     page.locator('#sim-speed').select_option('20');page.locator('#sim-play').click();expect(page.locator('#simulation-status')).to_contain_text('Afgelopen',timeout=10000)
     expect(page.locator('#sim-rewind')).to_be_enabled();page.get_by_role('button',name='10 seconden terug',exact=True).click()
     expect(page.locator('#simulation-status')).to_contain_text('Gepauzeerd',timeout=10000)
     sim.refresh_from_db();assert sim.position_ms==14000,(sim.position_ms,worker_errors)
     assert session.drivers.get().best['lap']==60451
     expect(page.locator('#history')).not_to_contain_text('0:59.000')
     page.locator('#sim-rewind').click();expect(page.locator('#simulation-status')).to_contain_text('0:04',timeout=10000);sim.refresh_from_db();assert sim.position_ms==4000
     page.locator('#sim-rewind').click();expect(page.locator('#simulation-status')).to_contain_text(re.compile(r'Gepauzeerd.*0:00'),timeout=10000);expect(page.locator('#sim-rewind')).to_be_disabled();sim.refresh_from_db();assert sim.position_ms==0
     page.locator('#sim-speed').select_option('5');page.locator('#sim-play').click()
     page.wait_for_function("Number(document.getElementById('simulation-progress').value)>=11000",timeout=10000)
     page.locator('#sim-rewind').click();expect(page.locator('#sim-pause')).to_be_enabled(timeout=10000);page.locator('#sim-pause').click();expect(page.locator('#simulation-status')).to_contain_text('Gepauzeerd')
     sim.refresh_from_db();assert sim.speed==5 and sim.position_ms<18000,(sim.speed,sim.position_ms)
     assert session.drivers.get().best.get('lap')!=59000
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
     assert not errors,errors;assert not worker_errors,worker_errors
     page.screenshot(path=f'/tmp/rewind-browser-{mobile}-{slow}.png',full_page=True)
     page.locator('#sim-stop').click();expect(page.locator('#simulation-status')).to_contain_text('Gestopt')
     ctx.close();item=dict(mobile=mobile,slow=slow,fcp_ms=round(fcp),finished_rewind=True,paused_rewind=True,playing_rewind=True,clamp_zero=True,ok=True);results.append(item);print(item,flush=True)
  finally:browser.close()
finally:
 stop.set();thread.join(timeout=10)
 FollowSession.objects.filter(owner=user).delete();TimingTrack.objects.filter(owner=user).delete();user.delete();recording.delete();path.unlink(missing_ok=True)
 Path('/tmp/kart-rewind-browser-results.json').write_text(json.dumps(results,indent=2))
