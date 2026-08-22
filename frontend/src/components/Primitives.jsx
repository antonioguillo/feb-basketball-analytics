import { useMemo } from 'react';
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

/**
 * Selector con aspecto de chip.
 *
 * Es un `<select>` real, no un adorno: se abre con el teclado, lo anuncian los
 * lectores de pantalla y su etiqueta va asociada aunque no se vea.
 */
export function Select({ label, value, options, onChange, disabled = false }) {
  return (
    <label className={`chip chip--select${disabled ? ' is-disabled' : ''}`}>
      <span className="sr-only">{label}</span>
      <select value={value ?? ''} onChange={(event) => onChange(event.target.value)}
              disabled={disabled} aria-label={label}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <ChevronDown />
    </label>
  );
}

export function Loading({ label = 'Cargando datos…' }) {
  return (
    <div style={{ textAlign: 'center', padding: 64, color: 'var(--muted)' }} role="status">
      {label}
    </div>
  );
}

const TODOS = '';

/**
 * Selector de qué se está mirando: competición, temporada y grupo.
 *
 * Las opciones salen del catálogo real (`/api/competitions`), así que solo se
 * ofrece lo que hay cargado: nada de listas escritas a mano que prometan
 * temporadas inexistentes. Compartido por todas las pantallas que filtran por
 * contexto (Ligas, Jugadores, Equipos).
 */
export function ContextPicker({ catalogo, contexto, onChange }) {
  const competiciones = useMemo(() => {
    const vistas = new Map();
    for (const entrada of catalogo) {
      if (!vistas.has(entrada.competitionKey)) {
        vistas.set(entrada.competitionKey, entrada.competition);
      }
    }
    return [...vistas].map(([value, label]) => ({ value, label }));
  }, [catalogo]);

  const temporadas = useMemo(
    () => catalogo
      .filter((entrada) => entrada.competitionKey === contexto.competition)
      .map((entrada) => ({ value: entrada.seasonKey, label: entrada.season })),
    [catalogo, contexto.competition],
  );

  const grupos = useMemo(() => {
    const entrada = catalogo.find((fila) => fila.competitionKey === contexto.competition
      && fila.seasonKey === contexto.season);
    const disponibles = entrada?.groups ?? [];
    return [{ value: TODOS, label: disponibles.length > 1 ? 'Todos los grupos' : 'Grupo único' },
            ...disponibles.map((grupo) => ({ value: grupo, label: `Grupo ${grupo}` }))];
  }, [catalogo, contexto.competition, contexto.season]);

  return (
    <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
      <Select
        label="Competición" value={contexto.competition} options={competiciones}
        onChange={(value) => {
          // Al cambiar de competición, la temporada y el grupo anteriores
          // pueden no existir en la nueva: se dejan que los resuelva la API.
          onChange({ competition: value, season: undefined, group: undefined });
        }}
      />
      <Select
        label="Temporada" value={contexto.season} options={temporadas}
        onChange={(value) => onChange({ ...contexto, season: value, group: undefined })}
      />
      <Select
        label="Grupo" value={contexto.group ?? TODOS} options={grupos}
        disabled={grupos.length <= 2}
        onChange={(value) => onChange({ ...contexto, group: value || undefined })}
      />
    </div>
  );
}

/** Paginador simple: anterior/siguiente sobre un listado con offset. */
export function Pager({ offset, total, size, onMove, noun = '' }) {
  const desde = total ? offset + 1 : 0;
  const hasta = Math.min(offset + size, total);
  return (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12, marginTop: 16 }}>
      <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
        {desde}-{hasta} de {total}{noun ? ` ${noun}` : ''}
      </span>
      <div className="row" style={{ gap: 8 }}>
        <button className="chip" disabled={offset === 0} onClick={() => onMove(offset - size)}>
          Anteriores
        </button>
        <button className="chip" disabled={hasta >= total} onClick={() => onMove(offset + size)}>
          Siguientes
        </button>
      </div>
    </div>
  );
}

/** Pestañas en píldora: el activo lleva fondo sólido, no solo un subrayado —
    se usa dentro de un Panel para cambiar de vista sin cambiar de pantalla. */
export function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: 'inline-flex', gap: 4, background: 'var(--surface-2)', borderRadius: 8, padding: 4, marginBottom: 18 }}>
      {tabs.map((item) => {
        const isActive = item.key === active;
        return (
          <button
            key={item.key}
            onClick={() => onChange(item.key)}
            style={{
              border: 'none', font: 'inherit', cursor: 'pointer', padding: '8px 18px', borderRadius: 6,
              fontSize: '0.875rem', background: isActive ? 'var(--accent)' : 'transparent',
              color: isActive ? 'var(--bg)' : 'var(--muted)', fontWeight: isActive ? 600 : 400,
            }}
          >
            {item.label}
          </button>
        );
      })}
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
