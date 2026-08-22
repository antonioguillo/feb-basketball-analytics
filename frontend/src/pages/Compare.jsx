import { useState, useEffect } from 'react';
import { getDashboard, getPlayer } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { useNavigate, href } from '../lib/router.js';
import { Panel, Loading, ErrorState } from '../components/Primitives.jsx';
import RadarChart, { RadarLegend, MAX_RADAR_PLAYERS } from '../components/RadarChart.jsx';
import { decimal, percent, signed, teamName } from '../lib/format.js';

export const MAX_COMPARE = 4;
// Mismo tope que LEADERS_MAX en api.py: se pide de una vez el pozo completo de
// jugadores elegibles de la competición para poder buscar por nombre en el
// cliente, sin un endpoint de búsqueda nuevo.
const POOL_LIMIT = 500;

const PER_GAME_ROWS = [
  { key: 'min', label: 'Minutos', format: decimal, best: false },
  { key: 'pts', label: 'Puntos', format: decimal, best: true },
  { key: 'reb', label: 'Rebotes', format: decimal, best: true },
  { key: 'ast', label: 'Asistencias', format: decimal, best: true },
  { key: 'stl', label: 'Robos', format: decimal, best: true },
  { key: 'blk', label: 'Tapones', format: decimal, best: true },
  { key: 'to', label: 'Pérdidas', format: decimal, best: false },
  { key: 'val', label: 'Valoración', format: decimal, best: true },
  { key: 'plusMinus', label: 'Plus / minus', format: signed, best: true },
];

const SHOOTING_ROWS = [
  { key: 't2', label: 'Tiros de 2', format: percent, best: true },
  { key: 't3', label: 'Triples', format: percent, best: true },
  { key: 'ft', label: 'Tiros libres', format: percent, best: true },
  { key: 'efg', label: 'eFG%', format: percent, best: true },
  { key: 'ts', label: 'TS%', format: percent, best: true },
];

const PER36_ROWS = [
  { key: 'pts', label: 'Puntos', format: decimal, best: true },
  { key: 'reb', label: 'Rebotes', format: decimal, best: true },
  { key: 'ast', label: 'Asistencias', format: decimal, best: true },
];

