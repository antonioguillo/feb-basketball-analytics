import { useEffect } from 'react';
import { getTeams, getCompetitions } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, Loading, ErrorState } from '../components/Primitives.jsx';
import { ContextPicker } from './Dashboard.jsx';
import { integer, signed, teamName } from '../lib/format.js';

export function StandingsRow({ team, onOpen, context }) {
  return (
    // Mismo patrón que LeaderRow: el clic en la fila es comodidad de ratón, el
    // enlace del nombre es lo que hace la navegación accesible.
    <tr className="is-clickable" onClick={() => onOpen(team.teamKey, context)}>
      <td className="is-left" style={{ color: 'var(--muted)', width: 34 }}>{team.rank}</td>
      <td className="is-left">
        <a
          href={href.team(team.teamKey, context)}
          style={{ color: 'var(--ink)', fontWeight: 500 }}
          onClick={(event) => event.stopPropagation()}
        >
          {teamName(team.team)}
        </a>
      </td>
      <td style={{ color: 'var(--muted)' }}>{team.games}</td>
      <td>{team.wins}</td>
      <td style={{ color: 'var(--muted)' }}>{team.losses}</td>
      <td>{integer(team.pointsFor)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(team.pointsAgainst)}</td>
      <td
        className="is-left"
        style={{ paddingLeft: 20, color: team.diff >= 0 ? 'var(--ink)' : 'var(--muted)', fontWeight: 500 }}
      >
        {signed(team.diff, 0)}
      </td>
    </tr>
  );
}

export default function Teams({ context = {}, onNavigate, onContextChange, onSource }) {
  const catalogo = useResource(() => getCompetitions(), []);
  const tabla = useResource(
    () => getTeams(context), [context.competition, context.season, context.group]);

  useEffect(() => {
    if (tabla.source) onSource?.(tabla.source);
  }, [tabla.source, onSource]);

  if (tabla.status === 'loading') return <Loading />;
  if (tabla.status === 'error') {
    return <ErrorState detail={tabla.error?.message} onRetry={tabla.retry} />;
  }

  const { meta, standings } = tabla.data;
  // Igual que en el dashboard: el contexto que se enseña es el que la
  // respuesta dice haber servido, no el que se pidió.
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
            Clasificación · Temporada {meta.season}
          </p>
        </div>
        <ContextPicker catalogo={catalogo.data?.competitions ?? []} contexto={contexto} onChange={onContextChange} />
      </div>

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
                  <th className="is-left" style={{ width: 34 }}>#</th>
                  <th className="is-left">Equipo</th>
                  <th style={{ width: 50 }}>PJ</th>
                  <th style={{ width: 46 }}>G</th>
                  <th style={{ width: 46 }}>P</th>
                  <th style={{ width: 60 }}>PF</th>
                  <th style={{ width: 60 }}>PC</th>
                  <th className="is-left" style={{ paddingLeft: 20, width: 70 }}>DIF</th>
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
    </>
  );
}
