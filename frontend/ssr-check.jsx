/* Comprobación de render fuera del navegador: monta las piezas de la interfaz
   con los datos reales y falla si alguna lanza. Se ejecuta con vite build --ssr
   (ver README) y no forma parte de la aplicación. */
import { renderToString } from 'react-dom/server';
import fixtures from './src/api/fixtures.json';
import ShotChart, { ShotLegend } from './src/components/ShotChart.jsx';
import { Panel, StatTile, Meter, LabelledBar, FilterChip, Loading, ErrorState } from './src/components/Primitives.jsx';
import { ZONE_ORDER, ZONE_LABEL, projectShot, VIEW_W, VIEW_H } from './src/lib/court.js';
import { decimal, percent, signed, teamName, integer, barWidth } from './src/lib/format.js';

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

const player = fixtures.players['ortega-ibanez-alejandro'];
if (!player) problems.push('fixtures: falta el jugador de referencia');

check('StatTile', () => renderToString(<StatTile label="Valoración" value="23.6" note="máximo 34" emphasis />));
check('Meter', () => renderToString(<Meter value={23.6} max={23.6} display="23.6" />));
check('LabelledBar', () => renderToString(<LabelledBar label="Triple" value={0.43} display="43%" detail="13/30" />));
check('FilterChip', () => renderToString(<FilterChip>Tercera FEB</FilterChip>));
check('Panel', () => renderToString(<Panel title="Líderes" hint="media por partido">contenido</Panel>));
check('Loading', () => renderToString(<Loading />));
check('ErrorState', () => renderToString(<ErrorState detail="fallo" onRetry={() => {}} />));
check('ShotLegend', () => renderToString(<ShotLegend made={38} missed={29} />));

const shotHtml = check('ShotChart', () => renderToString(<ShotChart shots={player.shots} />));
const circles = (shotHtml.match(/<circle/g) || []).length;
// Los tiros más los 3 círculos fijos de la pista: tiros libres, zona
// restringida y aro.
const COURT_CIRCLES = 3;
if (circles !== player.shots.length + COURT_CIRCLES) {
  problems.push(`ShotChart: ${circles} círculos, esperados ${player.shots.length + COURT_CIRCLES}`);
}

// Ningún tiro puede caer fuera del lienzo de media pista
for (const shot of player.shots) {
  const { cx, cy } = projectShot(shot);
  if (cx < 0 || cx > VIEW_W || cy < 0 || cy > VIEW_H) {
    problems.push(`proyección fuera de lienzo: ${JSON.stringify(shot)} -> ${cx},${cy}`);
    break;
  }
}

// Formateadores
const cases = [
  ['decimal', decimal(13.75), '13.8'],
  ['decimal nulo', decimal(null), '—'],
  ['percent', percent(0.6410), '64.1%'],
  ['percent nulo', percent(null), '—'],
  ['signed positivo', signed(6.9), '+6.9'],
  ['signed negativo', signed(-2.15), '-2.1'],
  ['integer', integer(8800), '8.800'],
  ['teamName', teamName('CB MORVEDRE'), 'CB Morvedre'],
  ['teamName acento', teamName('FUNDACIÓ CAIXA RURAL VILA-REAL'), 'Fundació Caixa Rural Vila-real'],
  ['barWidth tope', String(barWidth(50, 10)), '100'],
  ['barWidth sin max', String(barWidth(5, 0)), '0'],
];
for (const [name, got, want] of cases) {
  if (got !== want) problems.push(`${name}: "${got}" != "${want}"`);
}

// Cobertura de zonas: toda zona presente en los datos debe tener etiqueta
for (const slug of Object.keys(fixtures.players)) {
  for (const zone of Object.keys(fixtures.players[slug].zones)) {
    if (!ZONE_ORDER.includes(zone) || !ZONE_LABEL[zone]) {
      problems.push(`zona sin etiqueta: ${zone} (${slug})`);
    }
  }
}

// Todo líder debe tener ficha navegable
for (const leader of fixtures.leaders) {
  if (!fixtures.players[leader.slug]) problems.push(`líder sin ficha: ${leader.slug}`);
}

if (problems.length) {
  console.error('FALLOS:\n' + problems.map((p) => '  - ' + p).join('\n'));
  process.exit(1);
}
console.log(
  `OK — ${Object.keys(fixtures.players).length} fichas, ${player.shots.length} tiros renderizados, ` +
    `${cases.length} formateadores, todos los líderes navegables`
);
