/* Comprobación de render fuera del navegador: monta las piezas de la interfaz
   —incluidas las de las dos pantallas— con los datos reales y falla si alguna
   lanza o pinta algo incoherente. Se ejecuta con `npm run check` y no forma
   parte de la aplicación. */
import { renderToString } from 'react-dom/server';
import fixtures from './src/api/fixtures.json';
import ShotChart, { ShotLegend } from './src/components/ShotChart.jsx';
import {
  Panel, StatTile, Meter, LabelledBar, Select, ContextPicker, Pager, Tabs, Loading, ErrorState,
} from './src/components/Primitives.jsx';
import { LeaderRow, ClutchRow, FoulRow, TeamFoulRow } from './src/pages/Jugadores.jsx';
import { GameRow, agruparPorJornada } from './src/pages/Ligas.jsx';
import { Identity, ShootingPanel, GameLog } from './src/pages/Player.jsx';
import { CompareTable, SearchBox, filterCandidates, MAX_COMPARE } from './src/pages/Compare.jsx';
import RadarChart, { RadarLegend, RADAR_AXES, percentileRank } from './src/components/RadarChart.jsx';
import { StandingsRow } from './src/pages/Teams.jsx';
import { Identity as TeamIdentity, Roster, PaceLog } from './src/pages/Team.jsx';
import AssistNetwork from './src/components/AssistNetwork.jsx';
import { ZONE_ORDER, ZONE_LABEL, projectShot, VIEW_W, VIEW_H } from './src/lib/court.js';
import { decimal, percent, signed, teamName, teamSlug, integer, barWidth } from './src/lib/format.js';

/** React separa nodos de texto contiguos con comentarios al renderizar en
    servidor; para comprobar lo que LEE el usuario hay que quitarlos. */
const texto = (html) => html.replace(/<!--[^>]*-->/g, '');

const problems = [];
const check = (name, fn) => {
  try {
    const html = fn();
    if (!html || html.length < 10) problems.push(`${name}: render vacío`);
    return html;
  } catch (error) {
    problems.push(`${name}: ${error.message}`);
    return '';
  }
};

const leader = fixtures.leaders[0];
const player = fixtures.players[leader.slug];
const contexto = {
  competition: fixtures.meta.competitionKey,
  season: fixtures.meta.seasonKey,
  group: fixtures.meta.groupKey ?? undefined,
};

if (!player) problems.push('fixtures: el primer líder no tiene ficha');

// --- primitivas -------------------------------------------------------------

check('StatTile', () => renderToString(<StatTile label="Valoración" value="23.6" note="máx 34" emphasis />));
check('Meter', () => renderToString(<Meter value={23.6} max={23.6} display="23.6" />));
check('LabelledBar', () => renderToString(<LabelledBar label="Triple" value={0.43} display="43%" detail="13/30" />));
check('Panel', () => renderToString(<Panel title="Líderes" hint="media por partido">contenido</Panel>));
check('Loading', () => renderToString(<Loading />));
check('ErrorState', () => renderToString(<ErrorState detail="fallo" onRetry={() => {}} />));
check('ShotLegend', () => renderToString(<ShotLegend made={38} missed={29} />));

const selectHtml = check('Select', () => renderToString(
  <Select label="Competición" value="tercerafeb" onChange={() => {}}
          options={[{ value: 'tercerafeb', label: 'Tercera FEB' }]} />));
// El filtro tiene que ser un control de verdad, no un adorno con una flecha
if (!selectHtml.includes('<select')) problems.push('Select: no renderiza un <select> real');
if (!selectHtml.includes('aria-label')) problems.push('Select: sin etiqueta accesible');

// --- jugadores / ligas -------------------------------------------------------

const pickerHtml = check('ContextPicker', () => renderToString(
  <ContextPicker catalogo={fixtures.competitions} contexto={contexto} onChange={() => {}} />));
