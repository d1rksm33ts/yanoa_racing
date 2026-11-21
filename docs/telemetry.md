# Kartdashboard op Racing Live

De gebruiker kiest op `/live/` eerst Training, Sprint of Endurance. Binnen die modus staat **Dashboard per piloot** direct onder de pilotenlijst. Kies baan of opname, selecteer een piloot en kies bij diens naam een online dashboard. Vóór de sessiestart wordt die keuze bewaard tot **Start volgsessie**; bij bestaande gevolgde piloten geldt de wijziging direct. Nieuwe piloten in een bestaande sessie koppelen zodra **Update piloten** hen toevoegt. Apparaten en toewijzingen blijven eigenaargebonden. De fysieke setup is één dashboard, ondanks de twee ESP32-controllers.

## Transport en timing

De LilyGO maakt vanaf de bestaande wifi een uitgaande, geauthenticeerde **HTTPS**-verbinding met Racing. Er is geen publiek bereikbaar apparaatadres of extra Apex-scraper nodig. TLS-certificaatcontrole blijft ingeschakeld (publieke ISRG Root X1/X2); de ESP32 synchroniseert eerst zijn klok via NTP. Het privé-bearertoken staat alleen in het genegeerde `kartingdashboard/firmware/telemetry-node/include/racing_config.h`; de database bewaart de SHA-256-digest. Dit werkende PoC gebruikt HTTPS in plaats van de eerder voorgestelde MQTT-infrastructuur. De bestaande optionele `apex`-USB-relay blijft bruikbaar voor bench-ingest.

Een aparte ESP32-taak verstuurt de nieuwste sensorframe en verwerkt het antwoord. Een queue van één frame voorkomt een achterstand en houdt HTTPS buiten de GPS/IMU/SD/UI-loop. Antwoorden bevatten `timing` uit de bestaande `ApexAdapter`, gekoppeld via `TelemetryDevice.assigned_driver` aan `FollowDriver`. De bestaande live worker en replayparser leveren dezelfde brondata. Er wordt geen tweede timingstream geopend.

De LilyGO geeft timing via de bestaande UART aan de Panlee door. Het scherm toont piloot, kart, positie, beschikbare officiële rondeteller, laatste en beste ronde. `REPLAY / SIMULATION` onderscheidt een opname van live timing; gepauzeerde replay meldt `replay_paused`. Ontbrekende waarden blijven leeg/`--`. Een ontbrekende piloot, gestopte sessie of bron zonder werkende worker wist geldige timing. De bronheartbeat verloopt na 45 seconden; een ontbrekend succesvol serverantwoord na 3 seconden. Bij UART-uitval vervalt de displaydata na 1,5 seconde. Dataverlies levert geen nulrondetijden op.

Toewijzing hoort bij servermetadata. De sensorpayload houdt `session_id=null` en `sample_ts_ms=null`: servertoewijzing en NTP voor TLS maken nog geen betrouwbare UTC-timestamp van elke GPS/IMU-meting.

## API en provisioning

- `POST /live/api/devices/<device_id>/telemetry/`: onafhankelijke bearercredential, JSON, maximaal 4096 bytes. Cookie-login geeft geen schrijfrecht. Geaccepteerde frames geven HTTP 202 met `accepted`, `seq` en `timing` terug.
- `GET /live/api/devices/`: ingelogde eigenaar; eigen apparaten, online-status, huidige toewijzing en eigen piloten uit actieve volgsessies.
- `POST /live/api/devices/<device_id>/assign/`: ingelogde eigenaar plus CSRF. Body `{"driver_id":123}` of `{"driver_id":null}`. Nieuwe koppelingen vereisen een online apparaat. Elke wijziging verhoogt `assignment_revision`.
- `GET /live/api/devices/<device_id>/`: bestaande eigenaargebonden sensorstatus.

Online betekent een geaccepteerd frame in de laatste 15 seconden. Na 3 seconden meldt de website **Verbinding vertraagd**; na 15 seconden **Offline**. Dit is gescheiden van sensor- en timinggeldigheid. GPS/IMU worden ongeldig na 1 seconde zonder vers frame. Ingress accepteert maximaal 10Hz. Dubbele/oudere sequences, teruglopende uptime en hergebruik van oude boot-ID's worden geweigerd. Na 64 gepensioneerde boots is administratieve herprovisioning vereist. Er wordt alleen de laatste sensorframe opgeslagen; de SD-opname blijft op het apparaat.

Nieuw apparaat registreren met een bestaande gebruiker met `www.use_livecoach`:

