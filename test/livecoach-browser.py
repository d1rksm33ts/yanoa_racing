"""Local-only, isolated fixtures: real forms, SSE, desktop/mobile and slow loading.

Run with the Django ASGI preview at 127.0.0.1:8210 and an isolated development DB.
Uses the installed Chrome when the Browser plugin has no available browser.
"""
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SECURE_COOKIES", "false")
# Playwright's synchronous driver owns an event loop in this single-threaded
# test process. Fixture DB calls are sequential; the web server is another process.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright
from www.live_models import CoachEvent, FollowSession, TimingTrack
from www.live_service import ingest
from www.test_livecoach import GRID, lap, packet

if not settings.DEBUG or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    raise SystemExit("Local SQLite development environment required")

BASE = "http://127.0.0.1:8210"
password = secrets.token_urlsafe(24)
user = get_user_model().objects.create_superuser(username="browser-" + secrets.token_hex(5), password=password)
created_tracks = []
results = []
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
        try:
            for mobile in [False, True]:
                for slow in [False, True]:
                    track = TimingTrack.objects.create(slug="qa-" + secrets.token_hex(5), name="Replay QA", source_id="replay", mode="replay")
                    created_tracks.append(track.pk)
                    recording = "qa-" + str(track.pk)
                    ingest(track.pk, recording, {"type":"connection","state":"connected","seq":0,"receivedAt":timezone.now().isoformat()})
                    ingest(track.pk, recording, packet(1,"title2||BROWSER REPLAY\ngrid||"+GRID))
                    track.refresh_from_db()
                    context = browser.new_context(viewport={"width":390 if mobile else 1365,"height":844 if mobile else 900})
                    page = context.new_page()
                    errors=[]
                    page.on("pageerror",lambda error:errors.append(str(error)))
                    page.goto(BASE+'/live/login/?next=/live/')
                    page.get_by_label("Gebruikersnaam").fill(user.username)
                    page.get_by_label("Wachtwoord").fill(password)
                    page.get_by_role('button',name='Aanmelden',exact=True).click()
                    page.wait_for_url(BASE+'/live/')
                    cdp=context.new_cdp_session(page)
                    cdp.send('Network.enable')
                    cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
                    if slow:
                        cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':100000})
                    page.goto(BASE+'/live/',wait_until='domcontentloaded')
                    page.wait_for_function("performance.getEntriesByName('first-contentful-paint').length > 0")
                    fcp=page.evaluate("Math.round(performance.getEntriesByName('first-contentful-paint')[0].startTime)")
                    assert fcp <= (3000 if slow else 2000),fcp
                    expect(page.locator('#track option').filter(has_text='Replay QA')).not_to_have_count(0)
                    page.locator('#track').select_option(str(track.pk))
                    expect(page.locator('#source-status')).to_contain_text('Niet verbonden')
                    page.get_by_role('button',name='Verbinden',exact=True).click()
                    expect(page.locator('#source-status')).to_contain_text('verbonden')
                    page.locator('#pilots').get_by_role('checkbox',name=re.compile('NOAH SMEETS')).check()
                    page.locator('#session-name').fill('Browser live test')
                    page.get_by_role('button',name='Start volgsessie').click()
                    expect(page.locator('.driver-card')).to_have_count(1)
                    expect(page.locator('#standings .standing-row')).to_have_count(2)
                    expect(page.locator('#standings .selected-driver')).to_have_count(1)
                    expect(page.locator('#live-status')).to_contain_text('Live verbonden')
                    session=FollowSession.objects.get(owner=user,track=track)
                    ingest(track.pk,recording,lap(2,'1:01.400',4))
                    expect(page.locator('.driver-card:first-child .delta')).to_have_text('Referentie')
                    started=time.perf_counter()
                    ingest(track.pk,recording,lap(3,'1:01.200',5))
                    expect(page.locator('.driver-card:first-child .delta')).to_have_text('-0.200s',timeout=2000)
                    displayed_ms=round((time.perf_counter()-started)*1000)
                    assert displayed_ms < 1500,displayed_ms
                    page.locator('#pilots').get_by_role('checkbox',name=re.compile('OTHER DRIVER')).check()
                    page.get_by_role('button',name='Update piloten',exact=True).click()
                    expect(page.locator('.driver-card')).to_have_count(2)
                    expect(page.locator('.driver-card:first-child .delta')).to_have_text('-0.200s')
                    page.locator('#only-selected').check()
                    expect(page.locator('#standings .standing-row')).to_have_count(2)
                    page.locator('#pilots').get_by_role('checkbox',name=re.compile('OTHER DRIVER')).uncheck()
                    page.get_by_role('button',name='Update piloten',exact=True).click()
                    expect(page.locator('.driver-card')).to_have_count(1)
                    expect(page.locator('.driver-card:first-child .delta')).to_have_text('-0.200s')
                    expect(page.locator('#standings .standing-row')).to_have_count(1)
                    page.locator('#only-selected').uncheck()
                    expect(page.locator('#standings .standing-row')).to_have_count(2)
                    page.locator('#pilots').get_by_role('checkbox',name=re.compile('OTHER DRIVER')).check()
                    page.get_by_role('button',name='Update piloten',exact=True).click()
                    expect(page.locator('.driver-card')).to_have_count(2)
                    # Screen/connection restoration shows persisted references, without re-starting.
                    page.reload(wait_until='domcontentloaded')
                    page.get_by_role('button',name='Browser live test').first.click()
                    expect(page.locator('.driver-card:first-child .delta')).to_have_text('-0.200s')
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.get_by_role('button',name='Reset',exact=True).first.click()
                    expect(page.locator('.driver-card:first-child .delta')).to_have_text('—')
                    assert CoachEvent.objects.filter(session=session,kind='feedback').count()==2
                    ingest(track.pk,recording,lap(4,'1:01.100',6))
                    expect(page.locator('.driver-card:first-child .delta')).to_have_text('Referentie')
                    page.screenshot(path=f'/tmp/livecoach-{mobile}-{slow}.png',full_page=True)
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),'Horizontal overflow'
                    page.get_by_role('button',name='Stop & bewaar').click()
                    expect(page.locator('#session-badge')).to_have_text('BEWAARD')
                    before=CoachEvent.objects.filter(session=session,kind='feedback').count()
                    ingest(track.pk,recording,lap(5,'1:00.000',7))
                    assert CoachEvent.objects.filter(session=session,kind='feedback').count()==before
                    assert not errors,errors
                    results.append({'mobile':mobile,'slow':slow,'fcp_ms':fcp,'ingest_to_display_ms':displayed_ms,'ok':True})
                    print(results[-1],flush=True)
                    context.close()
            # A direct server-rendered summary remains available without JavaScript.
            context=browser.new_context(java_script_enabled=False)
            page=context.new_page()
            page.goto(BASE+'/live/login/?next=/live/samenvattingen/')
            page.get_by_label('Gebruikersnaam').fill(user.username)
            page.get_by_label('Wachtwoord').fill(password)
            page.get_by_role('button',name='Aanmelden',exact=True).click()
            expect(page.get_by_role('heading',name='Bewaarde sessies')).to_be_visible()
            expect(page.get_by_text('Browser live test',exact=True)).to_have_count(4)
            context.close()
        finally:
            browser.close()
finally:
    FollowSession.objects.filter(owner=user).delete()
    TimingTrack.objects.filter(pk__in=created_tracks).delete()
    user.delete()
    Path('/tmp/livecoach-browser-results.json').write_text(json.dumps(results,indent=2))
