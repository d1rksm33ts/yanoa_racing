"""Local-only strategy proof: colors, pit exit, post-pit/end projections and actionable pace."""
import json
import os
import re
import secrets
import sys
from datetime import datetime,timedelta
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
grid=GRID.replace('</tbody>',other+'</tbody>').replace('<tr class="head">','<tr class="head"><td data-id="c14" data-type="s3">S3</td>')
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
     assert page.locator('.driver-card .delta').count()==0
     expect(page.locator('#session-record-panel')).to_be_visible()
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
     ingest(track.pk,track.slug,packet(1,'r1c6|tn|40.000\nr1c14|tn|22.348'))
     ingest(track.pk,track.slug,packet(2,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'))
     expect(noah.locator('.driver-detail')).to_contain_text('1:00.000')
     expect(noah.locator('.lap-delta')).to_contain_text('Ref.')
     expect(noah.locator('.sector-strip')).not_to_contain_text('Referentie')
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
     # Seed rival pace and global benchmark; subsequent passages still use real ingest.
     track.refresh_from_db();state=track.parser_state
     state['rows']['r2']['recent_laps']=[{'kart':'7','timeMs':59000}]*6
     state['rows']['r2']['sector_bests']={'S1':38000,'S2':20500}
     state['rows']['r2']['cells']['c10']='59.000'
     track.parser_state=state;track.save(update_fields=['parser_state'])
     def feed(seq,payload,stamp=None):
      event=packet(seq,payload)
      if stamp:event['originalReceivedAt']=stamp.isoformat()
      ingest(track.pk,track.slug,event)
     def finish(seq,time,lap):feed(seq,f'r1c7|tn|20.000\nr1c8|tn|{time}\nr1c11|in|{lap}\nr2c8|tn|59.000\nr2c11|in|{lap}')
     finish(5,'59.900',5)
     feed(6,'dyn1|countdown|300000\nr1c6|tn|40.100')
     expect(page.locator('#race-title')).to_have_text('Pro heat')
     expect(page.locator('#race-clock')).to_have_text(re.compile(r'0[45]:[0-5][0-9]'))
     feed(600,'dyn1|text|Vuelta 6/6')
     expect(page.locator('#race-clock')).to_have_text('6/6')
     expect(page.locator('#race-clock-label')).to_have_text('Ronde')
     feed(602,'com||<p><b>10:24</b><span data-flag="penalty"></span><span class="com_no no4">9</span>Penalización - Push to pass - 3.000</p>')
     page.locator('#race-comments-panel > summary').click()
     expect(page.locator('#race-comments')).to_contain_text('10:24')
     expect(page.locator('#race-comments')).to_contain_text('#9')
     expect(page.locator('#race-comments')).to_contain_text('Push to pass')
     page.locator('#race-comments-panel > summary').click()
     expect(page.locator('#race-comments')).not_to_be_visible()
     feed(601,'dyn1|countdown|300000')
     expect(noah.locator('.sector-delta').first).to_have_class(re.compile('slower'))
     page.wait_for_function("Array.from(document.querySelectorAll('.sector-delta')).some(el=>getComputedStyle(el).color==='rgb(255, 180, 92)')")
     finish(7,'1:00.100',6)
     feed(8,'r1c6|tn|39.800')
     expect(noah.locator('.sector-delta').first).to_have_class(re.compile('faster'))
     finish(9,'59.800',7)
     feed(10,'r1c6|tn|37.000')
     expect(noah.locator('.sector-delta').first).to_have_class(re.compile('purple'))
     expect(noah.locator('.sector-strip > div').first.locator('strong')).to_have_class(re.compile('purple'))
     expect(noah.locator('.sector-best').first).to_contain_text('0:37.000')
     expect(page.locator('#session-records')).to_contain_text('SMEETS Noah')
     page.wait_for_function("Array.from(document.querySelectorAll('.sector-delta')).some(el=>parseFloat(getComputedStyle(el).fontSize)>=18)")
     finish(11,'57.000',8)
     expect(noah.locator('.finish-position')).to_contain_text('P')
     expect(noah.locator('.pace-advice')).to_contain_text('sneller')
     entry=datetime.now().astimezone();exit_time=entry+timedelta(seconds=90.847)
     feed(12,'r1|*in|0\nr1c13|in|1',entry)
     feed(13,'r1|*out|0',exit_time)
     expect(noah.locator('.pit-exit')).to_have_text('Pit uit 90.847s')
     expect(noah.locator('.projected-position')).to_contain_text('P')
     expect(noah.locator('.finish-position')).to_contain_text('P')
     expect(noah.locator('.pace-advice')).to_contain_text('sneller')
     page.wait_for_function("Array.from(document.querySelectorAll('.driver-card')).some(c=>{const p=c.querySelector('.driver-position'),s=c.querySelector('.projected-position'),f=c.querySelector('.finish-position');return p&&s&&f&&s.getBoundingClientRect().y>p.getBoundingClientRect().y&&f.getBoundingClientRect().y>s.getBoundingClientRect().y})")
     expect(noah.locator('.sector-strip > div')).to_have_count(3)
     page.wait_for_function("Array.from(document.querySelectorAll('.sector-strip>div')).every(c=>Array.from(c.children).every(el=>el.getBoundingClientRect().right<=c.getBoundingClientRect().right+1))")
     assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
     assert not errors,errors
     page.screenshot(path=f'/tmp/livecoach-strategy-{mobile}-{slow}.png',full_page=True)
     page.get_by_role('button',name='Stop & bewaar',exact=True).click();expect(page.locator('#session-badge')).to_have_text('BEWAARD')
     context.close();results.append(dict(mobile=mobile,slow=slow,fcp_ms=round(fcp),ok=True));print(results[-1],flush=True)
  finally:browser.close()
finally:
 FollowSession.objects.filter(owner=user).delete();TimingTrack.objects.filter(owner=user).delete();user.delete()
 Path('/tmp/livecoach-strategy-results.json').write_text(json.dumps(results,indent=2))
