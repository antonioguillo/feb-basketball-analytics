import { useEffect } from 'react';
import { getPlayer } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, StatTile, Meter, LabelledBar, Loading, ErrorState } from '../components/Primitives.jsx';
import ShotChart, { ShotLegend } from '../components/ShotChart.jsx';
import { ZONE_ORDER, ZONE_LABEL } from '../lib/court.js';
import { decimal, percent, signed, madeOfAttempts, teamName, teamSlug } from '../lib/format.js';

export function Identity({ player, meta, context }) {
  return (
    <div className="panel" style={{ marginBottom: 24 }}>
      <div
        className="row"
        style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 32, flexWrap: 'wrap' }}
      >
        <div className="row" style={{ gap: 20 }}>
          <div
            style={{
              width: 68,
              height: 68,
              borderRadius: 'var(--radius)',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <span className="num" style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent)' }}>
              {player.jersey}
            </span>
          </div>
          <div>
            <h1 style={{ fontSize: '1.75rem', letterSpacing: '-0.01em', marginBottom: 6 }}>{player.name}</h1>
            <div
              className="row"
              style={{ gap: 10, fontSize: '0.875rem', color: 'var(--muted)', flexWrap: 'wrap' }}
            >
              <a href={href.team(teamSlug(player.team), context)} style={{ color: 'var(--ink)' }}>
                {teamName(player.team)}
              </a>
              <span style={{ color: 'var(--faint)' }}>·</span>
              <span>
                {meta.competition}
                {player.group ? `, grupo ${player.group}` : ''}
              </span>
              <span style={{ color: 'var(--faint)' }}>·</span>
              <span>{meta.season}</span>
            </div>
          </div>
        </div>
        <span className="chip" style={{ flexShrink: 0 }}>
          {player.games} partidos
        </span>
      </div>
    </div>
  );
}

export function ShootingPanel({ shooting, totals }) {
  const cells = [
    { label: 'Tiros de 2', pct: shooting.t2, detail: madeOfAttempts(totals.t2m, totals.t2a) },
    { label: 'Triples', pct: shooting.t3, detail: madeOfAttempts(totals.t3m, totals.t3a) },
    { label: 'Tiros libres', pct: shooting.ft, detail: madeOfAttempts(totals.ftm, totals.fta) },
  ];

  return (
    <Panel title="Eficiencia en el tiro" style={{ flexGrow: 1 }}>
      <div
        className="grid"
        style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', margin: '20px 0 22px' }}
      >
        {cells.map((cell) => (
          <div
            key={cell.label}
            style={{
              background: 'var(--bg)',
              border: '1px solid var(--border-soft)',
              borderRadius: 6,
              padding: 14,
            }}
          >
            <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: 7 }}>{cell.label}</div>
            <div className="num" style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--ink)', lineHeight: 1 }}>
              {percent(cell.pct)}
            </div>
            <div className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 5 }}>
              {cell.detail}
            </div>
          </div>
        ))}
      </div>

      <div className="stack" style={{ gap: 14, borderTop: '1px solid var(--border-soft)', paddingTop: 20 }}>
        <AdvancedRow
          name="eFG%"
          note="tiro de campo ponderando el triple"
          value={percent(shooting.efg)}
        />
        <AdvancedRow
          name="TS%"
          note="acierto real, incluidos tiros libres"
          value={percent(shooting.ts)}
          emphasis
        />
      </div>
    </Panel>
  );
}

export function AdvancedRow({ name, note, value, emphasis }) {
  return (
    <div className="row" style={{ justifyContent: 'space-between', gap: 16 }}>
      <div>
        <div style={{ color: 'var(--ink)', fontSize: '0.875rem', fontWeight: 500 }}>{name}</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 2 }}>{note}</div>
      </div>
      <span
        className="num"
        style={{ fontSize: '1.25rem', fontWeight: 600, color: emphasis ? 'var(--accent)' : 'var(--ink)' }}
      >
        {value}
      </span>
    </div>
  );
}

