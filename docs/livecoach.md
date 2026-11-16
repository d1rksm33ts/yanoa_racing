# Live Coach — besloten versie

## Agadir en circuitkeuze zonder simulaties (15 november 2026)

Maroc Racing Kart Agadir is toegevoegd aan Python- en Node-bronregisters met
`wss://live-data.apex-timing.com:8023`. De officiële configuratie van
https://live.apex-timing.com/mrkagadir/javascript/config.js geeft poort 8020;
de officiële HTTPS-client gebruikt poort +3. Een echte WebSocket-snapshot is
ontvangen en bevat de 24H Agadir-finale, deelnemers en officiële commentaren.
Een eigen `agadir-worker` verzorgt ontvangst en raw-opname.

De circuitselectie toont uitsluitend live circuits. Simulatietracks blijven in
het interne API-resultaat voor hun eigen bediening. Een aparte replaycontext
maakt laden en starten mogelijk zonder een verborgen simulatoroptie in het
select-element. Via **Een opname simuleren → Open simulatie** kan een geladen
simulatie opnieuw worden geopend; met een bestaande actieve volgsessie wordt
die heropend met behoud van referenties. Het kiezen van een echt circuit verlaat
de replaycontext. Bestaande simulaties, opnames en volgsessies zijn niet gewist.

Release `/home/ubuntu/livecoach-build-20261115-agadir`, image
`yanoa-racing-live:20261115-agadir`, digest
`sha256:33eb4748e9be9586893d14059627dd748f48362a1e396cf9881fceb6c8bc65e4`.
Web bijgewerkt en uitsluitend de nieuwe Agadir-worker gestart. Bestaande actieve
workers blijven op hun image; gestopte Goodwill-recorders blijven gestopt.
81 Django-tests geslaagd. Simulatiebrowsercontrole op desktop/mobiel normaal/traag
controleert laden, circuitkeuze zonder replays, Open simulatie, heropenen na
herladen, starten/pauzeren/snelheid/herstarten/stoppen en behoud van feedback.
Gedeelde laadchecker vóór en na publicatie. Alleen ongebruikte Docker-bouwcache
is opgeruimd na een volle schijf; images, opnames en database zijn behouden.
Rollback web: `yanoa-racing-live:20261115-comments`.


## Ref., rondeteller en officiële meldingen (15 november 2026)

De korte feedbacklabel is overal **Ref.**. Drie sectoren passen naast elkaar
zonder overlappende tijden/labels. De dyn1-tekst herkent Ronde/Lap/Tour/Vuelta/Giro,
ook meervoud, en toont bijvoorbeeld **Ronde 6/6**. De laatste ronde is geen
finishsignaal; alleen de officiële vlag markeert de finish. Een rondeteller
vervangt een eerdere timer en omgekeerd.

De standaard ingeklapte sectie **Commentaar & penalties** toont de officiële
APEX-com-snapshot met tijd, type, kartnummer en oorspronkelijke melding. Nieuwe
snapshots vervangen de vorige lijst (geen dubbele meldingen). HTML wordt op de
server omgezet naar platte data en uitsluitend als tekst in de UI weergegeven.
Meldingen worden niet nogmaals als straftijd bij voorspellingen opgeteld.

Release `/home/ubuntu/livecoach-build-20261115-comments`, image
`yanoa-racing-live:20261115-comments`, digest
`sha256:32347f9c29fdadaf881deab7a289ea9f644214a716e04e09cef2f4a8032b0990`.
Web en actieve workers bijgewerkt, zonder migratie of referentiereset. Gestopte
Goodwill-recorders blijven gestopt. 81 Django-tests geslaagd. Vier browserprofielen
(desktop/mobiel, normaal/traag) controleren Ref., drie sectoren zonder overlap,
Vuelta 6/6, open/dichtklappen en kart/melding; FCP 24–504 ms. Gedeelde laadchecker
voor en na publicatie uitgevoerd. Rollback: webimage 20261115-clock en
workerimage 20261114-sectors.


## Sessietitel en aftelklok (15 november 2026)

Een compacte kaart boven Sessiebeste toont de APEX-baansessietitel en resterende
tijd in mm:ss. De server berekent de actuele tijd uit de APEX-deadline; de UI
werkt iedere seconde bij en synchroniseert bij nieuwe snapshots/statuspolls.
Replay gebruikt de oorspronkelijke klok bij het segmentbegin plus de huidige
simulatiepositie. Pauze bevriest de klok, afspeelsnelheid schaalt de aftelling.
Een officiële rondenrace toont resterende ronden; ontbrekende klokdata geeft —.
Bij nul verschijnt Wachten op finish; alleen een echte finishmelding toont FINISH.
Bij verbroken verbinding blijft de laatste stand zichtbaar.

Webrelease `/home/ubuntu/livecoach-build-20261115-clock`, image
`yanoa-racing-live:20261115-clock`, digest
`sha256:b960bd9aeeb9fa61ec863d89c9a655ec271a123da6970893cf3aac45b8a4855d`.
Web-only wijziging: timingworkers en alle tijden/referenties blijven behouden.
79 Django-tests geslaagd, waaronder live/disconnect en replay/snelheid/pauze.
Browsercontrole op desktop/mobiel, normaal/traag, inclusief klok en titel.
Rollback: webimage `yanoa-racing-live:20261114-sectors`.


## Grotere sectorfeedback en sessierecords (14 november 2026)

De dubbele grote passage-delta is verwijderd. S1/S2/S3 tonen grotere labels,
tijden en delta's, met de eigen beste sectortijd eronder. De compacte kaart
**Sessiebeste** toont de snelste ronde en beschikbare sectoren met de namen van
alle recordhouders. Records en namen blijven binnen dezelfde baansessie bewaard,
ook als een rij verdwijnt of een piloot van kart wisselt; een nieuwe sessie reset
ze. Een onbekende historische recordhouder wordt als — getoond.