```sh
python server/manage.py provision_telemetry_device BENCH-ESP32-001 --owner EXISTING_USER --token-file /private/path/device.token
```

Het commando overschrijft geen apparaat of tokenbestand en maakt het bestand met modus 0600. Trek toegang in met `enabled=False`. Deel tokens niet tussen apparaten. Migraties `0017_telemetry_device` en `0018_telemetry_assignment` voegen registratie/toewijzing toe.

## Geteste release, 20 november 2026

- Productie Live-image: `yanoa-racing-live:20261120-kart-dashboard`; gebouwd op de actieve Live-image met uitsluitend telemetrybestanden, routes/modelimport en dashboardpaneel. Hoofdwebsite en timing/simulatieworker-images bleven behouden.
- Backup en releasecontext: `/home/ubuntu/livecoach-build-20261120-kart-dashboard/`. Vorige webimage: `yanoa-racing-live:20261118-training-potential`; vorige compose-env is privé bewaard. Bij rollback kan de oude webimage met de extra tabellen blijven werken.
- Account `racing_admin`, apparaat `BENCH-ESP32-001`, label **Kartdashboard Noah**. Beide fysieke controllers draaien `0.4.0-racing`.
- Afzonderlijke volgsessie **Dashboard test · Goodwill · Noah**, echte opname **Goodwill · 13 november 2026 · Pro en overige reeksen**, segment 11, **SMEETS Noah**, kart 15. Bestaande simulaties/sessies zijn niet gewijzigd.
- 120 Django-tests ontdekt: 119 geslaagd, één optionele cross-repo-test overgeslagen. Browsermatrix desktop/mobiel × normaal/traag controleert offline/online, CSRF-koppelen, ontkoppelen, respons uit de replayparser, layout en zichtbare startup. Productiebrowsercontrole deed uitsluitend GET/HEAD; echte heartbeat/timing via fysieke ESP32's bevestigd.
- Gedeelde laadchecker voor en na publicatie: desktop en mobiel normaal/traag binnen 2s/3s. Ingelogde productiepagina FCP 216–560ms in de vier controles.

Browserproef lokaal (DEBUG + SQLite, ontwikkelserver op 127.0.0.1:8210):

```sh
python test/livecoach-devices-browser.py
```

De test maakt eigen tijdelijke opname/account/sessie aan en verwijdert die achteraf. Verdere praktijkproeven: scherm visueel bevestigen, fysieke blauwe/rode knop bedienen, GPS buiten met fix, lange wifi-uitval en belastings-/duurtest. Sensorhistoriek op de server, sector/delta-weergave en LTE zijn vervolgwerk.

De fysieke onderbrekingsproef slaagde: zeven seconden geen geaccepteerde heartbeat gaf `server_offline`, `valid=false` en lege rondetijden op de Panlee; daarna automatisch herstel. De testreplay is achtergelaten op **pauze**, snelheid **1×**, positie1, ronde13, laatste/beste63892ms. Hervat met **Afspelen** in de betreffende volgsessie.


## Bijgewerkte sessieflow en heartbeat

Release `yanoa-racing-live:20261120-device-flow`, context `/home/ubuntu/livecoach-build-20261120-device-flow/`, opvolger van `20261120-kart-dashboard`. Geen nieuwe migratie; bestaande hoofdwebsite, bronworkers en gebruikerssessies zijn behouden. De drie-modikeuze bevat geen losse apparaatkoppeling meer. De coach publiceert een beperkte `coach:dashboard-context` met gekozen modus/baan/piloten en de huidige actieve sessie; het dashboardpaneel matcht uitsluitend die pilootidentiteiten binnen die sessie. Vooraf gekozen apparaten worden toegewezen zodra de server de gevolgde piloten heeft aangemaakt. Een dashboard kan niet gelijktijdig voor twee nieuwe piloten worden gekozen.

`GET devices` geeft ook `connection_status` (`online`, `delayed`, `offline`), `receipt_age_ms`, plus identity/session_id/activity bij eigen actieve gevolgde piloten terug. Online-grace en toewijzing gebruiken dezelfde grens van 15s. Sensorfreshness blijft 1s, device-timingfreshness blijft 3s; grace presenteert geen oude metingen als actueel.

LilyGO **0.4.1-heartbeat** hergebruikt HTTPS/TLS, leest elke begrensde response volledig en heeft 800ms wachttijd na een geslaagd antwoord (ongeveer 1Hz). Connect-timeout 5s, TLS-handshake maximaal6s; netwerk blijft in de eigen taak. `/api/racing` bevat `racing_link` met antwoordleeftijd, ontvangen aantallen, fouten, laatste HTTP-code, roundtrip en RSSI. Panlee blijft **0.4.0-racing**. De ruwe TLS-diagnose is het resultaat van de onderliggende TLS-client, geen afzonderlijke heartbeatfoutenteller; positieve waarden kunnen een socketdescriptor zijn.

