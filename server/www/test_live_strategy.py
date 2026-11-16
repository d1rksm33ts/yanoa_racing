import copy,json,tempfile
from pathlib import Path
from django.test import SimpleTestCase,TestCase
from .live_core import ApexAdapter
from .live_pit import forecast
from .live_service import timing_color,ingest
from .live_models import TimingTrack
from .test_livecoach import packet
from .test_live_pit import GRID

class StrategyTests(SimpleTestCase):
    def row(self,identity,position,gap,pace=60000,stops=1):
        return dict(identity=identity,name=identity,position=position,gap=gap,kart='1',pitCount=stops,recentLaps=[dict(kart='1',timeMs=pace)]*6)
    def test_projection_after_own_pit_includes_rivals_pending_pit(self):
        own=self.row('Noah',2,'20.000',60000,1)
        rival=self.row('Rival',1,'',60000,0)
        result=forecast([own,rival],own,dict(durationSeconds=90,requiredStops=1,netLossSeconds=72),dict(remainingLaps=5))
        self.assertEqual(result['correctedPosition'],dict(best=1,worst=1))
        self.assertEqual(result['endPosition'],dict(best=1,worst=1))
        self.assertNotIn('temporaryPosition',result)
    def test_faster_rival_after_pit_needs_a_faster_target_lap(self):
        own=self.row('Noah',1,'',60000)
        rival=self.row('Rival',2,'5.000',59000)
        result=forecast([own,rival],own,dict(durationSeconds=90,requiredStops=1,netLossSeconds=72),dict(remainingLaps=10))
        self.assertEqual(result['endPosition'],dict(best=2,worst=2))
        self.assertGreater(result['coaching']['neededGainMs'],0)
        self.assertLess(result['coaching']['targetLapMs'],60000)
        self.assertIn('sneller',result['coaching']['text'])
        self.assertEqual(result['coaching']['threats'][0]['catchLaps'],5)
    def test_defending_third_warns_about_the_chaser_instead_of_an_already_distant_leader(self):
        rows=[self.row('Leader',1,'',57000),self.row('Second',2,'10.000',59500),self.row('Noah',3,'20.000',60000),self.row('Chaser',4,'21.000',59000)]
        r=forecast(rows,rows[2],dict(durationSeconds=90,requiredStops=1,netLossSeconds=72),dict(remainingLaps=10))
        self.assertEqual(r['coaching']['threats'][0]['name'],'Chaser')
        self.assertEqual(r['coaching']['targetPosition'],3)

    def test_rival_emerging_close_after_pit_is_a_threat(self):
        own=self.row('Noah',2,'70.500',60000,1)
        rival=self.row('Rival',1,'',60000,0)
        r=forecast([own,rival],own,dict(durationSeconds=90,requiredStops=1,netLossSeconds=72),dict(remainingLaps=4))
        self.assertEqual(r['coaching']['threats'][0]['marginAfterStopsMs'],1500)
        self.assertTrue(r['coaching']['threats'][0]['remainingStops'])
    def test_new_kart_keeps_a_provisional_end_range_but_no_fake_precise_advice(self):
        own=self.row('Noah',1,'');own['kart']='2'
        rival=self.row('Rival',2,'3.000')
        r=forecast([own,rival],own,dict(durationSeconds=90,requiredStops=1,netLossSeconds=72),dict(remainingLaps=2))
        self.assertIn('endPosition',r)
        self.assertTrue(r['paceProvisional'])
        self.assertNotIn('neededGainMs',r['coaching'])
    def test_unknown_finish_or_unknown_gap_does_not_invent_an_end_position(self):
        rows=[self.row('Noah',1,''),self.row('Rival',2,'2.000')]
        r=forecast(rows,rows[0],dict(durationSeconds=90,requiredStops=1,netLossSeconds=72))
        self.assertNotIn('endPosition',r)
        rows[1]['gap']='1 Ronde'
        r=forecast(rows,rows[1],dict(durationSeconds=90,requiredStops=1,netLossSeconds=72),dict(remainingLaps=4))
        self.assertEqual(r['status'],'unknown-gap')
        self.assertNotIn('endPosition',r)
    def test_pit_exit_delay_is_applied_until_the_pit_lap_reaches_the_line_only_once(self):
        own=self.row('Noah',1,'',60000);own['pitUnreflected']=True
        rival=self.row('Rival',2,'0.000',60000)
        third=self.row('Third',3,'100.000',60000)
        settings=dict(durationSeconds=90,requiredStops=1,netLossSeconds=72)
        r=forecast([own,rival,third],own,settings,dict(remainingLaps=3))
        self.assertEqual(r['correctedPosition'],dict(best=2,worst=2))
        own.update(pitUnreflected=False,position=2,gap='72.000');rival['position']=1
        r=forecast([own,rival,third],own,settings,dict(remainingLaps=3))
        self.assertEqual(r['correctedPosition'],dict(best=2,worst=2))

    def test_lapped_cohort_gap_is_not_treated_as_a_gap_to_the_overall_leader(self):
        a=ApexAdapter();a.apply(packet(0,'title2||Race\ngrid||'+GRID))
        leader=copy.deepcopy(a.state['rows']['r1']);leader['position']=1
        leader['cells'].update(c2='1',c5='Leader',c11='4',c9='Ronde 4')
        a.state['rows']['r2']=leader
        a.entrant('r2',leader)
        leader['lap_crossings']={'3':1000,'4':61000}
        own=a.state['rows']['r1'];own['cells'].update(c9='0.533',c11='3');own['lap_crossings']={'3':73000}
        self.assertEqual(next(r for r in a.standings() if r['name']=='SMEETS Noah')['gapMs'],72000)
        own['lap_crossings']={}
        self.assertIsNone(next(r for r in a.standings() if r['name']=='SMEETS Noah')['gapMs'])

    def test_race_countdown_uses_recorded_time_and_pit_exit_keeps_exact_duration(self):
        a=ApexAdapter();first=packet(0,'title2||Race\ngrid||'+GRID+'\ndyn1|countdown|600000')
        first['originalReceivedAt']='2026-11-13T20:00:00Z'
        a.apply(first)
        second=packet(1,'r1|*in|0')
        second['originalReceivedAt']='2026-11-13T20:00:00Z';a.apply(second)
        third=packet(2,'r1|*out|0')
        third['originalReceivedAt']='2026-11-13T20:01:30.847Z';a.apply(third)
        self.assertEqual(a.standings()[0]['lastPitMs'],90847)
        self.assertEqual(a.race_progress()['remainingMs'],509153)
        a.apply(packet(3,'dyn1|text|Ronde 10/18'))
        self.assertEqual(a.race_progress()['remainingLaps'],8)
        a.apply(packet(4,'light|lf|'))
        self.assertEqual(a.race_progress()['remainingMs'],0)
    def test_fast_sector_from_initial_grid_survives_a_slower_next_sector(self):
        a=ApexAdapter()
        grid=GRID.replace('<td data-id="r1c6"></td>','<td data-id="r1c6">39.000</td>')
        a.apply(packet(0,'title2||Race\ngrid||'+grid))
        self.assertEqual(a.session_bests()['S1'],39000)
        a.apply(packet(1,'r1c6|tn|40.000'))
        self.assertEqual(a.session_bests()['S1'],39000)

    def test_purple_uses_everyone_and_old_records_survive_later_passages(self):
        a=ApexAdapter();a.apply(packet(0,'title2||Race\ngrid||'+GRID))
        a.apply(packet(1,'r1c6|tn|39.500'))
        self.assertEqual(a.session_bests()['S1'],39500)
        a.apply(packet(2,'r1c7|tn|20.000\nr1c8|tn|59.500\nr1c11|in|4'))
        a.apply(packet(3,'r1c6|tn|40.000'))
        self.assertEqual(a.session_bests()['S1'],39500)
        a.state['rows']={}  # A departed driver must not erase the session record.
        self.assertEqual(a.session_bests()['S1'],39500)
        self.assertEqual(timing_color({'metric':'S1','timeMs':39500,'deltaMs':-100},a.session_bests())['color'],'purple')
        self.assertEqual(timing_color({'metric':'S1','timeMs':39600,'deltaMs':-100},a.session_bests())['color'],'green')
        self.assertEqual(timing_color({'metric':'S1','timeMs':40000,'deltaMs':100},a.session_bests())['color'],'orange')
        self.assertNotEqual(timing_color({'metric':'lap','timeMs':50000,'pitLap':True},a.session_bests())['color'],'purple')

