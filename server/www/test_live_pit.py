import copy
import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .live_core import ApexAdapter
from .live_pit import forecast, validate_settings
from .live_models import TimingTrack, FollowSession, FollowDriver, CoachEvent
from .live_service import ingest, snapshot
from .test_livecoach import packet

# Goodwill race schema: two sectors and an untyped official lap column.
HEADERS=[('c2','rk','Pos.'),('c3','sta',''),('c4','no','Kart'),('c5','dr','Piloot'),('c6','s1','S1'),('c7','s2','S2'),('c8','llp','Ronde'),('c9','gap','Verschil'),('c10','blp','Beste'),('c11','','Rondes'),('c12','','Totale pit tijd'),('c13','pit','Pit')]
GRID='<tbody><tr class="head">'+''.join(f'<td data-id="{c}" data-type="{t}">{label}</td>' for c,t,label in HEADERS)+'</tr><tr data-id="r1" data-pos="2">'+''.join(f'<td data-id="r1{c}">{dict(c2="2",c4="15",c5="SMEETS Noah",c8="1:00.000",c9="2.000",c10="1:00.000",c11="3",c13="0").get(c,"")}</td>' for c,_,_ in HEADERS)+'</tr></tbody>'


def feed(adapter, seq, payload, seconds=None):
    event=packet(seq,payload)
    if seconds is not None:event['originalReceivedAt']=(timezone.now().replace(microsecond=0)+timedelta(seconds=seconds)).isoformat()
    return adapter.apply(event)


class PitProtocolTests(SimpleTestCase):
    def test_legacy_identity_survives_kart_change_snapshot_but_not_name_change(self):
        a=ApexAdapter();feed(a,0,'title2||Race\ngrid||'+GRID)
        initial=a.entrants()[0]['identity']
        legacy=copy.deepcopy(a.state)
        for row in legacy['rows'].values():row.pop('identity_scope',None);row.pop('driver_identity',None)
        a=ApexAdapter(legacy)
        self.assertEqual(a.entrants()[0]['identity'],initial)
        feed(a,1,'r1c4|no7|25')
        self.assertEqual(a.entrants()[0]['identity'],initial)
        feed(a,2,'init||\ngrid||'+GRID.replace('>15<','>25<'))
        self.assertEqual(a.entrants()[0]['identity'],initial)
        feed(a,3,'r1c5||OTHER DRIVER')
        self.assertNotEqual(a.entrants()[0]['identity'],initial)

    def test_new_race_never_inherits_previous_pit_or_pace_data(self):
        a=ApexAdapter();feed(a,0,'title2||Race 1\ngrid||'+GRID)
        a.state['rows']['r1'].update(pit_samples=[{'bypassFraction':.3}],recent_laps=[{'timeMs':60000,'kart':'15'}],completed_pits=1)
        feed(a,1,'title2||Race 2\ngrid||'+GRID)
        row=a.standings()[0]
        self.assertEqual((row['pitSamples'],row['recentLaps'],row['pitCount']),([],[],0))

    def test_pit_entry_exit_measurement_and_no_dirty_sector_references(self):
        a=ApexAdapter();feed(a,0,'title2||Race\ngrid||'+GRID,0)
        clean=feed(a,1,'r1c6|tn|40.000\nr1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4',60)
        self.assertEqual([(p['metric'],p['lap']) for p in clean],[('S1',5),('S2',4),('lap',4)])
        self.assertEqual(a.sector_ids(),['S1','S2'])
        feed(a,2,'r1c13|in|1\nr1|*in|0',65)
        self.assertEqual(a.standings()[0]['pitCount'],0)
        feed(a,3,'r1c4|no7|25',80)
        feed(a,4,'r1|*out|0',155)
        self.assertEqual(a.standings()[0]['pitCount'],1)
        dirty=feed(a,5,'r1c6|tn|1:50.000\nr1c7|tn|20.000\nr1c8|tn|2:12.000\nr1c11|in|5',192)
        self.assertEqual([p['metric'] for p in dirty],['lap'])
        self.assertTrue(dirty[0]['pitLap'])
        sample=a.standings()[0]['pitSamples'][0]
        self.assertEqual((sample['pitMs'],sample['lossMs']),(90000,72000))
        self.assertAlmostEqual(sample['bypassFraction'],0.3)
        self.assertEqual(len(a.standings()[0]['recentLaps']),1)
        next_lap=feed(a,6,'r1c6|tn|39.000\nr1c7|tn|20.000\nr1c8|tn|59.000\nr1c11|in|6',251)
        self.assertFalse(next_lap[-1]['pitLap'])