Release `/home/ubuntu/livecoach-build-20261114-sectors`, image
`yanoa-racing-live:20261114-sectors`, digest
`sha256:79e79e60f00eefbc855bc70ce88b5cb6b5d65897fb627e6c25e34125d48bf08a`.
Geen migratie of wijzigingen aan persoonlijke referenties. Web en actieve timing-
en replayworkers bijgewerkt; de gestopte Goodwill-recorders blijven gestopt.
76 bestaande tests plus 13 strategietests (inclusief nieuwe recordregressie)
geslaagd op SQLite. Browserproef geslaagd op desktop/mobiel normaal/traag,
FCP 32–496 ms; screenshot en geen horizontale pagina-overflow gecontroleerd.
De productie-databasegebruiker mag geen testdatabase aanmaken; geen tests tegen
productiedata uitgevoerd. Gedeelde laadchecker voor en na publicatie geslaagd.


## Raceprojectie, tempo en paarse tijden (14 november 2026)

- Bij pit-uitgang blijft de gemeten ingang→uitgangduur op de pilootkaart staan,
  met drie decimalen. Ontbreekt een waargenomen ingang, dan wordt geen duur verzonnen.
- Groen geeft een eigen verbetering/evenaring aan; trager is oranje. Paars heeft
  voorrang als de ronde/sector de snelste bekende tijd van alle rijders in deze
  baansessie is. Rondebeste gebruikt APEX en echte passages; sectorrecords blijven
  behouden sinds ontvangst, ook over volgende rondes, kartwissels en verdwenen rijen.
  Een nieuwe baansessie reset de globale records; pitronden verbeteren ze niet.
- Onder de actuele plaats staan **Na stops** en **Einde**. De eerste corrigeert
  huidige achterstanden voor alle nog verplichte stops. De tweede trekt recent
  tempo door tot de finish, ook na de eigen pitstop. Waar alle tegenstanders
  vergelijkbaar zijn, wordt de middenraming getoond; anders de positierange.
  De mogelijke range en aannames blijven achter ⓘ beschikbaar.
- De APEX-`dyn1`-aftelklok en officiële resterende rondes bepalen de horizon.
  Een getimede race houdt rekening met de volgende finishlijnpassage na nul.
  De replay rekent met originele opnametijd, zodat pauzeren de projectie bevriest.
  Er wordt nooit vooruit gelezen in de opname om een voorspelling te maken.
- Recente schone ronden van dezelfde kart bepalen het tempo. Met minder dan drie
  nieuwe ronden zijn de marges ruimer. Direct na een kartwissel kan de positie
  voorlopig op het oude tempo worden geraamd, maar er volgt nog geen exact
  tempo-advies zolang geen nieuwe schone ronde is ontvangen.
- Het advies toont de benodigde winst per ronde en een doelrondetijd om de
  gekozen verdedigbare positie te houden. Het gebruikt een twee seconden buffer
  voor een nabije concurrent en waarschuwt voor aansluiting door achtervolgers,
  ook als hun verplichte stop nog moet gebeuren. Reeds ver vooruit rijdende
  leiders verdringen geen relevante naderende achtervolger. Weer, verkeer,
  vervangende kart en mogelijke straffen blijven onbekende factoren; dit zijn
  voorwaardelijke ramingen, geen gekalibreerde kansen of garanties.

Broncorrecties: een numerieke APEX-afstand van een gelapte groep is niet altijd
het verschil met de algemene leider. Bij een andere officiële rondestand worden
passages op dezelfde ronde vergeleken; ontbreekt die historie, dan blijft het
verschil onbekend. Een net voltooide pit telt zijn verlies nog mee zolang de
pitronde niet in de nieuwe finishlijnpassage is verwerkt, zodat de projectie bij
uitgang niet ineens onterecht naar P1 springt. Daarna wordt dit niet dubbel geteld.

De gebruiker bevestigde dat de handmatige **1,0 s netto verlies** in de huidige
Noah-opvolging vervangen moet worden door automatische berekening. Die keuze
is uitsluitend op de betreffende eigen actieve volgsessie toegepast.

`refresh_coach_checkpoints --owner-id …` vult alleen afgeleide metadata van
bestaande actieve/paused replays aan, tot hun huidige bytecursor. Identiteiten,
referentieblokken, persoonlijke besttijden, laatste feedback en cursor blijven
ongewijzigd. De aparte `--auto-pit-session`-optie vereist een expliciete eigenaar
plus sessie en publiceert de bevestigde instelling. Een private checkpointbackup
wordt vóór wijziging geschreven. De raw-opnames blijven ongewijzigd.

Herstart van liveworkers leest bestaande deduplicatiesleutels eenmaal per
opname in plaats van per oude regel een transactie te openen. Gaten blijven
herstelbaar; er wordt geen aaneengesloten reeks verondersteld en een onvolledige
laatste regel blijft onaangeroerd. Dit beperkt de herverbindtijd bij publicatie.

Verificatie: 76 gerichte/volledige Django-tests op SQLite/PostgreSQL, waaronder
projectie na de eigen pit, een snellere achtervolger, nabij terugkeren na pit,
nieuwe kart, onbekende raceduur/gaps, behoud van sessierecords, exact gemeten
pitduur en herladen van replaymetadata zonder referentieverlies. Vier browser-
profielen testen kleuren, uitgangsduur, onder-elkaar geplaatste projecties en
het tempo-advies (desktop/mobiel, normaal/traag). FCP lokaal 24–496 ms.
De afgesloten Goodwill-opname controleert onder meer de 90,851 s van Noahs tweede
heat en een P3-verwachting na zijn stop, zonder toekomstige data als invoer.