class RecoveryTests(TestCase):
    def test_recovery_fills_holes_and_preserves_incomplete_tail(self):
        from .management.commands.run_live_timing import recover_raw
        track=TimingTrack.objects.create(slug='recovery-test',name='Recovery',source_id='goodwill')
        events=[packet(i,'title2||Race\ngrid||'+GRID if i==0 else 'r1c2||2') for i in range(4)]
        ingest(track.pk,'recording',events[0]);ingest(track.pk,'recording',events[2])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'recording.ndjson'
            path.write_text(''.join(json.dumps(e)+'\n' for e in events[:3])+json.dumps(events[3]))
            original=path.read_bytes()
            self.assertEqual(recover_raw(track.pk,path),1)
            self.assertEqual(recover_raw(track.pk,path),0)
            self.assertEqual(path.read_bytes(),original)

class SessionRecordTests(SimpleTestCase):
    def test_record_holder_survives_disappearance_and_resets_with_new_session(self):
        adapter=ApexAdapter()
        adapter.apply(packet(0,'title2||Heat\ngrid||'+GRID))
        adapter.apply(packet(1,'r1c6|tn|37.000'))
        record=adapter.session_records()['S1']
        self.assertEqual(record['timeMs'],37000)
        self.assertEqual(record['drivers'][0]['name'],'SMEETS Noah')
        adapter.state['rows']={}
        self.assertEqual(adapter.session_records()['S1'],record)
        adapter.apply(packet(2,'title2||Next heat'))
        self.assertEqual(adapter.session_records(),{})

