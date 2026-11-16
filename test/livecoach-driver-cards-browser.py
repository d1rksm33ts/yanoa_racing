"""Local-only proof: equal cards, independent persisted forecasts, positions and kart history."""
import json
import os
import re
import secrets
import sys
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
from www.live_models import FollowSession,TimingTrack
from www.live_service import ingest
from www.test_livecoach import packet
from www.test_live_pit import GRID
if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':raise SystemExit('Local SQLite required')
other=GRID[GRID.index('<tr data-id="r1"'):GRID.index('</tbody>')].replace('r1','r2').replace('SMEETS Noah','OTHER DRIVER').replace('>15<','>7<').replace('data-pos="2"','data-pos="1"')
grid=GRID.replace('</tbody>',other+'</tbody>')
password=secrets.token_urlsafe(24)
user=get_user_model().objects.create_superuser(username='cards-browser-'+secrets.token_hex(5),password=password)
results=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
  try:
   for mobile in [False,True]:
    for slow in [False,True]:
     name='Equal cards '+secrets.token_hex(4)
     track=TimingTrack.objects.create(owner=user,slug='cards-browser-'+secrets.token_hex(6),name=name,source_id='goodwill',connection='connected')
     ingest(track.pk,track.slug,packet(0,'title2||Pro heat\nlight|lg|\ngrid||'+grid))
     context=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900})
     page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto('http://127.0.0.1:8210/live/login/?next=/live/')
     page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password)
     page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8210/live/')
     cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
     if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
     page.reload(wait_until='domcontentloaded')
     expect(page.locator('#track option').filter(has_text=name)).to_have_count(1)
     page.wait_for_function("performance.getEntriesByType('paint').some(p=>p.name==='first-contentful-paint')")
     fcp=page.evaluate("performance.getEntriesByType('paint').find(p=>p.name==='first-contentful-paint')?.startTime")
     assert fcp is not None and fcp<(3000 if slow else 2000),fcp
     page.locator('#track').select_option(str(track.pk));page.get_by_role('button',name='Verbinden',exact=True).click()
     expect(page.locator('#source-status')).to_contain_text('Verbonden')
     page.locator('#pilots').get_by_role('checkbox',name=re.compile('SMEETS Noah')).check()
     page.locator('#pilots').get_by_role('checkbox',name=re.compile('OTHER DRIVER')).check()
     page.locator('#session-name').fill(name)
     page.get_by_role('button',name='Start volgsessie').click();expect(page.locator('.driver-card')).to_have_count(2)
     noah=page.locator('.driver-card').filter(has_text='SMEETS Noah')
     rival=page.locator('.driver-card').filter(has_text='OTHER DRIVER')
     expect(noah.locator('.driver-position')).to_have_text('P2')
     expect(rival.locator('.driver-position')).to_have_text('P1')
     expect(noah.get_by_role('checkbox',name='Pitvoorspelling')).not_to_be_checked()
     expect(rival.get_by_role('checkbox',name='Pitvoorspelling')).not_to_be_checked()
     expect(page.locator('.pit-card')).to_have_count(0)
     widths=page.locator('.driver-card').evaluate_all('(cards)=>cards.map(c=>c.getBoundingClientRect().width)')
     assert abs(widths[0]-widths[1])<1,widths
     sizes=page.locator('.driver-card .delta').evaluate_all('(els)=>els.map(e=>getComputedStyle(e).fontSize)')
     assert sizes[0]==sizes[1],sizes
     assert page.locator('.primary-card').count()==0
     page.locator('#pit-settings-panel > summary').click();page.locator('#pit-net-loss').fill('72');page.locator('#pit-settings-save').click()
     rival.get_by_role('checkbox',name='Pitvoorspelling').check()
     expect(rival.locator('.pit-card')).to_contain_text('Nu pitten')
     expect(noah.locator('.pit-card')).to_have_count(0)
     noah.get_by_role('checkbox',name='Pitvoorspelling').check()
     expect(noah.locator('.projected-position')).to_contain_text('P')
     rival.get_by_role('checkbox',name='Pitvoorspelling').uncheck()
     expect(rival.locator('.pit-card')).to_have_count(0)
     page.reload(wait_until='domcontentloaded')
     page.locator('#sessions button').filter(has_text=name).click()
     expect(noah.get_by_role('checkbox',name='Pitvoorspelling')).to_be_checked()
     expect(rival.get_by_role('checkbox',name='Pitvoorspelling')).not_to_be_checked()
     expect(page.locator('#live-status')).to_contain_text('Live verbonden',timeout=12000)
     ingest(track.pk,track.slug,packet(1,'r1c6|tn|40.000'))
     ingest(track.pk,track.slug,packet(2,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'))
     expect(noah.locator('.driver-detail')).to_contain_text('1:00.000')
     ingest(track.pk,track.slug,packet(3,'r1c4|no7|25\nr1|#|1\nr2|#|2'))
     expect(noah.locator('.driver-karts')).to_contain_text('Kart #25')
     expect(noah.locator('.previous-kart')).to_contain_text('← #15')
     expect(noah.locator('.previous-kart')).to_contain_text('1:00.000')
     expect(noah.locator('.driver-position')).to_have_text('P1')
     expect(rival.locator('.driver-position')).to_have_text('P2')
     expect(noah.locator('.driver-pit-control .info-content')).not_to_be_visible()
     noah.get_by_label('Uitleg pitvoorspelling').click()
     expect(noah.locator('.driver-pit-control .info-content')).to_be_visible()
     ingest(track.pk,track.slug,packet(4,'r1c6|tn|39.900'))
     expect(noah.locator('.sector-strip')).to_contain_text('-0.100s')
     expect(noah.locator('.driver-pit-control .info-content')).to_be_visible()
     noah.get_by_label('Uitleg pitvoorspelling').click()
     expect(noah.locator('.driver-pit-control .info-content')).not_to_be_visible()
     assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
     assert not errors,errors
     page.screenshot(path=f'/tmp/livecoach-cards-{mobile}-{slow}.png',full_page=True)
     page.get_by_role('button',name='Stop & bewaar',exact=True).click();expect(page.locator('#session-badge')).to_have_text('BEWAARD')
     context.close();results.append(dict(mobile=mobile,slow=slow,fcp_ms=round(fcp),ok=True));print(results[-1],flush=True)
  finally:browser.close()
finally:
 FollowSession.objects.filter(owner=user).delete();TimingTrack.objects.filter(owner=user).delete();user.delete()
 Path('/tmp/livecoach-cards-results.json').write_text(json.dumps(results,indent=2))
