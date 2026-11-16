"""Pit and pace projections using only timing already received in this session."""
from math import ceil, floor, isfinite
from statistics import median
from .live_core import milliseconds, delta_text


def settings_for(track):
    return {"durationSeconds": 90, "requiredStops": 1 if track.source_id == "goodwill" else 0, "netLossSeconds": None}


def validate_settings(value):
    duration, stops, loss = value['durationSeconds'], value['requiredStops'], value.get('netLossSeconds')
    if type(duration) not in (int, float) or not isfinite(duration) or not 0 <= duration <= 1800:
        raise ValueError('Invalid pit duration')
    if type(stops) is not int or not 0 <= stops <= 5:
        raise ValueError('Invalid pit count')
    if loss is not None and (type(loss) not in (int, float) or not isfinite(loss) or not 0 <= loss <= 1800):
        raise ValueError('Invalid net loss')
    return {"durationSeconds": duration, "requiredStops": stops, "netLossSeconds": loss}


def gap_ms(row):
    if 'gapMs' in row:
        return row['gapMs']
    return 0 if row.get('position') == 1 or row.get('gap', '').strip() in {'0.000', '0,000', '0:00.000'} else milliseconds(row.get('gap', ''))


def clean_times(row):
    return [v['timeMs'] for v in row.get('recentLaps', []) if v['kart'] == row['kart']][-6:]


def pace(row):
    values = clean_times(row) or [v['timeMs'] for v in row.get('recentLaps', [])][-3:]
    return int(median(values[-3:])) if values else None


def pace_band(row):
    values = clean_times(row)[-3:]
    if len(values) == 3:
        return min(values)-100,max(values)+100
    if values:
        margin=max(1000 if len(values)==1 else 500,round(median(values)*0.02))
        return min(values)-margin,max(values)+margin
    previous=[v['timeMs'] for v in row.get('recentLaps', [])][-3:]
    if previous:
        center=int(median(previous));margin=max(3000,round(center*0.05))
        return center-margin,center+margin
    return None


def position_range(rows, own, own_interval, opponent_interval):
    low = high = 1
    for other in rows:
        if other['identity'] == own['identity']:
            continue
        interval = opponent_interval(other)
        if interval is None:
            high += 1
        else:
            low += interval[1] < own_interval[0]
            high += interval[0] <= own_interval[1]
    return {'best': low, 'worst': high}


def horizon(race, settings, reference_pace):
    if race.get('remainingLaps') is not None:
        n = race['remainingLaps']
        return (n, n), 'laps'
    if race.get('remainingMs') is not None and reference_pace:
        # A timed race ends at a finish-line passage, not exactly at zero on the clock.
        n = race['remainingMs'] / reference_pace
        return (max(0, floor(n)), ceil(n)+1), 'clock'
    return None, None


def future_interval(base, band, reference, laps):
    shifts = [(p-reference)*n for p in band for n in laps]
    return base[0]+min(shifts), base[1]+max(shifts)


