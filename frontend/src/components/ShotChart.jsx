import { useState } from 'react';
import { VIEW_W, VIEW_H, HOOP, THREE_R, RESTRICTED_AREA_M, ZONE_LABEL, projectShot } from '../lib/court.js';

const LINE = 'var(--border)';

/** Líneas de la pista: perímetro, zona, círculo de tiros libres, 6,75 y aro. */
function CourtLines() {
  const paintW = 490;
  const paintH = 577;
  const cornerX = HOOP.x - THREE_R;

  return (
    <g fill="none" stroke={LINE} strokeWidth="6">
      <rect x="3" y="3" width={VIEW_W - 6} height={VIEW_H - 6} />
      <rect x={HOOP.x - paintW / 2} y={VIEW_H - paintH} width={paintW} height={paintH} />
      <circle cx={HOOP.x} cy={VIEW_H - paintH} r="180" />
      <path
        d={`M ${cornerX} ${VIEW_H - 3} L ${cornerX} ${HOOP.y} A ${THREE_R} ${THREE_R} 0 0 1 ${
          HOOP.x + THREE_R
        } ${HOOP.y} L ${HOOP.x + THREE_R} ${VIEW_H - 3}`}
      />
      <path d={`M ${HOOP.x - 125} ${HOOP.y + 70} L ${HOOP.x + 125} ${HOOP.y + 70}`} />
      <circle
        cx={HOOP.x}
        cy={HOOP.y}
        r={RESTRICTED_AREA_M * 100}
        stroke="var(--border-soft)"
        strokeDasharray="14 12"
      />
      <circle cx={HOOP.x} cy={HOOP.y + 23} r="34" stroke="var(--faint)" strokeWidth="7" />
    </g>
  );
}

/**
 * Mapa de tiro.
 *
 * Anotado y fallado se distinguen por forma (relleno frente a aro hueco) además
 * de por color, para que se lean también sin percibir el matiz.
 */
export default function ShotChart({ shots = [] }) {
  const [hovered, setHovered] = useState(null);

  // Los anotados se pintan al final para que queden por encima de los fallados.
  const ordered = [...shots].sort((a, b) => a.made - b.made);

  return (
    <div style={{ position: 'relative' }}>
      <div
        style={{
          background: 'var(--bg)',
          border: '1px solid var(--border-soft)',
          borderRadius: 6,
          padding: 10,
        }}
      >
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          style={{ width: '100%', height: 'auto', display: 'block' }}
          role="img"
          aria-label={`Mapa de ${shots.length} tiros sobre media pista`}
        >
          <rect x="0" y="0" width={VIEW_W} height={VIEW_H} fill="var(--bg)" />
          <CourtLines />
          {ordered.map((shot, index) => {
            const { cx, cy } = projectShot(shot);
            const isHovered = hovered?.index === index;
            return shot.made ? (
              <circle
                key={index}
                cx={cx}
                cy={cy}
                r={isHovered ? 24 : 18}
                fill="var(--accent)"
                stroke="var(--surface)"
                strokeWidth="4"
                onMouseEnter={() => setHovered({ index, shot, cx, cy })}
                onMouseLeave={() => setHovered(null)}
              />
            ) : (
              <circle
                key={index}
                cx={cx}
                cy={cy}
                r={isHovered ? 22 : 16}
                fill="none"
                stroke="var(--shot-miss)"
                strokeWidth="5"
                onMouseEnter={() => setHovered({ index, shot, cx, cy })}
                onMouseLeave={() => setHovered(null)}
              />
            );
          })}
        </svg>
      </div>

      {hovered && (
        <div
          style={{
            position: 'absolute',
            left: `${(hovered.cx / VIEW_W) * 100}%`,
            top: `${(hovered.cy / VIEW_H) * 100}%`,
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
          <strong style={{ color: hovered.shot.made ? 'var(--accent)' : 'var(--muted)', fontWeight: 600 }}>
            {hovered.shot.made ? 'Anotado' : 'Fallado'}
          </strong>
          {' · '}
          {ZONE_LABEL[hovered.shot.zone] ?? hovered.shot.zone}
          {' · '}
          {hovered.shot.dist?.toFixed(1)} m
        </div>
      )}
    </div>
  );
}

/** Leyenda del mapa: la forma acompaña al color. */
export function ShotLegend({ made, missed }) {
  return (
    <div className="row" style={{ gap: 18, fontSize: '0.8125rem', flexWrap: 'wrap' }}>
      <span className="row" style={{ gap: 7 }}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <circle cx="7" cy="7" r="6" fill="var(--accent)" />
        </svg>
        <span style={{ color: 'var(--ink)' }}>Anotado {made}</span>
      </span>
      <span className="row" style={{ gap: 7 }}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <circle cx="7" cy="7" r="5" fill="none" stroke="var(--shot-miss)" strokeWidth="2" />
        </svg>
        <span style={{ color: 'var(--muted)' }}>Fallado {missed}</span>
      </span>
    </div>
  );
}