const selects = (pickerHtml.match(/<select/g) || []).length;
if (selects !== 3) problems.push(`ContextPicker: ${selects} selectores, esperados 3`);
// Las opciones salen del catálogo real, no de una lista escrita a mano
for (const entrada of fixtures.competitions) {
  if (entrada.competitionKey === contexto.competition
      && !pickerHtml.includes(entrada.season)) {
    problems.push(`ContextPicker: falta la temporada ${entrada.season} del catálogo`);
  }
}

const rowHtml = check('LeaderRow', () => renderToString(
  <table><tbody>
    <LeaderRow player={leader} rank={1} max={leader.perGame.val}
               onNavigate={() => {}} context={contexto} />
  </tbody></table>));
// El enlace debe llevar el contexto: si no, la ficha se abriría en otra competición
if (!rowHtml.includes(`competition=${contexto.competition}`)) {
  problems.push('LeaderRow: el enlace no arrastra la competición');
}
if (!rowHtml.includes(`#/jugador/${leader.slug}`)) {
  problems.push('LeaderRow: el enlace no apunta a la ficha');
}

const pagerHtml = check('Pager', () => renderToString(
  <Pager offset={0} total={fixtures.leadersTotal} size={10} onMove={() => {}} />));
if (!texto(pagerHtml).includes(`1-10 de ${fixtures.leadersTotal}`)) {
  problems.push('Pager: el rango mostrado no cuadra');
}
// En la primera página no se puede retroceder
const primeraPagina = renderToString(<Pager offset={0} total={100} size={10} onMove={() => {}} />);
if ((primeraPagina.match(/disabled/g) || []).length !== 1) {
  problems.push('Pager: en la primera página solo "Anteriores" debe estar deshabilitado');
}
const ultimaPagina = renderToString(<Pager offset={90} total={100} size={10} onMove={() => {}} />);
if (!texto(ultimaPagina).includes('91-100 de 100')) {
  problems.push('Pager: última página mal calculada');
}

check('GameRow', () => renderToString(<GameRow game={fixtures.recentGames[0]} />));

// Agrupar por jornada: todos los partidos de recentGames tienen que quedar
// repartidos sin perder ninguno, y cada grupo comparte fecha.
const jornadas = agruparPorJornada(fixtures.recentGames);
const totalAgrupado = jornadas.reduce((sum, j) => sum + j.partidos.length, 0);
if (totalAgrupado !== fixtures.recentGames.length) {
  problems.push(`agruparPorJornada: ${totalAgrupado} partidos agrupados, esperados ${fixtures.recentGames.length}`);
}
for (const jornada of jornadas) {
  if (jornada.partidos.some((g) => g.date !== jornada.date)) {
    problems.push(`agruparPorJornada: la jornada ${jornada.date} mezcla fechas distintas`);
  }
}

// --- pantalla de ficha ------------------------------------------------------

const identityHtml = check('Identity', () => renderToString(
  <Identity player={player} meta={player.meta} />));
if (!texto(identityHtml).includes(String(player.jersey))) problems.push('Identity: falta el dorsal');

check('ShootingPanel', () => renderToString(
  <ShootingPanel shooting={player.shooting} totals={player.totals} />));

const logHtml = check('GameLog', () => renderToString(
  <GameLog games={player.gameLog} maxVal={player.bests.val} />));
const filas = (logHtml.match(/<tr/g) || []).length - 1;   // menos la cabecera
if (filas !== player.gameLog.length) {
  problems.push(`GameLog: ${filas} filas para ${player.gameLog.length} partidos`);
}

const shotHtml = check('ShotChart', () => renderToString(<ShotChart shots={player.shots} />));
const COURT_CIRCLES = 3;   // tiros libres, zona restringida y aro
const circles = (shotHtml.match(/<circle/g) || []).length;
if (circles !== player.shots.length + COURT_CIRCLES) {
  problems.push(`ShotChart: ${circles} círculos, esperados ${player.shots.length + COURT_CIRCLES}`);
}