class ForecastTests(SimpleTestCase):
    def rows(self):
        return [dict(identity=str(i),position=i+1,kart='1',gap=f'{i*10}.000' if i else '',pitCount=0,
                     recentLaps=[{'kart':'1','timeMs':60000}]*6) for i in range(5)]
    def test_manual_loss_temporary_vs_corrected_and_no_double_pit_penalty(self):
        rows=self.rows();rows[0]['pitCount']=1
        result=forecast(rows,rows[1],dict(durationSeconds=90,requiredStops=1,netLossSeconds=25))
        self.assertEqual(result['temporaryPosition'],dict(best=4,worst=4))
        self.assertEqual(result['correctedPosition'],dict(best=2,worst=2))
        rows[1]['pitCount']=1
        self.assertEqual(forecast(rows,rows[1],dict(durationSeconds=90,requiredStops=1,netLossSeconds=25))['status'],'complete')
    def test_unknown_lapped_gap_is_a_range_not_a_fake_zero(self):
        rows=self.rows();rows[-1]['gap']='1 Ronde'
        r=forecast(rows,rows[1],dict(durationSeconds=90,requiredStops=1,netLossSeconds=25))
        self.assertEqual(r['temporaryPosition'],dict(best=4,worst=5))
        self.assertEqual(forecast(rows,rows[-1],dict(durationSeconds=90,requiredStops=1,netLossSeconds=25))['status'],'unknown-gap')
    def test_auto_needs_three_past_samples_and_uses_current_pace(self):
        rows=self.rows();settings=dict(durationSeconds=90,requiredStops=1,netLossSeconds=None)
        self.assertEqual(forecast(rows,rows[1],settings)['status'],'uncalibrated')
        rows[0]['pitSamples']=[dict(bypassFraction=.3)]*3
        r=forecast(rows,rows[1],settings)
        self.assertEqual((r['lossMinMs'],r['lossMaxMs']),(69000,75000))
    def test_drying_trend_excludes_pre_kart_change_samples(self):
        rows=self.rows()
        for row in rows:row['recentLaps']=[{'kart':'1','timeMs':x} for x in [70000]*3+[60000]*3]
        settings=dict(durationSeconds=90,requiredStops=1,netLossSeconds=72)
        r=forecast(rows,rows[1],settings)
        self.assertEqual(r['trendMs'],-10000)
        self.assertIn('Eerder pitten',r['strategy'])
        for row in rows:row['kart']='2'
        self.assertNotIn('trendMs',forecast(rows,rows[1],settings))
    def test_bad_settings_rejected(self):
        for bad in [float('nan'),float('inf'),True,-1,1801]:
            with self.assertRaises(ValueError):validate_settings(dict(durationSeconds=bad,requiredStops=1))


