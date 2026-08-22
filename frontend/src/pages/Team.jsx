import { useEffect, useState } from 'react';
import { getTeam, getAssistNetwork } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href, useNavigate } from '../lib/router.js';
import { Panel, StatTile, Meter, Tabs, Loading, ErrorState } from '../components/Primitives.jsx';
import ShotChart, { ShotLegend } from '../components/ShotChart.jsx';
import AssistNetwork from '../components/AssistNetwork.jsx';
import { decimal, percent, signed, integer, teamName } from '../lib/format.js';

// Por encima de esto el círculo deja de leerse: se recorta a los pares con
// más asistencias, no a jugadores al azar.
const MAX_EDGES = 40;

const TABS = [
  { key: 'resumen', label: 'Resumen' },
  { key: 'plantilla', label: 'Plantilla' },
  { key: 'ritmo', label: 'Ritmo' },
  { key: 'asistencias', label: 'Asistencias' },
];

export function Identity({ team, meta, standing }) {
  return (
    <div className="panel" style={{ marginBottom: 24 }}>
      <div
        className="row"
        style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 32, flexWrap: 'wrap' }}
      >
        <div>
          <h1 style={{ fontSize: '1.75rem', letterSpacing: '-0.01em', marginBottom: 6 }}>
            {teamName(team.team)}
          </h1>
          <div
            className="row"
            style={{ gap: 10, fontSize: '0.875rem', color: 'var(--muted)', flexWrap: 'wrap' }}
          >
            <span>
              {meta.competition}
              {team.group ? `, grupo ${team.group}` : ''}
            </span>
            <span style={{ color: 'var(--faint)' }}>·</span>
            <span>{meta.season}</span>
          </div>
        </div>
        <span className="chip" style={{ flexShrink: 0 }}>
          {standing.wins}-{standing.losses} · puesto {standing.rank}
        </span>
      </div>
    </div>
  );
}

export function RosterRow({ player, maxVal, context, onOpen }) {
  const zonaPct = (zona) => player.zones[zona]?.pct;
  return (
    <tr className="is-clickable" onClick={() => onOpen(player.slug, context)}>
      <td className="is-left" style={{ color: 'var(--muted)', width: 36 }}>{player.jersey ?? '—'}</td>
      <td className="is-left">
        <a
          href={href.player(player.slug, context)}
          style={{ color: 'var(--ink)', fontWeight: 500 }}
          onClick={(event) => event.stopPropagation()}
        >
          {player.name}
        </a>
      </td>
      <td style={{ color: 'var(--muted)' }}>{player.games}</td>
      <td>{decimal(player.perGame.min)}</td>
      <td>{decimal(player.perGame.pts)}</td>
      <td>{decimal(player.perGame.reb)}</td>
      <td>{decimal(player.perGame.ast)}</td>
      <td style={{ color: 'var(--muted)' }}>{percent(zonaPct('aro'), 0)}</td>
      <td style={{ color: 'var(--muted)' }}>{percent(zonaPct('media'), 0)}</td>
      <td style={{ color: 'var(--muted)' }}>{percent(zonaPct('triple'), 0)}</td>
      <td className="is-left" style={{ paddingLeft: 20, width: 168 }}>
        <Meter value={player.perGame.val} max={maxVal} display={decimal(player.perGame.val)} />
      </td>
    </tr>
  );
}

