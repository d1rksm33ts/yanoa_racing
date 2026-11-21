import json
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .live_core import delta_feedback, present_feedback
from .live_models import CoachEvent, FollowSession, TimingSimulation
from .live_simulation import control, create_simulation, index_recording, tick
from .test_livecoach import GRID, lap, packet


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class SimulationTests(TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config=override_settings(LIVECOACH_RECORDINGS_DIR=self.directory.name)
        self.config.enable();self.addCleanup(self.config.disable)
        self.user=get_user_model().objects.create_superuser(username='sim',password='test-only-password')
        self.client.force_login(self.user)
        self.base=timezone.now()
        self.path=Path(self.directory.name)/'race.ndjson'
        events=[packet(0,'title2||HEAT 1\ngrid||'+GRID),lap(1,'1:01.400',4),lap(2,'1:00.451',5),lap(3,'1:00.553',6),packet(4,'title2||HEAT 2\ngrid||'+GRID),lap(5,'1:00.000',4)]
        self.path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.original=self.path.read_bytes()
        self.recording=index_recording(self.path,'Test race')

    def create(self):
        return create_simulation(self.user,self.recording,0,uuid.uuid4())

    def post(self,url,data):
        return self.client.post(url,json.dumps(data),content_type='application/json')

    def follow(self,sim):
        track=sim.track
        response=self.post('/live/api/start/',{'trackId':track.pk,'drivers':[track.entrants[0]['identity']], 'requestId':str(uuid.uuid4()),'name':'Simulation test'})
        self.assertEqual(response.status_code,201)
        return FollowSession.objects.get(pk=response.json()['id'])

    def at(self,seconds):
        return patch('www.live_simulation.timezone.now',return_value=self.base+timedelta(seconds=seconds))

    def test_index_and_precise_feedback_from_same_ingest_path(self):
        self.assertEqual([s['title'] for s in self.recording.segments],['HEAT 1','HEAT 2'])
        sim=self.create(); session=self.follow(sim)
        with self.at(0):control(sim.pk,self.user,'play')
        with self.at(1.1):tick(sim.pk)
        first=session.events.filter(kind='feedback').get()
        self.assertIsNone(first.payload['deltaMs'])
        with self.at(2.1):tick(sim.pk)
        second=session.events.filter(kind='feedback').latest('pk')
        self.assertEqual((second.payload['deltaMs'],second.payload['deltaText']),(-949,'-0.949s'))
        with self.at(3.1):tick(sim.pk)
        third=session.events.filter(kind='feedback').latest('pk')
        self.assertEqual((third.payload['deltaMs'],third.payload['deltaText']),(102,'+0.102s'))
        with self.at(20):tick(sim.pk)
        sim.refresh_from_db()
        self.assertEqual(sim.state,'finished')
        self.assertEqual(session.events.filter(kind='feedback').count(),3)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_pause_speed_resume_and_restart_keep_history(self):
        sim=self.create();session=self.follow(sim)
        with self.at(0):control(sim.pk,self.user,'play')
        with self.at(1.1):control(sim.pk,self.user,'pause')
        with self.at(10):tick(sim.pk)
        self.assertEqual(session.events.filter(kind='feedback').count(),1)
        with self.at(10):control(sim.pk,self.user,'speed',speed=5)
        with self.at(10):control(sim.pk,self.user,'play')
        with self.at(10.4):tick(sim.pk)
        self.assertEqual(session.events.filter(kind='feedback').count(),3)
        with self.at(11):control(sim.pk,self.user,'restart')
        driver=session.drivers.get()
        self.assertEqual((driver.block,driver.best),(2,{}))
        with self.at(11):control(sim.pk,self.user,'play')
        with self.at(11.3):tick(sim.pk)
        feedback=session.events.filter(kind='feedback').latest('pk')
        self.assertEqual(feedback.payload['block'],2)
        self.assertIsNone(feedback.payload['deltaMs'])
        self.assertEqual(session.events.filter(kind='feedback').count(),4)

    def test_private_simulations_cannot_be_discovered_or_controlled_by_another_user(self):
        sim=self.create()
        other=get_user_model().objects.create_superuser(username='other',password='test-only-password')
        client=Client();client.force_login(other)
        overview=client.get('/live/api/').json()
        self.assertNotIn(sim.track_id,[t['id'] for t in overview['tracks']])
        self.assertEqual(overview['simulations'],[])
        self.assertEqual(client.post(f'/live/api/simulations/{sim.pk}/action/',json.dumps({'action':'play'}),content_type='application/json').status_code,404)
        self.assertEqual(client.post('/live/api/connect/',json.dumps({'action':'connect','trackId':sim.track_id}),content_type='application/json').status_code,404)

    def test_creation_retry_and_stop_preserve_saved_feedback(self):
        request_id=uuid.uuid4()
        a=create_simulation(self.user,self.recording,0,request_id)
        b=create_simulation(self.user,self.recording,0,request_id)
        self.assertEqual(a.pk,b.pk)
        session=self.follow(a)
        with self.at(0):control(a.pk,self.user,'play')
        with self.at(1.1):tick(a.pk)
        with self.at(1.2):control(a.pk,self.user,'stop')
        session.refresh_from_db()
        self.assertEqual(session.state,'stopped')
        with self.at(50):tick(a.pk)
        self.assertEqual(session.events.filter(kind='feedback').count(),1)

    def test_restart_restores_initial_kart_and_clears_only_visible_swap_history(self):
        from .live_service import ingest, snapshot
        sim=self.create();session=self.follow(sim)
        ingest(sim.track_id,'kart-restart-test',packet(1,'r1c4|no7|25'))
        self.assertEqual(session.drivers.get().kart,'25')
        session.refresh_from_db()
        self.assertEqual(snapshot(session)['drivers'][0]['kartHistory'][0]['kart'],'13')
        control(sim.pk,self.user,'restart')
        session.refresh_from_db()
        self.assertEqual(session.drivers.get().kart,'13')
        self.assertEqual(snapshot(session)['drivers'][0]['kartHistory'],[])
        ingest(sim.track_id,'kart-restart-test',packet(2,'r1c4|no7|13'))
        self.assertEqual(session.events.filter(kind='kart').count(),1)

    def test_refresh_replay_checkpoint_keeps_references_and_applies_explicit_auto_choice(self):
        from django.core.management import call_command
        from io import StringIO
        sim=self.create();session=self.follow(sim)
        with self.at(0):control(sim.pk,self.user,'play')
        with self.at(1.1):tick(sim.pk)
        driver=session.drivers.get();before=(driver.identity,driver.best,driver.last,driver.block)
        session.pit_settings={'durationSeconds':90,'requiredStops':1,'netLossSeconds':1}
        session.save(update_fields=['pit_settings'])
        call_command('refresh_coach_checkpoints',owner_id=self.user.pk,auto_pit_session=str(session.pk),backup=str(Path(self.directory.name)/'before.json'),stdout=StringIO())
        driver.refresh_from_db();session.refresh_from_db();sim.track.refresh_from_db()
        self.assertEqual((driver.identity,driver.best,driver.last,driver.block),before)
        self.assertIsNone(session.pit_settings['netLossSeconds'])
        self.assertEqual(sim.track.parser_state['rows']['r1']['observed_best_lap'],61400)

    def test_training_only_checkpoint_refresh_preserves_cursor_references_and_other_metadata(self):
        from django.core.management import call_command
        from io import StringIO
        sim=self.create();session=self.follow(sim)
        with self.at(0):control(sim.pk,self.user,'play')
        with self.at(1.1):tick(sim.pk)
        with self.at(1.1):control(sim.pk,self.user,'pause')
        sim.refresh_from_db();sim.track.refresh_from_db()
        driver=session.drivers.get();before=(driver.identity,driver.best,driver.last,driver.block)
        cursor=(sim.byte_offset,sim.position_ms,session.events.count())
        state=sim.track.parser_state;state['clockMs']=123456
        state['rows']['r1'].pop('training_times',None)
        state['rows']['r1'].pop('training_latest_metric',None)
        sim.track.parser_state=state;sim.track.save(update_fields=['parser_state'])
        call_command('refresh_coach_checkpoints',owner_id=self.user.pk,training_only=True,backup=str(Path(self.directory.name)/'training-before.json'),stdout=StringIO())
        driver.refresh_from_db();sim.refresh_from_db();sim.track.refresh_from_db()
        self.assertEqual((driver.identity,driver.best,driver.last,driver.block),before)
        self.assertEqual((sim.byte_offset,sim.position_ms,session.events.count()),cursor)
        self.assertEqual(sim.track.parser_state['clockMs'],123456)
        self.assertEqual(sim.track.parser_state['rows']['r1']['training_times']['lap']['timeMs'],61400)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_nonfirst_segment_is_loaded_and_limit_has_an_actionable_message(self):
        response=self.post('/live/api/simulate/',dict(recordingId=self.recording.pk,segment=1,requestId=str(uuid.uuid4())))
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json()['title'],'HEAT 2')
        self.create();self.create()
        response=self.post('/live/api/simulate/',dict(recordingId=self.recording.pk,segment=1,requestId=str(uuid.uuid4())))
        self.assertEqual(response.status_code,409)
        self.assertIn('Stop deze simulatie',response.json()['error'])
        sim=TimingSimulation.objects.filter(owner=self.user).first()
        control(sim.pk,self.user,'stop')
        response=self.post('/live/api/simulate/',dict(recordingId=self.recording.pk,segment=1,requestId=str(uuid.uuid4())))
        self.assertEqual(response.status_code,201)

    def test_changed_or_partial_recording_is_rejected(self):
        self.path.write_text('changed')
        with self.assertRaises(ValueError):self.create()
        with self.assertRaises(ValueError):index_recording(self.path,'Incomplete')

    def test_old_feedback_is_presented_in_thousandths_without_changing_stored_value(self):
        old={'metric':'lap','deltaMs':102,'message':'Ronde +1'}
        self.assertEqual(present_feedback(old)['message'],'Ronde +0.102s')
        self.assertEqual(old['message'],'Ronde +1')
        self.assertEqual(delta_feedback({'lap':60000},'lap',60000)[1]['deltaText'],'+0.000s')

    def rewind_fixture(self):
        from .test_live_pit import GRID as PIT_GRID
        from datetime import timedelta
        rows=[(0,'title2||Rewind heat\ngrid||'+PIT_GRID),
              (1000,'r1c6|tn|40.000'),(2000,'r1c7|tn|20.000\nr1c8|tn|1:00.000\nr1c11|in|4'),
              (5000,'r1|*in|0'),(12000,'r1|*out|0'),(15000,'r1c6|tn|50.000'),
              (18000,'r1c7|tn|18.000\nr1c8|tn|0:58.000\nr1c11|in|5'),
              (22000,'r1c6|tn|39.000'),(30000,'r1c7|tn|19.000\nr1c8|tn|0:58.000\nr1c11|in|6'),
              (35000,'r1c3|sf|\nlight|lf|'),(40000,'title2||Next\ngrid||'+PIT_GRID)]
        events=[]
        for i,(offset,payload) in enumerate(rows):
            event=packet(i,payload);event['offsetMs']=offset;event['receivedAt']=(self.base+timedelta(milliseconds=offset)).isoformat();events.append(event)
        path=Path(self.directory.name)/'rewind.ndjson';path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        recording=index_recording(path,'Rewind Goodwill');sim=create_simulation(self.user,recording,0,uuid.uuid4())
        return sim,self.follow(sim)

    def finish_rebuild(self,sim,seconds):
        for _ in range(20):
            with self.at(seconds):tick(sim.pk)
            sim.refresh_from_db()
            if sim.state!='rewinding':return
        self.fail('Rebuild did not complete in bounded batches')

    def test_rewind_restores_pit_and_references_hides_future_history_and_preserves_assignment(self):
        import hashlib
        from .live_core import ApexAdapter
        from .live_service import snapshot
        from .telemetry_models import TelemetryDevice
        from .telemetry_timing import timing_for
        sim,session=self.rewind_fixture();driver=session.drivers.get()
        device=TelemetryDevice.objects.create(device_id='REWIND-TEST',owner=self.user,token_digest=hashlib.sha256(b'test-only').hexdigest(),assigned_driver=driver)
        with self.at(0):control(sim.pk,self.user,'play')
        with self.at(23):control(sim.pk,self.user,'pause')
        sim.refresh_from_db();self.assertEqual(sim.position_ms,23000)
        self.assertFalse(ApexAdapter(sim.track.parser_state).standings()[0]['inPit'])
        with self.at(25):control(sim.pk,self.user,'rewind')
        sim.refresh_from_db();self.assertEqual(sim.anchor_ms,13000)
        # Rewind once more after restoring, to land inside the earlier pit stop.
        self.finish_rebuild(sim,25)
        with self.at(26):control(sim.pk,self.user,'rewind')
        device=TelemetryDevice.objects.select_related('assigned_driver__session__track').get(pk=device.pk)
        self.assertEqual(timing_for(device)['status'],'replay_rewinding');self.assertFalse(timing_for(device)['valid'])
        self.finish_rebuild(sim,26);self.assertEqual((sim.position_ms,sim.state),(3000,'paused'))
        sim.track.refresh_from_db();driver.refresh_from_db()
        self.assertEqual(driver.best['lap'],60000)
        self.assertIsNone(ApexAdapter(sim.track.parser_state).standings()[0]['lastPitMs'])
        session.refresh_from_db();shown=snapshot(session)['events']
        self.assertFalse(any(e['payload'].get('timeMs')==58000 for e in shown))
        self.assertTrue(session.events.filter(payload__timeMs=58000).exists())
        device.refresh_from_db();self.assertEqual(device.assigned_driver_id,driver.pk)
        with self.at(27):control(sim.pk,self.user,'rewind')
        self.finish_rebuild(sim,27);self.assertEqual(sim.position_ms,0)
        self.assertEqual(session.drivers.get().best,{})

    def test_rewind_playing_preserves_speed_and_restores_entry_exit_and_sector_handoff(self):
        from .live_core import ApexAdapter
        sim,session=self.rewind_fixture()
        with self.at(0):control(sim.pk,self.user,'speed',speed=2);control(sim.pk,self.user,'play')
        with self.at(9):control(sim.pk,self.user,'rewind')
        self.finish_rebuild(sim,9);self.assertEqual((sim.state,sim.position_ms,sim.speed),('playing',8000,2))
        sim.track.refresh_from_db();self.assertTrue(ApexAdapter(sim.track.parser_state).standings()[0]['inPit'])
        with self.at(12):tick(sim.pk)
        sim.track.refresh_from_db();row=ApexAdapter(sim.track.parser_state).standings()[0]
        self.assertFalse(row['inPit']);self.assertEqual(row['lastPitMs'],7000)
        self.assertTrue(sim.track.parser_state['rows']['r1']['pit_exit_pending'])
        with self.at(13):tick(sim.pk)
        sim.track.refresh_from_db();self.assertFalse(sim.track.parser_state['rows']['r1']['pit_exit_pending'])

    def test_rewind_from_finish_becomes_paused_before_finish_and_is_private(self):
        from .live_core import ApexAdapter
        sim,session=self.rewind_fixture()
        with self.at(0):control(sim.pk,self.user,'play')
        with self.at(50):tick(sim.pk)
        sim.refresh_from_db();self.assertEqual(sim.state,'finished')
        with self.at(60):response=self.post(f'/live/api/simulations/{sim.pk}/action/',{'action':'rewind'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['state'],'rewinding')
        self.finish_rebuild(sim,60);self.assertEqual((sim.state,sim.position_ms),('paused',30000))
        sim.track.refresh_from_db();self.assertFalse(ApexAdapter(sim.track.parser_state).standings()[0]['finished'])
        other=get_user_model().objects.create_superuser(username='rewind-other',password='test-only')
        self.client.force_login(other)
        self.assertEqual(self.post(f'/live/api/simulations/{sim.pk}/action/',{'action':'rewind'}).status_code,404)

    def test_rebuild_is_bounded_and_can_be_cancelled(self):
        events=[packet(0,'title2||Long rewind\ngrid||'+GRID)]
        events.extend(packet(i,'r1c6|ib|1:00.000') for i in range(1,601))
        events.append(packet(601,'title2||Next\ngrid||'+GRID))
        for i,event in enumerate(events):event['offsetMs']=i*100
        path=Path(self.directory.name)/'long-rewind.ndjson';path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        recording=index_recording(path,'Long rewind');sim=create_simulation(self.user,recording,0,uuid.uuid4());session=self.follow(sim)
        sim.state='finished';sim.position_ms=60100;sim.save()
        control(sim.pk,self.user,'rewind');tick(sim.pk);sim.refresh_from_db()
        self.assertEqual(sim.state,'rewinding')
        with self.assertRaises(ValueError):control(sim.pk,self.user,'rewind')
        control(sim.pk,self.user,'stop');sim.refresh_from_db();self.assertEqual(sim.state,'stopped')
        session.refresh_from_db();self.assertEqual(session.state,'stopped')


    def test_rewind_finished_simulation_respects_active_limit(self):
        from .live_simulation import SimulationLimitError
        sim=self.create();sim.state='finished';sim.position_ms=3000;sim.save()
        for _ in range(3):self.create()
        with self.assertRaises(SimulationLimitError):control(sim.pk,self.user,'rewind')
        sim.refresh_from_db();self.assertEqual(sim.state,'finished')


    def test_rewind_processing_time_is_not_counted_as_playback_time(self):
        from .live_simulation import target_position
        sim,session=self.rewind_fixture()
        with self.at(0):control(sim.pk,self.user,'speed',speed=2);control(sim.pk,self.user,'play')
        with self.at(9):control(sim.pk,self.user,'rewind')
        start=self.base+timedelta(seconds=9);completed=self.base+timedelta(seconds=12)
        stamps=iter([start])
        with patch('www.live_simulation.timezone.now',side_effect=lambda:next(stamps,completed)):tick(sim.pk)
        sim.refresh_from_db()
        self.assertEqual(sim.state,'playing');self.assertEqual(sim.anchor_at,completed)
        self.assertEqual(target_position(sim,completed),8000)