for (const shot of player.shots) {
  const { cx, cy } = projectShot(shot);
  if (cx < 0 || cx > VIEW_W || cy < 0 || cy > VIEW_H) {
    problems.push(`proyección fuera de lienzo: ${JSON.stringify(shot)} -> ${cx},${cy}`);
    break;
  }
}

// --- comparador de jugadores -------------------------------------------------

const compareSlugs = fixtures.leaders.slice(0, 2).map((l) => l.slug);
const comparePlayers = compareSlugs.map((slug) => fixtures.players[slug]);
if (comparePlayers.some((p) => !p)) problems.push('comparador: algún líder de prueba no tiene ficha');

const compareHtml = check('CompareTable', () => renderToString(
  <CompareTable players={comparePlayers} context={contexto} onRemove={() => {}} />));
for (const p of comparePlayers) {
  if (!texto(compareHtml).includes(p.name)) problems.push(`CompareTable: falta ${p.name}`);
}
const quitarBotones = (compareHtml.match(/Quitar ✕/g) || []).length;
if (quitarBotones !== comparePlayers.length) {
  problems.push(`CompareTable: ${quitarBotones} botones "Quitar", esperados ${comparePlayers.length}`);
}
for (const seccion of ['Medias por partido', 'Tiro', 'Por 36 minutos']) {
  if (!texto(compareHtml).includes(seccion)) problems.push(`CompareTable: falta la sección "${seccion}"`);
}

// Con un único jugador no debe fallar, aunque no tenga sentido resaltar nada.
check('CompareTable (1 jugador)', () => renderToString(
  <CompareTable players={[comparePlayers[0]]} context={contexto} onRemove={() => {}} />));

// El pozo de búsqueda es el mismo que "Líderes por valoración": una búsqueda
// sin acento tiene que encontrar a un jugador con nombre acentuado.
const acentuado = fixtures.leaders.find((l) => /[áéíóúñ]/i.test(l.name));
if (acentuado) {
  const sinAcento = acentuado.name.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const encontrado = filterCandidates(fixtures.leaders, sinAcento.slice(0, 6), [])
    .some((c) => c.slug === acentuado.slug);
  if (!encontrado) problems.push(`filterCandidates: "${sinAcento.slice(0, 6)}" no encuentra a ${acentuado.name}`);
}
if (filterCandidates(fixtures.leaders, 'a', []).length !== 0) {
  problems.push('filterCandidates: una letra no debería devolver candidatos');
}
const excluido = fixtures.leaders[0];
const conExclusion = filterCandidates(fixtures.leaders, excluido.name.slice(0, 4), [excluido.slug]);
if (conExclusion.some((c) => c.slug === excluido.slug)) {
  problems.push('filterCandidates: no respeta la exclusión de ya elegidos');
}

const searchHtml = check('SearchBox', () => renderToString(
  <SearchBox query={fixtures.leaders[0].name.slice(0, 4)}
             onQueryChange={() => {}}
             candidates={filterCandidates(fixtures.leaders, fixtures.leaders[0].name.slice(0, 4), [])}
             disabled={false}
             onPick={() => {}} />));
if (!texto(searchHtml).includes(fixtures.leaders[0].name)) {
  problems.push('SearchBox: no lista al candidato esperado');
}
const searchVacioHtml = check('SearchBox (sin resultados)', () => renderToString(
  <SearchBox query="zzzzzzzzzz" onQueryChange={() => {}} candidates={[]} disabled={false} onPick={() => {}} />));
if (!texto(searchVacioHtml).includes('Sin resultados')) {
  problems.push('SearchBox: no avisa cuando no hay resultados');
}
const searchLlenoHtml = check('SearchBox (cupo lleno)', () => renderToString(
  <SearchBox query="" onQueryChange={() => {}} candidates={[]} disabled onPick={() => {}} />));
if (!texto(searchLlenoHtml).includes(String(MAX_COMPARE))) {
  problems.push('SearchBox: no avisa del máximo de jugadores al estar deshabilitado');
}

// --- radar de percentiles -----------------------------------------------------