Release: `/home/ubuntu/livecoach-build-20261114-pace`;
image `yanoa-racing-live:20261114-pace`
(`sha256:4e9b56bb90d24460bc2a2c86b93ebdfac56065e5842c9737208ed07daf2495ee`).
Geen nieuwe databasemigratie. Alle actieve diensten zijn healthy. Twee bestaande
replaycheckpoints zijn bijgewerkt zonder referenties te wijzigen. De gedeelde
laadchecker slaagde vóór en na publicatie op desktop en mobiel; na publicatie
was eerste content op de loginpagina zichtbaar na 180–484 ms, ook bij de trage
verbinding. De ingelogde interface is lokaal met de vier browserprofielen getest.
Backup vóór publicatie: `racing-before-pace.dump`; afgeleide replaymetadata:
`replay-checkpoints-before.json` (beide 0600). Rollbackimages:
`yanoa-racing-live:before-pace-web-20261114` en
`yanoa-racing-live:before-pace-workers-20261114`. Geen volledig databaseherstel
uitvoeren over later ontvangen tijden. Gestopte recorders blijven gestopt.

## Compacte pilootkaarten en individuele pitkeuze (14 november 2026)

Alle piloten krijgen dezelfde kaartindeling en lettergroottes. De eerste selectie
blijft intern een sorteerkeuze voor compatibiliteit, maar heeft geen grotere kaart
of label Hoofdpiloot. Iedere kaart toont de actuele APEX-positie, huidige kart,
ronde- en sectordelta's en een eigen **Pitvoorspelling**-schakelaar. De schakelaars
staan standaard uit en worden per FollowDriver opgeslagen; toevoegen of verwijderen
van een andere piloot wist deze keuze of bestaande besttijden niet.

Alleen ingeschakelde piloten krijgen een server-side pitprognose. De bestaande
pitduur/stopinstellingen blijven per volgsessie gelden. Zichtbaar zijn alleen
statussen en kernwaarden: Nu pitten, Na stops, netto verlies en resterende pittijd.
Uitleg staat achter toetsenbord- en aanraakbare **ⓘ**-knoppen. Geopende kaartuitleg
blijft open bij volgende timingpassages. Historie is standaard ingeklapt.

Kartwissels tonen de eerdere kartnummers naast de huidige kart. Wanneer het
event de referentietijd van dat moment bevat, staat die ernaast. Oude worker-events
leveren het vorige kartnummer via hun bestaande wisselmelding. Een replayherstart herstelt de begin-kart en
toont alleen wissels van de nieuwe replayrun; oudere historie blijft bewaard.
Dit voorkomt dat opnieuw beginnen als een echte kartwissel wordt weergegeven.

Migratie `0015_followdriver_pit_enabled` voegt één boolean toe met zowel Python-
als databasedefault `false`, zodat oudere workers en rollback-webversies nog
kunnen schrijven. Het wijzigen van een pitkeuze vereist dezelfde eigenaar,
actieve volgsessie en CSRF-beveiligde POST als de overige sessieacties. Een piloot
uit een andere volgsessie kan via deze actie niet worden gewijzigd.

Releasefolder: `/home/ubuntu/livecoach-build-20261114-cards`.
Webimage: `yanoa-racing-live:20261114-driver-cards`.
Image-ID: `sha256:09dffc9b4a90a5d0b4e3a8392e9e1ca880e25c4ecdc625f1904bb43aff6aa01a`.
Rollback: `yanoa-racing-live:before-driver-cards-20261114`. Publicatie gebruikt de
web-only Compose-override; timingworkers en simulator blijven draaien en de
Goodwill-recorders blijven gestopt. Een databasebackup staat vóór migratie als
`racing-before-driver-cards.dump` in de releasefolder, mode 0600.

Verificatie: 63 Django-tests op SQLite en PostgreSQL. De gerichte kaarttest en
bestaande pilootupdate-/referentietest slagen op desktop/mobiel en normaal/traag.
Dit controleert gelijke kaartbreedte/lettergrootte, beide onafhankelijke pitkeuzes,
behoud na verversen, actuele plaatsen, kartreferenties, ⓘ-uitleg over passages heen
en de mobiele breedte. Lokale eerste content verschijnt binnen 28–472 ms.
De gedeelde laadchecker slaagt vóór en na publicatie in alle vier profielen;
na publicatie FCP 240–440 ms. De gehashte CSS/JS zijn bytegelijk aan de geteste bron.

## Herstel sessiekeuze bij simulatie (14 november 2026)

De laadknop bouwde de sessiekeuzelijst opnieuw op vóór het lezen van de selectie;
zo werd iedere opname vanaf segment 0 geladen. De gekozen segmentindex wordt nu
vóór het tekenen vastgelegd en bij hertekenen van dezelfde opname behouden.
Bij wisselen van opname wordt opnieuw een geldige eerste keuze gebruikt.

Onder **Een opname simuleren** staat nu iedere actieve simulatie met een directe
**Stop deze simulatie**-knop. De limietmelding noemt deze actie in plaats van de
algemene fout `Ongeldige aanvraag`. Alle actieve simulaties blijven bereikbaar,
onafhankelijk van de twintig recente beëindigde simulaties. Stoppen bewaart
bestaande opvolging en tijden. Twee door deze fout aangemaakte dubbels zijn alleen
gestopt na controle op positie 0, nooit afgespeeld, run 1 en geen FollowSession;
er zijn geen opnames of rijtijden verwijderd.

Web-only reparatie: `yanoa-racing-live:20261114-replay-fix` in dezelfde releasefolder.
Simulator en timingworkers behouden `20261114-pit`; er is geen migratie. De
browserregressie kiest nadrukkelijk segment 1, controleert de juiste titel, loopt
tegen drie actieve simulaties aan, stopt er één en laadt vervolgens de bedoelde
sessie. Vier profielen: desktop/mobiel, normaal/traag. Suite: 59 Django-tests
op SQLite en PostgreSQL. De gedeelde laadchecker slaagt vóór en na publicatie;
na publicatie FCP 224–484 ms. De gehashte frontendbestanden zijn bytegelijk aan
de geteste bron. Image-ID:
`sha256:1571e4752443a6058b81f75b7aae0513dbcc651669d3d963da1487e0c087c831`.
Rollback-webimage: `yanoa-racing-live:before-replay-fix-20261114`.

## Goodwill: kartwissels, rondedelta en pitstrategie (14 november 2026)

