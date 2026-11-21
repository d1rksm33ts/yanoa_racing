"""Local browser verification: owned dashboard selection, replay timing and staleness."""
import hashlib,json,os,secrets,sys,uuid,time
from datetime import timedelta
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','server.settings')
os.environ.setdefault('DJANGO_DEBUG','true');os.environ.setdefault('DJANGO_SECURE_COOKIES','false')
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE']='true'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import django;django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from playwright.sync_api import sync_playwright,expect
from www.live_models import FollowSession,FollowDriver,TimingSimulation
from www.live_simulation import index_recording,create_simulation,control,tick
from www.telemetry_models import TelemetryDevice
from www.test_telemetry import frame,TOKEN
from www.test_livecoach import GRID,packet,lap
assert settings.DEBUG and settings.DATABASES['default']['ENGINE']=='django.db.backends.sqlite3'
password=secrets.token_urlsafe(24)
user=get_user_model().objects.create_superuser(username='dashboard-browser-'+secrets.token_hex(4),password=password)
root=Path(settings.LIVECOACH_RECORDINGS_DIR);root.mkdir(parents=True,exist_ok=True)
path=root/('dashboard-browser-'+secrets.token_hex(5)+'.ndjson')
path.write_text(''.join(json.dumps(e)+'\n' for e in [packet(0,'title2||DASHBOARD REPLAY\ngrid||'+GRID),lap(1,'1:00.451',4),lap(9,'1:00.553',5)]))
recording=index_recording(path,'Dashboard browser recording')
device=TelemetryDevice.objects.create(device_id='BENCH-ESP32-001',owner=user,token_digest=hashlib.sha256(TOKEN.encode()).hexdigest())
import threading
from django.db import connections
stop=threading.Event();seq=0;heartbeat_errors=[]
def producer():
 global seq
 machine=Client()
 try:
  while not stop.is_set():
   seq+=1
   r=machine.post('/live/api/devices/BENCH-ESP32-001/telemetry/',json.dumps(frame(seq)),content_type='application/json',HTTP_AUTHORIZATION='Bearer '+TOKEN)
   if r.status_code!=202:heartbeat_errors.append((r.status_code,r.content))
   stop.wait(.8)
 finally:connections.close_all()
thread=threading.Thread(target=producer);thread.start()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
  for activity in ['training','sprint','endurance']:
   for mobile in [False,True]:
    for slow in [False,True]:
     context=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900})
     page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto('http://127.0.0.1:8211/live/login/?next=/live/')
     page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password)
     page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8211/live/')
     expect(page.locator('#kart-devices')).to_have_count(0)
     cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
     if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
     page.goto(f'http://127.0.0.1:8211/live/{activity}/',wait_until='domcontentloaded')
     expect(page.locator('#kart-devices')).to_contain_text('Kies eerst een piloot')
     expect(page.locator('#kart-device-status')).to_contain_text('Online')
     page.wait_for_function("performance.getEntriesByName('first-contentful-paint').length>0")
     fcp=page.evaluate("performance.getEntriesByName('first-contentful-paint')[0]?.startTime")
     assert fcp and fcp<(3000 if slow else 2000),(activity,mobile,slow,fcp)
     page.locator('summary').filter(has_text='Een opname simuleren').click()
     page.locator('#recording').select_option(str(recording.pk));page.locator('#recording-segment').select_option('0')
     page.locator('#load-simulation').click()
     page.locator('#pilots input').first.check()
     picker=page.get_by_label('Dashboard voor NOAH SMEETS',exact=True)
     expect(picker).to_be_visible();picker.select_option(device.device_id)
     expect(page.locator('.kart-device small')).to_contain_text('koppelt bij Start')
     device.refresh_from_db();assert device.assigned_driver_id is None
     page.locator('#session-name').fill('Flow '+activity)
     page.locator('#start').click()
     expect(page.locator('#kart-device-message')).to_contain_text('NOAH SMEETS is gekoppeld',timeout=12000)
     device.refresh_from_db();assert device.assigned_driver_id is not None
     followed=device.assigned_driver;assert followed.session.activity==activity
     expect(picker).to_have_value(device.device_id)
     page.screenshot(path=f'/tmp/kart-flow-{activity}-{mobile}-{slow}.png',full_page=True)
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
     picker.select_option('')
     expect(page.locator('#kart-device-message')).to_contain_text('losgekoppeld')
     device.refresh_from_db();assert device.assigned_driver_id is None
     picker.select_option(device.device_id)
     expect(page.locator('#kart-device-message')).to_contain_text('NOAH SMEETS is gekoppeld')
     assert not errors,errors
     print({'activity':activity,'mobile':mobile,'slow':slow,'fcp_ms':round(fcp),'prestart_choice':True,'automatic_assignment':True,'immediate_reassignment':True},flush=True)
     context.close()
     device.assigned_driver=None;device.save(update_fields=['assigned_driver'])
     for sim in TimingSimulation.objects.filter(owner=user):
      if sim.state in ['paused','playing']:control(sim.pk,user,'stop')
     FollowSession.objects.filter(owner=user).delete()
  browser.close()
 assert not heartbeat_errors,heartbeat_errors
finally:
 stop.set();thread.join(timeout=5)
 device.delete();FollowSession.objects.filter(owner=user).delete()
 from www.live_models import TimingTrack,TimingPacket,TimingConnection
 for track in TimingTrack.objects.filter(owner=user):
  TimingSimulation.objects.filter(track=track).delete();TimingPacket.objects.filter(track=track).delete();TimingConnection.objects.filter(track=track).delete();track.delete()
 recording.delete();path.unlink(missing_ok=True);user.delete()
