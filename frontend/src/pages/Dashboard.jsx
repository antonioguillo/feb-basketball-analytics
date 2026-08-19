import { useEffect, useMemo, useState } from 'react';
import { getDashboard, getCompetitions } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, StatTile, Meter, Select, Loading, ErrorState } from '../components/Primitives.jsx';
import { decimal, integer, teamName } from '../lib/format.js';

const PAGE_SIZE = 10;
const TODOS = '';

/**
 * Selector de qué se está mirando.
 *
 * Las opciones salen del catálogo real (`/api/competitions`), así que solo se
 * ofrece lo que hay cargado: nada de listas escritas a mano que prometan
 * temporadas inexistentes.
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

export function PageHead({ meta, catalogo, contexto, onChange }) {
  return (
    <div
      className="row"
      style={{ justifyContent: 'space-between', alignItems: 'flex-end', gap: 24, flexWrap: 'wrap', marginBottom: 24 }}
    >
      <div>
        <h1 style={{ fontSize: '1.75rem', letterSpacing: '-0.01em', marginBottom: 6 }}>
          {meta.competition} · {meta.group}
        </h1>
        <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--muted)' }}>
          Temporada {meta.season} · {meta.matchDays} fechas con partidos
        </p>
      </div>
      <ContextPicker catalogo={catalogo} contexto={contexto} onChange={onChange} />
    </div>
  );
}

export function LeaderRow({ player, max, rank, onOpen, context }) {
  return (
    // El clic en la fila es una comodidad para el ratón; el enlace del nombre
    // es lo que hace la navegación accesible por teclado y para un lector de
    // pantalla, así que la fila no lleva rol ni tabIndex propios.
    <tr className="is-clickable" onClick={() => onOpen(player.slug, context)}>
      <td className="is-left" style={{ color: 'var(--muted)', width: 34 }}>{rank}</td>
      <td className="is-left">
        <a
          href={href.player(player.slug, context)}
          style={{ color: 'var(--ink)', fontWeight: 500 }}
          onClick={(event) => event.stopPropagation()}
        >
          {player.name}
        </a>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
          {teamName(player.team)}
          {player.group ? ` · ${player.group}` : ''}
        </div>
      </td>
      <td style={{ color: 'var(--muted)' }}>{player.games}</td>
      <td>{decimal(player.perGame.min)}</td>
      <td>{decimal(player.perGame.pts)}</td>
      <td>{decimal(player.perGame.reb)}</td>
      <td>{decimal(player.perGame.ast)}</td>
      <td className="is-left" style={{ paddingLeft: 20 }}>
        <Meter value={player.perGame.val} max={max} display={decimal(player.perGame.val)} />
      </td>
    </tr>
  );
}

export function Pager({ offset, total, size, onMove }) {
  const desde = total ? offset + 1 : 0;
  const hasta = Math.min(offset + size, total);
  return (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12, marginTop: 16 }}>
      <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
        {desde}-{hasta} de {total} jugadores elegibles
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

/**
 * Un grupo recién cargado puede no tener a nadie con partidos suficientes.
 * No es un error: conviene decir por qué la tabla está vacía en vez de
 * dejarla en blanco.
 */
export function EmptyLeaders({ total }) {
  return (
    <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
      {total === 0
        ? 'Ningún jugador llega todavía al mínimo de 6 partidos y 15 minutos. '
          + 'Descarga más jornadas de esta competición para que aparezca el ranking.'
        : 'No hay jugadores en esta página del ranking.'}
    </p>
  );
}

export function ResultRow({ game, last }) {
  const homeWon = game.homeScore > game.awayScore;
  const side = (name, score, won) => (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12, marginTop: 5 }}>
      <span style={{ color: won ? 'var(--ink)' : 'var(--muted)', fontSize: '0.875rem', fontWeight: won ? 500 : 400 }}>
        {teamName(name)}
      </span>
      <span className="num" style={{ color: won ? 'var(--ink)' : 'var(--muted)', fontWeight: won ? 600 : 400 }}>
        {score}
      </span>
    </div>
  );

  return (
    <div style={{ padding: '12px 0', borderBottom: last ? 'none' : '1px solid var(--border-soft)' }}>
      <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{game.date}</div>
      {side(game.home, game.homeScore, homeWon)}
      {side(game.away, game.awayScore, !homeWon)}
    </div>
  );
}

