"""Local-only: stop any of five active sessions without opening it first."""
import os
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
from www.live_models import TimingTrack,FollowSession,FollowDriver
if not settings.DEBUG or settings.DATABASES['default']['ENGINE']!='django.db.backends.sqlite3':raise SystemExit('Local SQLite required')
password=secrets.token_urlsafe(24)
user=get_user_model().objects.create_superuser(username='session-controls-'+secrets.token_hex(4),password=password)
track=TimingTrack.objects.create(owner=user,slug='controls-'+secrets.token_hex(4),name='Session controls QA',source_id='replay',mode='replay')
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
        try:
            for mobile in [False,True]:
                for slow in [False,True]:
                    FollowSession.objects.filter(owner=user).delete()
                    for i in range(5):
                        session=FollowSession.objects.create(owner=user,track=track,name=f'Active trial {i+1}')
                        FollowDriver.objects.create(session=session,identity=secrets.token_hex(32),name='Noah',kart='13',best={'lap':60123},last={'metric':'lap','timeMs':60123},primary=True)
                    context=browser.new_context(viewport={'width':390 if mobile else 1365,'height':844 if mobile else 900})
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:8210/live/login/?next=/live/sprint/')
                    page.get_by_label('Gebruikersnaam').fill(user.username);page.get_by_label('Wachtwoord').fill(password)
                    page.get_by_role('button',name='Aanmelden',exact=True).click();page.wait_for_url('http://127.0.0.1:8210/live/sprint/')
                    cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
                    if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
                    page.reload(wait_until='domcontentloaded')
                    expect(page.locator('#active-sessions-panel')).to_be_visible()
                    expect(page.locator('#active-session-count')).to_have_text('5 / 5')
                    expect(page.locator('#active-name')).to_have_text('Klaar voor de start')
                    first=page.locator('.active-session-row').first
                    discarded=first.get_attribute('data-session-id')
                    first.get_by_role('button',name='Bekijken',exact=True).click()
                    expect(page.locator('#active-name')).to_have_text('Active trial 1')
                    page.once('dialog',lambda dialog:dialog.dismiss())
                    page.locator('#discard').click()
                    expect(page.locator('.active-session-row')).to_have_count(5)
                    assert FollowSession.objects.filter(pk=discarded).exists()
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.locator('#discard').click()
                    expect(page.locator('.active-session-row')).to_have_count(4)
                    assert not FollowSession.objects.filter(pk=discarded).exists()
                    expect(page.locator('#active-name')).to_have_text('Klaar voor de start')
                    second=page.locator('.active-session-row').first
                    discarded_second=second.get_attribute('data-session-id')
                    page.once('dialog',lambda dialog:dialog.accept())
                    second.get_by_role('button',name='Stop zonder bewaren',exact=True).click()
                    expect(page.locator('.active-session-row')).to_have_count(3)
                    assert not FollowSession.objects.filter(pk=discarded_second).exists()
                    for remaining in [2,1,0]:
                        row=page.locator('.active-session-row').first
                        identity=row.get_attribute('data-session-id')
                        row.get_by_role('button',name='Stop & bewaar',exact=True).click()
                        expect(page.locator('.active-session-row')).to_have_count(remaining)
                        saved=FollowSession.objects.get(pk=identity)
                        assert saved.state=='stopped'
                        assert saved.drivers.get().best['lap']==60123
                        if remaining==2:page.screenshot(path=f'/tmp/livecoach-stop-{mobile}-{slow}.png',full_page=True)
                    expect(page.locator('#active-sessions-panel')).to_be_hidden()
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    assert not errors,errors
                    print({'mobile':mobile,'slow':slow,'saved':3,'discarded':2,'cancel_preserves_data':True},flush=True)
                    context.close()
        finally:browser.close()
finally:
    FollowSession.objects.filter(owner=user).delete();track.delete();user.delete()
