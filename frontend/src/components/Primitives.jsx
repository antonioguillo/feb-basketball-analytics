import { barWidth } from '../lib/format.js';
import { ChevronDown, AlertIcon } from './Icons.jsx';

/** Bloque de contenido con título opcional. */
export function Panel({ title, hint, action, children, style }) {
  return (
    <section className="panel" style={style}>
      {(title || action) && (
        <div className="panel__head">
          {title && <h2 className="panel__title">{title}</h2>}
          {action}
        </div>
      )}
      {hint && <p className="panel__hint">{hint}</p>}
      {children}
    </section>
  );
}

/**
 * Cifra destacada. `emphasis` la pinta en el color de acento; se reserva para
 * el dato principal de la pantalla, no para todos.
 */
export function StatTile({ label, value, note, emphasis = false, size = 'md' }) {
  return (
    <div className="panel" style={{ padding: size === 'sm' ? '16px 18px' : '18px 20px' }}>
      <div className="eyebrow" style={{ marginBottom: size === 'sm' ? 8 : 10 }}>
        {label}
      </div>
      <div
        className="num"
        style={{
          fontSize: size === 'sm' ? '2rem' : '2.25rem',
          fontWeight: 600,
          lineHeight: 1,
          color: emphasis ? 'var(--accent)' : 'var(--ink)',
        }}
      >
        {value}
      </div>
      {note && (
        <div style={{ fontSize: size === 'sm' ? '0.75rem' : '0.8125rem', color: 'var(--muted)', marginTop: 6 }}>
          {note}
        </div>
      )}
    </div>
  );
}

/** Barra de magnitud con su valor a la derecha. */
export function Meter({ value, max, display, width = 34 }) {
  return (
    <div className="row" style={{ gap: 10 }}>
      <div className="meter">
        <div className="meter__fill" style={{ width: `${barWidth(value, max)}%` }} />
      </div>
      <span
        className="num"
        style={{ color: 'var(--ink)', fontWeight: 600, width, textAlign: 'right', flexShrink: 0 }}
      >
        {display}
      </span>
    </div>
  );
}

/** Barra a ancho completo, con etiqueta y valor encima (acierto por zona). */
export function LabelledBar({ label, value, display, detail }) {
  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
        <span style={{ color: 'var(--ink)', fontSize: '0.875rem', fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          <span className="num" style={{ color: 'var(--ink)', fontWeight: 600, fontSize: '1rem' }}>
            {display}
          </span>
          {detail && <> · {detail}</>}
        </span>
      </div>
      <div className="meter" style={{ height: 10, borderRadius: '0 5px 5px 0' }}>
        <div className="meter__fill" style={{ width: `${barWidth(value, 1)}%`, borderRadius: '0 5px 5px 0' }} />
      </div>
    </div>
  );
}

/** Selector de filtro. Sin lógica todavía: refleja el estado actual del conjunto. */
export function FilterChip({ children }) {
  return (
    <span className="chip">
      {children}
      <ChevronDown />
    </span>
  );
}

export function Loading({ label = 'Cargando datos…' }) {
  return (
    <div style={{ textAlign: 'center', padding: 64, color: 'var(--muted)' }} role="status">
      {label}
    </div>
  );
}

export function ErrorState({ title = 'No se pudieron cargar los datos', detail, onRetry }) {
  return (
    <div className="panel" style={{ textAlign: 'center', padding: 48 }} role="alert">
      <div style={{ color: 'var(--accent)', display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
        <AlertIcon size={26} />
      </div>
      <h2 style={{ fontSize: '1.125rem', marginBottom: 8 }}>{title}</h2>
      {detail && <p style={{ margin: '0 0 20px', fontSize: '0.875rem', color: 'var(--muted)' }}>{detail}</p>}
      {onRetry && (
        <button className="chip chip--primary" onClick={onRetry}>
          Reintentar
        </button>
      )}
    </div>
  );
}
