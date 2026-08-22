import { useEffect, useState } from 'react';
import { getFouls, getCompetitions } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, Loading, ErrorState } from '../components/Primitives.jsx';
import { ContextPicker, Pager } from './Dashboard.jsx';
import { decimal, integer, teamName } from '../lib/format.js';

const PAGE_SIZE = 15;

export function FoulRow({ player, rank, onNavigate, context }) {
  return (
    <tr className="is-clickable" onClick={() => onNavigate(player.slug, context)}>
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
        </div>
      </td>
      <td style={{ color: 'var(--muted)' }}>{player.games}</td>
      <td className="num" style={{ fontWeight: 600, color: 'var(--ink)' }}>{integer(player.totalFouls)}</td>
      <td>{decimal(player.foulsPerGame, 2)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(player.personalFouls)}</td>
      <td style={{ color: player.technicalFouls ? 'var(--accent)' : 'var(--muted)' }}>
        {integer(player.technicalFouls)}
      </td>
      <td style={{ color: player.disqualifyingFouls ? 'var(--accent)' : 'var(--muted)' }}>
        {integer(player.disqualifyingFouls)}
      </td>
      <td style={{ color: player.fouledOutGames ? 'var(--ink)' : 'var(--muted)', fontWeight: player.fouledOutGames ? 500 : 400 }}>
        {integer(player.fouledOutGames)}
      </td>
    </tr>
  );
}

function TeamFoulRow({ team, context }) {
  return (
    <tr>
      <td className="is-left">
        <a href={href.team(team.teamKey, context)} style={{ color: 'var(--ink)', fontWeight: 500 }}>
          {teamName(team.team)}
        </a>
      </td>
      <td style={{ color: 'var(--muted)' }}>{team.games}</td>
      <td className="num" style={{ fontWeight: 600, color: 'var(--ink)' }}>{decimal(team.foulsPerGame, 2)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(team.totalFouls)}</td>
      <td style={{ color: team.technicalFouls ? 'var(--accent)' : 'var(--muted)' }}>
        {integer(team.technicalFouls)}
      </td>
      <td style={{ color: team.disqualifyingFouls ? 'var(--accent)' : 'var(--muted)' }}>
        {integer(team.disqualifyingFouls)}
      </td>
    </tr>
  );
}

export default function Fouls({ context = {}, onNavigate, onContextChange, onSource }) {
  const [offset, setOffset] = useState(0);

  const catalogo = useResource(() => getCompetitions(), []);
  const tabla = useResource(
    () => getFouls({ ...context, limit: PAGE_SIZE, offset }),
    [context.competition, context.season, context.group, offset],
  );

  useEffect(() => { setOffset(0); }, [context.competition, context.season, context.group]);

  useEffect(() => {
    if (tabla.source) onSource?.(tabla.source);
  }, [tabla.source, onSource]);

  if (tabla.status === 'loading') return <Loading />;
  if (tabla.status === 'error') {
    return <ErrorState detail={tabla.error?.message} onRetry={tabla.retry} />;
  }

  const { meta, players, playersTotal, teams, foulOutThreshold } = tabla.data;
  const contexto = { competition: meta.competitionKey, season: meta.seasonKey,
                     group: meta.groupKey ?? undefined };

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
            Disciplina de faltas · Temporada {meta.season}
          </p>
        </div>
        <ContextPicker catalogo={catalogo.data?.competitions ?? []} contexto={contexto} onChange={onContextChange} />
      </div>

      <div
        className="grid grid--split"
        style={{ gridTemplateColumns: 'minmax(0, 1.85fr) minmax(0, 1fr)', gap: 24 }}
      >
        <Panel
          title="Jugadores"
          hint={`Ordenado por faltas totales · mínimo 3 partidos jugados · elimina a las `
            + `${foulOutThreshold} personales en un mismo partido`}
        >
          {players.length === 0 ? (
            <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
              Nadie llega todavía al mínimo de partidos.
            </p>
          ) : (
            <div className="table--scroll-sm">
              <table className="table">
                <thead>
                  <tr>
                    <th className="is-left" style={{ width: 34 }}>#</th>
                    <th className="is-left">Jugador</th>
                    <th style={{ width: 46 }}>PJ</th>
                    <th style={{ width: 54 }}>TOT</th>
                    <th style={{ width: 54 }}>F/PJ</th>
                    <th style={{ width: 50 }}>Pers.</th>
                    <th style={{ width: 50 }}>Téc.</th>
                    <th style={{ width: 50 }}>Desc.</th>
                    <th style={{ width: 54 }}>Elim.</th>
                  </tr>
                </thead>
                <tbody>
                  {players.map((player, index) => (
                    <FoulRow
                      key={player.slug}
                      player={player}
                      rank={offset + index + 1}
                      onNavigate={onNavigate}
                      context={contexto}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {playersTotal > 0 && (
            <Pager offset={offset} total={playersTotal} size={PAGE_SIZE} onMove={setOffset} />
          )}
        </Panel>

        <Panel title="Por equipo" hint="Ordenado por faltas por partido">
          <div className="table--scroll-sm">
            <table className="table">
              <thead>
                <tr>
                  <th className="is-left">Equipo</th>
                  <th style={{ width: 42 }}>PJ</th>
                  <th style={{ width: 54 }}>F/PJ</th>
                  <th style={{ width: 46 }}>TOT</th>
                  <th style={{ width: 46 }}>Téc.</th>
                  <th style={{ width: 46 }}>Desc.</th>
                </tr>
              </thead>
              <tbody>
                {teams.map((team) => (
                  <TeamFoulRow key={team.teamKey} team={team} context={contexto} />
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  );
}