const puntosAxis = RADAR_AXES.find((a) => a.key === 'pts');
const pctPool = [{ perGame: { pts: 10 } }, { perGame: { pts: 20 } }, { perGame: { pts: 30 } }];
if (percentileRank(pctPool, puntosAxis, 20) !== 67) {
  problems.push(`percentileRank: esperado 67, dio ${percentileRank(pctPool, puntosAxis, 20)}`);
}
if (percentileRank(pctPool, puntosAxis, 30) !== 100) problems.push('percentileRank: el máximo del pozo debe ser 100');
if (percentileRank(pctPool, puntosAxis, null) !== null) problems.push('percentileRank: un valor nulo debe dar percentil nulo');
if (percentileRank([], puntosAxis, 20) !== null) problems.push('percentileRank: un pozo vacío debe dar percentil nulo');

const radarHtml = check('RadarChart', () => renderToString(
  <RadarChart players={comparePlayers} pool={fixtures.leaders} />));
for (const p of comparePlayers) {
  if (!radarHtml.includes(p.name)) problems.push(`RadarChart: falta ${p.name} en el aria-label`);
}
for (const axis of RADAR_AXES) {
  if (!texto(radarHtml).includes(axis.label)) problems.push(`RadarChart: falta el eje "${axis.label}"`);
}
// Un polígono de percentiles por jugador + los 4 anillos de la rejilla.
const poligonos = (radarHtml.match(/<polygon/g) || []).length;
if (poligonos !== comparePlayers.length + 4) {
  problems.push(`RadarChart: ${poligonos} polígonos, esperados ${comparePlayers.length + 4}`);
}

// Con más jugadores de los que el radar admite (chequeo de daltonismo por
// parejas, no solo adyacentes) se recorta a los tres primeros, no se rompe.
const cuatroJugadores = fixtures.leaders.slice(0, 4).map((l) => fixtures.players[l.slug]);
const radarLimitadoHtml = check('RadarChart (4 jugadores)', () => renderToString(
  <RadarChart players={cuatroJugadores} pool={fixtures.leaders} />));
if (cuatroJugadores[3] && radarLimitadoHtml.includes(cuatroJugadores[3].name)) {
  problems.push('RadarChart: dibuja un cuarto jugador, debería recortar a 3');
}

const legendHtml = check('RadarLegend', () => renderToString(<RadarLegend players={comparePlayers} />));
for (const p of comparePlayers) {
  if (!texto(legendHtml).includes(p.name)) problems.push(`RadarLegend: falta ${p.name}`);
}

// --- clasificación / ficha de equipo ------------------------------------------

// El slug se calcula en el cliente en varios sitios (fila de líder, cabecera
// de jugador) para enlazar a la ficha sin que la API lo traiga ya resuelto;
// tiene que coincidir con el que genera el backend (src/naming.py:team_slug),
// o el enlace apuntaría a un equipo que el índice del servidor no reconoce.
for (const fila of fixtures.teamsStandings) {
  if (teamSlug(fila.team) !== fila.teamKey) {
    problems.push(`teamSlug: "${fila.team}" -> "${teamSlug(fila.team)}", esperado "${fila.teamKey}"`);
  }
}

const primerEquipoKey = Object.keys(fixtures.teams)[0];
const equipo = fixtures.teams[primerEquipoKey];
if (!equipo) problems.push('fixtures: no hay ninguna ficha de equipo');

const standingsRowHtml = check('StandingsRow', () => renderToString(
  <table><tbody>
    <StandingsRow team={fixtures.teamsStandings[0]} onOpen={() => {}} context={contexto} />
  </tbody></table>));
if (!standingsRowHtml.includes(`#/equipo/${fixtures.teamsStandings[0].teamKey}`)) {
  problems.push('StandingsRow: el enlace no apunta a la ficha de equipo');
}

const teamIdentityHtml = check('Team Identity', () => renderToString(
  <TeamIdentity team={equipo} meta={equipo.meta} standing={equipo.standing} />));
