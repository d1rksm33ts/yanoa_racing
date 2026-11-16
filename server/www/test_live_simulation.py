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
