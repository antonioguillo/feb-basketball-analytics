import { useEffect } from 'react';
import { getDashboard } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, StatTile, Meter, FilterChip, Loading, ErrorState } from '../components/Primitives.jsx';
import { decimal, integer, teamName } from '../lib/format.js';

const LEADERS_SHOWN = 7;

function PageHead({ meta }) {
  return (
    <div
      className="row"
      style={{ justifyContent: 'space-between', alignItems: 'flex-end', gap: 24, flexWrap: 'wrap', marginBottom: 24 }}
    >
      <div>
        <h1 style={{ fontSize: '1.75rem', letterSpacing: '-0.01em', marginBottom: 6 }}>
          {meta.competition} · Grupo {meta.groupKey}
        </h1>
        <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--muted)' }}>
          Temporada {meta.season} · jornadas 1-{meta.journeys} procesadas
        </p>
      </div>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <FilterChip>{meta.competition}</FilterChip>
        <FilterChip>{meta.season}</FilterChip>
        <FilterChip>{meta.group}</FilterChip>
      </div>
    </div>
  );
}

function LeaderRow({ player, max, onOpen }) {
  return (
    <tr className="is-clickable" onClick={() => onOpen(player.slug)}>
      <td className="is-left">
        <a
          href={href.player(player.slug)}
          style={{ color: 'var(--ink)', fontWeight: 500 }}
          onClick={(event) => event.stopPropagation()}
        >
          {player.name}
        </a>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>{teamName(player.team)}</div>
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

function ResultRow({ game, last }) {
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

export default function Dashboard({ onNavigate, onSource }) {
  const { status, data, source, error, retry } = useResource(() => getDashboard(), []);

  // Avisar del origen de los datos es un efecto, no algo que hacer al pintar.
  useEffect(() => {
    if (source) onSource?.(source);
  }, [source, onSource]);

  if (status === 'loading') return <Loading />;
  if (status === 'error') {
    return <ErrorState detail={error?.message} onRetry={retry} />;
  }

  const { meta, summary, leaders, recentGames } = data;
  const shown = leaders.slice(0, LEADERS_SHOWN);
  const maxVal = shown.length ? shown[0].perGame.val : 1;

  return (
    <>
      <PageHead meta={meta} />

      <div className="grid grid--kpi-4" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', marginBottom: 24 }}>
        <StatTile label="Partidos" value={integer(summary.games)} note={`de ${meta.groupTotalGames} en el grupo`} />
        <StatTile label="Equipos" value={integer(summary.teams)} note="liga regular completa" />
        <StatTile label="Jugadores" value={integer(summary.players)} note="con minutos registrados" />
        <StatTile label="Tiros localizados" value={integer(summary.shots)} note="con coordenadas x/y" />
      </div>

      <div
        className="grid grid--split"
        style={{ gridTemplateColumns: 'minmax(0, 1.85fr) minmax(0, 1fr)', gap: 24 }}
      >
        <Panel
          title="Líderes por valoración"
          hint={`Valoración media por partido · mínimo 6 partidos y 15 minutos`}
          action={
            <span style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
              {leaders.length} jugadores elegibles
            </span>
          }
        >
          <div className="table--scroll-sm">
            <table className="table">
              <thead>
                <tr>
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
                {shown.map((player) => (
                  <LeaderRow key={player.slug} player={player} max={maxVal} onOpen={onNavigate} />
                ))}
              </tbody>
            </table>
          </div>
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