export function GameLog({ games, maxVal }) {
  return (
    <Panel title="Partido a partido">
      <div className="table--scroll-sm" style={{ marginTop: 20 }}>
        <table className="table">
          <thead>
            <tr>
              <th className="is-left" style={{ width: 96 }}>Fecha</th>
              <th className="is-left">Rival</th>
              <th style={{ width: 60, textAlign: 'center' }}>L/V</th>
              <th style={{ width: 84 }}>Resultado</th>
              <th style={{ width: 56 }}>MIN</th>
              <th style={{ width: 56 }}>PTS</th>
              <th style={{ width: 56 }}>REB</th>
              <th style={{ width: 56 }}>AST</th>
              <th className="is-left" style={{ paddingLeft: 24, width: 168 }}>VAL</th>
            </tr>
          </thead>
          <tbody>
            {games.map((game) => (
              <tr key={game.gameId} className={game.val === maxVal ? 'is-highlight' : undefined}>
                <td className="is-left" style={{ color: 'var(--muted)' }}>{game.date}</td>
                <td className="is-left">{teamName(game.opponent)}</td>
                <td style={{ textAlign: 'center', color: 'var(--muted)' }}>{game.home ? 'L' : 'V'}</td>
                <td style={{ color: 'var(--muted)' }}>{game.score}</td>
                <td>{game.min}</td>
                <td>{game.pts}</td>
                <td>{game.reb}</td>
                <td>{game.ast}</td>
                <td className="is-left" style={{ paddingLeft: 24 }}>
                  <Meter value={game.val} max={maxVal} display={game.val} width={22} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export default function Player({ slug, context, onSource }) {
  const { status, data, source, error, retry } = useResource(
    () => getPlayer(slug, context), [slug, context?.competition, context?.season, context?.group]);

  useEffect(() => {
    if (source) onSource?.(source);
  }, [source, onSource]);

  if (status === 'loading') return <Loading label="Cargando ficha…" />;
  if (status === 'error' || !data) {
    return (
      <ErrorState
        title="Jugador no encontrado"
        detail={`No hay datos para «${slug}». ${error?.message ?? ''}`}
        onRetry={retry}
      />
    );
  }

  const player = data;
  // La cabecera la describe la propia respuesta: dice de qué competición y
  // temporada son los datos que se están mostrando.
  const cabecera = player.meta;
  const madeShots = player.shots.filter((shot) => shot.made).length;

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div className="row" style={{ gap: 8, fontSize: '0.8125rem' }}>
          <a href={href.dashboard(context)} style={{ color: 'var(--muted)' }}>
            Dashboard
          </a>
          <span style={{ color: 'var(--faint)' }}>/</span>
          <span style={{ color: 'var(--ink)' }}>{player.name}</span>
        </div>
        <a href={href.compare([player.slug], context)} className="chip chip--button">
          Comparar con otro jugador
        </a>
      </div>

      <Identity player={player} meta={cabecera} context={context} />

      <div
        className="grid grid--kpi-6"
        style={{ gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', marginBottom: 24 }}
      >
        <StatTile size="sm" emphasis label="Valoración" value={decimal(player.perGame.val)} note={`máximo ${player.bests.val}`} />
        <StatTile size="sm" label="Puntos" value={decimal(player.perGame.pts)} note={`${decimal(player.per36.pts)} por 36 min`} />
        <StatTile size="sm" label="Rebotes" value={decimal(player.perGame.reb)} note={`máximo ${player.bests.reb}`} />
        <StatTile size="sm" label="Asistencias" value={decimal(player.perGame.ast)} note={`${decimal(player.perGame.to)} pérdidas`} />
        <StatTile size="sm" label="Minutos" value={decimal(player.perGame.min)} note="de 40 posibles" />
        <StatTile size="sm" label="Plus / minus" value={signed(player.perGame.plusMinus)} note="por partido" />
      </div>

      <div
        className="grid grid--halves"
        style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 24, marginBottom: 24 }}
      >
        <Panel
          title="Mapa de tiro"
          hint={`${player.shots.length} tiros de campo localizados · ${player.games} partidos`}
        >
          <div style={{ marginBottom: 16 }}>
            <ShotLegend made={madeShots} missed={player.shots.length - madeShots} />
          </div>
          <ShotChart shots={player.shots} />
        </Panel>

        <div className="stack" style={{ gap: 24 }}>
          <Panel title="Acierto por zona" hint="Zona calculada desde las coordenadas, no desde el acta">
            <div className="stack" style={{ gap: 18 }}>
              {ZONE_ORDER.map((zone) => {
                const stats = player.zones[zone];
                if (!stats) return null;
                return (
                  <LabelledBar
                    key={zone}
                    label={ZONE_LABEL[zone]}
                    value={stats.pct}
                    display={percent(stats.pct, 0)}
                    detail={madeOfAttempts(stats.made, stats.att)}
                  />
                );
              })}
            </div>
          </Panel>

          <ShootingPanel shooting={player.shooting} totals={player.totals} />
        </div>
      </div>

      <GameLog games={player.gameLog} maxVal={player.bests.val} />
    </>
  );
}
