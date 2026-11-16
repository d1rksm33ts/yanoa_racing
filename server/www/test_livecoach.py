import asyncio
import copy
import json
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import AsyncClient, Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .live_core import ApexAdapter, delta_feedback, milliseconds
from .live_models import CoachEvent, FollowSession, TimingPacket, TimingTrack, TimingConnection
from .live_service import ingest, seed_tracks


GRID = '<tbody><tr data-id="r0" class="head"><td data-id="c4" data-type="no">Kart</td><td data-id="c5" data-type="dr">Pilote</td><td data-id="c6" data-type="llp">Dernier T.</td><td data-id="c9" data-type="tlp">Tours</td></tr><tr data-id="r1"><td><div data-id="r1c4">13</div></td><td data-id="r1c5">NOAH SMEETS</td><td data-id="r1c6">1:01.500</td><td data-id="r1c9">3</td></tr><tr data-id="r2"><td data-id="r2c4">7</td><td data-id="r2c5">OTHER DRIVER</td><td data-id="r2c6">1:02.000</td><td data-id="r2c9">3</td></tr></tbody>'


def packet(seq, payload):
    return {"type": "packet", "encoding": "utf8", "seq": seq, "offsetMs": seq * 1000,
            "receivedAt": timezone.now().isoformat(), "payload": payload}


def lap(seq, value, number, row="r1"):
    return packet(seq, f"{row}c9|in|{number}\n{row}c6|ti|{value}\n{row}|*|999999|0\n")


