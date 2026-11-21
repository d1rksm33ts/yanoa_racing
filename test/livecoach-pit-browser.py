"""Local-only browser proof of kart changes, two sectors, persistent lap delta and pit settings."""
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','server.settings')
os.environ.setdefault('DJANGO_DEBUG','true')
os.environ.setdefault('DJANGO_SECURE_COOKIES','false')
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE']='true'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from playwright.sync_api import expect,sync_playwright
from www.live_models import FollowSession, TimingTrack
from www.live_service import ingest
from www.test_livecoach import packet
from www.test_live_pit import GRID
if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':raise SystemExit('Local SQLite required')
password=secrets.token_urlsafe(24)
user=get_user_model().objects.create_superuser(username='pit-browser-'+secrets.token_hex(4),password=password)
results=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
  try:
   for mobile in [False,True]:
    for slow in [False,True]:
     track=TimingTrack.objects.create(owner=user,slug='pit-browser-'+secrets.token_hex(6),name='Goodwill browser fixture '+secrets.token_hex(4),source_id='goodwill',connection='connected')
     key=track.slug
     ingest(track.pk,key,packet(0,'title2||Pro heat\nlight|lg|\ngrid||'+GRID))
     context=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900})
     page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto('http://127.0.0.1:8210/live/login/?next=/live/sprint/')
     page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password)
     page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8210/live/sprint/')
     cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
     if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
     page.reload(wait_until='domcontentloaded')
     expect(page.locator('#track option').filter(has_text=track.name)).to_have_count(1)
     page.locator('#track').select_option(str(track.pk));page.get_by_role('button',name='Verbinden',exact=True).click()
     expect(page.locator('#source-status')).to_contain_text('Verbonden')
     page.locator('#pilots').get_by_role('checkbox',name=re.compile('SMEETS Noah')).check()
     page.get_by_role('button',name='Start volgsessie').click();expect(page.locator('.driver-card:first-child')).to_be_visible()
     page.locator('#pit-settings-panel > summary').click()
     expect(page.locator('#pit-duration')).to_have_value('90')
     page.locator('#pit-net-loss').fill('72');page.locator('#pit-settings-save').click()
     page.locator('.driver-card:first-child').get_by_role('checkbox',name='Pitvoorspelling').check()
     expect(page.locator('.driver-card:first-child .pit-card')).to_contain_text('Netto verlies')
     expect(page.locator('#live-status')).to_contain_text('Live verbonden',timeout=12000)
     passage_sent=time.monotonic()
     ingest(track.pk,key,packet(1,'r1c6|tn|40.000'))
     ingest(track.pk,key,packet(2,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'))
     try:expect(page.locator('.driver-card:first-child .driver-detail')).to_contain_text('1:00.000',timeout=12000)
     except Exception:
      print('DB',list(FollowSession.objects.filter(owner=user,track=track).values('id','state','started_at')),list(FollowSession.objects.filter(owner=user,track=track).first().drivers.values('last','best')))
      print('UI',page.locator('#live-status').inner_text(),page.locator('#error').inner_text(),errors)
      raise
     print('Passage-to-display',round((time.monotonic()-passage_sent)*1000),'ms',dict(mobile=mobile,slow=slow),flush=True)
     ingest(track.pk,key,packet(3,'r1c4|no7|25'))
     expect(page.locator('.driver-card:first-child .driver-top')).to_contain_text('P2')
     expect(page.locator('.driver-card:first-child .driver-karts')).to_contain_text('Kart #25')
     ingest(track.pk,key,packet(4,'r1c6|tn|40.102'))
     ingest(track.pk,key,packet(5,'r1c7|tn|20.000\nr1c8|tn|1:00.102\nr1c11|in|5'))
     expect(page.locator('.driver-card:first-child .lap-delta')).to_contain_text('+0.102s')
     ingest(track.pk,key,packet(6,'r1c6|tn|39.051'))
     expect(page.locator('.driver-card:first-child .metric')).to_contain_text('S1')
     expect(page.locator('.driver-card:first-child .lap-delta')).to_contain_text('+0.102s')
     strip=page.locator('.driver-card:first-child .sector-strip');expect(strip.locator('div')).to_have_count(2)
     expect(strip.locator('div').nth(0)).to_contain_text('-0.949s')
     expect(strip.locator('div').nth(1)).to_contain_text('0:20.000')
     ingest(track.pk,key,packet(7,'r1c7|tn|20.000\nr1c8|tn|59.051\nr1c11|in|6'))
     expect(page.locator('.driver-card:first-child .lap-delta')).to_contain_text('-0.949s')
     expect(page.locator('.driver-card:first-child .driver-detail')).to_contain_text('0:59.051')
     expect(page.locator('#standings .selected-driver')).to_contain_text('-0.949s')
     ingest(track.pk,key,packet(8,'r1|*in|0\nr1c13|in|1'))
     expect(page.locator('.driver-card:first-child .pit-card')).to_contain_text('IN PIT')
     expect(page.locator('.driver-card:first-child .pit-card')).to_contain_text('90.0s resterend')
     assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
     assert page.locator('#standings').evaluate('(el)=>el.scrollWidth <= el.clientWidth'), 'standings overflow'
     assert not errors,errors
     page.screenshot(path=f'/tmp/livecoach-pit-{mobile}-{slow}.png',full_page=True)
     page.get_by_role('button',name='Stop & bewaar',exact=True).click();expect(page.locator('#session-badge')).to_have_text('BEWAARD')
     context.close();results.append(dict(mobile=mobile,slow=slow,ok=True));print(results[-1],flush=True)
  finally:browser.close()
finally:
 FollowSession.objects.filter(owner=user).delete();TimingTrack.objects.filter(owner=user).delete();user.delete()
 Path('/tmp/livecoach-pit-results.json').write_text(json.dumps(results,indent=2))