class DisplayClockTests(TestCase):
    def test_live_clock_uses_deadline_and_freezes_on_disconnect(self):
        from django.utils import timezone
        from datetime import timedelta
        from .live_service import display_clock
        now=timezone.now()
        clock=int(now.timestamp()*1000)
        track=TimingTrack.objects.create(slug='clock-test',name='Clock',connection='connected',worker_at=now,parser_state={'title':'Heat','headers':{},'rows':{},'clockMs':clock-5000,'race_deadline_ms':clock+316000})
        self.assertEqual(display_clock(track,now)['remainingMs'],316000)
        track.connection='offline'
        self.assertEqual(display_clock(track,now+timedelta(seconds=10))['remainingMs'],321000)
        self.assertEqual(display_clock(track,now)['rate'],0)
    def test_replay_uses_original_clock_and_speed_and_pause(self):
        from django.utils import timezone
        from unittest.mock import patch
        from types import SimpleNamespace
        from .live_service import display_clock
        now=timezone.now()
        origin=1700000000000
        track=TimingTrack.objects.create(slug='clock-replay',name='Replay',mode='replay',parser_state={'title':'Heat','headers':{},'rows':{},'clockMs':origin,'race_deadline_ms':origin+316000})
        sim=SimpleNamespace(recording=SimpleNamespace(segments=[{'state':{'clockMs':origin},'startMs':5000,'endMs':600000}]),segment=0,state='playing',speed=2,anchor_ms=10000,anchor_at=now)
        with patch('www.live_models.TimingSimulation.objects') as objects:
            objects.filter.return_value.select_related.return_value.first.return_value=sim
            result=display_clock(track,now)
            self.assertEqual(result['remainingMs'],306000)
            self.assertEqual(result['rate'],2)
            sim.state='paused'
            self.assertEqual(display_clock(track,now)['remainingMs'],306000)
            self.assertEqual(display_clock(track,now)['rate'],0)

class LapCounterTests(SimpleTestCase):
    def test_localized_lap_counter_replaces_timer_without_inventing_finish(self):
        for label in ['Vuelta','Vueltas','Ronde','Lap','Tour','Giro']:
            with self.subTest(label=label):
                adapter=ApexAdapter()
                adapter.apply(packet(0,'dyn1|countdown|316000'))
                adapter.apply(packet(1,f'dyn1|text|{label} 6/6'))
                race=adapter.race_progress()
                self.assertEqual((race['currentLap'],race['totalLaps'],race['remainingLaps']),(6,6,0))
                self.assertIsNone(race['remainingMs'])
                self.assertFalse(race['finished'])
                adapter.apply(packet(2,'dyn1|countdown|50000'))
                self.assertIsNone(adapter.race_progress()['currentLap'])

class CommentTests(SimpleTestCase):
    def test_official_snapshot_keeps_time_kart_and_penalty_as_text(self):
        adapter=ApexAdapter()
        payload='<p><b>10:24</b><span data-flag="penalty"></span><span class="com_no no4">9</span>Penalización - Push to pass - 3.000</p><p><b>10:26</b><span data-flag="msg"></span>REVIEWING &amp; CHECKING</p>'
        adapter.apply(packet(0,'com||'+payload))
        self.assertEqual(adapter.state['comments'][0],dict(time='10:24',kart='9',kind='penalty',message='Penalización - Push to pass - 3.000'))
        self.assertEqual(adapter.state['comments'][1]['message'],'REVIEWING & CHECKING')
        adapter.apply(packet(1,'com||'+payload))
        self.assertEqual(len(adapter.state['comments']),2)
        adapter.apply(packet(2,'com||'))
        self.assertEqual(adapter.state['comments'],[])
