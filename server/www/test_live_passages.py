import json
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, override_settings

from .live_core import ApexAdapter
from .live_models import TimingTrack, TimingConnection, FollowSession, CoachEvent
from .live_service import ingest
from .test_livecoach import packet

HEADERS = [('c2','sta'),('c3','rk'),('c4','no'),('c5','dr'),('c6','s1'),('c7','s2'),('c8','s3'),('c9','llp'),('c10','blp'),('c13','tlp')]
SECTOR_GRID='<tbody><tr data-id="r0" class="head">'+''.join(f'<td data-id="{c}" data-type="{t}">{t}</td>' for c,t in HEADERS)+'</tr>'
for rid,name,kart,rank in [('r1','NOAH SMEETS',13,2),('r2','OTHER DRIVER',7,1)]:
    values={'c2':'','c3':str(rank),'c4':str(kart),'c5':name,'c6':'','c7':'','c8':'','c9':'1:24.000','c10':'1:23.000','c13':'3'}
    SECTOR_GRID+=f'<tr data-id="{rid}" data-pos="{rank}">'+''.join(f'<td data-id="{rid}{c}" class="sr">{values[c]}</td>' for c,_ in HEADERS)+'</tr>'
SECTOR_GRID+='</tbody>'


class SectorProtocolTests(SimpleTestCase):
    def test_sectors_arrive_before_lap_and_best_or_pit_snapshots_do_not_emit(self):
        adapter=ApexAdapter()
        self.assertEqual(adapter.apply(packet(0,'title2||FP\nlight|lg|\ngrid||'+SECTOR_GRID)),[])
        one=adapter.apply(packet(1,'r1c6|tn|26.500\nr1c7||\nr1c8||\nr1|*i1|35000'))
        self.assertEqual([(p['metric'],p['lap'],p['timeMs']) for p in one],[('S1',4,26500)])
        two=adapter.apply(packet(2,'r1c7|ti|35.300'))
        self.assertEqual([(p['metric'],p['lap']) for p in two],[('S2',4)])
        self.assertEqual(adapter.apply(packet(3,'r1|*i2|22000')),[])
        self.assertEqual(adapter.apply(packet(3,'r1c7|tn|35.300')),[]) # repeated cell in the same lap
        end=adapter.apply(packet(4,'r1c8|ti|22.000\nr1c9|ti|1:23.800\nr1c13|in|4\nr1|*|999999|0'))
        self.assertEqual([(p['metric'],p['lap']) for p in end],[('S3',4),('lap',4)])
        self.assertEqual(adapter.apply(packet(5,'r1c6|ib|20.000\nr1c7|ib|30.000\nr1c8|ib|15.000\nr1|*in|0')),[])
        self.assertEqual(adapter.apply(packet(6,'r1c7|tn|35.300')),[]) # pit sectors are not clean references
        self.assertEqual(adapter.apply(packet(7,'r1c6|tn|26.500')),[])

    def test_position_commands_and_finish_classes_are_real_source_signals(self):
        adapter=ApexAdapter();adapter.apply(packet(0,'title2||FP\nlight|lg|\ngrid||'+SECTOR_GRID))
        self.assertEqual([r['name'] for r in adapter.standings()],['OTHER DRIVER','NOAH SMEETS'])
        adapter.apply(packet(1,'r1|#|1\nr2|#|2\nr1c2|sf|\nlight|lf|'))
        self.assertEqual(adapter.standings()[0]['name'],'NOAH SMEETS')
        self.assertTrue(adapter.standings()[0]['finished'])
        self.assertEqual(adapter.state['flag'],'lf')


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class SelectionAndFinishTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(username='passages',password='test-only-password')
        self.client.force_login(self.user)
        self.track=TimingTrack.objects.create(slug='sector-track',name='Sector Track',source_id='campillos',connection='connected')
        TimingConnection.objects.create(owner=self.user,track=self.track)
        ingest(self.track.pk,'sectors',packet(0,'title2||FP\nlight|lg|\ngrid||'+SECTOR_GRID))
        self.track.refresh_from_db()
        self.ids={r['name']:r['identity'] for r in self.track.entrants}
        reply=self.post('/live/api/start/',{'trackId':self.track.pk,'drivers':[self.ids['NOAH SMEETS']],'requestId':str(uuid.uuid4())})
        self.session=FollowSession.objects.get(pk=reply.json()['id'])

    def post(self,path,data):
        return self.client.post(path,json.dumps(data),content_type='application/json')

    def update(self,names):
        return self.post(f'/live/api/sessions/{self.session.pk}/action/',{'action':'drivers','drivers':[self.ids[n] for n in names],'requestId':str(uuid.uuid4())})

    def test_add_and_remove_drivers_preserves_retained_driver_identity_reference_and_times(self):
        ingest(self.track.pk,'sectors',packet(1,'r1c6|ti|26.500'))
        noah=self.session.drivers.get();before=(noah.pk,noah.best,noah.last,noah.block)
        self.assertEqual(self.update(['NOAH SMEETS','OTHER DRIVER']).status_code,200)
        noah.refresh_from_db()
        self.assertEqual((noah.pk,noah.best,noah.last,noah.block),before)
        other=self.session.drivers.get(name='OTHER DRIVER')
        self.assertEqual(other.best,{})
        ingest(self.track.pk,'sectors',packet(2,'r2c6|ti|27.000'))
        other.refresh_from_db();expected=(other.pk,other.best,other.last,other.block)
        self.assertEqual(self.update(['OTHER DRIVER']).status_code,200)
        other.refresh_from_db()
        self.assertEqual((other.pk,other.best,other.last,other.block),expected)
        self.assertEqual(self.session.drivers.count(),1)
        self.assertFalse(self.session.drivers.filter(name='NOAH SMEETS').exists())
        self.assertEqual(self.session.state,'active')

    def test_sector_deltas_and_per_metric_history_survive_lap_feedback(self):
        for seq,payload in enumerate(['r1c6|ti|26.500','r1c7|ti|35.300','r1c8|ti|22.000\nr1c9|ti|1:23.800\nr1c13|in|4',
                                      'r1c6|tn|26.400','r1c7|tn|35.402','r1c8|tn|21.051\nr1c9|tn|1:22.853\nr1c13|in|5'],1):
            ingest(self.track.pk,'sectors',packet(seq,payload))
        driver=self.session.drivers.get()
        self.assertEqual(driver.last['byMetric']['S1']['deltaText'],'-0.100s')
        self.assertEqual(driver.last['byMetric']['S2']['deltaText'],'+0.102s')
        self.assertEqual(driver.last['byMetric']['S3']['deltaText'],'-0.949s')
        self.assertEqual(driver.last['metric'],'lap')
        self.assertEqual(self.session.events.filter(kind='feedback').count(),8)
        state=self.client.get(f'/live/api/sessions/{self.session.pk}/').json()
        self.assertTrue(state['track']['capabilities']['sectors'])
        self.assertEqual(len(state['track']['standings']),2)

    def test_finish_is_announced_once_without_erasing_or_stopping_final_passages(self):
        ingest(self.track.pk,'sectors',packet(1,'r1c6|ti|26.500'))
        self.assertFalse(self.client.get(f'/live/api/sessions/{self.session.pk}/').json()['track']['finished'])
        ingest(self.track.pk,'sectors',packet(2,'light|lf|\nr1c2|sf|'))
        ingest(self.track.pk,'sectors',packet(3,'light|lf|'))
        state=self.client.get(f'/live/api/sessions/{self.session.pk}/').json()
        self.assertTrue(state['track']['finished'])
        self.assertTrue(state['drivers'][0]['finished'])
        self.assertEqual(self.session.events.filter(kind='finish').count(),2) # session + selected driver
        self.assertEqual(state['drivers'][0]['best']['S1'],26500)
        ingest(self.track.pk,'sectors',packet(4,'r1c7|ti|35.300'))
        self.assertEqual(self.session.events.filter(kind='feedback').count(),2)
        self.session.refresh_from_db();self.assertEqual(self.session.state,'active')

    def test_source_outage_is_not_a_finish(self):
        from django.utils import timezone
        ingest(self.track.pk,'sectors',{'type':'connection','seq':1,'state':'disconnected','receivedAt':timezone.now().isoformat()})
        state=self.client.get(f'/live/api/sessions/{self.session.pk}/').json()
        self.assertFalse(state['track']['finished'])
        self.assertEqual(self.session.events.filter(kind='finish').count(),0)