- De pilootidentiteit blijft gelijk bij een ander kartnummer op dezelfde rij in
  dezelfde baansessie. Kartnummer en wisselmelding worden bijgewerkt; eigen
  beste rondes/sectoren, referentieblok en historie blijven bewaard. Een andere
  naam, nieuwe baansessie of teruglopende rondeteller wordt niet automatisch
  samengevoegd. Bestaande selecties gebruiken bij upgrade hun oude hash als
  controle; daardoor kunnen ook reeds verwisselde karts hun referenties behouden.
- Goodwill heeft **twee** sectoren. De adapter publiceert dynamische `sectorIds`;
  kaarten en baanoverzicht tonen alle werkelijk beschikbare sectoren. De
  ongetypeerde kolom **Rondes** wordt als officiële rondeteller herkend.
- Een blijvende **Ronde Δ** vergelijkt de laatste volledige schone ronde met de
  eigen beste ronde vóór die passage, naast onafhankelijke sectorverschillen.
  Alle verschillen blijven op duizendsten. Het baanoverzicht zet de tijden onder
  de naam in één compacte rij; geselecteerde piloten en filter blijven beschikbaar.
- **Pitinstellingen** gelden per volgsessie en worden server-side opgeslagen
  (`0014_followsession_pit_settings`, additieve JSON-kolom). Goodwill start op
  één verplichte stop van **90 s, pit-ingang → pit-uitgang**. Andere banen starten
  zonder verplichte stop. Een Goodwill-opname krijgt dezelfde standaardinstelling.
  Het optionele veld voor netto tijdverlies kan de automatische schatting vervangen.
- `*in` en `*out` meten de waargenomen pitduur. De bron verhoogt de pitteller al
  bij ingang; dit telt pas als voltooide stop na uitgang. Pitsectoren en de eerste
  ronde met pittijd verbeteren geen referenties en tellen niet mee als rijtempo.
  De eerstvolgende schone tijden worden opnieuw vergeleken met de behouden beste
  tijden. De afteller gebruikt de bronklok, ook bij replay; pauzeren bevriest hem.
  Dit zijn ontvangen timingmeldingen, geen officiële controle van minimumduur.
- Een pitduur van 90 s is niet hetzelfde als 90 s netto verlies. Uit een voltooide
  pitronde en de mediaan van de drie voorafgaande schone ronden wordt het
  overgeslagen aandeel van een gewone ronde geschat. Vanaf drie waargenomen
  pitstops gebruikt de prognose de volledige geobserveerde spreiding, een marge
  van vijf procentpunten en recent tempo om een netto verliesrange te tonen.
  Alleen reeds ontvangen gegevens van deze baansessie worden gebruikt; replay
  leest voor de prognose nooit vooruit. Nieuwe baansessies wissen oude kalibratie.
- **Nu pitten** toont een tijdelijke positierange. **Na verplichte stops** telt
  ook nog verschuldigde stops van tegenstanders mee. Onbekende exacte achterstanden
  (bijvoorbeeld alleen `1 Ronde`) verruimen de range; bij een onbekende eigen
  achterstand verschijnt geen schijnnauwkeurige positie. Tijdens de pit worden
  afteller en resterende stops getoond; na finish geen nieuwe pitprognose.
- De baantrend vergelijkt per rijder de recente drie met de vorige drie schone
  ronden, steeds met dezelfde kart. De mediaan van minstens drie rijders geeft
  een voorwaardelijke richting: sneller wordende baan → eerder pitten kan gunstiger
  zijn; trager wordende baan → later kan gunstiger zijn. Dit voorspelt geen weer,
  verkeer, pitvenster, straffen of tempo van de vervangende kart.

De afgesloten **Goodwill-opname van 13 november** is toegevoegd aan de replay-
bibliotheek. Selecteer de Pro-sessies met **Noah** in de keuzelijst. De cloudbron
blijft ongewijzigd; bibliotheekkopie is alleen-lezen. SHA256:
`0dfa9261382209cd12fd032c78751c201ccfbaa07dc3859d2e8cb19b9cda8570`.

Verificatie: 58 Django-tests op SQLite en PostgreSQL; browserprofielen voor
kartwissel/twee sectoren/rondedelta/pitinstellingen, drie-sectoren/finish en
pilootupdates/filter, telkens desktop/mobiel en normaal/traag. De afgesloten
Goodwill-opname bewijst drie behouden identiteiten (30→25, 15→25, 3→30), drie
apart behandelde pitronden en hervatte schone tijden. In heat 2 verschijnt de
verwachte richting voor een opdrogende baan. Lokale passage→zichtbare feedback
bij reeds verbonden UI: circa 44–208 ms; dit meet niet de vertraging vanuit APEX.

Gepubliceerd image-ID:
`sha256:1f95a9c4276b65c68547e6e5e696d56e271747af0aab06ebdf6ef6ec76466a87`.
De gedeelde laadchecker slaagt vóór en na publicatie in alle vier profielen;
na publicatie FCP **320–440 ms**. De werkelijke gehashte CSS/JS zijn bytegelijk
met de geteste bron. Goodwill bevat 18 sessies; Noah staat in segmenten
4/5, 10/11 en 16/17 (kwalificatie/race). Tijdelijke PostgreSQL-QA is verwijderd.

Releasefolder: `/home/ubuntu/livecoach-build-20261114-pit`.
Images: `yanoa-racing-coach-base:20261114-pit`, `yanoa-racing-live:20261114-pit`.
De webservice, simulator en actieve Spa/Campillos-workers gebruiken dezelfde
parser. Goodwill-worker wordt alleen aangemaakt met het nieuwe image, niet
opgestart; restart-policy blijft `no`. Ook `apex-goodwill` en de Pi-recorder
blijven gestopt. De nieuwe UI-bestanden hebben een versieparameter voor caches.