export default function Dashboard({ context = {}, onNavigate, onContextChange, onSource }) {
  const [offset, setOffset] = useState(0);

  const catalogo = useResource(() => getCompetitions(), []);
  const tablero = useResource(
    () => getDashboard({ ...context, limit: PAGE_SIZE, offset }),
    [context.competition, context.season, context.group, offset],
  );

  // Cambiar de competición, temporada o grupo empieza el listado de cero.
  useEffect(() => { setOffset(0); },
    [context.competition, context.season, context.group]);

  useEffect(() => {
    if (tablero.source) onSource?.(tablero.source);
  }, [tablero.source, onSource]);

  if (tablero.status === 'loading') return <Loading />;
  if (tablero.status === 'error') {
    return <ErrorState detail={tablero.error?.message} onRetry={tablero.retry} />;
  }

  const { meta, summary, leaders, recentGames } = tablero.data;
  const total = tablero.data.leadersTotal ?? leaders.length;
  // El contexto que se enseña es el que la respuesta dice haber servido, no el
  // que se pidió: si no se pidió ninguno, la API elige y aquí se refleja.
  const contexto = { competition: meta.competitionKey, season: meta.seasonKey,
                     group: meta.groupKey ?? undefined };
  const maxVal = leaders.length ? leaders[0].perGame.val : 1;

  return (
    <>
      <PageHead
        meta={meta}
        catalogo={catalogo.data?.competitions ?? []}
        contexto={contexto}
        onChange={onContextChange}
      />

      <div className="grid grid--kpi-4" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', marginBottom: 24 }}>
        <StatTile label="Partidos" value={integer(summary.games)} note={`en ${meta.matchDays} fechas`} />
        <StatTile label="Equipos" value={integer(summary.teams)} note={meta.group} />
        <StatTile label="Jugadores" value={integer(summary.players)} note="con minutos registrados" />
        <StatTile label="Tiros localizados" value={integer(summary.shots)} note="con coordenadas x/y" />
      </div>

      <div
        className="grid grid--split"
        style={{ gridTemplateColumns: 'minmax(0, 1.85fr) minmax(0, 1fr)', gap: 24 }}
      >
        <Panel
          title="Líderes por valoración"
          hint="Valoración media por partido · mínimo 6 partidos y 15 minutos"
        >
          {leaders.length === 0 ? (
            <EmptyLeaders total={total} />
          ) : (
          <div className="table--scroll-sm">
            <table className="table">
              <thead>
                <tr>
                  <th className="is-left" style={{ width: 34 }}>#</th>
                  <th className="is-left">Jugador</th>
                  <th style={{ width: 46 }}>PJ</th>
                  <th style={{ width: 54 }}>MIN</th>
                  <th style={{ width: 54 }}>PTS</th>
                  <th style={{ width: 50 }}>REB</th>
                  <th style={{ width: 50 }}>AST</th>
                  <th className="is-left" style={{ paddingLeft: 20, width: 190 }}>
                    Valoración
                  </th>
                </tr>
              </thead>
              <tbody>
                {leaders.map((player, index) => (
                  <LeaderRow
                    key={player.slug}
                    player={player}
                    rank={offset + index + 1}
                    max={maxVal}
                    onOpen={onNavigate}
                    context={contexto}
                  />
                ))}
              </tbody>
            </table>
          </div>
          )}
          {total > 0 && (
            <Pager offset={offset} total={total} size={PAGE_SIZE} onMove={setOffset} />
          )}
        </Panel>

        <Panel title="Últimos resultados">
          <div className="stack" style={{ marginTop: 16 }}>
            {recentGames.map((game, index) => (
              <ResultRow key={game.gameId} game={game} last={index === recentGames.length - 1} />
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}
