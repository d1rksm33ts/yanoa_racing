"""Local-only browser test of a server-paced recording simulation."""
import json
import os
import re
import secrets
import sys
import uuid
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
from playwright.sync_api import expect, sync_playwright
from www.live_models import FollowSession, TimingRecording, TimingSimulation, TimingTrack
from www.live_simulation import index_recording, create_simulation, control
from www.test_livecoach import GRID, lap, packet

if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':
    raise SystemExit('Local development SQLite database required')
root=Path(settings.LIVECOACH_RECORDINGS_DIR)
root.mkdir(parents=True,exist_ok=True)
path=root/('browser-'+secrets.token_hex(6)+'.ndjson')
events=[packet(0,'title2||QUALIFICATION\ngrid||'+GRID),packet(1,'title2||SIMULATED HEAT\ngrid||'+GRID),lap(2,'1:01.400',4),lap(3,'1:00.451',5),lap(4,'1:00.553',6),packet(5,'title2||NEXT\ngrid||'+GRID)]
path.write_text(''.join(json.dumps(e)+'\n' for e in events))
recording=index_recording(path,'Browser simulation '+secrets.token_hex(4))
password=secrets.token_urlsafe(24)
user=get_user_model().objects.create_superuser(username='sim-browser-'+secrets.token_hex(4),password=password)
results=[]
try:
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
        try:
            for mobile in [False,True]:
                for slow in [False,True]:
                    for _ in range(3):create_simulation(user,recording,0,uuid.uuid4())
                    context=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900})
                    page=context.new_page();errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:8210/live/login/?next=/live/sprint/')
                    page.get_by_label('Gebruikersnaam').fill(user.username)
                    page.get_by_label('Wachtwoord').fill(password)
                    page.get_by_role('button',name='Aanmelden',exact=True).click()
                    page.wait_for_url('http://127.0.0.1:8210/live/sprint/')
                    cdp=context.new_cdp_session(page)
                    cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
                    if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
                    page.reload(wait_until='domcontentloaded')
                    page.locator('summary').filter(has_text='Een opname simuleren').click()
                    expect(page.locator('#recording option').filter(has_text=recording.name)).to_have_count(1)
                    page.locator('#recording').select_option(str(recording.pk))
                    page.locator('#recording-segment').select_option('1')
                    page.get_by_role('button',name='Simulatie laden',exact=True).click()
                    expect(page.locator('#error')).to_contain_text('drie actieve simulaties')
                    expect(page.locator('#active-simulations').get_by_role('button',name='Stop deze simulatie',exact=True)).to_have_count(3)
                    page.locator('#active-simulations').get_by_role('button',name='Stop deze simulatie',exact=True).first.click()
                    expect(page.locator('#active-simulations').get_by_role('button',name='Stop deze simulatie',exact=True)).to_have_count(2)
                    expect(page.locator('#recording-segment')).to_have_value('1')
                    page.get_by_role('button',name='Simulatie laden',exact=True).click()
                    expect(page.locator('#simulation-panel')).to_be_visible()
                    expect(page.locator('#simulation-title')).to_contain_text('SIMULATED HEAT')
                    expect(page.locator('#track option').filter(has_text='Simulatie')).to_have_count(0)
                    expect(page.locator('#track option').filter(has_text='REPLAY')).to_have_count(0)
                    expect(page.locator('#track option').filter(has_text='Maroc Racing Kart Agadir')).to_have_count(1)
                    assert TimingSimulation.objects.filter(owner=user).latest('track_id').segment == 1
                    expect(page.locator('#simulation-status')).to_contain_text('Gepauzeerd')
                    expect(page.locator('#sim-play')).to_be_disabled()
                    page.locator('#track').select_option(label='Maroc Racing Kart Agadir')
                    expect(page.locator('#simulation-panel')).not_to_be_visible()
                    page.locator('#active-simulations .simulation-list-row').filter(has_text='SIMULATED HEAT').get_by_role('button',name='Open simulatie',exact=True).click()
                    expect(page.locator('#simulation-panel')).to_be_visible()
                    page.locator('#pilots').get_by_role('checkbox',name=re.compile('NOAH SMEETS')).check()
                    page.locator('#pilots').get_by_role('checkbox',name=re.compile('OTHER DRIVER')).check()
                    page.locator('#session-name').fill('Simulation browser test')
                    page.get_by_role('button',name='Start volgsessie').click()
                    expect(page.locator('.driver-card')).to_have_count(2)
                    page.reload(wait_until='domcontentloaded')
                    page.locator('#sessions button').filter(has_text='Simulation browser test').first.click()
                    expect(page.locator('#simulation-title')).to_contain_text('SIMULATED HEAT')
                    expect(page.locator('#track option').filter(has_text='Simulatie')).to_have_count(0)
                    page.get_by_role('button',name='Afspelen',exact=True).click()
                    expect(page.locator('.driver-card:first-child .lap-delta strong')).to_have_text('-0.949s',timeout=6000)
                    page.get_by_role('button',name='Pauzeren',exact=True).click()
                    expect(page.locator('#simulation-status')).to_contain_text('Gepauzeerd')
                    sim=TimingSimulation.objects.filter(owner=user).latest('track_id')
                    session=FollowSession.objects.get(owner=user,track_id=sim.track_id)
                    before=session.events.filter(kind='feedback').count()
                    page.wait_for_timeout(1200)
                    assert session.events.filter(kind='feedback').count()==before==2
                    page.locator('#sim-speed').select_option('2')
                    page.get_by_role('button',name='Afspelen',exact=True).click()
                    expect(page.locator('.driver-card:first-child .lap-delta strong')).to_have_text('+0.102s',timeout=4000)
                    expect(page.locator('#simulation-status')).to_contain_text('Afgelopen',timeout=4000)
                    expect(page.locator('#connect')).to_have_text('Simulatie geladen')
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.get_by_role('button',name='Opnieuw beginnen',exact=True).click()
                    expect(page.locator('.driver-card:first-child .lap-delta strong')).to_have_text('—')
                    page.locator('#sim-speed').select_option('5')
                    page.get_by_role('button',name='Afspelen',exact=True).click()
                    expect(page.locator('#simulation-status')).to_contain_text('Afgelopen',timeout=4000)
                    expect(page.locator('.driver-card:first-child .lap-delta strong')).to_have_text('+0.102s')
                    assert session.events.filter(kind='feedback').count()==6
                    assert session.drivers.get(primary=True).block==2
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    assert not errors,errors
                    page.screenshot(path=f'/tmp/livecoach-simulation-{mobile}-{slow}.png',full_page=True)
                    page.get_by_role('button',name='Stop & bewaar').click()
                    expect(page.locator('#session-badge')).to_have_text('BEWAARD')
                    context.close()
                    for sim in TimingSimulation.objects.filter(owner=user,state__in=['paused','playing']):control(sim.pk,user,'stop')
                    results.append({'mobile':mobile,'slow':slow,'ok':True})
                    print(results[-1],flush=True)
        finally:browser.close()
finally:
    FollowSession.objects.filter(owner=user).delete()
    TimingTrack.objects.filter(owner=user).delete()
    user.delete();recording.delete();path.unlink(missing_ok=True)
    Path('/tmp/livecoach-simulation-results.json').write_text(json.dumps(results,indent=2))
