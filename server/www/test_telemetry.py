import hashlib
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .telemetry_core import validate
from .telemetry_models import TelemetryDevice

TOKEN = 'synthetic_test_credential_123456789012345'


def frame(seq=1, boot='synthetic-boot', valid=False):
    return {'schema_version':1,'device_id':'BENCH-ESP32-001','session_id':None,'boot_id':boot,'seq':seq,
        'sample_ts_ms':None,'uptime_ms':seq*200,'gnss':{'valid':valid,
            'lat_deg':50.965123 if valid else None,'lon_deg':5.538456 if valid else None,
            'speed_mps':23.17 if valid else None,'heading_deg':127.2 if valid else None,
            'h_accuracy_m':1.8 if valid else None,'satellites':12 if valid else 0,
            'fix_type':3 if valid else 0,'itow_ms':1000,'age_ms':0},
        'imu':{'valid':False,'accel_mps2':None,'gyro_dps':None,'frame':'sensor'},
        'local_timing':{'valid':False,'delta_ms':None},'battery_pct':None,'lte_rssi_dbm':None,
        'diagnostics':{'pvt_frames':25,'ubx_checksum_errors':0,'interval_ms':40,'gap_events':0}}


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class TelemetryTests(TestCase):
    def setUp(self):
        users=get_user_model()
        self.owner=users.objects.create_superuser(username='telemetry-owner',password='test-only')
        self.other=users.objects.create_superuser(username='telemetry-other',password='test-only')
        self.device=TelemetryDevice.objects.create(device_id='BENCH-ESP32-001',owner=self.owner,
            token_digest=hashlib.sha256(TOKEN.encode()).hexdigest())
        self.url='/live/api/devices/BENCH-ESP32-001/telemetry/'
        self.detail='/live/api/devices/BENCH-ESP32-001/'
        self.now=timezone.now()
        self.clock=patch('www.telemetry_views.timezone.now',side_effect=lambda:self.now)
        self.clock.start();self.addCleanup(self.clock.stop)

    def post(self,data=None,token=TOKEN,client=None):
        return (client or self.client).post(self.url,json.dumps(data if data is not None else frame()),
            content_type='application/json',HTTP_AUTHORIZATION='Bearer '+token)

    def test_bearer_only_ingress_and_owner_scoped_read(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.post(token='wrong').status_code,401)
        self.assertEqual(self.client.post(self.url,json.dumps(frame()),content_type='application/json').status_code,401)
        # A correct bearer works without a CSRF cookie or a logged-in session.
        machine=Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client=machine).status_code,202)
        result=self.client.get(self.detail).json()
        self.assertTrue(result['online']);self.assertFalse(result['telemetry']['gnss']['valid'])
        self.assertNotIn('token',json.dumps(result))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.detail).status_code,404)
        self.client.logout();self.assertEqual(self.client.get(self.detail).status_code,302)

    def test_invalid_payloads_and_body_limits(self):
        self.assertEqual(self.client.post(self.url,'{',content_type='application/json',HTTP_AUTHORIZATION='Bearer '+TOKEN).status_code,400)
        self.assertEqual(self.client.post(self.url,'x'*4097,content_type='application/json',HTTP_AUTHORIZATION='Bearer '+TOKEN).status_code,413)
        self.assertEqual(self.client.post(self.url,'{}',content_type='text/plain',HTTP_AUTHORIZATION='Bearer '+TOKEN).status_code,415)
        for change in ({'schema_version':True},{'seq':True},{'device_id':'OTHER'},{'sample_ts_ms':1}, {'session_id':'unassigned'}):
            data=frame();data.update(change)
            self.assertEqual(self.post(data).status_code,400,change)
        for key,value in [('lat_deg',float('nan')),('lat_deg',91),('speed_mps',-1),('age_ms',1001),('fix_type',0)]:
            data=frame(valid=True);data['gnss'][key]=value
            self.assertEqual(self.post(data).status_code,400,(key,value))
        data=frame();data['gnss']['lat_deg']=0
        self.assertEqual(self.post(data).status_code,400)
        self.assertFalse(TelemetryDevice.objects.get(pk=self.device.pk).latest)

    def test_duplicate_out_of_order_and_retired_boot_do_not_refresh(self):
        self.assertEqual(self.post().status_code,202)
        received=TelemetryDevice.objects.get(pk=self.device.pk).received_at
        self.now+=timedelta(seconds=1)
        self.assertEqual(self.post().status_code,409)
        self.assertEqual(self.post(frame(seq=0)).status_code,409)
        self.assertEqual(TelemetryDevice.objects.get(pk=self.device.pk).received_at,received)
        self.assertEqual(self.post(frame(seq=0,boot='new-boot')).status_code,202)
        self.now+=timedelta(seconds=1)
        self.assertEqual(self.post(frame(seq=99)).status_code,409)

    def test_uptime_regression_and_rate_limit(self):
        self.assertEqual(self.post(frame(seq=10)).status_code,202)
        self.assertEqual(self.post(frame(seq=11)).status_code,429)
        self.now+=timedelta(seconds=1)
        data=frame(seq=11);data['uptime_ms']=1
        self.assertEqual(self.post(data).status_code,409)

    def test_disconnect_invalidates_position_without_modifying_stored_measurement(self):
        self.assertEqual(self.post(frame(valid=True)).status_code,202)
        self.client.force_login(self.owner)
        self.assertTrue(self.client.get(self.detail).json()['telemetry']['gnss']['valid'])
        self.now+=timedelta(seconds=1.1)
        result=self.client.get(self.detail).json()
        self.assertTrue(result['online'])
        self.assertFalse(result['telemetry']['gnss']['valid'])
        self.assertIsNone(result['telemetry']['gnss']['lat_deg'])
        self.assertTrue(TelemetryDevice.objects.get(pk=self.device.pk).latest['gnss']['valid'])
        self.now+=timedelta(seconds=2)
        delayed=self.client.get(self.detail).json()
        self.assertTrue(delayed['online']);self.assertEqual(delayed['connection_status'],'delayed')
        self.now+=timedelta(seconds=12)
        self.assertFalse(self.client.get(self.detail).json()['online'])

    def test_device_and_owner_can_be_disabled(self):
        self.assertEqual(self.post(frame(valid=True)).status_code,202)
        self.device.refresh_from_db()
        self.device.enabled=False;self.device.save()
        self.client.force_login(self.owner)
        disabled=self.client.get(self.detail).json()
        self.assertFalse(disabled['online'])
        self.assertFalse(disabled['telemetry']['gnss']['valid'])
        self.assertEqual(self.post().status_code,401)
        self.device.enabled=True;self.device.save()
        self.owner.is_active=False;self.owner.save()
        self.assertEqual(self.post().status_code,401)

    def test_boot_history_is_bounded_without_forgetting_retired_ids(self):
        self.device.boot_id='old';self.device.retired_boots=[f'boot-{i}' for i in range(64)];self.device.save()
        self.assertEqual(self.post().status_code,409)
        self.assertEqual(TelemetryDevice.objects.get(pk=self.device.pk).boot_id,'old')

    def test_measured_imu_vectors_and_stale_invalidation(self):
        sample=frame()
        sample['imu']={'valid':True,'accel_mps2':[0,0,9.80665],'gyro_dps':[0.1,-0.2,0.3],'frame':'sensor'}
        self.assertEqual(self.post(sample).status_code,202)
        self.client.force_login(self.owner)
        self.assertTrue(self.client.get(self.detail).json()['telemetry']['imu']['valid'])
        self.now+=timedelta(seconds=1.1)
        stale=self.client.get(self.detail).json()['telemetry']['imu']
        self.assertFalse(stale['valid']);self.assertIsNone(stale['accel_mps2'])
        for invalid in ([0,0], [0,0,float('nan')], [0,0,True], [0,0,161]):
            sample['imu']['accel_mps2']=invalid
            self.assertEqual(self.post(sample).status_code,400)

    def test_provisioning_writes_private_token_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'token'
            call_command('provision_telemetry_device','TEST-SECOND',owner=self.owner.username,token_file=str(path),verbosity=0)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            token=path.read_text().strip()
            self.assertEqual(TelemetryDevice.objects.get(device_id='TEST-SECOND').token_digest,hashlib.sha256(token.encode()).hexdigest())
            with self.assertRaises(CommandError):
                call_command('provision_telemetry_device','TEST-SECOND',owner=self.owner.username,token_file=str(path),verbosity=0)
            self.assertEqual(path.read_text().strip(),token)

