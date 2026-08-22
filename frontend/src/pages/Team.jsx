import { useEffect } from 'react';
import { getTeam } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href, useNavigate } from '../lib/router.js';
import { Panel, StatTile, Meter, Loading, ErrorState } from '../components/Primitives.jsx';
import ShotChart, { ShotLegend } from '../components/ShotChart.jsx';
import { decimal, percent, signed, integer, teamName } from '../lib/format.js';

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
    <Panel title="Plantilla" hint="AR/MD/3P = acierto por zona: cerca del aro, media distancia y triple.">
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
    </Panel>
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
    <Panel
      title="Ritmo y eficiencia por partido"
      hint="Posesiones estimadas (FGA - RO + PER + 0,44·TL), propias y del rival — rating por 100 posesiones."
    >
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
    </Panel>
  );
}

export default function Team({ slug, context, onSource }) {
  const navigate = useNavigate();
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

      <Panel
        title="Mapa de tiro del equipo"
        hint={`${team.shots.length} tiros de campo localizados de toda la plantilla`}
        style={{ marginBottom: 24 }}
      >
        <div style={{ marginBottom: 16 }}>
          <ShotLegend made={madeShots} missed={team.shots.length - madeShots} />
        </div>
        <div style={{ maxWidth: 420, margin: '0 auto' }}>
          <ShotChart shots={team.shots} />
        </div>
      </Panel>

      <div style={{ marginBottom: 24 }}>
        <Roster
          roster={team.roster} context={context}
          onOpen={(playerSlug) => navigate(href.player(playerSlug, context).slice(1))}
        />
      </div>

      <PaceLog gameLog={team.gameLog} />
    </>
  );
}