export function Roster({ roster, context, onOpen }) {
  const maxVal = roster.reduce((max, p) => Math.max(max, p.perGame.val), 1);
  return (
    <div className="table--scroll">
      <table className="table">
        <thead>
          <tr>
            <th className="is-left" style={{ width: 36 }}>#</th>
            <th className="is-left">Jugador</th>
            <th style={{ width: 46 }}>PJ</th>
            <th style={{ width: 54 }}>MIN</th>
            <th style={{ width: 54 }}>PTS</th>
            <th style={{ width: 50 }}>REB</th>
            <th style={{ width: 50 }}>AST</th>
            <th style={{ width: 50 }}>AR</th>
            <th style={{ width: 50 }}>MD</th>
            <th style={{ width: 50 }}>3P</th>
            <th className="is-left" style={{ paddingLeft: 20, width: 168 }}>VAL</th>
          </tr>
        </thead>
        <tbody>
          {roster.map((player) => (
            <RosterRow key={player.slug} player={player} maxVal={maxVal} context={context} onOpen={onOpen} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PaceRow({ game }) {
  return (
    <tr>
      <td className="is-left" style={{ color: 'var(--muted)' }}>{game.date}</td>
      <td className="is-left">{teamName(game.opponent)}</td>
      <td
        className="num"
        style={{ color: game.won ? 'var(--ink)' : 'var(--muted)', fontWeight: game.won ? 600 : 400 }}
      >
        {game.pointsFor}-{game.pointsAgainst}
      </td>
      <td>{decimal(game.possessions)}</td>
      <td>{decimal(game.ortg)}</td>
      <td>{decimal(game.drtg)}</td>
    </tr>
  );
}

export function PaceLog({ gameLog }) {
  return (
    <div className="table--scroll-sm">
      <table className="table">
        <thead>
          <tr>
            <th className="is-left" style={{ width: 96 }}>Fecha</th>
            <th className="is-left">Rival</th>
            <th style={{ width: 84 }}>Resultado</th>
            <th style={{ width: 70 }}>Poses.</th>
            <th style={{ width: 70 }}>ORTG</th>
            <th style={{ width: 70 }}>DRTG</th>
          </tr>
        </thead>
        <tbody>
          {gameLog.map((game) => <PaceRow key={game.gameId} game={game} />)}
        </tbody>
      </table>
    </div>
  );
}

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

export function AsistenciasTab({ slug, context, onNavigate }) {
  const red = useResource(
    () => getAssistNetwork({ ...context, team: slug }), [slug, context?.competition, context?.season, context?.group]);

  if (red.status === 'loading') return <p style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>Cargando…</p>;
  if (red.status === 'error') return <ErrorState detail={red.error?.message} onRetry={red.retry} />;

  const { nodes, edges } = red.data;
  if (nodes.length === 0) {
    return (
      <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
        No hay asistencias registradas con jugador y anotador resueltos en este filtro.
      </p>
    );
  }

  const shownEdges = edges.slice(0, MAX_EDGES);
  const involucrados = new Set(shownEdges.flatMap((edge) => [edge.passerSlug, edge.scorerSlug]));
  const shownNodes = nodes.filter((node) => involucrados.has(node.slug));

  return (
    <div>
      <p style={{ margin: '0 0 18px', fontSize: '0.8125rem', color: 'var(--muted)' }}>
        Quién asiste a quién dentro de la plantilla · pasa el ratón por un nodo o una línea para el detalle.
        {edges.length > shownEdges.length && ` Se muestran los ${shownEdges.length} pares con más asistencias de ${edges.length}.`}
      </p>
      <div
        className="grid grid--split"
        style={{ gridTemplateColumns: 'minmax(0, 1.3fr) minmax(0, 1fr)', gap: 24, alignItems: 'start' }}
      >
        <AssistNetwork nodes={shownNodes} edges={shownEdges} />

        <div className="stack" style={{ gap: 24 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Jugadores · asistencias dadas</div>
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
                    <NodeRow key={node.slug} node={node} context={context} onNavigate={onNavigate} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Pares · pasador → anotador</div>
            <div className="table--scroll-sm">
              <table className="table">
                <thead>
                  <tr>
                    <th className="is-left">Pasador</th>
                    <th className="is-left">Anotador</th>
                    <th style={{ width: 46 }}>Ast.</th>
                  </tr>
                </thead>
                <tbody>
                  {shownEdges.slice(0, 12).map((edge) => (
                    <EdgeRow key={`${edge.passerSlug}-${edge.scorerSlug}`} edge={edge} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Team({ slug, context, onSource }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState('resumen');
  const { status, data, source, error, retry } = useResource(
    () => getTeam(slug, context), [slug, context?.competition, context?.season, context?.group]);

  useEffect(() => {
    if (source) onSource?.(source);
  }, [source, onSource]);

  if (status === 'loading') return <Loading label="Cargando ficha…" />;
  if (status === 'error' || !data) {
    return (
      <ErrorState
        title="Equipo no encontrado"
        detail={`No hay datos para «${slug}». ${error?.message ?? ''}`}
        onRetry={retry}
      />
    );
  }

  const team = data;
  const cabecera = team.meta;
  const madeShots = team.shots.filter((shot) => shot.made).length;
  const onOpenPlayer = (playerSlug) => navigate(href.player(playerSlug, context).slice(1));

  return (
    <>
      <div className="row" style={{ gap: 8, fontSize: '0.8125rem', marginBottom: 20 }}>
        <a href={href.teams(context)} style={{ color: 'var(--muted)' }}>
          Equipos
        </a>
        <span style={{ color: 'var(--faint)' }}>/</span>
        <span style={{ color: 'var(--ink)' }}>{teamName(team.team)}</span>
      </div>

      <Identity team={team} meta={cabecera} standing={team.standing} />

      <Panel>
        <Tabs tabs={TABS} active={tab} onChange={setTab} />

        {tab === 'resumen' && (
          <div>
            <div
              className="grid grid--kpi-6"
              style={{ gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', marginBottom: 24 }}
            >
              <StatTile
                size="sm" emphasis label="Récord" value={`${team.standing.wins}-${team.standing.losses}`}
                note={`${integer(team.standing.pointsFor)} a favor`}
              />
              <StatTile
                size="sm" label="Diferencial" value={signed(team.standing.diff, 0)}
                note={`${integer(team.standing.pointsAgainst)} en contra`}
              />
              <StatTile size="sm" label="Posesiones" value={decimal(team.pace.avgPossessions)} note="por partido" />
              <StatTile size="sm" label="Rating ofensivo" value={decimal(team.pace.avgOrtg)} note="por 100 posesiones" />
              <StatTile size="sm" label="Rating defensivo" value={decimal(team.pace.avgDrtg)} note="por 100 posesiones" />
              <StatTile size="sm" emphasis label="Net rating" value={signed(team.pace.avgNetRtg)} note="ORTG − DRTG" />
            </div>

            <div style={{ marginBottom: 4 }}>
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
                <span style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--ink)' }}>Mapa de tiro del equipo</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{team.shots.length} tiros localizados</span>
              </div>
              <div style={{ marginBottom: 16 }}>
                <ShotLegend made={madeShots} missed={team.shots.length - madeShots} />
              </div>
              <div style={{ maxWidth: 420, margin: '0 auto' }}>
                <ShotChart shots={team.shots} />
              </div>
            </div>
          </div>
        )}

        {tab === 'plantilla' && (
          <>
            <p style={{ margin: '0 0 18px', fontSize: '0.8125rem', color: 'var(--muted)' }}>
              AR/MD/3P = acierto por zona: cerca del aro, media distancia y triple.
            </p>
            <Roster roster={team.roster} context={context} onOpen={onOpenPlayer} />
          </>
        )}

        {tab === 'ritmo' && (
          <>
            <p style={{ margin: '0 0 18px', fontSize: '0.8125rem', color: 'var(--muted)' }}>
              Posesiones estimadas (FGA − RO + PÉR + 0,44·TL), propias y del rival — rating por 100 posesiones.
            </p>
            <PaceLog gameLog={team.gameLog} />
          </>
        )}

        {tab === 'asistencias' && (
          <AsistenciasTab slug={team.slug} context={context} onNavigate={onOpenPlayer} />
        )}
      </Panel>
    </>
  );
}
