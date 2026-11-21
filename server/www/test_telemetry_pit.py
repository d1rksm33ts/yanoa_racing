from datetime import timedelta
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from .live_core import ApexAdapter
from .test_live_pit import GRID,feed
from . import test_dashboard_screens as fixtures

class PitDisplayProtocolTests(SimpleTestCase):
    def adapter(self):
        a=ApexAdapter();feed(a,0,'title2||Pit display\ngrid||'+GRID,0)
        feed(a,1,'r1|*in|0',10);feed(a,2,'r1|*out|0',100)
        self.assertEqual(a.standings()[0]['lastPitMs'],90000)
        self.assertTrue(a.state['rows']['r1']['pit_exit_pending'])
        return a
    def test_dirty_sector_after_exit_clears_hold_without_polluting_bests(self):
        a=self.adapter()
        feed(a,3,'r1c2|rk|1',101);self.assertTrue(a.state['rows']['r1']['pit_exit_pending'])
        feed(a,4,'r1c6|ib|45.000',102);self.assertTrue(a.state['rows']['r1']['pit_exit_pending'])
        passages=feed(a,5,'r1c6|tn|45.000',103)
        self.assertFalse(a.state['rows']['r1']['pit_exit_pending']);self.assertEqual(passages,[])
        self.assertNotIn('S1',a.state['rows']['r1'].get('sector_bests',{}))
    def test_snapshot_and_same_packet_exit_do_not_clear_hold(self):
        a=ApexAdapter();feed(a,0,'grid||'+GRID,0);feed(a,1,'r1|*in|0',10)
        feed(a,2,'r1|*out|0\nr1c6|tn|45.000',100)
        self.assertTrue(a.state['rows']['r1']['pit_exit_pending'])
        feed(a,3,'init||\ngrid||'+GRID,101)
        self.assertTrue(a.state['rows']['r1']['pit_exit_pending'])
        feed(a,4,'r1c7|tn|20.000',102);self.assertFalse(a.state['rows']['r1']['pit_exit_pending'])
    def test_no_sector_track_waits_for_actual_lap_crossing(self):
        a=self.adapter();a.state['headers']={k:v for k,v in a.state['headers'].items() if v not in {'s1','s2'}}
        feed(a,3,'r1c8|tn|1:00.000',101);self.assertTrue(a.state['rows']['r1']['pit_exit_pending'])
        feed(a,4,'r1c8|tn|2:00.000\nr1c11|in|4',102);self.assertFalse(a.state['rows']['r1']['pit_exit_pending'])
    def test_new_driver_and_new_race_clear_old_hold(self):
        a=self.adapter();feed(a,3,'r1c5||OTHER DRIVER',101);a.standings()
        self.assertNotIn('pit_exit_pending',a.state['rows']['r1'])
        a=self.adapter();feed(a,3,'title2||New session\ngrid||'+GRID,102)
        self.assertNotIn('pit_exit_pending',a.state['rows']['r1'])

class PitDisplayProjectionTests(TestCase):
    setUp = fixtures.DashboardScreenTests.setUp
    data = fixtures.DashboardScreenTests.data
    def test_all_modes_show_configured_minimum_and_actual_pit_duration(self):
        for mode in ['training','sprint','endurance']:
            self.session.activity=mode;self.session.pit_settings={'durationSeconds':90,'requiredStops':1};self.session.save()
            raw=self.track.parser_state;raw['rows']['r1'].update(in_pit=True,pit_enter_ms=int((timezone.now()-timedelta(seconds=45)).timestamp()*1000))
            self.track.parser_state=raw;self.track.save()
            pit=self.data()['pit'];self.assertEqual(pit['phase'],'in');self.assertEqual(pit['required_ms'],90000)
            self.assertAlmostEqual(pit['remaining_ms'],45000,delta=1000)
            raw['rows']['r1'].update(in_pit=False,last_pit_ms=85000,pit_exit_pending=True)
            self.track.parser_state=raw;self.track.save()
            pit=self.data()['pit'];self.assertEqual(pit['phase'],'exit');self.assertEqual(pit['last_duration_ms'],85000)
    def test_unconfigured_minimum_stays_unknown_and_stale_source_clears_pit(self):
        self.session.activity='training';self.session.pit_settings={};self.session.save()
        raw=self.track.parser_state;raw['rows']['r1'].update(in_pit=True,pit_enter_ms=int(timezone.now().timestamp()*1000))
        self.track.parser_state=raw;self.track.save()
        self.assertIsNone(self.data()['pit']['required_ms']);self.assertIsNone(self.data()['pit']['remaining_ms'])
        self.track.connection='offline';self.track.save()
        self.assertIsNone(self.data()['pit'])


    def test_sector_potential_is_available_in_every_pit_mode(self):
        raw=self.track.parser_state;raw['session_best_times']={'S1':19500,'S2':40000}
        self.track.parser_state=raw;self.track.save()
        for mode in ['training','sprint','endurance']:
            self.session.activity=mode;self.session.save()
            self.assertEqual(next(m for m in self.data()['metrics'] if m['id']=='S1')['potential_ms'],300)


class PitExitPositionTests(SimpleTestCase):
    def setup_rows(self):
        own=dict(identity='own',gapMs=10000,laps=4,inPit=False,recentLaps=[],pitSamples=[])
        other=dict(identity='other',gapMs=50000,laps=4,inPit=False,recentLaps=[],pitSamples=[])
        raw={'pit_entry_field':[dict(own),dict(other)]}
        return own,other,raw
    def test_uses_entry_gaps_not_already_delayed_current_gaps_and_includes_overstay(self):
        from .telemetry_pit import exit_position
        own,other,raw=self.setup_rows();own['gapMs']=65000
        settings={'durationSeconds':90,'netLossSeconds':30}
        self.assertEqual(exit_position(own,raw,[own,other],settings,45000),{'best':1,'worst':1})
        self.assertEqual(exit_position(own,raw,[own,other],settings,110000),{'best':2,'worst':2})
    def test_uncalibrated_or_lapped_own_position_remains_unknown(self):
        from .telemetry_pit import exit_position
        own,other,raw=self.setup_rows()
        self.assertIsNone(exit_position(own,raw,[own,other],{'durationSeconds':90}))
        raw['pit_entry_field'][0]['gapEstimated']=True
        self.assertIsNone(exit_position(own,raw,[own,other],{'durationSeconds':90,'netLossSeconds':30}))
    def test_three_observed_samples_allow_range_and_unknown_opponents_widen_it(self):
        from .telemetry_pit import exit_position
        own,other,raw=self.setup_rows();own['recentLaps']=[{'kart':'15','timeMs':60000}];own['kart']='15'
        own['pitSamples']=[{'bypassFraction':.3}]*3
        self.assertEqual(exit_position(own,raw,[own,other],{'durationSeconds':90}),{'best':2,'worst':2})
        raw['pit_entry_field'][1]['inPit']=True
        self.assertEqual(exit_position(own,raw,[own,other],{'durationSeconds':90}),{'best':1,'worst':2})
    def test_parser_captures_entry_field_and_clears_it_for_new_driver(self):
        a=ApexAdapter();feed(a,0,'title2||Pit estimate\ngrid||'+GRID,0)
        feed(a,1,'r1|*in|0',10);raw=a.state['rows']['r1']
        self.assertEqual(raw['pit_entry_field'][0]['gapMs'],2000)
        self.assertFalse(raw['pit_entry_field'][0]['inPit'])
        feed(a,2,'r1c5||OTHER DRIVER',20);a.standings()
        self.assertNotIn('pit_entry_field',a.state['rows']['r1'])