@override_settings(SECURE_SSL_REDIRECT=False,SESSION_COOKIE_SECURE=False)
class KartPersistenceTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(username='pit-test',password='test-only-password')
        self.track=TimingTrack.objects.create(slug='pit-test',name='Goodwill',source_id='goodwill',connection='connected')
        ingest(self.track.pk,'pit-test',packet(0,'title2||Race\ngrid||'+GRID))
        self.track.refresh_from_db()
        self.session=FollowSession.objects.create(owner=self.user,track=self.track,name='Noah')
        self.driver=FollowDriver.objects.create(session=self.session,**{k:v for k,v in self.track.entrants[0].items() if k in {'name','kart','identity'}},best={'lap':60000,'S1':40000,'S2':20000})
        self.client.force_login(self.user)
    def test_references_and_last_lap_persist_across_kart_swap_and_new_laps(self):
        ingest(self.track.pk,'pit-test',packet(1,'r1c4|no7|25'))
        self.driver.refresh_from_db();self.assertEqual(self.driver.kart,'25');self.assertEqual(self.driver.best['lap'],60000)
        ingest(self.track.pk,'pit-test',packet(2,'r1c6|tn|40.102\nr1c7|tn|20.000\nr1c8|tn|1:00.102\nr1c11|in|4'))
        self.driver.refresh_from_db();self.assertEqual(self.driver.last['byMetric']['lap']['deltaText'],'+0.102s')
        ingest(self.track.pk,'pit-test',packet(3,'r1c6|tn|39.051\nr1c7|tn|20.000\nr1c8|tn|59.051\nr1c11|in|5'))
        self.driver.refresh_from_db();self.assertEqual(self.driver.best['lap'],59051)
        self.assertEqual(self.driver.last['byMetric']['lap']['deltaText'],'-0.949s')
        state=self.client.get(f'/live/api/sessions/{self.session.pk}/').json()
        self.assertEqual(state['pitSettings']['durationSeconds'],90)
        self.assertEqual(state['track']['capabilities']['sectorIds'],['S1','S2'])
    def test_upgrade_recovers_a_verified_legacy_selection_after_an_existing_swap(self):
        self.track.refresh_from_db()
        state=self.track.parser_state
        state['rows']['r1']['cells']['c4']='25'
        state['rows']['r1'].pop('identity_scope',None)
        state['rows']['r1'].pop('driver_identity',None)
        self.track.parser_state=state
        self.track.save(update_fields=['parser_state'])
        ingest(self.track.pk,'pit-test',packet(1,'r1c6|tn|40.102'))
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.kart,'25')
        self.assertEqual(self.driver.best['lap'],60000)
        self.assertEqual(self.driver.last['deltaText'],'+0.102s')
        self.assertTrue(self.client.get(f'/live/api/sessions/{self.session.pk}/').json()['drivers'][0]['present'])

    def add_other(self):
        self.track.refresh_from_db()
        adapter=ApexAdapter(self.track.parser_state)
        other=copy.deepcopy(adapter.state['rows']['r1'])
        other['cells'].update(c2='1',c4='7',c5='OTHER DRIVER')
        other['position']=1
        adapter.state['rows']['r2']=other
        self.track.entrants=adapter.entrants()
        self.track.parser_state=adapter.state
        self.track.save(update_fields=['entrants','parser_state'])
        entrant=next(e for e in self.track.entrants if e['name']=='OTHER DRIVER')
        return FollowDriver.objects.create(session=self.session,**{k:v for k,v in entrant.items() if k in {'name','kart','identity'}})

    def test_pit_prediction_is_independent_for_every_driver_and_survives_updates(self):
        other=self.add_other()
        url=f'/live/api/sessions/{self.session.pk}/action/'
        def toggle(driver,enabled):return self.client.post(url,json.dumps(dict(action='driver-pit',driverId=driver.pk,enabled=enabled,requestId=str(uuid.uuid4()))),content_type='application/json')
        initial=self.client.get(f'/live/api/sessions/{self.session.pk}/').json()
        self.assertTrue(all(not d['pitEnabled'] and d['pit'] is None for d in initial['drivers']))
        response=toggle(other,True)
        self.assertEqual(response.status_code,200)
        by_id={d['id']:d for d in response.json()['drivers']}
        self.assertTrue(by_id[other.pk]['pitEnabled'])
        self.assertIsNotNone(by_id[other.pk]['pit'])
        self.assertEqual(by_id[other.pk]['position'],1)
        self.assertIsNone(by_id[self.driver.pk]['pit'])
        self.assertEqual(by_id[self.driver.pk]['position'],2)
        self.assertEqual(toggle(self.driver,True).status_code,200)
        self.assertEqual(toggle(other,False).status_code,200)
        self.assertEqual(toggle(other,'true').status_code,400)
        selected=[self.driver.identity,other.identity]
        response=self.client.post(url,json.dumps(dict(action='drivers',drivers=selected,requestId=str(uuid.uuid4()))),content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.driver.refresh_from_db();other.refresh_from_db()
        self.assertTrue(self.driver.pit_enabled)
        self.assertFalse(other.pit_enabled)
        self.assertEqual(self.driver.best['lap'],60000)
        foreign=FollowSession.objects.create(owner=self.user,track=self.track,name='Other session')
        foreign_driver=FollowDriver.objects.create(session=foreign,identity='x'*64,name='Unrelated')
        self.assertEqual(toggle(foreign_driver,True).status_code,404)
        self.assertFalse(FollowDriver.objects.get(pk=foreign_driver.pk).pit_enabled)

    def test_older_web_or_worker_code_can_insert_without_the_new_pit_column(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO www_followdriver (session_id,identity,name,kart,"primary",block,best,last) SELECT session_id,%s,name,kart,"primary",block,best,last FROM www_followdriver WHERE id=%s RETURNING pit_enabled', ['z'*64,self.driver.pk])
            self.assertFalse(cursor.fetchone()[0])

    def test_kart_history_shows_previous_reference_and_supports_older_workers(self):
        ingest(self.track.pk,'pit-test',packet(1,'r1c4|no7|25'))
        state=self.client.get(f'/live/api/sessions/{self.session.pk}/').json()
        self.assertEqual(state['drivers'][0]['kart'],'25')
        self.assertEqual(state['drivers'][0]['kartHistory'],[{'kart':'15','best':{'lap':60000,'S1':40000,'S2':20000}}])
        CoachEvent.objects.create(session=self.session,driver=self.driver,kind='kart',payload={'message':'Kartwissel #25 → #30; besttijden behouden.'})
        state=self.client.get(f'/live/api/sessions/{self.session.pk}/').json()
        self.assertEqual([old['kart'] for old in state['drivers'][0]['kartHistory']],['15','25'])

    def test_pit_settings_owned_and_persisted(self):
        url=f'/live/api/sessions/{self.session.pk}/action/'
        def post(settings):return self.client.post(url,json.dumps(dict(action='pit',requestId=str(uuid.uuid4()),settings=settings)),content_type='application/json')
        self.assertEqual(post(dict(durationSeconds=90,requiredStops=1,netLossSeconds=72)).status_code,200)
        self.session.refresh_from_db();self.assertEqual(self.session.pit_settings['netLossSeconds'],72)
        self.assertEqual(post(dict(durationSeconds=-1,requiredStops=1)).status_code,400)
        other=get_user_model().objects.create_user(username='other-pit',password='test-only-password',is_superuser=True,is_staff=True)
        self.client.force_login(other)
        self.assertEqual(post(dict(durationSeconds=90,requiredStops=1)).status_code,404)