if (!texto(teamIdentityHtml).includes(`${equipo.standing.wins}-${equipo.standing.losses}`)) {
  problems.push('Team Identity: falta el récord');
}

const rosterHtml = check('Roster', () => renderToString(
  <Roster roster={equipo.roster} context={contexto} onOpen={() => {}} />));
const filasRoster = (rosterHtml.match(/<tr/g) || []).length - 1;
if (filasRoster !== equipo.roster.length) {
  problems.push(`Roster: ${filasRoster} filas para ${equipo.roster.length} jugadores`);
}
for (const jugador of equipo.roster) {
  if (!texto(rosterHtml).includes(jugador.name)) problems.push(`Roster: falta ${jugador.name}`);
}

const paceLogHtml = check('PaceLog', () => renderToString(<PaceLog gameLog={equipo.gameLog} />));
const filasPace = (paceLogHtml.match(/<tr/g) || []).length - 1;
if (filasPace !== equipo.gameLog.length) {
  problems.push(`PaceLog: ${filasPace} filas para ${equipo.gameLog.length} partidos`);
}

const teamShotHtml = check('ShotChart (equipo)', () => renderToString(<ShotChart shots={equipo.shots} />));
const circulosEquipo = (teamShotHtml.match(/<circle/g) || []).length;
if (circulosEquipo !== equipo.shots.length + COURT_CIRCLES) {
  problems.push(`ShotChart equipo: ${circulosEquipo} círculos, esperados ${equipo.shots.length + COURT_CIRCLES}`);
}

// Las fichas de equipo tienen que traer la misma forma que sirve la API.
for (const clave of ['teamsStandings', 'teams']) {
  if (!(clave in fixtures)) problems.push(`fixtures: falta "${clave}"`);
}
for (const clave of ['team', 'group', 'meta', 'standing', 'pace', 'gameLog', 'roster', 'shots']) {
  if (!(clave in equipo)) problems.push(`fixtures.teams: falta "${clave}" en la ficha de ${primerEquipoKey}`);
}

// --- clutch / faltas / red de asistencias ------------------------------------

for (const clave of ['clutch', 'fouls', 'assistNetwork', 'assistNetworkByTeam']) {
  if (!(clave in fixtures)) problems.push(`fixtures: falta "${clave}"`);
}

const clutchRowHtml = check('ClutchRow', () => renderToString(
  <table><tbody>
    <ClutchRow player={fixtures.clutch.players[0]} rank={1} onNavigate={() => {}} context={contexto} />
  </tbody></table>));
if (!clutchRowHtml.includes(`#/jugador/${fixtures.clutch.players[0].slug}`)) {
  problems.push('ClutchRow: el enlace no apunta a la ficha');
}

const foulRowHtml = check('FoulRow', () => renderToString(
  <table><tbody>
    <FoulRow player={fixtures.fouls.players[0]} rank={1} onNavigate={() => {}} context={contexto} />
  </tbody></table>));
if (!foulRowHtml.includes(`#/jugador/${fixtures.fouls.players[0].slug}`)) {
  problems.push('FoulRow: el enlace no apunta a la ficha');
}
if (!fixtures.fouls.teams.length) problems.push('fixtures.fouls: sin resumen por equipo');

check('TeamFoulRow', () => renderToString(
  <table><tbody>
    <TeamFoulRow team={fixtures.fouls.teams[0]} context={contexto} />
  </tbody></table>));

// La red de una competición entera puede tener cientos de nodos; el
// diagrama solo se usa recortado (ver Assists.jsx), pero tiene que
// aguantar tanto un puñado de nodos (equipo) como una lista más larga.
const primerEquipoAsistencias = Object.values(fixtures.assistNetworkByTeam)[0];
if (!primerEquipoAsistencias) problems.push('fixtures.assistNetworkByTeam: vacío');
if (primerEquipoAsistencias) {
  const networkHtml = check('AssistNetwork', () => renderToString(
    <AssistNetwork nodes={primerEquipoAsistencias.nodes} edges={primerEquipoAsistencias.edges} />));
  const nodosDibujados = (networkHtml.match(/<circle/g) || []).length;
  if (nodosDibujados !== primerEquipoAsistencias.nodes.length) {
    problems.push(`AssistNetwork: ${nodosDibujados} nodos dibujados, esperados ${primerEquipoAsistencias.nodes.length}`);
  }
  for (const edge of primerEquipoAsistencias.edges) {
    if (edge.passerSlug === edge.scorerSlug) problems.push('AssistNetwork: un jugador no puede asistirse a sí mismo');
  }
}
check('AssistNetwork (vacío)', () => renderToString(<AssistNetwork nodes={[]} edges={[]} />));