# Optional cross-repository integration, using the real Node relay and C++-generated frame.
import os
import subprocess
from unittest import skipUnless
from django.test import LiveServerTestCase


@skipUnless(os.environ.get('APEX_TELEMETRY_RELAY') and os.environ.get('TELEMETRY_FIXTURE'),
            'Set APEX_TELEMETRY_RELAY and TELEMETRY_FIXTURE for the cross-repository test')
@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class RelayIntegrationTests(LiveServerTestCase):
    def test_native_firmware_json_through_real_node_relay_into_racing(self):
        owner=get_user_model().objects.create_superuser(username='integration-owner',password='test-only')
        TelemetryDevice.objects.create(device_id='BENCH-ESP32-001',owner=owner,
            token_digest=hashlib.sha256(TOKEN.encode()).hexdigest())
        first=Path(os.environ['TELEMETRY_FIXTURE']).read_text().splitlines()[0]
        validate(json.loads(first),'BENCH-ESP32-001')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'token';path.write_text(TOKEN);path.chmod(0o600)
            env={**os.environ,'TELEMETRY_TOKEN_FILE':str(path),
                'TELEMETRY_URL':self.live_server_url+'/live/api/devices/BENCH-ESP32-001/telemetry/'}
            result=subprocess.run(['node',os.environ['APEX_TELEMETRY_RELAY']],input=first+'\n',
                text=True,capture_output=True,env=env,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        device=TelemetryDevice.objects.get(device_id='BENCH-ESP32-001')
        self.assertEqual(device.latest,json.loads(first))
        self.client.force_login(owner)
        snapshot=self.client.get('/live/api/devices/BENCH-ESP32-001/').json()
        self.assertTrue(snapshot['online'])
        self.assertEqual(snapshot['telemetry']['gnss']['satellites'],json.loads(first)['gnss']['satellites'])


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class DashboardAssignmentTests(TelemetryTests):
    def setUp(self):
        super().setUp()
        from .live_models import FollowDriver, FollowSession, TimingTrack
        from .live_core import ApexAdapter
        from .test_livecoach import GRID, packet
        adapter=ApexAdapter();adapter.apply(packet(0,"title2||Dashboard test\ngrid||"+GRID))
        self.track=TimingTrack.objects.create(slug="dashboard-test",name="Dashboard test",parser_state=adapter.state,worker_at=self.now,connection="connected")
        self.session=FollowSession.objects.create(owner=self.owner,track=self.track,name="Dashboard replay")
        self.driver=FollowDriver.objects.create(session=self.session,identity=adapter.entrants()[0]["identity"],name="NOAH SMEETS",kart="13")
        self.assign_url='/live/api/devices/BENCH-ESP32-001/assign/'
        self.client.force_login(self.owner)

    def assign(self,driver_id):
        return self.client.post(self.assign_url,json.dumps({"driver_id":driver_id}),content_type="application/json")

    def test_online_select_assignment_and_timing_on_ingest(self):
        self.assertEqual(self.assign(self.driver.pk).status_code,409)
        self.assertEqual(self.post().status_code,202)
        listing=self.client.get('/live/api/devices/').json()
        self.assertTrue(listing['devices'][0]['online'])
        self.assertEqual(listing['drivers'][0]['id'],self.driver.pk)
        self.assertEqual(self.assign(self.driver.pk).status_code,200)
        self.now+=timedelta(seconds=.2)
        timing=self.post(frame(2)).json()['timing']
        self.assertTrue(timing['valid']);self.assertEqual(timing['last_lap_ms'],61500)
        self.assertEqual(timing['kart_number'],'13')
        self.assertEqual(self.assign(None).json()['timing']['status'],'unassigned')

    def test_owner_isolation_and_csrf(self):
        self.post();self.client.force_login(self.other)
        self.assertEqual(self.client.get('/live/api/devices/').json()['devices'],[])
        self.assertEqual(self.assign(self.driver.pk).status_code,404)
        self.device.owner=self.other;self.device.save(update_fields=['owner'])
        self.assertEqual(self.assign(self.driver.pk).status_code,404)
        protected=Client(enforce_csrf_checks=True);protected.force_login(self.other)
        self.assertEqual(protected.post(self.assign_url,'{}',content_type='application/json').status_code,403)

    def test_source_and_session_staleness_clear_values(self):
        from .telemetry_timing import timing_for
        self.device.assigned_driver=self.driver
        self.track.worker_at=self.now-timedelta(seconds=46);self.track.save(update_fields=['worker_at'])
        # Reload relation, like the HTTP response path.
        device=TelemetryDevice.objects.select_related('assigned_driver__session__track').get(pk=self.device.pk)
        device.assigned_driver=self.driver
        self.driver.session=self.session;self.session.track=self.track
        state=timing_for(device,self.now)
        self.assertFalse(state['valid']);self.assertIsNone(state['last_lap_ms'])
        self.session.state='stopped'
        self.assertEqual(timing_for(device,self.now)['status'],'session_stopped')


    def test_heartbeat_grace_does_not_extend_sensor_freshness(self):
        self.post(frame(valid=True));self.client.force_login(self.owner)
        self.now+=timedelta(seconds=5)
        state=self.client.get(self.detail).json()
        self.assertTrue(state['online']);self.assertEqual(state['connection_status'],'delayed')
        self.assertFalse(state['telemetry']['gnss']['valid'])
        self.assertEqual(self.assign(self.driver.pk).status_code,200)
        self.now+=timedelta(seconds=11)
        self.assertFalse(self.client.get(self.detail).json()['online'])
        self.assertEqual(self.assign(self.driver.pk).status_code,409)