class TimingCoreTests(SimpleTestCase):
    def test_delta_compares_before_improving_and_rounds_half_away_from_zero(self):
        best, first = delta_feedback({}, "S1", 20000)
        self.assertIsNone(first["deltaMs"])
        best, faster = delta_feedback(best, "S1", 19850)
        self.assertEqual((faster["deltaMs"], faster["message"], best["S1"]), (-150, "S1 -0.150s", 19850))
        best, slower = delta_feedback(best, "S1", 20000)
        self.assertEqual((slower["message"], best["S1"]), ("S1 +0.150s", 19850))
        self.assertEqual(delta_feedback(best, "S1", 19851)[1]["message"], "S1 +0.001s")
        self.assertNotIn("lap", best)

    def test_time_validation(self):
        self.assertEqual(milliseconds("1:01.536"), 61536)
        self.assertEqual(milliseconds("36,105"), 36105)
        for value in ["", "-1.001", "1:99.000", "<script>", "0.000", "NaN"]:
            self.assertIsNone(milliseconds(value))
        with self.assertRaises(ValueError):
            delta_feedback({}, "lap", -1)

    def test_snapshot_is_not_a_passage_and_protocol_uses_last_lap_not_animation(self):
        adapter = ApexAdapter()
        self.assertEqual(adapter.apply(packet(0, "init|p|\ntitle2||HEAT 1\ngrid||" + GRID)), [])
        self.assertTrue(adapter.supported)
        passages = adapter.apply(lap(1, "1:01.400", 4))
        self.assertEqual([(p["timeMs"], p["lap"]) for p in passages], [(61400, 4)])
        self.assertEqual(adapter.apply(lap(2, "1:01.400", 4)), [])
        self.assertEqual(adapter.apply(packet(3, "r1|*|61400|0")), [])

    def test_restart_snapshot_preserves_identity_and_never_duplicates(self):
        adapter = ApexAdapter()
        adapter.apply(packet(0, "title2||HEAT 1\ngrid||" + GRID))
        identity = adapter.entrants()[0]["identity"]
        restored = ApexAdapter(copy.deepcopy(adapter.state))
        self.assertEqual(restored.apply(packet(1, "init|p|\ntitle2||HEAT 1\ngrid||" + GRID)), [])
        self.assertEqual(restored.entrants()[0]["identity"], identity)
        self.assertEqual(restored.apply(lap(2, "1:01.300", 4))[0]["identity"], identity)

    def test_new_session_or_driver_does_not_inherit_identity(self):
        adapter = ApexAdapter()
        adapter.apply(packet(0, "title2||HEAT 1\ngrid||" + GRID))
        first = adapter.entrants()[0]["identity"]
        adapter.apply(packet(1, "title2||HEAT 2\ngrid||" + GRID))
        self.assertNotEqual(first, adapter.entrants()[0]["identity"])
        self.assertEqual(adapter.apply(packet(2, "r1c5||SOMEONE ELSE\nr1c6|ti|1:00.000\nr1c9|in|4")), [])

    def test_unknown_schema_is_not_guessed_and_missing_laps_are_flagged(self):
        adapter = ApexAdapter()
        adapter.apply(packet(0, "grid||" + GRID.replace('data-type="llp"', 'data-type="unknown"')))
        self.assertFalse(adapter.supported)
        self.assertEqual(adapter.apply(lap(1, "1:00.000", 4)), [])
        adapter = ApexAdapter()
        adapter.apply(packet(0, "grid||" + GRID))
        self.assertTrue(adapter.apply(lap(1, "1:00.000", 7))[0]["gap"])

    def test_verified_race_layout_without_lap_counter_counts_observed_passages(self):
        race = GRID.replace('data-type="tlp"', 'data-type="gap"').replace('</tr><tr data-id="r1">', '<td data-id="c8" data-type="blp">Best</td></tr><tr data-id="r1">')
        adapter=ApexAdapter()
        adapter.apply(packet(0,'title2||HEAT 1\ngrid||'+race))
        self.assertTrue(adapter.supported)
        result=adapter.apply(packet(1,'r1c6|ti|1:01.200\nr1|*||0'))
        self.assertEqual((result[0]['timeMs'],result[0]['lap'],result[0]['lapCountKnown']),(61200,1,False))
        self.assertEqual(adapter.apply(packet(2,'r1|*|999999|0')),[])


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class CoachAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="coach", password="test-only-password")
        self.user.user_permissions.add(Permission.objects.get(codename="use_livecoach"))
        self.client.force_login(self.user)
        seed_tracks()
        self.track = TimingTrack.objects.get(slug="spa")
        ingest(self.track.pk, "raw", {"type": "connection", "state": "connected", "seq": 0, "receivedAt": timezone.now().isoformat()})
        ingest(self.track.pk, "raw", packet(1, "title2||HEAT 1\ngrid||" + GRID))
        self.track.refresh_from_db()
        TimingConnection.objects.create(owner=self.user,track=self.track)

    def post(self, path, data):
        return self.client.post(path, data=json.dumps(data), content_type="application/json")

    def start(self, client=None, request_id=None):
        return (client or self.client).post('/live/api/start/', data=json.dumps({"requestId": request_id or str(uuid.uuid4()), "trackId": self.track.pk, "drivers": [e["identity"] for e in self.track.entrants], "name": "Noah test"}), content_type="application/json")

    def action(self, session, kind, **kwargs):
        return self.post(f'/live/api/sessions/{session}/action/', {"requestId":str(uuid.uuid4()), "action":kind, **kwargs})

    def test_start_retry_is_idempotent(self):
        request = str(uuid.uuid4())
        first, second = self.start(request_id=request), self.start(request_id=request)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(FollowSession.objects.count(), 1)

    def test_live_feedback_multiple_drivers_reset_stop_and_raw_deduplication(self):
        session = self.start().json()["id"]
        self.assertEqual(ingest(self.track.pk,"raw",lap(2,"1:01.400",4)), 1)
        self.assertEqual(ingest(self.track.pk,"raw",lap(2,"1:01.400",4)), 0)
        ingest(self.track.pk,"raw",lap(3,"1:01.200",5))
        ingest(self.track.pk,"raw",lap(4,"1:02.000",4,"r2"))
        state = self.client.get(f'/live/api/sessions/{session}/').json()
        noah, other = state["drivers"]
        self.assertEqual((noah["last"]["message"], noah["best"]["lap"]), ("Ronde -0.200s",61200))
        self.assertEqual(other["best"]["lap"],62000)
        self.assertEqual(self.action(session,"reset",driverId=noah["id"]).status_code,200)
        state = self.client.get(f'/live/api/sessions/{session}/').json()
        self.assertEqual(state["drivers"][0]["best"],{})
        self.assertEqual(state["drivers"][1]["best"]["lap"],62000)
        self.assertEqual(CoachEvent.objects.filter(kind="feedback").count(),3)
        ingest(self.track.pk,"raw",lap(5,"1:01.100",6))
        self.assertEqual(CoachEvent.objects.filter(kind="feedback").latest("pk").payload["block"],2)
        self.assertIsNone(CoachEvent.objects.filter(kind="feedback").latest("pk").payload["deltaMs"])
        self.assertEqual(self.action(session,"stop").status_code,200)
        self.assertEqual(ingest(self.track.pk,"raw",lap(6,"1:01.000",7)),0)
        self.assertEqual(self.action(session,"reset").status_code,409)

    def test_two_users_share_source_but_cannot_read_or_control_each_other(self):
        first = self.start().json()["id"]
        other = get_user_model().objects.create_user(username="other")
        other.user_permissions.add(Permission.objects.get(codename="use_livecoach"))
        client = Client(); client.force_login(other)
        TimingConnection.objects.create(owner=other,track=self.track)
        second = self.start(client=client).json()["id"]
        self.assertEqual(self.client.get(f'/live/api/sessions/{second}/').status_code,404)
        for path in ["", "events/", "export/"]:
            self.assertEqual(client.get(f'/live/api/sessions/{first}/{path}').status_code,404)
        self.assertEqual(self.action(second,"stop").status_code,404)
        self.action(first,"stop")
        self.assertEqual(ingest(self.track.pk,"raw",lap(2,"1:00.000",4)),1)

    def test_login_permission_and_csrf_are_required(self):
        anonymous = Client()
        self.assertEqual(anonymous.get('/live/api/').status_code,302)
        user = get_user_model().objects.create_user(username="no-permission")
        anonymous.force_login(user)
        self.assertEqual(anonymous.get('/live/api/').status_code,403)
        csrf = Client(enforce_csrf_checks=True); csrf.force_login(self.user)
        self.assertEqual(self.start(client=csrf).status_code,403)

    def test_offline_or_unknown_source_cannot_start(self):
        TimingTrack.objects.filter(pk=self.track.pk).update(worker_at=None)
        self.assertEqual(self.start().status_code,409)

    def test_connection_is_explicit_and_disconnect_preserves_other_users(self):
        TimingConnection.objects.filter(owner=self.user,track=self.track).delete()
        status=self.client.get('/live/api/').json()
        source=next(t for t in status['tracks'] if t['id']==self.track.pk)
        self.assertEqual((source['connection'],source['entrants']),('disconnected',[]))
        self.assertEqual(self.start().status_code,409)
        self.assertEqual(self.post('/live/api/connect/',{'trackId':self.track.pk,'action':'connect'}).status_code,200)
        session=self.start().json()['id']
        self.assertEqual(self.post('/live/api/connect/',{'trackId':self.track.pk,'action':'disconnect'}).status_code,409)
        self.action(session,'stop')
        self.assertEqual(self.post('/live/api/connect/',{'trackId':self.track.pk,'action':'disconnect'}).status_code,200)
        self.track.refresh_from_db()
        self.assertEqual(self.track.connection,'connected')

    def test_stale_pre_session_packets_are_not_new_feedback(self):
        session = self.start().json()["id"]
        p=lap(2,"1:01.000",4)
        p["receivedAt"]="2026-01-01T00:00:00+00:00"
        self.assertEqual(ingest(self.track.pk,"raw",p),0)
        self.assertEqual(CoachEvent.objects.filter(session_id=session,kind="feedback").count(),0)

    def test_reset_retry_only_creates_one_block(self):
        session=self.start().json()["id"]
        data={"requestId":str(uuid.uuid4()),"action":"reset"}
        for _ in range(2):
            self.assertEqual(self.post(f'/live/api/sessions/{session}/action/',data).status_code,200)
        self.assertEqual(FollowSession.objects.get(pk=session).drivers.first().block,2)

    def test_archive_and_export_keep_history(self):
        session=self.start().json()["id"]
        self.assertContains(self.client.get('/live/samenvattingen/'),"Noah test")
        result=self.client.get(f'/live/api/sessions/{session}/export/')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()["events"][0]["kind"],"started")

    def test_all_active_sessions_can_be_found_and_stopped_even_beyond_recent_archive(self):
        ids=[self.start().json()['id'] for _ in range(5)]
        ingest(self.track.pk,'raw',lap(2,'1:01.400',4))
        for i in range(51):
            FollowSession.objects.create(owner=self.user,track=self.track,name=f'Later saved {i}',state='stopped')
        overview=self.client.get('/live/api/').json()
        self.assertEqual(len(overview['activeSessions']),5)
        self.assertFalse(any(s['state']=='active' for s in overview['sessions']))
        self.assertEqual(self.start().status_code,409)
        stopped=FollowSession.objects.get(pk=ids[0]);before=list(stopped.drivers.values('pk','best','last','block'))
        self.assertEqual(self.action(ids[0],'stop').status_code,200)
        self.assertEqual(list(stopped.drivers.values('pk','best','last','block')),before)
        self.assertEqual(len(self.client.get('/live/api/').json()['activeSessions']),4)
        self.assertEqual(self.start().status_code,201)

    def test_stop_without_saving_deletes_only_the_chosen_follow_session(self):
        first=self.start().json()['id'];second=self.start().json()['id']
        ingest(self.track.pk,'raw',lap(2,'1:01.400',4))
        kept=FollowSession.objects.get(pk=second)
        before=list(kept.drivers.values('pk','best','last','block'))
        packet_count=TimingPacket.objects.count()
        self.assertEqual(self.post(f'/live/api/sessions/{first}/discard/',{}).status_code,200)
        self.assertFalse(FollowSession.objects.filter(pk=first).exists())
        self.assertFalse(CoachEvent.objects.filter(session_id=first).exists())
        self.assertEqual(list(kept.drivers.values('pk','best','last','block')),before)
        self.assertEqual(TimingPacket.objects.count(),packet_count)
        self.track.refresh_from_db();self.assertEqual(self.track.connection,'connected')
        self.assertEqual(self.client.get(f'/live/api/sessions/{first}/').status_code,404)

    def test_discard_requires_owner_post_and_csrf(self):
        identity=self.start().json()['id']
        path=f'/live/api/sessions/{identity}/discard/'
        self.assertEqual(self.client.get(path).status_code,405)
        other=get_user_model().objects.create_superuser(username='discard-other',password='test-only-password')
        client=Client();client.force_login(other)
        self.assertEqual(client.post(path,'{}',content_type='application/json').status_code,404)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.user)
        self.assertEqual(csrf.post(path,'{}',content_type='application/json').status_code,403)
        self.assertTrue(FollowSession.objects.filter(pk=identity).exists())


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class SSETests(TransactionTestCase):
    async def test_sse_snapshot_is_authorized_and_immediate(self):
        from asgiref.sync import sync_to_async

        @sync_to_async
        def setup():
            user=get_user_model().objects.create_superuser(username="stream",password="test-only-password")
            track=TimingTrack.objects.create(slug="test",name="Test",source_id="spa")
            session=FollowSession.objects.create(owner=user,track=track,name="Live")
            return user,session.pk

        user,pk=await setup()
        client=AsyncClient()
        await client.aforce_login(user)
        response=await client.get(f'/live/api/sessions/{pk}/events/')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.is_async)
        stream=response.streaming_content
        self.assertIn(b'retry:',await anext(stream))
        self.assertIn(b'event: snapshot',await asyncio.wait_for(anext(stream),timeout=1))
        @sync_to_async
        def new_event():
            from .live_service import publish
            return publish(FollowSession.objects.get(pk=pk),"save",{"message":"updated"})
        await new_event()
        self.assertIn(b'updated',await asyncio.wait_for(anext(stream),timeout=1.5))
        await stream.aclose()
