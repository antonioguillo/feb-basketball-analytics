import { useEffect, useMemo, useState } from 'react';
import { getTeams, getGames, getCompetitions } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { Panel, ContextPicker, Loading, ErrorState } from '../components/Primitives.jsx';
import { StandingsRow } from './Teams.jsx';
import { teamName } from '../lib/format.js';

/** Agrupa los partidos (ya ordenados por fecha desc) en jornadas: un grupo
    por fecha distinta. Sin número de jornada real en los datos —FEB no lo
    publica—, la posición dentro de esta lista hace de aproximación. */
export function agruparPorJornada(games) {
  const porFecha = new Map();
  for (const game of games) {
    if (!porFecha.has(game.date)) porFecha.set(game.date, []);
    porFecha.get(game.date).push(game);
  }
  return [...porFecha.entries()].map(([date, partidos]) => ({ date, partidos }));
}

export function GameRow({ game }) {
  const homeWon = game.homeScore > game.awayScore;
  const side = (name, score, won) => (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12 }}>
      <span style={{ color: won ? 'var(--ink)' : 'var(--muted)', fontSize: '0.875rem', fontWeight: won ? 600 : 400 }}>
        {teamName(name)}
      </span>
      <span className="num" style={{ color: won ? 'var(--ink)' : 'var(--muted)', fontWeight: won ? 600 : 400 }}>
        {score}
      </span>
    </div>
  );
  return (
    <div style={{ padding: '12px 0', borderBottom: '1px solid var(--border-soft)' }}>
      {side(game.home, game.homeScore, homeWon)}
      <div style={{ marginTop: 5 }}>{side(game.away, game.awayScore, !homeWon)}</div>
    </div>
  );
}

function JornadaNav({ indice, total, onMove }) {
  return (
    <div className="row" style={{ gap: 10 }}>
      <button
        aria-label="Jornada anterior"
        disabled={indice >= total - 1}
        onClick={() => onMove(indice + 1)}
        style={{
          width: 26, height: 26, borderRadius: 4, background: 'var(--surface-2)',
          border: '1px solid var(--border)', color: 'var(--muted)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          opacity: indice >= total - 1 ? 0.4 : 1, cursor: indice >= total - 1 ? 'not-allowed' : 'pointer',
        }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M15 6l-6 6 6 6" /></svg>
      </button>
      <span style={{ fontSize: '0.8125rem', color: 'var(--ink)', fontWeight: 500, whiteSpace: 'nowrap' }}>
        Jornada {total - indice} de {total}
      </span>
      <button
        aria-label="Jornada siguiente"
        disabled={indice <= 0}
        onClick={() => onMove(indice - 1)}
        style={{
          width: 26, height: 26, borderRadius: 4, background: 'var(--surface-2)',
          border: '1px solid var(--border)', color: 'var(--muted)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          opacity: indice <= 0 ? 0.4 : 1, cursor: indice <= 0 ? 'not-allowed' : 'pointer',
        }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M9 6l6 6-6 6" /></svg>
      </button>
    </div>
  );
}

export default function Ligas({ context = {}, onNavigate, onContextChange, onSource }) {
  const [indice, setIndice] = useState(0);

  const catalogo = useResource(() => getCompetitions(), []);
  const tabla = useResource(
    () => getTeams(context), [context.competition, context.season, context.group]);
  const partidos = useResource(
    () => getGames(context), [context.competition, context.season, context.group]);

  useEffect(() => { setIndice(0); }, [context.competition, context.season, context.group]);

  useEffect(() => {
    if (tabla.source) onSource?.(tabla.source);
  }, [tabla.source, onSource]);

  const jornadas = useMemo(
    () => (partidos.data ? agruparPorJornada(partidos.data.games) : []),
    [partidos.data],
  );

  if (tabla.status === 'loading') return <Loading />;
  if (tabla.status === 'error') {
    return <ErrorState detail={tabla.error?.message} onRetry={tabla.retry} />;
  }

  const { meta, standings } = tabla.data;
  // Igual que en el resto de pantallas: el contexto que se enseña es el que
  // la respuesta dice haber servido, no el que se pidió.
  const contexto = { competition: meta.competitionKey, season: meta.seasonKey,
                     group: meta.groupKey ?? undefined };
  const jornadaActual = jornadas[Math.min(indice, Math.max(jornadas.length - 1, 0))];

  return (
    <>
      <div
        className="row"
        style={{ justifyContent: 'space-between', alignItems: 'flex-end', gap: 24, flexWrap: 'wrap', marginBottom: 24 }}
      >
        <div>
          <h1 style={{ fontSize: '1.75rem', letterSpacing: '-0.01em', marginBottom: 6 }}>
            {meta.competition} · {meta.group}
          </h1>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--muted)' }}>
            Temporada {meta.season}
            {jornadas.length > 0 ? ` · Jornada ${jornadas.length - indice} de ${jornadas.length}` : ''}
          </p>
        </div>
        <ContextPicker catalogo={catalogo.data?.competitions ?? []} contexto={contexto} onChange={onContextChange} />
      </div>

      <div
        className="grid grid--split"
        style={{ gridTemplateColumns: 'minmax(0, 1.15fr) minmax(0, 1fr)', gap: 24, alignItems: 'start' }}
      >
        <Panel
          title="Clasificación"
          hint="Ordenada por victorias y, a igualdad, por diferencial de puntos — no son las reglas de desempate oficiales de la FEB."
        >
          {standings.length === 0 ? (
            <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
              No hay partidos jugados todavía en este grupo.
            </p>
          ) : (
            <div className="table--scroll-sm">
              <table className="table">
                <thead>
                  <tr>
                    <th className="is-left" style={{ width: 28 }}>#</th>
                    <th className="is-left">Equipo</th>
                    <th style={{ width: 38 }}>PJ</th>
                    <th style={{ width: 34 }}>G</th>
                    <th style={{ width: 34 }}>P</th>
                    <th style={{ width: 50 }}>PF</th>
                    <th style={{ width: 50 }}>PC</th>
                    <th className="is-left" style={{ paddingLeft: 20, width: 56 }}>DIF</th>
                  </tr>
                </thead>
                <tbody>
                  {standings.map((team) => (
                    <StandingsRow key={team.teamKey} team={team} onOpen={onNavigate} context={contexto} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel
          title="Resultados"
          action={jornadas.length > 0 && <JornadaNav indice={indice} total={jornadas.length} onMove={setIndice} />}
        >
          {partidos.status === 'loading' && <p style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>Cargando…</p>}
          {jornadaActual && (
            <>
              <p style={{ margin: '0 0 14px', fontSize: '0.75rem', color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {jornadaActual.date}
              </p>
              <div>
                {jornadaActual.partidos.map((game) => <GameRow key={game.gameId} game={game} />)}
              </div>
            </>
          )}
          {partidos.status === 'ready' && jornadas.length === 0 && (
            <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
              No hay resultados todavía en este grupo.
            </p>
          )}
        </Panel>
      </div>
    </>
  );
}
