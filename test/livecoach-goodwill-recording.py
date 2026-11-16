"""Read-only regression against the closed Goodwill recording (path argument)."""
import json
import sys
from collections import defaultdict
from www.live_core import ApexAdapter
from www.live_pit import forecast
adapter=ApexAdapter();previous={};swaps=[];pits=[];clean=defaultdict(int)
for line in open(sys.argv[1]):
 event=json.loads(line)
 passages=adapter.apply(event)
 if event['seq']==5750:
  standings=adapter.standings();noah=next(r for r in standings if r['name']=='SMEETS Noah')
  result=forecast(standings,noah,dict(durationSeconds=90,requiredStops=1,netLossSeconds=None),adapter.race_progress())
  assert noah['lastPitMs']==90851
  assert result['expectedCorrectedPosition']==result['expectedEndPosition']==3

 for entrant in adapter.entrants():
  if entrant['name']!='SMEETS Noah':continue
  old=previous.get(adapter.state['generation'])
  if old and old['kart']!=entrant['kart']:
   assert old['identity']==entrant['identity']
   swaps.append((old['kart'],entrant['kart']))
  previous[adapter.state['generation']]=entrant
 for passage in passages:
  if passage['name']=='SMEETS Noah' and passage['metric']=='lap':
   if passage['pitLap']:pits.append(passage['timeMs'])
   else:clean[adapter.state['title']]+=1
assert swaps==[('30','25'),('15','25'),('3','30')],swaps
assert pits==[141875,136545,130653],pits
assert adapter.sector_ids()==['S1','S2']
assert all(clean[title]>10 for title in ['Wedstrijd 1','Wedstrijd 2','Wedstrijd 3'])
noah=next(row for row in adapter.standings() if row['name']=='SMEETS Noah')
assert noah['pitCount']==1 and noah['pitSamples'][0]['pitMs']==90847
print('PASS: 3 kart changes keep identity; 3 pit laps excluded; clean laps continue after each swap; two sectors; measured entry-to-exit pit duration.')
