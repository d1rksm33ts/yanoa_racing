"""Local-only proof of training, source choice, full screen and durable kart reports."""
import json,os,re,secrets,sys
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','server.settings');os.environ.setdefault('DJANGO_DEBUG','true');os.environ.setdefault('DJANGO_SECURE_COOKIES','false');os.environ['DJANGO_ALLOW_ASYNC_UNSAFE']='true'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from playwright.sync_api import expect,sync_playwright
from www.live_models import TimingTrack,FollowSession,KartReport
from www.live_service import ingest
from www.test_livecoach import packet
from www.test_live_pit import GRID
if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':raise SystemExit('Local SQLite only')
password=secrets.token_urlsafe(24);user=get_user_model().objects.create_superuser(username='training-browser-'+secrets.token_hex(5),password=password)
tracks=[];results=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
  try:
   for mobile in [False,True]:
    for slow in [False,True]:
     name='Training QA '+secrets.token_hex(4)
     base=GRID[GRID.index('<tr data-id="r1"'):GRID.index('</tbody>')].replace('<td data-id="r1c6"></td>','<td data-id="r1c6">40.000</td>').replace('<td data-id="r1c7"></td>','<td data-id="r1c7">20.000</td>')
     faster=base.replace('r1','r2').replace('SMEETS Noah','FASTER DRIVER').replace('>15<','>7<').replace('1:00.000','0:59.000').replace('data-pos="2"','data-pos="20"')
     slower=base.replace('r1','r3').replace('SMEETS Noah','SLOWER DRIVER').replace('>15<','>8<').replace('1:00.000','1:01.000').replace('data-pos="2"','data-pos="1"')
     leader=base.replace('r1','r4').replace('SMEETS Noah','LEADER').replace('>15<','>12<').replace('1:00.000','0:55.000').replace('40.000','34.000')
     other=base.replace('r1','r5').replace('SMEETS Noah','OTHER FASTER').replace('>15<','>14<').replace('1:00.000','0:58.000').replace('40.000','38.000').replace('20.000','19.000')
     grid=GRID.replace('</tbody>',faster+slower+leader+other+'</tbody>')
     track=TimingTrack.objects.create(slug='training-qa-'+secrets.token_hex(4),name=name,source_id='goodwill',connection='connected');tracks.append(track.pk)
     ingest(track.pk,track.slug,packet(0,'title2||Practice\ndyn1|countdown|600000\ngrid||'+grid))
     ctx=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto('http://127.0.0.1:8215/live/login/?next=/live/')
     page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password);page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8215/live/')
     expect(page.locator('.mode-choice')).to_have_count(3)
     cdp=ctx.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
     if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
     page.get_by_role('link',name=re.compile('Training')).click();page.wait_for_url('http://127.0.0.1:8215/live/training/')
     expect(page.locator('#track option').filter(has_text=name)).to_have_count(1)
     page.wait_for_function("performance.getEntriesByType('paint').some(p=>p.name==='first-contentful-paint')")
     fcp=page.evaluate("performance.getEntriesByType('paint').find(p=>p.name==='first-contentful-paint').startTime")
     assert fcp<(3000 if slow else 2000),fcp
     page.locator('#training-provider').select_option('manual');expect(page.locator('#provider-note')).to_be_visible();expect(page.locator('#connect')).to_be_disabled()
     page.locator('#training-provider').select_option('other');expect(page.locator('#connect')).to_be_disabled()
     page.locator('#training-provider').select_option('apex');page.locator('#track').select_option(str(track.pk));page.get_by_role('button',name='Verbinden',exact=True).click()
     expect(page.locator('#source-status')).to_contain_text('Verbonden')
     page.locator('#pilots').get_by_role('radio',name=re.compile('SMEETS Noah')).check()
     page.locator('#session-name').fill(name);page.get_by_role('button',name='Start volgsessie',exact=False).click()
     expect(page.locator('#training-dashboard')).to_be_visible();expect(page.locator('body')).not_to_have_class(re.compile('training-fullscreen'))
     page.get_by_role('button',name='Fullscreen training',exact=True).click();expect(page.locator('body')).to_have_class(re.compile('training-fullscreen'))
     expect(page.locator('#training-live')).to_contain_text('SMEETS Noah')
     expect(page.locator('#race-clock-panel')).to_be_visible()
     assert page.locator('#race-clock-panel').bounding_box()['y'] < page.locator('#training-dashboard').bounding_box()['y']
     expect(page.locator('#training-comparison')).to_contain_text('FASTER DRIVER');expect(page.locator('#training-comparison')).to_contain_text('SLOWER DRIVER')
     ingest(track.pk,track.slug,packet(1,'r1c6|tn|40.000'))
     ingest(track.pk,track.slug,packet(2,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'))
     ingest(track.pk,track.slug,packet(3,'r1c6|tn|39.500'))
     expect(page.locator('#training-live')).to_contain_text('-0.500s');expect(page.locator('#training-live')).to_contain_text('Beste 0:39.500')
     expect(page.locator('#training-comparison')).to_contain_text('Δ eigen')
     expect(page.locator('#history')).to_contain_text('Ronde 5')
     expect(page.locator('.training-rows-table tbody tr:not(.ideal-training-row)')).to_have_count(4)
     expect(page.locator('.followed-training-row .training-pace-position')).to_have_text('T4')
     expect(page.locator('.ideal-training-row')).to_contain_text('0:53.000')
     expect(page.locator('.passage-freshness')).to_have_count(0)
     expect(page.locator('.followed-training-row')).not_to_contain_text('GEVOLGD')
     expect(page.locator('#training-live .training-time').nth(0).locator('.ideal-delta')).to_have_text('Te winnen 5.500s')
     expect(page.locator('.followed-training-row .training-row-time').nth(0).locator('.ideal-delta')).to_have_text('Te winnen 5.500s')
     expect(page.locator('.followed-training-row .training-row-time').nth(2).locator('.ideal-delta')).to_have_text('Te winnen 7.000s')
     expect(page.locator('#training-live .training-time').nth(0)).to_have_attribute('data-phase','current')
     expect(page.locator('#training-live .training-time').nth(1)).to_have_attribute('data-phase','previous')
     expect(page.locator('.followed-training-row .training-row-time').nth(0).locator('.own-delta')).to_have_text('Δ eigen -0.500s')
     ingest(track.pk,track.slug,packet(100,'r1c7|tn|19.500\nr1c8|tn|54.000\nr1c10|tn|54.000\nr1c11|in|5'))
     expect(page.locator('.followed-training-row')).to_have_attribute('data-lap-color','purple')
     expect(page.locator('#training-live .training-time').nth(2)).to_have_attribute('data-active','true')
     page.wait_for_function("getComputedStyle(document.querySelector('.followed-training-row')).borderLeftColor==='rgb(181, 154, 255)'")
     page.wait_for_function("getComputedStyle(document.querySelectorAll('#training-live .training-time')[2]).borderTopColor==='rgb(181, 154, 255)'")
     expect(page.locator('#training-live .training-time').nth(0)).to_have_attribute('data-active','true')
     expect(page.locator('#training-live .training-time').nth(1)).to_have_attribute('data-active','true')
     ingest(track.pk,track.slug,packet(101,'r1c6|tn|39.750'))
     expect(page.locator('#training-live .training-time').nth(0).locator('.ideal-delta')).to_have_text('Te winnen 5.500s')
     expect(page.locator('#training-live .training-time').nth(0)).to_have_attribute('data-active','true')
     expect(page.locator('#training-live .training-time').nth(2)).to_have_attribute('data-active','false')
     expect(page.locator('.followed-training-row .training-row-time').nth(2).locator('.own-delta')).to_have_text('Δ eigen -6.000s')
     expect(page.locator('.followed-training-row .training-row-time').nth(2).locator('.ideal-delta')).to_have_text('Te winnen 1.000s')
     page.wait_for_function("getComputedStyle(document.querySelectorAll('#training-live .training-time')[0]).borderTopColor==='rgb(255, 180, 92)' && getComputedStyle(document.querySelectorAll('#training-live .training-time')[2].querySelector('b')).color==='rgb(168, 173, 184)'")
     page.wait_for_function("getComputedStyle(document.querySelector('.ideal-training-row')).backgroundColor==='rgba(0, 0, 0, 0)'")
     ingest(track.pk,track.slug,packet(102,'r4c8|tn|54.500\nr4c10|tn|54.500\nr4c11|in|4'))
     expect(page.locator('.training-rows-table tbody tr').filter(has_text='LEADER').first.locator('.training-row-time').nth(2).locator('.own-delta')).to_have_text('Δ eigen -0.500s')
     ingest(track.pk,track.slug,packet(103,'r4c8|tn|53.500\nr4c10|tn|53.500\nr4c11|in|5'))
     expect(page.locator('.followed-training-row')).to_have_attribute('data-lap-color','green')
     page.wait_for_function("getComputedStyle(document.querySelector('.followed-training-row')).borderLeftColor==='rgb(98, 223, 178)'")
     ingest(track.pk,track.slug,packet(104,'r1c7|tn|19.500\nr1c8|tn|55.000\nr1c11|in|6'))
     expect(page.locator('.training-potential [data-stat=ownBest] strong')).to_have_text('0:54.000')
     expect(page.locator('.training-potential [data-stat=lastToBest]')).to_have_count(0)
     expect(page.locator('.training-potential [data-stat=lastToIdeal]')).to_have_count(0)
     expect(page.locator('.training-potential [data-stat=idealLap] strong')).to_have_text('0:53.000')
     expect(page.locator('.training-potential [data-stat=bestToIdeal] strong')).to_have_text('1.000s')
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
     box=page.locator('.live-area').bounding_box();assert box['x']<=1 and box['y']<=1,box
     page.screenshot(path=f'/tmp/training-focus-{mobile}-{slow}.png',full_page=False)
     page.locator('.training-comparison').screenshot(path=f'/tmp/training-rows-{mobile}-{slow}.png')
     page.get_by_role('button',name='Verlaat fullscreen',exact=True).click();expect(page.locator('body')).not_to_have_class(re.compile('training-fullscreen'))
     ingest(track.pk,track.slug,packet(4,'r1c4|no7|25'));expect(page.locator('#training-live')).to_contain_text('Kart #25')
     page.get_by_role('button',name='Kart beoordelen',exact=True).click()
     expect(page.locator('#report-kart option')).to_have_count(2);page.locator('#report-kart').select_option('15')
     page.get_by_label('Acceleratie',exact=True).select_option('4');page.get_by_label('Balans',exact=True).select_option('2');page.locator('#report-conditions').select_option('wet');page.locator('#report-notes').fill('Goede motor; onderstuur bij insturen.')
     page.get_by_role('button',name='Verslag bewaren',exact=True).click();expect(page.locator('#report-status')).to_have_text('Verslag bewaard.')
     page.locator('#kart-dialog').get_by_role('button',name='Sluiten',exact=True).click()
     report=KartReport.objects.get(owner=user,track=track);assert report.kart=='15' and report.timing['lap']==54000
     page.get_by_role('button',name='Stop & bewaar',exact=True).click();expect(page.locator('#session-badge')).to_have_text('BEWAARD')
     page.goto('http://127.0.0.1:8215/live/sprint/');page.get_by_role('button',name='Kartverslagen',exact=True).click();page.locator('#library-circuit').select_option(str(track.pk));page.locator('#library-kart').fill('15');page.get_by_role('button',name='Zoeken',exact=True).click()
     expect(page.locator('#kart-report-list')).to_contain_text('Goede motor; onderstuur bij insturen.');expect(page.locator('#kart-report-list')).to_contain_text('Acceleratie: 4/5')
     page.locator('#kart-library').get_by_role('button',name='Sluiten',exact=True).click()
     page.locator('#sessions button').filter(has_text=name).click();page.wait_for_url(re.compile('/live/training/\\?session='));expect(page.locator('#training-dashboard')).to_be_visible()
     assert not errors,errors
     ctx.close();results.append(dict(mobile=mobile,slow=slow,fcp_ms=round(fcp),ok=True));print(results[-1],flush=True)
  finally:browser.close()
finally:
 KartReport.objects.filter(owner=user).delete();FollowSession.objects.filter(owner=user).delete();TimingTrack.objects.filter(pk__in=tracks).delete();user.delete()
 Path('/tmp/training-browser-results.json').write_text(json.dumps(results,indent=2))
