"""Training replay stays in normal view until the explicit fullscreen button is used."""
import json,os,re,secrets,sys
from pathlib import Path
from datetime import timedelta
os.environ.setdefault('DJANGO_SETTINGS_MODULE','server.settings');os.environ.setdefault('DJANGO_DEBUG','true');os.environ.setdefault('DJANGO_SECURE_COOKIES','false');os.environ['DJANGO_ALLOW_ASYNC_UNSAFE']='true'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import django
django.setup()
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from playwright.sync_api import expect,sync_playwright
from www.live_models import FollowSession,TimingTrack,TimingRecording,TimingSimulation
from www.live_simulation import index_recording,tick,control
from www.test_livecoach import packet
from www.test_live_pit import GRID
if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':raise SystemExit('Local SQLite only')
root=Path(settings.LIVECOACH_RECORDINGS_DIR);root.mkdir(parents=True,exist_ok=True)
path=root/('replay-focus-'+secrets.token_hex(5)+'.ndjson')
events=[packet(0,'title2||Focus replay\ngrid||'+GRID),packet(1,'r1c6|tn|40.000'),packet(2,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'),packet(60,'dyn1|countdown|100000')]
path.write_text(''.join(json.dumps(item)+'\n' for item in events));recording=index_recording(path,'Focus replay '+secrets.token_hex(4))
password=secrets.token_urlsafe(24);user=get_user_model().objects.create_superuser(username='focus-replay-'+secrets.token_hex(5),password=password);results=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
  try:
   for mobile in [False,True]:
    for slow in [False,True]:
     ctx=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto('http://127.0.0.1:8210/live/login/?next=/live/training/')
     page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password);page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8210/live/training/')
     cdp=ctx.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
     if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
     page.reload(wait_until='domcontentloaded');page.locator('summary').filter(has_text='Een opname simuleren').click()
     expect(page.locator('#recording option').filter(has_text=recording.name)).to_have_count(1);page.locator('#recording').select_option(str(recording.pk));page.get_by_role('button',name='Simulatie laden',exact=True).click()
     expect(page.locator('#simulation-status')).to_contain_text('Gepauzeerd')
     page.locator('#pilots').get_by_role('radio',name=re.compile('SMEETS Noah')).check()
     name='Paused replay '+secrets.token_hex(4);page.locator('#session-name').fill(name);page.get_by_role('button',name='Start volgsessie',exact=False).click()
     expect(page.locator('#training-dashboard')).to_be_visible();expect(page.locator('body')).not_to_have_class(re.compile('training-fullscreen'))
     expect(page.get_by_role('button',name='Afspelen',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Afspelen',exact=True)).to_be_enabled()
     page.reload(wait_until='domcontentloaded');page.locator('#sessions button').filter(has_text=name).click()
     expect(page.locator('#simulation-status')).to_contain_text('Gepauzeerd');expect(page.locator('body')).not_to_have_class(re.compile('training-fullscreen'))
     page.get_by_role('button',name='Afspelen',exact=True).click();expect(page.locator('body')).not_to_have_class(re.compile('training-fullscreen'))
     page.get_by_role('button',name='Fullscreen training',exact=True).click();expect(page.locator('body')).to_have_class(re.compile('training-fullscreen'))
     sim=TimingSimulation.objects.filter(owner=user).latest('track_id');tick(sim.pk,timezone.now()+timedelta(seconds=2.5))
     expect(page.locator('#training-live')).to_contain_text('0:40.000')
     page.get_by_role('button',name='Verlaat fullscreen',exact=True).click();page.get_by_role('button',name='Pauzeren',exact=True).click();expect(page.locator('#simulation-status')).to_contain_text('Gepauzeerd')
     expect(page.locator('body')).not_to_have_class(re.compile('training-fullscreen'))
     page.get_by_role('button',name='Stop & bewaar',exact=True).click();control(sim.pk,user,'stop')
     assert not errors,errors
     fcp=page.evaluate("performance.getEntriesByType('paint').find(p=>p.name==='first-contentful-paint')?.startTime")
     assert fcp is not None and fcp<(3000 if slow else 2000)
     ctx.close();results.append(dict(mobile=mobile,slow=slow,fcp_ms=round(fcp),ok=True));print(results[-1],flush=True)
  finally:browser.close()
finally:
 FollowSession.objects.filter(owner=user).delete();TimingTrack.objects.filter(owner=user).delete();user.delete();recording.delete();path.unlink(missing_ok=True)
 Path('/tmp/replay-focus-results.json').write_text(json.dumps(results,indent=2))
