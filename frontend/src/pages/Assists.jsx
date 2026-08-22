import { useEffect, useMemo } from 'react';
import { getAssistNetwork, getTeams, getCompetitions } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, Select, Loading, ErrorState } from '../components/Primitives.jsx';
import { ContextPicker } from './Dashboard.jsx';
import AssistNetwork from '../components/AssistNetwork.jsx';
import { integer, teamName } from '../lib/format.js';

const TODOS = '';
// Por encima de esto el círculo deja de leerse: se recorta a los pares con
// más asistencias, no a jugadores al azar.
const MAX_EDGES_LEAGUE = 24;
const MAX_EDGES_TEAM = 40;

function NodeRow({ node, context, onNavigate }) {
  return (
    <tr className="is-clickable" onClick={() => onNavigate(node.slug, context)}>
      <td className="is-left">
        <a
          href={href.player(node.slug, context)}
          style={{ color: 'var(--ink)', fontWeight: 500 }}
          onClick={(event) => event.stopPropagation()}
        >
          {node.name}
        </a>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>
          {teamName(node.team)}
        </div>
      </td>
      <td className="num" style={{ fontWeight: 600, color: 'var(--ink)' }}>{integer(node.assistsGiven)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(node.assistsReceived)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(node.pointsCreated)}</td>
    </tr>
  );
}

function EdgeRow({ edge }) {
  return (
    <tr>
      <td className="is-left">{edge.passer}</td>
      <td className="is-left" style={{ color: 'var(--muted)' }}>{edge.scorer}</td>
      <td className="num" style={{ fontWeight: 600, color: 'var(--ink)' }}>{integer(edge.assists)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(edge.points)}</td>
    </tr>
  );
}

export default function Assists({ context = {}, team, onNavigate, onContextChange, onTeamChange, onSource }) {
  const catalogo = useResource(() => getCompetitions(), []);
  const equipos = useResource(
    () => getTeams(context), [context.competition, context.season, context.group]);
  const red = useResource(
    () => getAssistNetwork({ ...context, team: team || undefined }),
    [context.competition, context.season, context.group, team],
  );

  useEffect(() => {
    if (red.source) onSource?.(red.source);
  }, [red.source, onSource]);

  const opcionesEquipo = useMemo(() => [
    { value: TODOS, label: 'Toda la competición' },
    ...(equipos.data?.standings ?? []).map((row) => ({ value: row.teamKey, label: teamName(row.team) })),
  ], [equipos.data]);

  if (red.status === 'loading') return <Loading />;
  if (red.status === 'error') {
    return <ErrorState detail={red.error?.message} onRetry={red.retry} />;
  }

  const { meta, nodes, edges } = red.data;
  const contexto = { competition: meta.competitionKey, season: meta.seasonKey,
                     group: meta.groupKey ?? undefined };

  const maxEdges = team ? MAX_EDGES_TEAM : MAX_EDGES_LEAGUE;
  const shownEdges = edges.slice(0, maxEdges);
  const involucrados = new Set(shownEdges.flatMap((edge) => [edge.passerSlug, edge.scorerSlug]));
  const shownNodes = nodes.filter((node) => involucrados.has(node.slug));

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
            Red de asistencias · Temporada {meta.season}
          </p>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <Select
            label="Equipo" value={team || TODOS} options={opcionesEquipo}
            onChange={(value) => onTeamChange(contexto, value || null)}
          />
          <ContextPicker catalogo={catalogo.data?.competitions ?? []} contexto={contexto} onChange={onContextChange} />
        </div>
      </div>

      {nodes.length === 0 ? (
        <Panel>
          <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
            No hay asistencias registradas con jugador y anotador resueltos en este filtro.
          </p>
        </Panel>
      ) : (
        <div
          className="grid grid--split"
          style={{ gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 24, alignItems: 'start' }}
        >
          <Panel
            title={team ? `Quién asiste a quién en ${teamName(nodes[0]?.team ?? '')}` : 'Pares con más asistencias'}
            hint={edges.length > shownEdges.length
              ? `Se muestran los ${shownEdges.length} pares con más asistencias de ${edges.length} · pasa el ratón por un nodo o una línea para el detalle`
              : 'Pasa el ratón por un nodo o una línea para el detalle'}
          >
            <AssistNetwork nodes={shownNodes} edges={shownEdges} />
          </Panel>

          <div className="stack" style={{ gap: 24 }}>
            <Panel title="Jugadores" hint="Ordenado por asistencias dadas">
              <div className="table--scroll-sm">
                <table className="table">
                  <thead>
                    <tr>
                      <th className="is-left">Jugador</th>
                      <th style={{ width: 54 }}>Dadas</th>
                      <th style={{ width: 62 }}>Recib.</th>
                      <th style={{ width: 54 }}>Pts.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {nodes.slice(0, 12).map((node) => (
                      <NodeRow key={node.slug} node={node} context={contexto} onNavigate={onNavigate} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Pares" hint="Pasador → anotador">
              <div className="table--scroll-sm">
                <table className="table">
                  <thead>
                    <tr>
                      <th className="is-left">Pasador</th>
                      <th className="is-left">Anotador</th>
                      <th style={{ width: 46 }}>Ast.</th>
                      <th style={{ width: 46 }}>Pts.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {edges.slice(0, 12).map((edge) => (
                      <EdgeRow key={`${edge.passerSlug}-${edge.scorerSlug}`} edge={edge} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
