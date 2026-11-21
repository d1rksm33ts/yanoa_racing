"""Pit display facts; duration is a configured reminder, never a guessed rule."""
def pit_display(row, raw, track, session, now, race, simulation=None):
    source_now = int(now.timestamp() * 1000)
    if track.mode == 'replay':
        source_now = track.parser_state.get('clockMs', 0)
        if simulation:
            from .live_simulation import target_position
            origin = simulation.recording.segments[simulation.segment].get('state', {}).get('clockMs')
            if origin is not None:
                source_now = origin + target_position(simulation, now)
    elif not race.get('rate'):
        source_now = track.parser_state.get('clockMs', source_now)
    configured = (session.pit_settings or {}).get('durationSeconds')
    required = round(configured * 1000) if type(configured) in (int, float) and configured >= 0 else None
    elapsed = max(0, source_now - raw['pit_enter_ms']) if row.get('inPit') and type(raw.get('pit_enter_ms')) is int else None
    phase = 'in' if row.get('inPit') else 'exit' if raw.get('pit_exit_pending') else 'track'
    return {'phase': phase, 'in_pit': bool(row.get('inPit')), 'elapsed_ms': elapsed,
            'required_ms': required,
            'remaining_ms': max(0, required - elapsed) if required is not None and elapsed is not None else None,
            'last_duration_ms': row.get('lastPitMs')}


def exit_position(row, raw, rows, settings, elapsed_ms=None):
    """Estimate after this stop from entry gaps + calibrated total net pit loss.

    Current gaps may already include part of a stop: never add full loss to them.
    Missing/lapped/in-pit opponents widen the range rather than inventing a rank.
    """
    from .live_pit import pace, position_range
    from statistics import median
    field = raw.get('pit_entry_field', [])
    own = next((r for r in field if r.get('identity') == row['identity']), None)
    if not own or type(own.get('gapMs')) is not int or own.get('gapEstimated') or own.get('laps') is None:
        return None
    duration = settings.get('durationSeconds')
    if type(duration) not in (int, float) or duration < 0:
        return None
    manual = settings.get('netLossSeconds')
    if type(manual) in (int, float) and manual >= 0:
        low = high = round(manual * 1000)
    else:
        samples = [s['bypassFraction'] for r in rows for s in r.get('pitSamples', []) if type(s.get('bypassFraction')) in (int, float) and 0 <= s['bypassFraction'] <= .8]
        paces = [p for r in rows if (p := pace(r))]
        current_pace = pace(row) or (int(median(paces)) if paces else None)
        if len(samples) < 3 or not current_pace:
            return None
        low = max(0, round(duration*1000-min(.8,max(samples)+.05)*current_pace))
        high = max(low, round(duration*1000-max(0,min(samples)-.05)*current_pace))
    overstay = max(0, (elapsed_ms or 0) - round(duration*1000))
    low += overstay; high += overstay
    def interval(other):
        if other.get('inPit') or other.get('gapEstimated') or type(other.get('gapMs')) is not int or other.get('laps') != own['laps']:
            return None
        return (max(0, other['gapMs']-500), other['gapMs']+500)
    return position_range(field, row, (own['gapMs']+low, own['gapMs']+high), interval)