Validatie: 121 Django-tests ontdekt,120 geslaagd en1 optioneel overgeslagen. Nieuwe browsermatrix: Training/Sprint/Endurance × desktop/mobiel × normaal/traag, alle12 geslaagd, inclusief vooraf kiezen, automatisch toewijzen bij start, direct ontkoppelen/herkoppelen. FCP lokaal28–764ms. Productie12 uitsluitend-lezen scenario's geslaagd; geen pilotkeuzes/formulieren verstuurd. Tijdelijke browsersessie verwijderd. Fysieke 90s-heartbeatmeting:81 meetpunten,93 nieuwe geaccepteerde antwoorden,0 nieuwe fouten, maximale antwoordleeftijd1124ms,0 timing-offlinepunten. Er waren5 fouten vóór deze duurmeting bij opstarten/herverbinden. Dit is een korte functionele proef, geen lange wifi-duurtest.

## Physical session screens

`20261120-session-screens` extends only the timing adapter. It publishes `activity`, bounded `metrics` (sectors+lap, time/delta/best/color/active/ideal delta), training pace/ideal, exact gap-ahead when calculable, race clock/rate/finish and endurance pit state/projections. Calculations reuse Live Coach helpers; no extra Apex connection or duplicate predictor is introduced. Unknowns stay null; stale/session-stopped responses clear metrics and mode-specific values. Official finish keeps a clearly marked frozen result rather than pretending a new live passage.

The physical firmware0.5.0 selects its layout from FollowSession.activity automatically. Existing website selection flow is unchanged. See `../kartingdashboard/docs/session-screens.md` and `www.test_dashboard_screens`. Seven dedicated tests cover website parity, mode isolation/staleness, exact versus leader gap, Unicode/frame bounds and official finish. The full126-test suite passed125, optional cross-repo test skipped. Release directory `/home/ubuntu/livecoach-build-20261120-session-screens/` retains prior compose-env; previous webimage `20261120-device-flow` is the rollback target. No migration or frontend changes. Current user assignment/session and all other container images were preserved.

## Latest-sector projection for the focused training display

Release `20261120-focused-training` adds nullable `latest_sector` to the existing timing payload. It selects the maximum observed `(sector cycle, sector order)` from the selected row's `sector_seen`. A newS1 outranks the previous lap's final sector; lap feedback leaves the final sector selected; an unobserved snapshot remains unknown. Invalid/unassigned source responses clear this field. Regression tests cover those cases. No model migration or website frontend change. The corresponding physical firmware is0.5.1-focused-training; see sibling display documentation for the compact title, black background, latest-sector emphasis and real wallclock/connectivity status.


## Trainingspotentieel en T-positie (20 november 2026)

`training_comparison` levert `potentialMs` als eigen beste min ideale beste per sector. De ronde vergelijkt eigen beste ronde met de som van de ideale sectoren. Een tragere laatste passage vergroot dit winstpotentieel niet. Onbekende referenties blijven null; winst is minimaal nul. De trainingspagina toont dit als **Te winnen** en beperkt het potentieelpaneel tot Eigen beste, Ideale ronde en Nog te winnen.

Het fysieke dashboard ontvangt hetzelfde getal in `metrics[].potential_ms` (`ideal_delta_ms` blijft een compatibiliteitsalias). `training.position` is T1/T2/… op beste rondetijd, los van de racepositie. Panlee0.5.4-training-delta zet de eigen delta groot, de werkelijke sectortijd en winstpotentieel kleiner, en toont de T-positie. De Inter-sectorletter heeft marge tegen afknippen. LilyGO blijft0.5.1-focused-training.

Geïsoleerde productie-image `yanoa-racing-live:20261120-training-gain`, geen migratie of wijziging van actieve koppeling/bronworkers. Volledige Django-suite132tests:131 geslaagd,1optionele skip. Lokale interactieve browsermatrix desktop/mobiel normaal/traag geslaagd; gedeelde website-startupchecker vóór/na publicatie.


## Pitweergave op het kartscherm (0.5.6)

`telemetry_pit.py` projecteert pitgegevens voor training, sprint en endurance: `pit.phase` (`in`/`exit`/`track`), `in_pit`, `elapsed_ms`, `required_ms`, `remaining_ms`, `last_duration_ms`. Het minimum komt uitsluitend uit de sessiepitinstellingen en is een ingestelde herinnering, geen afgeleid reglement. Ontbrekende instellingen/metingen blijven null. Replay gebruikt de originele tijdlijn inclusief speed/pause. Verlopen brondata levert geen geldige pitweergave.

