import { useState } from 'react';
import { decimal, percent } from '../lib/format.js';

const SIZE = 480;
const CENTER = SIZE / 2;
const RADIUS = 172;
const RINGS = [25, 50, 75, 100];

export const RADAR_AXES = [
  { key: 'pts', label: 'Puntos', group: 'perGame', format: decimal },
  { key: 'reb', label: 'Rebotes', group: 'perGame', format: decimal },
  { key: 'ast', label: 'Asistencias', group: 'perGame', format: decimal },
  { key: 'stl', label: 'Robos', group: 'perGame', format: decimal },
  { key: 'blk', label: 'Tapones', group: 'perGame', format: decimal },
  { key: 'ts', label: 'TS%', group: 'shooting', format: percent },
];

// blue / orange / aqua: las tres tonalidades del sistema que superan el
// chequeo de daltonismo por TODAS las parejas (no solo adyacentes) sobre un
// fondo oscuro — un radar es una forma "all-pairs", cualquier par de
// jugadores puede solaparse en pantalla. Una cuarta serie no lo pasaría
// (ver dataviz skill, palette.md), así que el radar se limita a 3 y la tabla
// de abajo sigue enseñando hasta 4.
export const RADAR_COLORS = ['#3987e5', '#d95926', '#199e70'];
export const MAX_RADAR_PLAYERS = RADAR_COLORS.length;

function axisValue(player, axis) {
  const value = player[axis.group]?.[axis.key];
  return value === null || value === undefined || Number.isNaN(value) ? null : value;
}

/**
 * Percentil 0-100 del valor dentro del pozo de jugadores elegibles: qué
 * proporción del pozo queda igual o por debajo. Así los seis ejes comparten
 * una única escala (percentil) en vez de mezclar puntos, rebotes y
 * porcentajes de tiro en el mismo radio — la alternativa (una escala propia
 * por eje) infla visualmente el área sin que sea comparable entre ejes.
 */
export function percentileRank(pool, axis, value) {
  if (value === null || value === undefined) return null;
  const values = pool
    .map((p) => p[axis.group]?.[axis.key])
    .filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (!values.length) return null;
  const below = values.filter((v) => v <= value).length;
  return Math.round((below / values.length) * 100);
}

function point(axisIndex, radiusFraction) {
  const angle = (Math.PI * 2 * axisIndex) / RADAR_AXES.length - Math.PI / 2;
  return {
    x: CENTER + Math.cos(angle) * RADIUS * radiusFraction,
    y: CENTER + Math.sin(angle) * RADIUS * radiusFraction,
  };
}

function polygonPoints(fractions) {
  return fractions.map((fraction, index) => point(index, fraction)).map((p) => `${p.x},${p.y}`).join(' ');
}

function RadarGrid() {
  return (
    <g fill="none" stroke="var(--border-soft)" strokeWidth="1">
      {RINGS.map((ring) => (
        <polygon key={ring} points={polygonPoints(RADAR_AXES.map(() => ring / 100))} />
      ))}
      {RADAR_AXES.map((axis, index) => {
        const tip = point(index, 1);
        return <line key={axis.key} x1={CENTER} y1={CENTER} x2={tip.x} y2={tip.y} />;
      })}
    </g>
  );
}

/** Las etiquetas se colocan por índice de eje, no por geometría: con 6 ejes
    y el primero arriba (ver point()), el índice 0 es siempre "arriba" y el
    N/2 siempre "abajo", así que no hace falta comparar coordenadas. */
function RadarLabels() {
  const n = RADAR_AXES.length;
  return (
    <g>
      {RADAR_AXES.map((axis, index) => {
        const tip = point(index, 1.16);
        const isTop = index === 0;
        const isBottom = index === n / 2;
        const isRight = index > 0 && index < n / 2;
        return (
          <text
            key={axis.key}
            x={tip.x}
            y={tip.y}
            textAnchor={isTop || isBottom ? 'middle' : isRight ? 'start' : 'end'}
            dominantBaseline={isTop ? 'auto' : isBottom ? 'hanging' : 'middle'}
            style={{ fontSize: 13, fill: 'var(--muted)' }}
          >
            {axis.label}
          </text>
        );
      })}
    </g>
  );
}