Backup vóór migratie: `racing-before-pit.dump` in de releasefolder (0600).
Rollbackimages: `yanoa-racing-live:before-pit-web-20261114` en
`yanoa-racing-live:before-pit-workers-20261114`. De extra JSON-kolom kan blijven
bestaan bij rollback; herstel geen databasebackup over inmiddels nieuwe tijden.
Gebruik bij rollback `up --no-deps` per actieve service met het bijbehorende
oude image, zodat de gestopte Goodwill-service niet onbedoeld wordt gestart.

## Live-link op de publieke website

Het hoofdmenu van `racing.yanoa.be` bevat **Live** tussen Contact en Login/Beheer,
ook in het mobiele menu. Doel: `/live/`; aanmelden gebeurt zo nodig op de aparte
Live Coach-login. Gecontroleerd door de link aan te klikken in vier verse
browserprofielen (desktop/mobiel, normaal/traag), zonder formulieren in te dienen.
De gedeelde laadchecker slaagde na publicatie in alle profielen: FCP 248–376 ms.
Eén eerdere nulmeting zag de bestaande laadlaag nog na vier seconden; de gerichte
hercontrole en alle controles na de menuwijziging slaagden.

De publicatie vervangt uitsluitend `www/templates/index.html` bovenop het
bestaande publieke website-image; Live Coach en recorders zijn niet herstart.
Image `yanoa-racing:live-link-20261113`, ook getagd als `yanoa-racing:local`.
Rollback: `yanoa-racing:before-live-link-20261113`.
Bron/bouwinstructie: `Dockerfile.live-link`, `compose.live-link.yml` en
`/home/ubuntu/racing-live-link-20261113` op de server.

## Een actieve volgsessie stoppen

Er zijn twee keuzes, zowel bij de actuele opvolging als in de lijst bovenaan:

- **Stop & bewaar:** sluit de volgsessie en behoudt haar tijden en historie.
- **Stop zonder bewaren:** vraagt bevestiging en verwijdert die volgsessie,
  haar pilootreferenties en feedbackhistorie. Annuleren verandert niets. Andere
  volgsessies en de oorspronkelijke/gedeelde bronopnames blijven intact.

De optie zonder bewaren wordt alleen na de gebruikersbevestiging via een
beveiligde POST uitgevoerd. De huidige kaart en historie worden leeggemaakt
als de verwijderde sessie in beeld stond. Tests controleren eigenaarstoegang,
CSRF, verwijdering van uitsluitend de gekozen sessie en behoud van andere tijden.
Suite: 47 tests; beide keuzes en annuleren getest op desktop/mobiel, normaal/traag.
De web-only override gebruikt nu `yanoa-racing-live:20261113-discard`.
Image-ID: `sha256:2b585c4a1ac4d7bca79375fc6558bc93432ec0f871a96e1c7fec023b391dc7de`.
Er is geen databasemigratie; de deleteactie verwijdert alleen de eigen
FollowSession met haar gekoppelde piloten, events en acties. TimingPacket,
TimingTrack, opnames en andere FollowSessions worden niet verwijderd.

Ververs `/live/`. Bovenaan staat **Actieve volgsessies**, met het aantal actieve
sessies (maximum vijf). Klap dit open als het is ingeklapt. Iedere sessie toont
naam, baan, starttijd in Europe/Brussels en geselecteerde piloten. Klik direct
**Stop & bewaar** bij de gewenste sessie; je hoeft haar niet eerst te openen.
Bij **Stop & bewaar** blijven tijden en referenties opgeslagen. Met **Bekijken** open je de
bestaande opvolging zonder een nieuwe sessie te starten.

De lijst van actieve sessies is onafhankelijk van de vijftig recente archiefitems:
ook oudere actieve sessies blijven bereikbaar. De limietmelding verwijst naar
deze bediening. Er worden bij deze UI-update geen gebruikerssessies automatisch
gestopt. De directe stopactie is met vijf lokale fixtures getest op desktop en
mobiel, normaal en traag; alle tijden bleven behouden. Volledige suite: 45 tests.

Web-only image: `yanoa-racing-live:20261113-stop`
(`sha256:719f6c0f131089bdc95088ed9a132b0a36a73b5ee5c3f5786757142be2e7cd95`).
Gebruik in de releasefolder `compose.live-web.yml` naast `compose.live.yml` om
alleen deze webversie te beheren; timing- en simulatieprocessen behouden hun image.

## Actuele uitbreiding: baanstand, sectoren, pilotupdates en finish

- Het **baanoverzicht** toont alle rijders met echte APEX-posities, kart,
  laatste/beste ronde, ronden en beschikbare S1/S2/S3. Geselecteerde piloten zijn
  gemarkeerd; de filter kan alleen de selectie tonen. Hun grote feedbackkaarten
  en laatste passagedelta blijven zichtbaar. De bronbeste tijd en de eigen
  referentie van een volgsessie zijn afzonderlijke begrippen.
- **Update piloten** wijzigt dezelfde actieve volgsessie. Behouden piloten houden
  hun database-identiteit, besttijden, laatste passages en referentieblok. Nieuwe
  piloten beginnen met lege referenties. Verwijderde piloten en hun feedback worden
  uit deze opvolging verwijderd; de raw-opnames worden nooit gewijzigd. Tijdens
  een aanvraag zijn selectievakjes tijdelijk geblokkeerd, zodat een tweede wijziging
  niet door het antwoord op de eerste aanvraag wordt overschreven. Enter in het
  formulier start geen nieuwe sessie zolang een actieve selectie wordt bijgewerkt.
- **Campillos-sectoren zijn geverifieerd en ingeschakeld**: bronkolomtypes `s1`,
  `s2`, `s3`. Positieve celupdates geven directe sectorpassages; een afzonderlijk
  `*i1`/`*i2`-animatiebericht kan later volgen en wordt niet dubbel geteld. Besttijd-
  snapshots (`ib`), volledige grids en pit-snapshots (`*in`/`*out`) zijn geen nieuwe
  sectorpassages. S3 en de ronde kunnen samen bij de finishlijn arriveren; de
  laatste feedback per sector blijft daarom apart bewaard en zichtbaar.
