"""Enrich existing replay checkpoints without replaying feedback or changing identities."""
import copy
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from www.live_core import ApexAdapter
from www.live_models import TimingSimulation, TimingTrack, FollowSession
from www.live_simulation import recording_path
from www.live_service import publish

ROOT_FIELDS=('race_deadline_ms','race_remaining_laps','clockMs','session_best_times')
ROW_FIELDS=('sector_bests','observed_best_lap','lap_crossings','last_pit_ms','last_pit_exit_ms','pit_sample_pending','pit_dirty','pit_samples','pit_pace_ms','completed_pits','in_pit','training_times','training_latest_metric')

class Command(BaseCommand):
    help='Refresh derived replay timing fields only, preserving driver IDs and reference blocks.'
    def add_arguments(self, parser):
        parser.add_argument('--owner-id',type=int,required=True)
        parser.add_argument('--auto-pit-session')
        parser.add_argument('--training-only',action='store_true')
        parser.add_argument('--backup',default='/tmp/pace-checkpoints-before.json')
    @transaction.atomic
    def handle(self,*args,**options):
        backups=[];count=0
        sims=TimingSimulation.objects.select_for_update(of=('self',)).select_related('recording').filter(owner_id=options['owner_id'],state__in=['paused','playing']).order_by('track_id')
        for sim in sims:
            track=TimingTrack.objects.select_for_update().get(pk=sim.track_id)
            sessions=list(FollowSession.objects.select_for_update().filter(track=track))
            original=copy.deepcopy(track.parser_state)
            adapter=ApexAdapter(copy.deepcopy(sim.recording.segments[sim.segment]['state']))
            with recording_path(sim.recording).open('rb') as source:
                source.seek(sim.recording.segments[sim.segment]['byteOffset'])
                while source.tell()<sim.byte_offset:
                    line=source.readline()
                    if not line.endswith(b'\n'):
                        raise ValueError('Incomplete replay checkpoint')
                    adapter.apply(json.loads(line))
            backups.append({'trackId':track.pk,'parserState':original})
            backup=Path(options['backup']);backup.write_text(json.dumps(backups));backup.chmod(0o600)
            # Preserve legacy identities/run IDs even if old parsing generated them differently.
            for key in (() if options.get("training_only") else ROOT_FIELDS):
                if key in adapter.state:track.parser_state[key]=adapter.state[key]
            old_adapter=ApexAdapter(track.parser_state)
            for rid,row in track.parser_state.get('rows',{}).items():
                fresh=adapter.state['rows'].get(rid)
                if fresh is None or old_adapter.field(row,'dr')!=adapter.field(fresh,'dr') or old_adapter.field(row,'no')!=adapter.field(fresh,'no'):
                    continue
                for key in (("training_times", "training_latest_metric") if options.get("training_only") else ROW_FIELDS):
                    if key in fresh:row[key]=copy.deepcopy(fresh[key])
                    else:row.pop(key,None)
            track.save(update_fields=['parser_state'])
            count+=1
        automatic=False
        if options.get('auto_pit_session'):
            session=FollowSession.objects.select_for_update().get(pk=options['auto_pit_session'],owner_id=options['owner_id'])
            if session.state=='active' and session.pit_settings.get('netLossSeconds')==1:
                session.pit_settings={**session.pit_settings,'netLossSeconds':None}
                session.save(update_fields=['pit_settings'])
                publish(session,'pit',{'message':'Netto pitverlies automatisch berekend.'})
                automatic=True
        self.stdout.write(json.dumps({'replayCheckpointsUpdated':count,'automaticPitLoss':automatic,'driverReferencesChanged':False}))
