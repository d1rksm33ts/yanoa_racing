import hashlib
import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from .live_models import TimingTrack,FollowSession,FollowDriver
from .live_service import snapshot
from .live_core import ApexAdapter
from .telemetry_models import TelemetryDevice
from .telemetry_timing import timing_for
from .test_live_pit import GRID
from .test_livecoach import packet

class DashboardScreenTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user(username='screen-owner')
        adapter=ApexAdapter();adapter.apply(packet(0,'title2||Screen fixture\ngrid||'+GRID))
        self.track=TimingTrack.objects.create(slug='screen-fixture',source_id='goodwill',connection='connected',worker_at=timezone.now(),parser_state=adapter.state,entrants=adapter.entrants())
        self.session=FollowSession.objects.create(owner=self.owner,track=self.track,name='Screen fixture')
        self.driver=FollowDriver.objects.create(session=self.session,identity=adapter.entrants()[0]['identity'],name='SMEETS Noah',kart='15',best={'lap':59900,'S1':19800,'S2':40100},last={'metric':'lap','timeMs':60000,'deltaMs':100,'lap':4,'byMetric':{'lap':{'metric':'lap','timeMs':60000,'deltaMs':100},'S1':{'metric':'S1','timeMs':19900,'deltaMs':100}}})
        self.device=TelemetryDevice.objects.create(device_id='SCREEN-TEST',owner=self.owner,token_digest=hashlib.sha256(b'test').hexdigest(),assigned_driver=self.driver)
    def data(self):
        return timing_for(TelemetryDevice.objects.select_related('assigned_driver__session__track').get(pk=self.device.pk))
    def test_mode_selects_only_applicable_panel_and_preserves_color_delta(self):
        for activity in ['training','sprint','endurance']:
            self.session.activity=activity;self.session.save(update_fields=['activity'])
            state=self.data();self.assertEqual(state['activity'],activity)
            self.assertEqual(state['training'] is not None,activity=='training')
            self.assertIsNotNone(state['pit']);self.assertEqual(state['pit']['phase'],'track')
            lap=next(m for m in state['metrics'] if m['id']=='lap')
            self.assertEqual(lap['time_ms'],60000)
            self.assertEqual(lap['delta_ms'],100)
            self.assertEqual(lap['best_ms'],59900)
            self.assertIn(lap['color'],{'purple','green','orange','neutral'})
            self.assertLess(len(json.dumps(state).encode()),2048)
    def test_training_uses_same_pace_ideal_and_own_sector_values_as_website(self):
        self.session.activity='training';self.session.save(update_fields=['activity'])
        expected=snapshot(FollowSession.objects.select_related('track').get(pk=self.session.pk))['training']
        state=self.data()
        self.assertEqual(state['training']['pace_ms'],expected['paceMs'])
        self.assertEqual(state['training']['ideal_lap_ms'],expected['ideal']['lap'])
        for metric in state['metrics']:
            self.assertEqual(metric['time_ms'],expected['ownLatest'][metric['id']]['timeMs'])
            self.assertEqual(metric['delta_ms'],expected['ownLatest'][metric['id']]['deltaMs'])
    def test_endurance_uses_same_pit_forecast_as_website_and_does_not_invent_when_off(self):
        self.session.activity='endurance';self.session.pit_settings={'durationSeconds':90,'requiredStops':2,'netLossSeconds':30};self.session.save()
        self.driver.pit_enabled=True;self.driver.save(update_fields=['pit_enabled'])
        expected=snapshot(FollowSession.objects.select_related('track').get(pk=self.session.pk))['drivers'][0]['pit']
        state=self.data()['pit']
        self.assertEqual(state['stops_left'],expected['remainingStops'])
        self.assertEqual(state['after_stops'],expected.get('correctedPosition'))
        self.assertEqual(state['at_finish'],expected.get('endPosition'))
        self.driver.pit_enabled=False;self.driver.save(update_fields=['pit_enabled'])
        state=self.data()['pit'];self.assertFalse(state['enabled']);self.assertIsNone(state['after_stops'])
    def test_source_staleness_and_assignment_changes_clear_mode_specific_values(self):
        self.session.activity='training';self.session.save(update_fields=['activity'])
        self.assertIsNotNone(self.data()['training'])
        self.track.connection='offline';self.track.save(update_fields=['connection'])
        state=self.data();self.assertFalse(state['valid']);self.assertEqual(state['activity'],'training')
        self.assertEqual(state['metrics'],[]);self.assertIsNone(state['training']);self.assertIsNone(state['pit'])
        self.device.assigned_driver=None;self.device.save(update_fields=['assigned_driver'])
        state=self.data();self.assertIsNone(state['activity']);self.assertEqual(state['metrics'],[])
    def test_leader_gap_is_not_mislabeled_as_gap_ahead(self):
        with patch('www.telemetry_timing.ApexAdapter.standings',return_value=[
            dict(identity='leader',row='r1',sectors={},position=1,gapMs=0,laps=4),dict(identity='ahead',row='r1',sectors={},position=2,gapMs=2000,laps=4),
            dict(ApexAdapter(self.track.parser_state).standings()[0],position=3,gapMs=5000,laps=4)]):
            self.assertEqual(self.data()['gap_ahead_ms'],3000)
        with patch('www.telemetry_timing.ApexAdapter.standings',return_value=[dict(identity='ahead',row='r1',sectors={},position=2,gapMs=2000,laps=5),dict(ApexAdapter(self.track.parser_state).standings()[0],position=3,gapMs=5000,laps=4)]):
            self.assertIsNone(self.data()['gap_ahead_ms'])

    def test_long_names_and_all_sectors_fit_the_bounded_device_reply(self):
        self.driver.name='🏁'*32;self.driver.kart='🏎'*12;self.driver.pit_enabled=True;self.driver.save()
        self.session.activity='endurance';self.session.save(update_fields=['activity'])
        with patch('www.telemetry_timing.ApexAdapter.sector_ids',return_value=['S1','S2','S3']), patch('www.telemetry_timing.forecast',return_value={'coaching':{'text':'🏁'*48}}):
            state=self.data()
        size=len(json.dumps(state).encode())
        self.assertLess(size,3072)
        self.assertLess(len(json.dumps({'accepted':True,'seq':123,'timing':state}).encode()),3328)

    def test_official_finish_retains_final_stand_without_becoming_live_again(self):
        from datetime import timedelta
        state=self.track.parser_state;state['flag']='lf'
        self.track.parser_state=state;self.track.connection='offline';self.track.worker_at=timezone.now()-timedelta(minutes=5);self.track.save()
        result=self.data()
        self.assertTrue(result['valid']);self.assertTrue(result['finished']);self.assertEqual(result['status'],'finished')
        self.assertEqual(result['race_rate'],0)


    def test_last_sector_uses_observed_cycle_not_array_order_or_lap_feedback(self):
        self.session.activity='training';self.session.save(update_fields=['activity'])
        self.assertIsNone(self.data()['latest_sector'])
        raw=self.track.parser_state
        raw['rows']['r1']['sector_seen']={'S1':4,'S2':3}
        self.track.parser_state=raw;self.track.save(update_fields=['parser_state'])
        self.assertEqual(self.data()['latest_sector'],'S1')
        raw['rows']['r1']['sector_seen']['S2']=4
        self.track.parser_state=raw;self.track.save(update_fields=['parser_state'])
        self.assertEqual(self.data()['latest_sector'],'S2')
        self.assertEqual(self.driver.last['metric'],'lap')


    def test_training_projection_uses_best_potential_and_training_rank(self):
        self.session.activity='training';self.session.save(update_fields=['activity'])
        state=self.track.parser_state;state['session_best_times']={'S1':19500,'S2':40000}
        self.track.parser_state=state;self.track.save(update_fields=['parser_state'])
        result=self.data();metric=next(m for m in result['metrics'] if m['id']=='S1')
        self.assertEqual(metric['potential_ms'],300)
        self.assertEqual(metric['ideal_delta_ms'],300)
        self.assertEqual(result['training']['position'],1)
        self.assertEqual(result['position'],2)

    def test_selected_pilot_finish_is_reported_before_global_finish(self):
        raw=self.track.parser_state;raw['flag']='lg';raw['rows']['r1'].setdefault('classes',{})['c3']='sf'
        self.track.parser_state=raw;self.track.save(update_fields=['parser_state'])
        for activity in ['training','sprint','endurance']:
            self.session.activity=activity;self.session.save(update_fields=['activity'])
            result=self.data();self.assertTrue(result['valid']);self.assertTrue(result['finished'])
            self.assertEqual(result['status'],'live')  # Other pilots can still be racing.
        raw['rows']['r1']['classes']['c3']='';self.track.parser_state=raw;self.track.save(update_fields=['parser_state'])
        self.assertFalse(self.data()['finished'])