- **Finish**: APEX `light|lf|` toont de finishvlag voor de baansessie. De rijderstatus
  `sf` markeert een gefinishte piloot. De officiële APEX-stijlen verwijzen naar
  `Ff.png` respectievelijk `st_finish.png`/`st_finish_2.png`. Alleen deze echte
  signalen geven een finishmelding; een verbroken verbinding of een stille feed
  doet dat niet. Een banner, badge per piloot en historie-event maken dit zichtbaar.
  Laatste passages blijven verwerkt worden; tijden worden niet gewist en stoppen
  van de eigen volgsessie blijft een expliciete actie.
- Een alleen-lezen **Campillos-snapshot tot bevestigde finish** is naast Spa
  beschikbaar voor simulatie. SHA256:
  `896b6b9fe7a52b694a907806576c0aa6cf031cff5de3e22f221125c275c20597`.
  De oorspronkelijke recorder is niet gestopt om deze snapshot te maken.

Verificatie: **44 tests op SQLite en PostgreSQL**. Vier browserprofielen voor
behoud van referenties bij toevoegen/verwijderen en voor de volledige stand;
vier voor S1/S2/S3-delta's, filter, finishbanner, rijderfinish en mobiele breedte.
Geselecteerde sectoren hebben onafhankelijke referenties; de eerste echte passage
zet die referentie. Voor een baan zonder sectorgegevens worden geen tijden afgeleid.

Deze release gebruikt `/home/ubuntu/livecoach-build-20261113-passages` en image
`yanoa-racing-live:20261113-live`. De JSON-parsercheckpointvelden zijn uitgebreid;
er is geen nieuwe databasemigratie na `0013`. De webservice, simulator en timing-
adapters moeten deze versie gebruiken voor actuele posities en sectordelta's.
De oorspronkelijke autonome Spa/Goodwill-opnames staan hiervan los.

Gepubliceerd image-ID: `sha256:9ff6bda4247f9d02a4a583b48f8b03b7267c5ffef0e0fb47a48600f72d3a1c54`.
Alle vijf Live Coach-services zijn healthy. Campillos stond na publicatie op
`FP37`, verbonden met bevestigde sectorkolommen; 40 rijders hadden reeds echte
sectorpassages in het nieuwe checkpoint. De Campillos-bibliotheek bevat drie
opgenomen sessies, Spa 26. De standalone Goodwill-recorder behield zijn
oorspronkelijke starttijd `2026-11-13T15:32:43.58634473Z`.

De gedeelde checker slaagde na publicatie in alle vier profielen: FCP 160–520 ms.
De aangeboden JS is bytegelijk aan de geteste bron. De tijdelijke PostgreSQL-
testdatabase en het bijbehorende testnetwerk zijn verwijderd. Backup van vóór
deze release: `racing-before-passages.dump` in de releasefolder, mode 0600.

## Uitbreiding: simulatie, duizendsten en expliciet verbinden

Op 13 november uitgebreid met:

- **Verbinden** als afzonderlijke actie. Eerst een baan kiezen en verbinden;
  daarna verschijnen deelnemers. Statussen onderscheiden niet verbonden,
  verbinden/herverbinden, verbonden zonder timingdata en klaar voor volgen.
  Dit is jouw aansluiting op een gedeelde serverfeed. Verbreken stopt geen
  recorders of andere gebruikers; stop eerst je eigen actieve volgsessie.
- Verschillen als seconden met **drie decimalen**: `+0.102s`, `-0.949s`,
  `+0.000s`. Geen afronding op tienden. Ook oude opgeslagen feedback wordt met
  de oorspronkelijke exacte `deltaMs` in deze notatie weergegeven.
- Een opnamebibliotheek met de afgesloten **Spa-racedag van 7 november**,
  verdeeld in **26 sessies**. De originele checksum is geverifieerd en de bron
  is alleen-lezen gemount. Geen wijziging aan de oorspronkelijke opname.
- Kies **Een opname simuleren → opname → sessie → Simulatie laden**. Kies
  piloten, start volgen en druk **Afspelen**. Pauze, snelheid (0,25×–20×),
  opnieuw beginnen en stoppen worden volledig door de server verwerkt.
- Een simulatie is privé voor de gebruiker die haar start. Ze heeft een eigen
  baanstatus, cursor en referenties, en gebruikt dezelfde ingest/parser-engine
  als live timing. Herstart verhoogt het referentieblok van actieve volgsessies;
  eerdere feedback blijft bewaard. Een echte baansessie wordt niet aangeraakt.

De aanvullende `simulation-worker`-service voert duurzame afspeelopdrachten uit;
de website start geen achtergrondproces. Het schema is uitgebreid met migratie
`0013`; bestaande actieve volgsessies behouden hun verbinding bij migratie.
Een tijdelijke databasefout rolt de tick terug en wordt opnieuw geprobeerd.
Bij een stille bron blijft de UI de ouderdom van de laatste passage bijwerken.

Opnamebeheer (alleen voor serverbeheerder): plaats een afgesloten NDJSON in
`LIVECOACH_RECORDINGS_DIR`, maak het bestand onveranderlijk voor de app en voer
`python manage.py import_coach_recording BESTAND --name 'Naam'` uit. Hetzelfde
bestand opnieuw importeren behoudt bestaande segmentidentiteiten. Een gewijzigd
bestand met bestaande simulaties moet een nieuwe naam krijgen.

Tests van deze uitbreiding: **38 tests op SQLite en PostgreSQL**, plus vier
live-browserprofielen en vier simulatie-browserprofielen. De simulatieproeven
bevestigen `-0.949s`, `+0.102s`, pauze zonder verdere passages, snelheid, herstart
met nieuwe referenties en behoud van historie. Alleen lokale formulieren zijn
automatisch bediend; productiebrowserchecks dienen geen formulieren in.

