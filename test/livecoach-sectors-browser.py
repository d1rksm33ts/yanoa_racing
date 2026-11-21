"""Local-only UI proof: actual APEX sector layout, selected deltas and finish."""
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
from www.live_simulation import index_recording
from www.test_livecoach import packet
from www.test_live_passages import SECTOR_GRID

if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':raise SystemExit('Local SQLite required')
root=Path(settings.LIVECOACH_RECORDINGS_DIR);root.mkdir(parents=True,exist_ok=True)
path=root/('sector-browser-'+secrets.token_hex(5)+'.ndjson')
payloads=['title2||SECTOR TEST\nlight|lg|\ngrid||'+SECTOR_GRID,'r1c6|ti|26.500','r1c7|ti|35.300',
          'r1c8|ti|22.000\nr1c9|ti|1:23.800\nr1c13|in|4','r1c6|tn|26.400','r1c7|tn|35.402',
          'r1c8|tn|21.051\nr1c9|tn|1:22.853\nr1c13|in|5','light|lf|\nr1c2|sf|','title2||NEXT\ngrid||'+SECTOR_GRID]
path.write_text(''.join(json.dumps(packet(i,p))+'\n' for i,p in enumerate(payloads)))
recording=index_recording(path,'Sector browser '+secrets.token_hex(4))
password=secrets.token_urlsafe(24)
user=get_user_model().objects.create_superuser(username='sectors-'+secrets.token_hex(4),password=password)
results=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
        try:
            for mobile in [False,True]:
                for slow in [False,True]:
                    context=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900})
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:8210/live/login/?next=/live/sprint/')
                    page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password)
                    page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8210/live/sprint/')
                    cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
                    if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
                    page.reload(wait_until='domcontentloaded')
                    page.locator('summary').filter(has_text='Een opname simuleren').click()
                    expect(page.locator('#recording option').filter(has_text=recording.name)).to_have_count(1)
                    page.locator('#recording').select_option(str(recording.pk));page.locator('#recording-segment').select_option('0')
                    page.get_by_role('button',name='Simulatie laden',exact=True).click()
                    expect(page.locator('#simulation-panel')).to_be_visible()
                    page.locator('#pilots').get_by_role('checkbox',name=re.compile('NOAH SMEETS')).check()
                    page.get_by_role('button',name='Start volgsessie').click()
                    expect(page.locator('#standings .standing-row')).to_have_count(2)
                    expect(page.locator('#standings .selected-driver')).to_have_count(1)
                    page.locator('#sim-speed').select_option('2')
                    expect(page.locator('#simulation-status')).to_contain_text('2×')
                    page.get_by_role('button',name='Afspelen',exact=True).click()
                    strip=page.locator('.driver-card:first-child .sector-strip')
                    expect(strip.locator('div').nth(0).locator('small')).to_have_text('-0.100s',timeout=7000)
                    expect(strip.locator('div').nth(1).locator('small')).to_have_text('+0.102s',timeout=4000)
                    expect(strip.locator('div').nth(2).locator('small')).to_have_text('-0.949s',timeout=4000)
                    expect(page.locator('#finish-banner')).to_be_visible(timeout=4000)
                    expect(page.locator('.driver-card:first-child .driver-finish')).to_have_text('🏁 FINISH')
                    expect(page.locator('#standings .selected-driver')).to_contain_text('-0.949s')
                    expect(page.locator('#history')).to_contain_text('Finishvlag')
                    page.locator('#only-selected').check();expect(page.locator('#standings .standing-row')).to_have_count(1)
                    page.locator('#only-selected').uncheck();expect(page.locator('#standings .standing-row')).to_have_count(2)
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    assert not errors,errors
                    page.screenshot(path=f'/tmp/livecoach-sectors-{mobile}-{slow}.png',full_page=True)
                    page.get_by_role('button',name='Stop & bewaar').click();expect(page.locator('#session-badge')).to_have_text('BEWAARD')
                    context.close();results.append({'mobile':mobile,'slow':slow,'ok':True});print(results[-1],flush=True)
        finally:browser.close()
finally:
    FollowSession.objects.filter(owner=user).delete();TimingTrack.objects.filter(owner=user).delete()
    user.delete();recording.delete();path.unlink(missing_ok=True)
    Path('/tmp/livecoach-sectors-results.json').write_text(json.dumps(results,indent=2))