def forecast(rows, own, settings, race=None):
    race = race or {}
    duration = round(settings['durationSeconds']*1000)
    required = settings['requiredStops']
    remaining = max(0, required-own.get('pitCount', 0))
    result = {'remainingStops': remaining, 'inPit': own.get('inPit', False),
              'pitElapsedMs': own.get('pitElapsedMs'),
              'pitRemainingMs': max(0,duration-(own.get('pitElapsedMs') or 0)) if own.get('inPit') else None}
    if own.get('finished') or race.get('finished'):
        return {**result,'status':'finished','correctedPosition':{'best':own['position'],'worst':own['position']} if own.get('position') else None,'endPosition':{'best':own['position'],'worst':own['position']} if own.get('position') else None,'message':'Finish · huidige APEX-eindstand.'}
    pending = any(max(0,required-r.get('pitCount',0)) or r.get('pitUnreflected') for r in rows)
    samples = [s for r in rows for s in r.get('pitSamples',[])]
    field_paces = [p for r in rows if (p := pace(r))]
    reference = int(median(field_paces)) if field_paces else None
    current_pace = pace(own) or reference
    result['paceMs'] = current_pace
    manual = settings.get('netLossSeconds')
    def loss_for(row):
        if not pending:
            return (0,0)
        if manual is not None:
            loss = round(manual*1000)
            return (loss,loss)
        p = pace(row) or current_pace
        if len(samples)<3 or not p:
            return None
        fractions = [s['bypassFraction'] for s in samples]
        low = max(0,round(duration-min(0.8,max(fractions)+0.05)*p))
        high = max(low,round(duration-max(0,min(fractions)-0.05)*p))
        return low,high
    own_loss = loss_for(own)
    if own_loss is None:
        return {**result,'status':'uncalibrated','message':'Nog onvoldoende pitdata. Vul eventueel netto tijdverlies in; pitduur is niet hetzelfde als netto verlies.'}
    if pending:
        result.update(lossMinMs=own_loss[0],lossMaxMs=own_loss[1],basis='Handmatige aanname voor netto tijdverlies' if manual is not None else f'Schatting uit {len(samples)} waargenomen pitstops en recent tempo')
    own_gap = gap_ms(own)
    if own_gap is None:
        return {**result,'status':'unknown-gap','message':'APEX publiceert geen exact eigen tijdverschil; geen betrouwbare positie- of tempo-instructie.'}
    def adjusted(row):
        gap = gap_ms(row)
        if gap is None or row.get('inPit'):
            return None
        stops = max(0,required-row.get('pitCount',0)) + int(row.get('pitUnreflected',False))
        loss = loss_for(row)
        return (max(0,gap-500)+stops*loss[0],gap+500+stops*loss[1]) if loss and row.get('gapEstimated') else (gap+stops*loss[0],gap+stops*loss[1]) if loss else None
    if own.get('inPit'):
        return {**result,'status':'in-pit','message':'In de pit · positie wordt opnieuw berekend bij uitgang.'}
    own_adjusted = adjusted(own)
    net = position_range(rows,own,own_adjusted,adjusted)
    result.update(status='complete' if not remaining else 'estimated', correctedPosition=net,
                  positionsChange={'best':(own.get('position') or 1)-net['best'],'worst':(own.get('position') or 1)-net['worst']},
                  message='Na stops: huidige achterstanden inclusief alle nog verplichte stops. Einde: recent tempo doorgetrokken tot de finish; ranges tonen onzekerheid.')
    point = position_range(rows,own,(sum(own_adjusted)/2,)*2,lambda r: (sum(value)/2,)*2 if (value:=adjusted(r)) is not None else None)
    if point['best']==point['worst']:
        result['expectedCorrectedPosition']=point['best']
    if remaining:
        result['temporaryPosition'] = position_range(rows,own,(own_gap+own_loss[0],own_gap+own_loss[1]),lambda r: None if r.get('inPit') or gap_ms(r) is None else (gap_ms(r),gap_ms(r)))
    laps, source = horizon(race,settings,reference)
    own_band = pace_band(own)
    result['paceProvisional'] = len(clean_times(own)) < 3
    if laps is not None:
        result.update(horizonLaps={'min':laps[0],'max':laps[1]},horizonSource=source)
    if laps is not None and reference and own_band:
        own_end = future_interval(own_adjusted,own_band,reference,laps)
        def end_interval(row):
            start,band = adjusted(row),pace_band(row)
            return future_interval(start,band,reference,laps) if start is not None and band else None
        result['endPosition'] = position_range(rows,own,own_end,end_interval)
        n_center=sum(laps)/2
        own_center=sum(own_adjusted)/2+(current_pace-reference)*n_center
        def end_center(row):
            base=adjusted(row)
            return (sum(base)/2+(pace(row)-reference)*n_center,)*2 if base is not None and pace_band(row) else None
        point=position_range(rows,own,(own_center,own_center),end_center)
        if point['best']==point['worst']:
            result['expectedEndPosition']=point['best']
    n = (sum(laps)/2) if laps is not None else None
    if n and own_band and current_pace and clean_times(own):
        rivals=[]
        for row in rows:
            if row['identity']==own['identity']:
                continue
            start,band = adjusted(row),pace_band(row)
            if start is None or band is None:
                continue
            margin = sum(start)/2-sum(own_adjusted)/2
            other_pace=pace(row)
            closing = current_pace-other_pace
            rivals.append({'name':row['name'],'position':row.get('position'),'remainingStops':max(0,required-row.get('pitCount',0)),
                           'marginAfterStopsMs':round(margin),'closingMsPerLap':closing,
                           'catchLaps':round(margin/closing,1) if margin>0 and closing>0 else None,
                           'endMarginMs':round(margin-n*closing),
                           'targetLapMs':round(other_pace+(margin-2000)/n)})
        # Target the better of the current on-track position and the corrected position.
        target=min(own.get('position') or net['best'],net['best'])
        ordered=sorted(rivals,key=lambda r:r['targetLapMs'])
        target_rival=ordered[target-1] if len(ordered)>=target else None
        threats=sorted((r for r in rivals if r['marginAfterStopsMs']>=0 and (r['endMarginMs']<=2000 or r['marginAfterStopsMs']<=2000)),key=lambda r:r['endMarginMs'])
        if (result.get('expectedCorrectedPosition') or net['best'])>target:
            threats += sorted((r for r in rivals if r['marginAfterStopsMs']<0),key=lambda r:-r['marginAfterStopsMs'])
        if target_rival:
            gain=max(0,current_pace-target_rival['targetLapMs'])
            all_known=len(rivals)==len(rows)-1 and all(len(clean_times(r))>=3 for r in rows)
            instruction = f'P{target} buiten bereik bij dit tempo' if target_rival['targetLapMs'] <= 0 else f'Voor P{target}: ≈{gain/1000:.3f}s/ronde sneller' if gain else (f'Houd tempo voor P{target}' if all_known else f'Tempo lijkt voldoende voor P{target}')
            result['coaching']={'text':instruction,'targetPosition':target,'neededGainMs':gain,
                                'targetLapMs':max(0,target_rival['targetLapMs']) if gain else current_pace,
                                'limitedData':not all_known,'threats':threats[:3]}
        else:
            result['coaching']={'text':f'Houd tempo voor P{target}' if len(rivals)==len(rows)-1 else 'Onvoldoende vergelijkbare tegenstanders','limitedData':len(rivals)!=len(rows)-1,'threats':threats[:3]}
    else:
        result['coaching']={'text':'Nieuw karttempo nog onbekend' if own_band and not clean_times(own) else 'Wacht op rondetijden' if not own_band else 'Resterende raceduur onbekend','limitedData':True,'threats':[]}
    trends=[]
    for row in rows:
        values=clean_times(row)
        if len(values)==6:
            trends.append(median(values[3:])-median(values[:3]))
    if len(trends)>=3:
        trend=round(median(trends));result.update(trendMs=trend,trendDrivers=len(trends),trendText=delta_text(trend))
        result['strategy']='De baan wordt sneller. Eerder pitten kan gunstig zijn.' if trend < -300 else 'De baan wordt trager. Later pitten kan gunstig zijn.' if trend>300 else 'Geen duidelijke voorkeur voor vroeg of laat pitten.'
    else:
        result['strategy']='Nog onvoldoende vergelijkbare rondes voor een baantrend.'
    return result