Live: **https://racing.yanoa.be/live/**, gepubliceerd op 13 november 2026.
Gebruik een bestaand Racing-account met `www.use_livecoach`; superusers hebben
deze toegang automatisch. Andere Racing-accounts krijgen geen toegang totdat
deze permissie expliciet is toegekend. Geen publieke timingproxy.

## Gebruik

Kies een baan met actuele deelnemers, selecteer één of meerdere piloten en start
een benoemde volgsessie. De eerste geselecteerde piloot staat groot in beeld.
Alle berekeningen en opnames draaien op de server; telefoon en browser mogen
sluiten. Open een actieve sessie opnieuw vanuit het overzicht om verder te kijken.

Een nieuwe ronde wordt eerst met de bestaande beste ronde vergeleken en verbetert
daarna eventueel de referentie. `-0.949s` is 949 milliseconden sneller, `+0.102s`
102 milliseconden trager. De eerste nieuwe ronde zet de referentie; een
beginsnapshot is geen nieuwe ronde. De exacte milliseconden blijven bewaard.

**Stop & bewaar** sluit alleen jouw volgsessie af. De gedeelde bronrecorder blijft
lopen voor andere gebruikers en preview. **Reset** begint een nieuw referentieblok
voor één piloot of alle geselecteerde piloten; eerdere feedback blijft in de
historie en export. **Naam opslaan** wijzigt alleen de sessienaam. De meetgegevens
worden al automatisch opgeslagen. **Export** bevat alle sessie-events als JSON.
Het no-JavaScript-overzicht staat op `/live/samenvattingen/`.

Gebruik tijdens het rijden: lees de actuele melding en spreek die via je bestaande
commsysteem uit. Automatische audio en een rechtstreekse commsysteemkoppeling
zijn nog niet gebouwd.

## Architectuur van deze implementatie

- Django beheert autorisatie, sessies, resets, database en SSE.
- Eén Python-managementworker per baan normaliseert passages en berekent feedback.
- De worker start een kleine Node-transportbridge met de bestaande APEX-recorder.
  Die bewaart raw NDJSON en stuurt events over een lokale pipe naar de worker.
  De transportcode in `server/timing/` is overgenomen uit het APEX-project.
- Alle referenties, feedback en parsercheckpoints staan in PostgreSQL.
- `CoachEvent` is tevens een duurzame outbox. PostgreSQL NOTIFY wekt SSE-clients;
  na reconnect wordt de actuele snapshot met recente historie verzonden.
- Start/stop/reset zijn direct transactionele databaseacties; de worker leest
  dezelfde status. Daardoor is in deze versie geen aparte commandowachtrij nodig.
- Herhaalde start-/resetverzoeken zijn idempotent. Een advisory lock voorkomt twee
  live workers voor dezelfde baan. Opgeslagen raw-pakketten zonder bijbehorende
  databasecommit worden bij herstart ingehaald; een afgebroken laatste regel wordt
  niet verwerkt. Opnames blijven onafhankelijk van een open telefoon.

De timingkern staat bewust in Python naast Django's transacties. Node verzorgt
alleen het reeds geteste transport en raw-opslagbeheer; er is geen dubbele
referentie-engine in de UI of in twee verschillende runtimes.

## Huidige grenzen

- Ronde- en sectorfeedback werken op de geverifieerde Campillos-indeling.
  Andere banen moeten hun eigen sectorvelden daadwerkelijk aanleveren; oudere
  Spa-opnames hebben uitsluitend rondegegevens.
- Gecontroleerde bronregistratie: Spa, Goodwill en Campillos. Geen vrije URL-invoer.
  Bij publicatie leverde Campillos een ondersteunde tabel. Goodwill was verbonden
  met alleen heartbeats; Spa herverbond wegens een fout vanaf de cloudserver.
  Een gezonde worker is iets anders dan een beschikbare bron of verse passage.
- Spa-kwalificaties hebben een rondeteller. De geverifieerde Spa-race-indeling heeft
  die niet: daar telt de adapter **waargenomen passages** met `*` als bevestiging.
  De getoonde tijd komt uit `llp`, niet uit de animatiereferentietijd. De app labelt
  het waargenomen nummer expliciet; dit is geen gereconstrueerd officieel rondenummer.
- Naam/kart/baansessie identificeren samen een geselecteerde deelnemer. Na een
  wijziging wordt geen andere piloot stilzwijgend overgenomen. Kies opnieuw en
  start een nieuwe volgsessie. Geen automatische overdracht van besttijden.
- Bronvaliditeit, uitronden en tijdcorrecties achteraf zijn nog niet volledig
  geïnterpreteerd. Referenties zijn de beste **waargenomen, parseerbare** tijden
  binnen jouw blok. De UI benoemt de onbekende bronvaliditeit. Correcties op een
  reeds verwerkt rondenummer worden niet als nieuwe passage gebruikt; automatische
  herberekening van oude referenties is vervolgwerk.
- Geen telefoonachtergrondaudio, geen native app/PWA en geen claim over vertraging
  vóór ontvangst van APEX. Bij reconnect is de actuele toestand leidend; oude
  meldingen worden niet als nieuwe audio afgespeeld.
- Raw-bestanden en pakketindex blijven bewaard. Automatische retentie, segmentrotatie,
  schijfalarmering en een aparte beperkte worker-databaserol zijn vervolgwerk vóór
  bredere uitrol. Houd vrije ruimte bij en wis geen actieve bestanden.
- Replay is via de website bedienbaar. Willekeurig zoeken binnen een sessie
  is nog niet beschikbaar; pauze, snelheid en vanaf het begin afspelen wel.

## Lokale ontwikkeling en verificatie

Python 3.14, Node 22.4+ (getest met Node 24), projectrequirements.

```sh
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py migrate
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python -m uvicorn server.asgi:application --app-dir server --host 127.0.0.1 --port 8210
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py run_live_timing --track goodwill
```

De standaard datamap is `server/live-data/<baan>` (buiten Git). Productie gebruikt
`LIVECOACH_DATA_DIR`. De preview serveert lokale static files alleen bij DEBUG.
Gebruik de asynchrone server voor SSE; de bestaande WSGI-site is ongewijzigd.