/**
 * Radar de percentiles. `pool` es el mismo pozo de jugadores elegibles que
 * usa el buscador del comparador (mínimo 6 partidos y 15 minutos), y define
 * contra quién se mide el percentil de cada jugador comparado.
 */
export default function RadarChart({ players, pool }) {
  const [hovered, setHovered] = useState(null);
  const shown = players.slice(0, MAX_RADAR_PLAYERS);

  const series = shown.map((player, seriesIndex) => ({
    player,
    color: RADAR_COLORS[seriesIndex],
    values: RADAR_AXES.map((axis) => {
      const raw = axisValue(player, axis);
      return { raw, pct: percentileRank(pool, axis, raw) };
    }),
  }));

  return (
    <div style={{ position: 'relative' }}>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ width: '100%', height: 'auto', display: 'block' }}
        role="img"
        aria-label={`Comparativa por percentil de ${shown.map((p) => p.name).join(', ')}`}
      >
        <RadarGrid />
        {series.map((s) => (
          <polygon
            key={s.player.slug}
            points={polygonPoints(s.values.map((v) => (v.pct ?? 0) / 100))}
            fill={s.color}
            fillOpacity="0.12"
            stroke={s.color}
            strokeWidth="2"
            strokeLinejoin="round"
          />
        ))}
        {series.map((s) => s.values.map((v, axisIndex) => {
          const p = point(axisIndex, (v.pct ?? 0) / 100);
          const key = `${s.player.slug}-${axisIndex}`;
          const isHovered = hovered?.key === key;
          return (
            <g key={key}>
              {/* Diana de 28px: el punto visible es más pequeño de lo que conviene acertar con el ratón. */}
              <circle
                cx={p.x}
                cy={p.y}
                r={14}
                fill="transparent"
                onMouseEnter={() => setHovered({ key, s, axis: RADAR_AXES[axisIndex], value: v, p })}
                onMouseLeave={() => setHovered(null)}
              />
              <circle
                cx={p.x}
                cy={p.y}
                r={isHovered ? 6 : 4}
                fill={s.color}
                stroke="var(--surface)"
                strokeWidth="2"
                pointerEvents="none"
              />
            </g>
          );
        }))}
        <RadarLabels />
      </svg>

      {hovered && (
        <div
          style={{
            position: 'absolute',
            left: `${(hovered.p.x / SIZE) * 100}%`,
            top: `${(hovered.p.y / SIZE) * 100}%`,
            transform: 'translate(-50%, -140%)',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '7px 10px',
            fontSize: '0.75rem',
            color: 'var(--ink)',
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
            zIndex: 2,
          }}
        >
          <strong style={{ color: hovered.s.color }}>{hovered.s.player.name}</strong>
          {' · '}
          {hovered.axis.label}{' '}
          <strong>{hovered.value.raw === null ? '—' : hovered.axis.format(hovered.value.raw)}</strong>
          {hovered.value.pct !== null && <> · percentil {hovered.value.pct}</>}
        </div>
      )}
    </div>
  );
}

/** La leyenda usa un trazo corto, no una caja rellena: el radar es una marca
    de línea + área, no una barra. */
export function RadarLegend({ players }) {
  return (
    <div className="row" style={{ gap: 18, fontSize: '0.8125rem', flexWrap: 'wrap' }}>
      {players.slice(0, MAX_RADAR_PLAYERS).map((player, index) => (
        <span key={player.slug} className="row" style={{ gap: 7 }}>
          <svg width="16" height="4" viewBox="0 0 16 4" aria-hidden="true">
            <rect width="16" height="4" rx="2" fill={RADAR_COLORS[index]} />
          </svg>
          <span style={{ color: 'var(--ink)' }}>{player.name}</span>
        </span>
      ))}
    </div>
  );
}
