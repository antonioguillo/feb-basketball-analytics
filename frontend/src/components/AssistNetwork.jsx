import { useState } from 'react';
import { integer } from '../lib/format.js';

const SIZE = 560;
const CENTER = SIZE / 2;
const RADIUS = 210;

// Como el radar: todos los nodos en corro, el primero arriba y el resto en el
// sentido del reloj. Con hasta ~18 jugadores (una plantilla completa) el
// círculo sigue siendo legible; una red liga-completa se recorta antes de
// llegar aquí (ver Assists.jsx).
function layout(nodes) {
  const n = nodes.length;
  return nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / n - Math.PI / 2;
    return {
      node,
      x: CENTER + Math.cos(angle) * RADIUS,
      y: CENTER + Math.sin(angle) * RADIUS,
      // Las etiquetas se apoyan hacia fuera, en la misma dirección que el nodo.
      labelX: CENTER + Math.cos(angle) * (RADIUS + 22),
      labelY: CENTER + Math.sin(angle) * (RADIUS + 22),
      isRight: Math.cos(angle) > 0.15,
      isLeft: Math.cos(angle) < -0.15,
    };
  });
}

/** Grosor 1.4-7px por peso relativo del par, no lineal con el recuento crudo:
    así un par de 40 asistencias no aplasta visualmente a uno de 8. */
function strokeWidth(assists, max) {
  if (!max) return 1.4;
  return 1.4 + Math.sqrt(assists / max) * 5.6;
}

/**
 * Diagrama circular de quién asiste a quién dentro de un equipo (o el top de
 * la competición si no se ha filtrado por equipo). No es una vista con física
 * de fuerzas: la posición es solo el orden que llega de la API, para que el
 * dibujo sea estable entre recargas y no "salte" al pasar el ratón.
 */
export default function AssistNetwork({ nodes, edges }) {
  const [hovered, setHovered] = useState(null); // { kind: 'node'|'edge', key, ... }
  const placed = layout(nodes);
  const posBySlug = new Map(placed.map((p) => [p.node.slug, p]));
  const maxAssists = edges.reduce((max, edge) => Math.max(max, edge.assists), 0);

  const isEdgeDim = (edge) => {
    if (!hovered) return false;
    if (hovered.kind === 'edge') return hovered.key !== `${edge.passerSlug}-${edge.scorerSlug}`;
    return hovered.slug !== edge.passerSlug && hovered.slug !== edge.scorerSlug;
  };
  const isNodeDim = (node) => {
    if (!hovered) return false;
    if (hovered.kind === 'node') return hovered.slug !== node.slug;
    return hovered.passerSlug !== node.slug && hovered.scorerSlug !== node.slug;
  };

  return (
    <div style={{ position: 'relative' }}>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ width: '100%', height: 'auto', display: 'block' }}
        role="img"
        aria-label={`Red de asistencias entre ${nodes.length} jugadores`}
      >
        <g fill="none" stroke="var(--accent)">
          {edges.map((edge) => {
            const from = posBySlug.get(edge.passerSlug);
            const to = posBySlug.get(edge.scorerSlug);
            if (!from || !to) return null;
            const key = `${edge.passerSlug}-${edge.scorerSlug}`;
            const dim = isEdgeDim(edge);
            return (
              <line
                key={key}
                x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                strokeWidth={strokeWidth(edge.assists, maxAssists)}
                strokeOpacity={dim ? 0.06 : 0.4}
                strokeLinecap="round"
                onMouseEnter={() => setHovered({ kind: 'edge', key, edge })}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: 'pointer' }}
              />
            );
          })}
        </g>

        {placed.map(({ node, x, y, labelX, labelY, isRight, isLeft }) => {
          const dim = isNodeDim(node);
          const weight = node.assistsGiven + node.assistsReceived;
          const r = Math.max(4, Math.min(11, 4 + Math.sqrt(weight)));
          return (
            <g
              key={node.slug}
              opacity={dim ? 0.3 : 1}
              onMouseEnter={() => setHovered({ kind: 'node', slug: node.slug, node })}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: 'pointer' }}
            >
              <circle cx={x} cy={y} r={r} fill="var(--surface)" stroke="var(--accent)" strokeWidth="2" />
              <text
                x={labelX}
                y={labelY}
                textAnchor={isRight ? 'start' : isLeft ? 'end' : 'middle'}
                dominantBaseline="middle"
                style={{ fontSize: 12, fill: 'var(--ink)', fontWeight: 500 }}
              >
                {node.name.split(' ').slice(-1)[0]}
              </text>
            </g>
          );
        })}
      </svg>

      {hovered?.kind === 'edge' && (
        <Tooltip>
          <strong style={{ color: 'var(--ink)' }}>{hovered.edge.passer}</strong>
          {' → '}
          <strong style={{ color: 'var(--ink)' }}>{hovered.edge.scorer}</strong>
          <br />
          {integer(hovered.edge.assists)} asistencias · {integer(hovered.edge.points)} puntos generados
        </Tooltip>
      )}
      {hovered?.kind === 'node' && (
        <Tooltip>
          <strong style={{ color: 'var(--ink)' }}>{hovered.node.name}</strong>
          <br />
          {integer(hovered.node.assistsGiven)} dadas · {integer(hovered.node.assistsReceived)} recibidas
          · {integer(hovered.node.pointsCreated)} puntos generados
        </Tooltip>
      )}
    </div>
  );
}

function Tooltip({ children }) {
  return (
    <div
      style={{
        position: 'absolute', left: '50%', bottom: 4, transform: 'translateX(-50%)',
        background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6,
        padding: '8px 12px', fontSize: '0.8125rem', color: 'var(--muted)',
        pointerEvents: 'none', whiteSpace: 'nowrap', zIndex: 2,
      }}
    >
      {children}
    </div>
  );
}