```sh
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py test www
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python test/livecoach-browser.py
docker compose -f compose.live.yml config --quiet
```

De browsertest gebruikt uitsluitend lokale, geïsoleerde fixtures en weigert een
productie-PostgreSQL-configuratie. De Browser-plugin bood geen browser; deze test
gebruikt daarom de lokale Chrome-installatie. Schermafbeeldingen en metingen
worden onder `/tmp/livecoach-*` geschreven.

Replay maakt altijd een **afzonderlijke REPLAY-baan** en wijzigt geen live bron:

```sh
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py replay_live_timing ../apex/data/RECORDING.ndjson --speed 10 --wait-for-session
```

Kies de nieuwe replaybaan in de UI. De stream wacht maximaal vijf minuten tot
een volgsessie gestart is. De oorspronkelijke raw-opname wordt niet gewijzigd.

## Server en beheer

Releasebron en Compose: `/home/ubuntu/livecoach-build-20261113` op de bestaande
YaNoa-server. Image: `yanoa-racing-live:20261113`; eerste image-ID
`sha256:5391ab194cbf9e4fa047cad2738bf6a662ec0d1896a714e317471ffb00ca2597`.
Na de ouderdomsweergavecorrectie gebruikt de webservice image-ID
`sha256:5e99d6548952e480b3344e0b36bb186c153c48a8147d5e66c1f97dc59c19361e`;
de recorderprocessen hoefden daarvoor niet te herstarten.
De bestaande image-tag `yanoa-racing:local` en oorspronkelijke webcontainer zijn
niet vervangen. De raw-opslag staat in `/srv/yanoa/data/racing-livecoach` (UID 10001).
Neem die map mee in backups, naast de Racing-database.

Services:

- `yanoa-racing-live`: aparte ASGI-webservice, bestaande Racing-login/database.
- `yanoa-racing-goodwill-worker`, `yanoa-racing-campillos-worker`,
  `yanoa-racing-spa-worker`: gedeelde baanrecorders, zonder publieke beheerpoort.

```sh
cd /home/ubuntu/livecoach-build-20261113
LIVECOACH_IMAGE=yanoa-racing-live:20261113 LIVECOACH_DATA_DIR=/srv/yanoa/data/racing-livecoach RACING_MEDIA_DIR=/srv/yanoa/repositories/yanoa_racing/media docker compose -f compose.live.yml ps
docker logs --tail 20 yanoa-racing-goodwill-worker
docker exec yanoa-racing-live python manage.py check_live_worker --track goodwill
```

Een bestaande privébackup van vóór migratie staat als
`racing-before-live.dump` in de releasefolder (mode 0600). Het nieuwe schema is
migratie `www.0012`; eerdere migraties waren reeds toegepast. Productieformulieren
zijn tijdens browsercontroles niet ingediend. De eerdere autonome Goodwill-opnames
op cloud en Pi blijven los hiervan doorlopen.

De Caddy-route geldt alleen voor `/live`, `/live/*` en de twee Live Coach-static
prefixen. SSE heeft `flush_interval -1`. Configuratie werd gevalideerd en in-place
geschreven, zodat de bestaande bind-mount geldig bleef; daarna SIGUSR1-reload.
Rollback: herstel alleen de toegevoegde `@livecoach`/`handle`-route (backup
`Caddyfile.before-livecoach`), valideer en reload Caddy; stop daarna de vier nieuwe
services met deze Compose-file. De oude Racing-site blijft draaien. Nieuwe tabellen
en raw-opnames behouden voor onderzoek; geen databaseherstel of dataverwijdering
nodig voor deze rollback.

## Resultaten op 13 november

- **31 Django-tests geslaagd op SQLite én een tijdelijke PostgreSQL 16-database**,
  inclusief autorisatie/CSRF, start/reset-retries, twee gebruikers op één bron,
  besttijden, stops, snapshot/reconnect, onbekend schema, race-indeling en SSE-updates.
- De Spa-racedagopname leverde 3.148 waargenomen rondepassages op, waarvan 94 voor
  Noah, inclusief de finale en latere sessies. Deze replay-audit is geen nieuwe
  kartselectieanalyse en gebruikt dus geen prefinale cutoff.
- Vier lokale browserprofielen geslaagd: desktop/mobiel, normaal/1,6 Mbit/s met
  150 ms latency. FCP 24–388 ms; gemeten ingest-tot-scherm 86–189 ms in de laatste
  run. Dit is een kleine functionele proef, **geen p95-belastingmeting** en geen
  transponder-tot-schermmeting.
- Geen horizontale overflow; start, twee piloten, live delta, herladen/openen,
  referentiereset, stop en no-JavaScript-samenvatting gecontroleerd.
- Gedeelde laadchecker vóór publicatie: Racing-homepage op desktop/mobiel normaal
  en traag geslaagd; FCP 200–396 ms.
- Na publicatie: Live Coach-aanmelding slaagde in alle vier profielen, FCP
  224–400 ms. De ongewijzigde homepage slaagde op desktop en mobiel; één mobiele
  trage run zag de bestaande laadlaag nog na vier seconden, terwijl de eerste
  inhoud op 392 ms verscheen. De gerichte hercontrole slaagde, FCP 288/308 ms.
  Dat is vastgelegd als een tijdelijke assetvertraging, niet als bewezen permanente
  regressie of als garantie dat die nooit terugkomt.
- Laatste lokale browserproef met bijgewerkte passage-ouderdom: FCP 20–396 ms en
  ingest-tot-scherm 87–190 ms, vier profielen geslaagd.
- Definitieve webversie opnieuw extern gecontroleerd: vier Live Coach-profielen
  geslaagd, FCP 208–524 ms. De publiek aangeboden JS is bytegelijk aan de geteste
  bron. Alle vier nieuwe services zijn healthy; de oude Racing-container en
  oorspronkelijke Goodwill-recorder bleven draaien.
