/* Comprobación de render fuera del navegador: monta las piezas de la interfaz
   —incluidas las de las dos pantallas— con los datos reales y falla si alguna
   lanza o pinta algo incoherente. Se ejecuta con `npm run check` y no forma
   parte de la aplicación. */
import { renderToString } from 'react-dom/server';
import fixtures from './src/api/fixtures.json';
import ShotChart, { ShotLegend } from './src/components/ShotChart.jsx';
import {
  Panel, StatTile, Meter, LabelledBar, Select, Loading, ErrorState,
} from './src/components/Primitives.jsx';
import { ContextPicker, PageHead, LeaderRow, Pager, ResultRow, EmptyLeaders } from './src/pages/Dashboard.jsx';
import { Identity, ShootingPanel, GameLog } from './src/pages/Player.jsx';
import { ZONE_ORDER, ZONE_LABEL, projectShot, VIEW_W, VIEW_H } from './src/lib/court.js';
import { decimal, percent, signed, teamName, integer, barWidth } from './src/lib/format.js';

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

// --- pantalla de dashboard --------------------------------------------------

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

check('PageHead', () => renderToString(
  <PageHead meta={fixtures.meta} catalogo={fixtures.competitions}
            contexto={contexto} onChange={() => {}} />));

const rowHtml = check('LeaderRow', () => renderToString(
  <table><tbody>
    <LeaderRow player={leader} rank={1} max={leader.perGame.val}
               onOpen={() => {}} context={contexto} />
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

// Un grupo con pocos partidos no tiene a nadie sobre el mínimo: hay que decirlo
const vacioHtml = check('EmptyLeaders', () => renderToString(<EmptyLeaders total={0} />));
if (!texto(vacioHtml).includes('6 partidos')) {
  problems.push('EmptyLeaders: no explica el umbral');
}

check('ResultRow', () => renderToString(
  <ResultRow game={fixtures.recentGames[0]} last={false} />));

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