Parserveld `pit_exit_pending` wordt bij een gemeten pit-uit gezet en bij de volgende echte sector verwijderd, ook als de sector niet meetelt voor schone bests wegens pit_dirty. Snapshots, ib-styling, positie-updates en een sector in hetzelfde pakket als pit-uit beëindigen de weergave niet. Zonder sectoren geldt de volgende bevestigde rondepassage. Identiteits-/sessie-/rondetellerreset wist de oude pitstatus. Een late/reconnect-client ontvangt hierdoor dezelfde toestand als een al aangesloten scherm.

Panlee0.5.6-pit-screen toont in de pit een minimumafteller en tussensamenvatting; na uitgang de pittijd groot en een melding als het ingestelde minimum niet is gehaald. De volgende sector herstelt de gewone modus; finish geeft voorrang aan het eindoverzicht. Alleen backend/firmware aangepast, geen frontendassets of migraties.

Gerichte geïsoleerde images: web `yanoa-racing-live:20261120-pit-web` bovenop training-gain; bestaande simulation/agadir/campillos/spa workers `yanoa-racing-live:20261120-pit-worker` bovenop training-colors. Andere bronworkers zijn niet gestart, hoofdwebsite en assignment behouden. Rollback-env alleen privé in de releasefolder. Django138tests:137geslaagd,1optionele skip; gedeelde loadingchecker vóór/na geslaagd.


## Pit-uitprojectie en sectorwinsten in alle modi (0.5.8)

De parser bewaart bij pit-in `pit_entry_field`: minimale positiespecifieke brongegevens (identity, gapMs, gapEstimated, laps, inPit) uit één tijdstip. Deze snapshot wordt behouden bij reconnect en gewist bij nieuwe piloot/sessie/tellerreset. `telemetry_pit.exit_position` vergelijkt die startachterstanden plus totale netto pitverliestijd met het veld. Een handmatige `netLossSeconds` of minstens3waargenomen bypassmonsters en pace zijn nodig. Er wordt niet nogmaals een volledig pitverlies bij een al vertraagde actuele achterstand geteld. Ontbrekende/niet vergelijkbare tegenstanders verbreden het bereik; ontbrekende eigen entrydata/calibratie geeft null. Extra verblijf boven de doelduur telt mee. Dit is een schatting bij gelijk relatief tempo, geen gegarandeerde uitgangspositie.

De timing-API levert `pit.exit_position` met best/worst voor alle drie sessietypes en gedeelde `metrics[].potential_ms` voor sectorwinsten ook in sprint/endurance. Training blijft de bestaande vergelijking gebruiken. Andere race-/pitforecastvelden blijven intact. Bestaande stops van vóór de upgrade hebben geen entrysnapshot; de volgende waargenomen pit-in levert die automatisch.

Geïsoleerde releases `yanoa-racing-live:20261120-pit-focus-web` en `...pit-focus-worker` bovenop de vorige pit-images; alleen parser/projectie toegevoegd, geen schema-/frontendwijziging. Actieve simulation/agadir/campillos/spa workers herstart met behoud van sessies en replaydata; andere workers niet gestart. Panlee0.5.8, SIM0.5.1blijft behouden. Volledige Django143tests:142geslaagd/1optionele skip;11gerichte pittestcases daarna geslaagd inclusief gain-in-alle-modi. Native tests controleren exact1s/2s-grenzen en sectorprioriteiten.

Loadingchecker desktop/mobiel normaal/traag vóór en na; één trage precheck3.684s, herhaling geslaagd (trage verbinding0.408s). Geen frontendcode aangepast. Productiebrowser gebruikt uitsluitend leesverzoeken; tijdelijke authsessie wordt nadien verwijderd.

Eindcontrole0.5.8: alle16 fysieke renderproeven vastgelegd, DEMO0 bevestigd, UART online, Inter geladen, oplopende ACKs en OTA klaar. Beide controller-MACs/versies gecontroleerd; SIM niet geflasht. De gebruiker schakelde tijdens het werk naar een andere endurance-sessie (assignment_revision13); deze is behouden. Vier verse leesbrowsers op de daadwerkelijk gekoppelde endurance geslaagd (desktop/mobiel normaal/traag, FCP200–544ms), web/workers healthy. Gedeelde checker na publicatie desktop196/416ms en mobiel260/456ms. Geen productieformulier of toewijzing bediend.