// --- formateadores ----------------------------------------------------------

const cases = [
  ['decimal', decimal(13.75), '13.8'],
  ['decimal nulo', decimal(null), '—'],
  ['percent', percent(0.6410), '64.1%'],
  ['percent nulo', percent(null), '—'],
  ['signed positivo', signed(6.9), '+6.9'],
  ['signed negativo', signed(-2.15), '-2.1'],
  ['integer', integer(8800), '8.800'],
  ['teamName', teamName('CB MORVEDRE'), 'CB Morvedre'],
  // Capitalizar tras guion acierta en la mayoría de nombres del catálogo
  // (patrón patrocinador-localidad, "Rigalli-Alginet"). Vila-real es una
  // excepción ortográfica del topónimo que se asume a conciencia.
  ['teamName guion', teamName('RIGALLI-ALGINET'), 'Rigalli-Alginet'],
  ['teamName apostrofo', teamName("SOCAGE JOVENS L'ELIANA"), "Socage Jovens L'Eliana"],
  ['teamName sigla con punto', teamName('C.A. MONTEMAR'), 'C.A. Montemar'],
  ['teamName sigla sin vocales', teamName('CMG HIDRÁULICA NB TORRENT'), 'CMG Hidráulica NB Torrent'],
  ['teamName palabra corta con vocal', teamName('THE FITZGERALD EL PILAR'), 'The Fitzgerald El Pilar'],
  ['barWidth tope', String(barWidth(50, 10)), '100'],
  ['barWidth sin max', String(barWidth(5, 0)), '0'],
];
for (const [name, got, want] of cases) {
  if (got !== want) problems.push(`${name}: "${got}" != "${want}"`);
}

// --- coherencia de los datos de ejemplo -------------------------------------

for (const slug of Object.keys(fixtures.players)) {
  for (const zone of Object.keys(fixtures.players[slug].zones)) {
    if (!ZONE_ORDER.includes(zone) || !ZONE_LABEL[zone]) {
      problems.push(`zona sin etiqueta: ${zone} (${slug})`);
    }
  }
}
// Los datos de ejemplo tienen que traer la misma forma que sirve la API, o el
// modo sin conexión enseñaría algo distinto justo cuando menos conviene.
for (const clave of ['meta', 'summary', 'leaders', 'leadersTotal', 'recentGames',
                     'competitions', 'players']) {
  if (!(clave in fixtures)) problems.push(`fixtures: falta "${clave}"`);
}
for (const clave of ['competitionKey', 'seasonKey', 'groups', 'matchDays']) {
  if (!(clave in fixtures.meta)) problems.push(`fixtures.meta: falta "${clave}"`);
}
if (!('group' in leader)) problems.push('fixtures.leaders: falta "group"');

const navegables = fixtures.leaders.filter((l) => fixtures.players[l.slug]).length;
if (navegables === 0) problems.push('ningún líder tiene ficha');

if (problems.length) {
  console.error('FALLOS:\n' + problems.map((p) => '  - ' + p).join('\n'));
  process.exit(1);
}
console.log(
  `OK — ${Object.keys(fixtures.players).length} fichas · ${navegables}/${fixtures.leaders.length} líderes navegables · `
  + `${player.shots.length} tiros · ${cases.length} formateadores · `
  + `${fixtures.competitions.length} entradas de catálogo · ambas pantallas renderizadas`
);