/** Sin tildes ni mayúsculas, para que "ibanez" encuentre a "Ibáñez". */
function normalize(text) {
  return (text ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

/** Candidatos del pozo de líderes que casan con el texto buscado. */
export function filterCandidates(pool, query, excludeSlugs = [], limit = 8) {
  const needle = normalize(query).trim();
  if (needle.length < 2) return [];
  return pool
    .filter((player) => !excludeSlugs.includes(player.slug))
    .filter((player) => normalize(player.name).includes(needle) || normalize(player.team).includes(needle))
    .slice(0, limit);
}

function statRow(label, players, group, key, format, best, showBest) {
  const values = players.map((player) => player[group][key]);
  const numeric = values.filter((value) => value !== null && value !== undefined && !Number.isNaN(value));
  const max = best && numeric.length ? Math.max(...numeric) : null;

  return (
    <tr key={`${group}-${key}`}>
      <td className="is-left" style={{ color: 'var(--muted)' }}>{label}</td>
      {values.map((value, index) => {
        const isBest = showBest && max !== null && value === max;
        return (
          <td
            key={players[index].slug}
            style={{ color: isBest ? 'var(--accent)' : 'var(--ink)', fontWeight: isBest ? 600 : 400 }}
          >
            {format(value)}
          </td>
        );
      })}
    </tr>
  );
}

export function CompareTable({ players, context, onRemove }) {
  // Con un solo jugador no hay nada que comparar: resaltar su única columna
  // como "mejor" en todo no aporta nada y despista.
  const showBest = players.length > 1;

  return (
    <Panel title="Comparativa">
      <div className="table--scroll">
        <table className="table table--compare">
          <thead>
            <tr>
              <th className="is-left">&nbsp;</th>
              {players.map((player) => (
                <th key={player.slug} style={{ textAlign: 'center', minWidth: 140 }}>
                  <div className="stack" style={{ alignItems: 'center', gap: 6 }}>
                    <button
                      type="button"
                      className="chip"
                      style={{ padding: '2px 8px', fontSize: '0.6875rem', fontWeight: 400 }}
                      onClick={() => onRemove(player.slug)}
                      aria-label={`Quitar a ${player.name} de la comparativa`}
                    >
                      Quitar ✕
                    </button>
                    <a href={href.player(player.slug, context)} style={{ color: 'var(--ink)', fontWeight: 600 }}>
                      {player.name}
                    </a>
                    <span style={{
                      fontSize: '0.75rem', color: 'var(--muted)', fontWeight: 400,
                      textTransform: 'none', letterSpacing: 0,
                    }}
                    >
                      {teamName(player.team)} · {player.games} PJ
                    </span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="is-section">
              <td colSpan={players.length + 1}>Medias por partido</td>
            </tr>
            {PER_GAME_ROWS.map((row) =>
              statRow(row.label, players, 'perGame', row.key, row.format, row.best, showBest))}

            <tr className="is-section">
              <td colSpan={players.length + 1}>Tiro</td>
            </tr>
            {SHOOTING_ROWS.map((row) =>
              statRow(row.label, players, 'shooting', row.key, row.format, row.best, showBest))}

            <tr className="is-section">
              <td colSpan={players.length + 1}>Por 36 minutos</td>
            </tr>
            {PER36_ROWS.map((row) =>
              statRow(row.label, players, 'per36', row.key, row.format, row.best, showBest))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function SearchBox({ query, onQueryChange, candidates, disabled, onPick }) {
  const showList = !disabled && query.trim().length >= 2;

  return (
    <div className="combo" style={{ maxWidth: 360 }}>
      <label className="chip" style={{ width: '100%', cursor: disabled ? 'not-allowed' : 'text' }}>
        <span className="sr-only">Buscar jugador por nombre</span>
        <input
          type="text"
          value={query}
          disabled={disabled}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={disabled ? `Máximo ${MAX_COMPARE} jugadores` : 'Buscar jugador por nombre…'}
          style={{
            background: 'none', border: 'none', outline: 'none', color: 'inherit',
            font: 'inherit', width: '100%',
          }}
        />
      </label>
      {showList && (
        <div className="combo__list" role="listbox">
          {candidates.length === 0 ? (
            <div className="combo__empty">Sin resultados</div>
          ) : (
            candidates.map((player) => (
              <button
                key={player.slug}
                type="button"
                className="combo__option"
                onClick={() => onPick(player.slug)}
              >
                <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{player.name}</span>
                <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>
                  {teamName(player.team)} · {decimal(player.perGame.val)} val
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function ComparePage({ slugs, context = {}, onSource }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  // El pozo de búsqueda comparte umbral con "Líderes por valoración": solo se
  // puede comparar entre quienes juegan minutos de rotación de verdad.
  const pool = useResource(
    () => getDashboard({ ...context, limit: POOL_LIMIT }),
    [context.competition, context.season, context.group],
  );

  const playersRes = useResource(
    () => (slugs.length === 0
      ? Promise.resolve({ data: [], source: 'api' })
      : Promise.all(slugs.map((slug) => getPlayer(slug, context))).then((results) => ({
        data: results.map((result) => result.data),
        source: results.some((result) => result.source === 'fixtures') ? 'fixtures' : 'api',
      }))),
    [slugs.join('|'), context.competition, context.season, context.group],
  );

  useEffect(() => {
    if (playersRes.source) onSource?.(playersRes.source);
  }, [playersRes.source, onSource]);

  const addPlayer = (slug) => {
    if (slugs.includes(slug) || slugs.length >= MAX_COMPARE) return;
    setQuery('');
    navigate(href.compare([...slugs, slug], context).slice(1));
  };
  const removePlayer = (slug) => {
    navigate(href.compare(slugs.filter((s) => s !== slug), context).slice(1));
  };

  const candidates = pool.status === 'ready'
    ? filterCandidates(pool.data.leaders, query, slugs)
    : [];

  return (
    <>
      <div className="row" style={{ gap: 8, fontSize: '0.8125rem', marginBottom: 20 }}>
        <a href={href.ligas(context)} style={{ color: 'var(--muted)' }}>Ligas</a>
        <span style={{ color: 'var(--faint)' }}>/</span>
        <span style={{ color: 'var(--ink)' }}>Comparador</span>
      </div>

      <div className="panel" style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '1.75rem', letterSpacing: '-0.01em', marginBottom: 6 }}>
          Comparador de jugadores
        </h1>
        <p style={{ margin: '0 0 18px', fontSize: '0.875rem', color: 'var(--muted)' }}>
          {pool.status === 'ready' && `${pool.data.meta.competition} · ${pool.data.meta.season} · `}
          Busca hasta {MAX_COMPARE} jugadores entre quienes cumplen el mínimo de 6 partidos y 15 minutos.
        </p>
        <SearchBox
          query={query}
          onQueryChange={setQuery}
          candidates={candidates}
          disabled={slugs.length >= MAX_COMPARE}
          onPick={addPlayer}
        />
        {slugs.length >= MAX_COMPARE && (
          <p style={{ marginTop: 10, fontSize: '0.75rem', color: 'var(--muted)' }}>
            Máximo {MAX_COMPARE} jugadores. Quita uno para añadir otro.
          </p>
        )}
        {pool.status === 'error' && (
          <p style={{ marginTop: 10, fontSize: '0.75rem', color: 'var(--muted)' }}>
            No se pudo cargar la lista de jugadores para buscar. {pool.error?.message}
          </p>
        )}
      </div>

      {slugs.length === 0 && (
        <p style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>
          Añade jugadores con el buscador de arriba para empezar a comparar.
        </p>
      )}
      {slugs.length > 0 && playersRes.status === 'loading' && <Loading label="Cargando jugadores…" />}
      {slugs.length > 0 && playersRes.status === 'error' && (
        <ErrorState detail={playersRes.error?.message} onRetry={playersRes.retry} />
      )}
      {slugs.length > 0 && playersRes.status === 'ready' && playersRes.data.length > 0 && (
        <>
          {pool.status === 'ready' && (
            <Panel
              title="Perfil por percentil"
              hint={`Percentil sobre los ${pool.data.leaders.length} jugadores de ${pool.data.meta.competition} `
                + `· ${pool.data.meta.season} que cumplen el mínimo de 6 partidos y 15 minutos. `
                + '100 = el mejor del grupo en esa estadística.'}
              style={{ marginBottom: 24 }}
            >
              <div style={{ marginBottom: 16 }}>
                <RadarLegend players={playersRes.data} />
              </div>
              {playersRes.data.length > MAX_RADAR_PLAYERS && (
                <p style={{ margin: '0 0 16px', fontSize: '0.75rem', color: 'var(--muted)' }}>
                  El radar compara a los {MAX_RADAR_PLAYERS} primeros; la tabla de abajo incluye a los {playersRes.data.length}.
                </p>
              )}
              <div style={{ maxWidth: 520, margin: '0 auto' }}>
                <RadarChart players={playersRes.data} pool={pool.data.leaders} />
              </div>
            </Panel>
          )}
          <CompareTable players={playersRes.data} context={context} onRemove={removePlayer} />
        </>
      )}
    </>
  );
}
