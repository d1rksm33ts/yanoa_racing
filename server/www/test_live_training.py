import json
import uuid
from types import SimpleNamespace
from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model
from .live_core import ApexAdapter
from .live_models import FollowSession, FollowDriver, TimingTrack, TimingConnection, CoachEvent, KartReport
from .live_service import ingest, snapshot
from .live_training import training_comparison
from .test_livecoach import packet
from .test_live_pit import GRID


class TrainingComparisonTests(SimpleTestCase):
    def test_neighbors_use_best_lap_instead_of_race_positions_and_fastest_sectors(self):
        driver=SimpleNamespace(identity='own',kart='15',best={'lap':61000,'S1':40000})
        rows=[dict(identity='own',name='Noah',kart='15',position=30,bestLapMs=61000,sectorBests={'S1':40000},recentLaps=[{'kart':'15','timeMs':62000},{'kart':'15','timeMs':61000},{'kart':'15','timeMs':63000},{'kart':'7','timeMs':50000}]),
              dict(identity='fast',name='Fast',kart='1',position=20,bestLapMs=59000,sectorBests={'S1':39500}),
              dict(identity='near',name='Nearest faster',kart='2',position=18,bestLapMs=60500,sectorBests={'S1':40500}),
              dict(identity='slow',name='Nearest slower',kart='3',position=1,bestLapMs=61500,sectorBests={'S1':41000})]
        result=training_comparison(driver,rows,{'lap':59000,'S1':39000})
        self.assertEqual(result['comparisons'][0]['name'],'Nearest faster')
        self.assertEqual(result['comparisons'][1]['name'],'Nearest slower')
        self.assertEqual(result['comparisons'][0]['deltas'],{'lap':500,'S1':-500})
        self.assertEqual(result['comparisons'][2]['deltas']['S1'],1000)
        self.assertEqual(result['paceMs'],62000)
        self.assertEqual(result['paceLaps'],3)
    def test_disappeared_driver_is_not_compared_with_another_baansession(self):
        driver=SimpleNamespace(identity='missing',kart='15',best={'lap':61000})
        result=training_comparison(driver,[],{'lap':59000})
        self.assertFalse(result['present'])
        self.assertEqual(result['comparisons'][2]['deltas'],{})


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class TrainingAPITests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(username='training',password='test-only')
        self.client.force_login(self.user)
        self.track=TimingTrack.objects.create(slug='training-track',name='Training track',source_id='goodwill',connection='connected')
        ingest(self.track.pk,'training',packet(0,'title2||TRAINING\ngrid||'+GRID))
        self.track.refresh_from_db()
        self.identity=self.track.entrants[0]['identity']
        TimingConnection.objects.create(owner=self.user,track=self.track)
    def post(self,path,data):
        return self.client.post(path,json.dumps(data),content_type='application/json')
    def start(self):
        response=self.post('/live/api/start/',dict(requestId=str(uuid.uuid4()),trackId=self.track.pk,drivers=[self.identity],name='Training Noah',activity='training'))
        self.assertEqual(response.status_code,201)
        return FollowSession.objects.get(pk=response.json()['id'])
    def data(self,session):
        return dict(requestId=str(uuid.uuid4()),driverId=session.drivers.get().pk,trackId=self.track.pk,kart='15',conditions='wet',scores={'acceleration':4,'balance':2},notes='Onderstuur bij insturen')
    def test_modes_and_training_snapshot_are_separate_from_sprint(self):
        page=self.client.get('/live/')
        for link in ['/live/training/','/live/sprint/','/live/endurance/']:self.assertContains(page,link)
        self.assertContains(self.client.get('/live/training/'),'training-provider')
        session=self.start()
        self.assertEqual(snapshot(session)['activity'],'training')
        self.assertIn('training',snapshot(session))
        self.assertEqual(FollowSession._meta.get_field('activity').db_default,'sprint')
    def test_training_rejects_multiple_pilots_and_invalid_kind(self):
        request=dict(requestId=str(uuid.uuid4()),trackId=self.track.pk,drivers=[self.identity,self.identity],activity='training')
        self.assertEqual(self.post('/live/api/start/',request).status_code,400)
        request.update(drivers=[self.identity],activity='unknown')
        self.assertEqual(self.post('/live/api/start/',request).status_code,400)
        session=self.start()
        self.assertEqual(self.post(f'/live/api/sessions/{session.pk}/action/',dict(action='drivers',requestId=str(uuid.uuid4()),drivers=[self.identity,self.identity])).status_code,400)
    def test_report_is_idempotent_and_survives_kart_change_and_session_deletion(self):
        session=self.start();driver=session.drivers.get()
        ingest(self.track.pk,'training',packet(1,'r1c6|tn|40.000'))
        ingest(self.track.pk,'training',packet(2,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'))
        ingest(self.track.pk,'training',packet(3,'r1c4|no7|25'))
        driver.refresh_from_db();self.assertEqual(driver.kart,'25')
        data=self.data(session);url=f'/live/api/sessions/{session.pk}/kart-reports/'
        response=self.post(url,data);self.assertEqual(response.status_code,201)
        report=KartReport.objects.get(pk=response.json()['id'])
        self.assertEqual(report.kart,'15');self.assertEqual(report.timing['lap'],60000)
        self.assertEqual(report.template['version'],1)
        self.assertEqual(self.post(url,data).json()['id'],str(report.pk))
        self.assertEqual(KartReport.objects.count(),1)
        session.delete();report.refresh_from_db();self.assertIsNone(report.session_id)
        records=self.client.get('/live/api/kart-reports/',{'trackId':self.track.pk,'kart':'15'}).json()['reports']
        self.assertEqual(records[0]['notes'],'Onderstuur bij insturen')
        self.assertEqual(records[0]['pilot'],'SMEETS Noah')
        self.assertContains(self.client.get('/live/sprint/'),'Kartverslagen')
    def test_reports_are_private_and_validate_scores_circuit_and_used_kart(self):
        session=self.start();url=f'/live/api/sessions/{session.pk}/kart-reports/';data=self.data(session)
        for change in [dict(scores={'acceleration':6}),dict(scores={'acceleration':True}),dict(scores={}),dict(kart='999'),dict(conditions='snow')]:
            self.assertEqual(self.post(url,{**data,**change}).status_code,400)
        other_track=TimingTrack.objects.create(slug='other-track',name='Other',source_id='spa')
        self.assertEqual(self.post(url,{**data,'trackId':other_track.pk}).status_code,400)
        self.assertEqual(self.post(url,data).status_code,201)
        other=get_user_model().objects.create_superuser(username='outsider',password='test-only');self.client.force_login(other)
        self.assertEqual(self.client.get('/live/api/kart-reports/').json()['reports'],[])
        self.assertEqual(self.post(url,data).status_code,404)


class TrainingRowsTests(SimpleTestCase):
    def rows(self, count=7):
        return [dict(identity=str(i),row='r'+str(i),name='Driver '+str(i),kart=str(i),position=count-i,
                     bestLapMs=60000+i*1000,lastLapMs=61000+i*1000,laps=4,sectors={'S1':40000+i*100,'S2':21000+i*100},sectorBests={'S1':39000+i*100,'S2':20000+i*100}) for i in range(count)]
    def data(self,index,count=7,bests=None):
        rows=self.rows(count)
        driver=SimpleNamespace(identity=str(index),name='Driver '+str(index),kart=str(index),best={},last={})
        state={'headers':{'c1':'s1','c2':'s2'},'rows':{row['row']:{'observed':4,'sector_seen':{'S1':5,'S2':4}} for row in rows}}
        return training_comparison(driver,rows,bests or {'S1':38011,'S2':26999,'lap':65050},state)
    def test_four_rows_are_leader_nearest_faster_own_and_nearest_slower(self):
        for index in [2,3,4,5]:
            with self.subTest(index=index):
                result=self.data(index)
                self.assertEqual([row['position'] for row in result['rows']],[1,index,index+1,index+2])
                self.assertEqual(sum(row['selected'] for row in result['rows']),1)
                self.assertTrue(result['rows'][2]['selected'])
    def test_first_and_second_use_three_unique_rows_and_small_fields_do_not_invent_drivers(self):
        for index in [0,1]:
            self.assertEqual([row['position'] for row in self.data(index)['rows']],[1,2,3])
        self.assertEqual(len(self.data(0,count=1)['rows']),1)
        self.assertEqual([row['position'] for row in self.data(6)['rows']],[1,6,7])
    def test_ideal_is_sum_of_sector_records_not_the_fastest_actual_lap(self):
        result=self.data(3)
        self.assertEqual(result['ideal']['lap'],65010)
        self.assertNotEqual(result['ideal']['lap'],65050)
        self.assertIsNone(self.data(3,bests={'S1':38011,'lap':65050})['ideal']['lap'])
    def test_freshness_distinguishes_current_sector_from_previous_sector_and_lap(self):
        latest=self.data(3)['ownLatest']
        self.assertEqual(latest['S1']['phase'],'current')
        self.assertEqual(latest['S2']['phase'],'previous')
        self.assertEqual(latest['lap']['phase'],'previous')
        self.assertEqual(latest['S1']['lap'],5)
    def test_reconnect_snapshot_does_not_invent_fresh_passages(self):
        from .live_training import latest_times
        row=self.rows()[0]
        self.assertEqual(latest_times(row,{'observed':3,'sector_seen':{'S1':4}})['S1']['phase'],'unknown')
        self.assertEqual(latest_times(row,{})['lap']['phase'],'unknown')
    def test_completed_lap_has_all_times_updated_then_next_sector_stales_previous_ones(self):
        from .live_training import latest_times
        row=self.rows()[0]
        raw={'observed':4,'sector_seen':{'S1':4,'S2':4}}
        self.assertTrue(all(value['phase']=='current' for key,value in latest_times(row,raw).items() if value['timeMs']))
        raw['sector_seen']['S1']=5
        self.assertEqual(latest_times(row,raw)['lap']['phase'],'previous')


class TrainingColorTests(SimpleTestCase):
    def test_source_delta_uses_the_best_before_a_new_record_even_if_apex_updates_best_in_same_packet(self):
        adapter=ApexAdapter()
        adapter.apply(packet(0,'title2||Training\ngrid||'+GRID))
        adapter.apply(packet(1,'r1c6|tn|40.000'))
        adapter.apply(packet(2,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'))
        adapter.apply(packet(3,'r1c6|tn|39.000'))
        adapter.apply(packet(4,'r1c7|tn|20.000\nr1c8|tn|59.000\nr1c10|tn|59.000\nr1c11|in|5'))
        raw=adapter.state['rows']['r1']
        self.assertEqual(raw['training_times']['lap']['deltaMs'],-1000)
        self.assertEqual(raw['training_times']['S1']['deltaMs'],-1000)
        self.assertEqual(raw['training_latest_metric'],'lap')
        from .live_training import latest_times
        values=latest_times(adapter.standings()[0],raw,session_bests=adapter.session_bests())
        self.assertEqual(values['lap']['color'],'purple')
        self.assertTrue(values['lap']['active'])
        self.assertTrue(values['S1']['active'])
        self.assertTrue(values['S2']['active'])
        adapter.apply(packet(5,'r1c6|tn|39.500'))
        values=latest_times(adapter.standings()[0],raw,session_bests=adapter.session_bests())
        self.assertEqual(values['S1']['deltaMs'],500)
        self.assertEqual(values['S1']['color'],'orange')
        self.assertTrue(values['S1']['active'])
        self.assertFalse(values['lap']['active'])
        self.assertEqual(values['lap']['color'],'purple')
    def test_followed_feedback_keeps_own_reference_and_only_last_metric_is_active(self):
        from .live_training import latest_times
        row=dict(laps=10,lastLapMs=66172,bestLapMs=66172,sectors={'S1':39375,'S2':27494},sectorBests={'S1':38678,'S2':27494})
        driver=SimpleNamespace(last={'metric':'S1','timeMs':39375,'lap':11,'deltaMs':697,'byMetric':{'S1':{'metric':'S1','timeMs':39375,'lap':11,'deltaMs':697},'S2':{'metric':'S2','timeMs':27494,'lap':10,'deltaMs':-37},'lap':{'metric':'lap','timeMs':66172,'lap':10,'deltaMs':-846}}})
        values=latest_times(row,{},driver,{'lap':66172,'S1':38678,'S2':27075})
        self.assertEqual(values['lap']['color'],'purple')
        self.assertEqual(values['lap']['deltaMs'],-846)
        self.assertFalse(values['lap']['active'])
        self.assertFalse(values['S2']['active'])
        self.assertTrue(values['S1']['active'])
        self.assertEqual(values['S1']['color'],'orange')


class TrainingRoundCycleTests(SimpleTestCase):
    def test_completed_round_stays_colored_until_first_sector_then_accumulates_new_splits(self):
        from .live_training import latest_times
        row=dict(laps=10,lastLapMs=60000,bestLapMs=60000,sectors={'S1':40000,'S2':20000},sectorBests={'S1':40000,'S2':20000})
        metrics={metric:dict(metric=metric,timeMs=value,lap=10,deltaMs=0) for metric,value in [('S1',40000),('S2',20000),('lap',60000)]}
        driver=SimpleNamespace(last={**metrics['lap'],'byMetric':metrics},best={'lap':60000})
        def active():return {key for key,value in latest_times(row,{},driver).items() if value['active']}
        self.assertEqual(active(),{'S1','S2','lap'})
        metrics['S1']=dict(metric='S1',timeMs=39900,lap=11,deltaMs=-100)
        driver.last={**metrics['S1'],'byMetric':metrics}
        self.assertEqual(active(),{'S1'})
        metrics['S2']=dict(metric='S2',timeMs=19900,lap=11,deltaMs=-100)
        driver.last={**metrics['S2'],'byMetric':metrics}
        self.assertEqual(active(),{'S1','S2'})
        metrics['lap']=dict(metric='lap',timeMs=59800,lap=11,deltaMs=-200)
        driver.last={**metrics['lap'],'byMetric':metrics}
        self.assertEqual(active(),{'S1','S2','lap'})
    def test_losing_session_record_turns_personal_best_green_even_with_no_first_reference_delta(self):
        from .live_training import latest_times
        row=dict(laps=10,lastLapMs=60000,bestLapMs=60000,sectors={},sectorBests={})
        driver=SimpleNamespace(last=dict(metric='lap',timeMs=60000,lap=10,deltaMs=None),best={'lap':60000})
        self.assertEqual(latest_times(row,{},driver,{'lap':60000})['lap']['color'],'purple')
        self.assertEqual(latest_times(row,{},driver,{'lap':59900})['lap']['color'],'green')

class TrainingPotentialTests(SimpleTestCase):
    def test_potential_uses_own_best_and_ranking_uses_best_lap(self):
        driver=SimpleNamespace(identity='own',kart='15',best={'lap':61000,'S1':20000,'S2':41000},last={})
        own=dict(identity='own',row='r1',name='Noah',kart='15',position=1,bestLapMs=61000,lastLapMs=65000,sectors={'S1':22000,'S2':43000},sectorBests={'S1':20000,'S2':41000},recentLaps=[])
        faster=dict(identity='fast',row='r2',name='Fast',kart='7',position=20,bestLapMs=60000,lastLapMs=64000,sectors={},sectorBests={})
        args=([own,faster],{'lap':60000,'S1':19000,'S2':40000},{'headers':{'c6':'s1','c7':'s2'}})
        result=training_comparison(driver,*args)
        self.assertEqual(result['potentialMs'],{'S1':1000,'S2':1000,'lap':2000})
        self.assertEqual(result['position'],2)
        own['sectors']['S1']=25000;own['lastLapMs']=68000
        self.assertEqual(training_comparison(driver,*args)['potentialMs'],result['potentialMs'])
    def test_missing_reference_stays_unknown_and_zero_is_a_real_result(self):
        driver=SimpleNamespace(identity='own',name='Noah',kart='15',best={'S1':20000},last={})
        own=dict(identity='own',row='r1',name='Noah',kart='15',bestLapMs=None,lastLapMs=None,sectors={},sectorBests={},recentLaps=[])
        result=training_comparison(driver,[own],{'S1':20000},{'headers':{'c6':'s1','c7':'s2'}})
        self.assertEqual(result['potentialMs'],{'S1':0,'S2':None,'lap':None});self.assertIsNone(result['position'])
