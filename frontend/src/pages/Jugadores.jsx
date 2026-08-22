import { useEffect, useState } from 'react';
import { getDashboard, getClutch, getFouls, getCompetitions } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, ContextPicker, Meter, Pager, Tabs, Loading, ErrorState } from '../components/Primitives.jsx';
import { decimal, integer, percent, teamName, teamSlug } from '../lib/format.js';

const PAGE_SIZE = 15;

const TABS = [
  { key: 'lideres', label: 'Líderes' },
  { key: 'clutch', label: 'Clutch' },
  { key: 'faltas', label: 'Faltas' },
];

const HINTS = {
  lideres: 'Valoración media por partido · mínimo 6 partidos y 15 minutos',
  clutch: null, // se arma con la definición que trae la propia respuesta
  faltas: 'Ordenado por faltas totales · mínimo 3 partidos jugados',
};

export function LeaderRow({ player, max, rank, onNavigate, context }) {
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
          <a
            href={href.team(teamSlug(player.team), context)}
            style={{ color: 'var(--muted)' }}
            onClick={(event) => event.stopPropagation()}
          >
            {teamName(player.team)}
          </a>
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

export function ClutchRow({ player, rank, onNavigate, context }) {
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
      <td className="num" style={{ fontWeight: 600, color: 'var(--ink)' }}>{integer(player.points)}</td>
      <td>{percent(player.shooting.fg)}</td>
      <td>{percent(player.shooting.fg3)}</td>
      <td>{percent(player.shooting.ft)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(player.ast)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(player.tov)}</td>
      <td style={{ color: 'var(--muted)' }}>{integer(player.fouls)}</td>
    </tr>
  );
}

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

export function TeamFoulRow({ team, context }) {
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

export default function Jugadores({ context = {}, onNavigate, onContextChange, onSource }) {
  const [tab, setTab] = useState('lideres');
  const [offset, setOffset] = useState(0);

  const catalogo = useResource(() => getCompetitions(), []);
  const tabla = useResource(() => {
    if (tab === 'clutch') return getClutch({ ...context, limit: PAGE_SIZE, offset });
    if (tab === 'faltas') return getFouls({ ...context, limit: PAGE_SIZE, offset });
    return getDashboard({ ...context, limit: PAGE_SIZE, offset });
  }, [tab, context.competition, context.season, context.group, offset]);

  useEffect(() => { setOffset(0); }, [tab, context.competition, context.season, context.group]);

  useEffect(() => {
    if (tabla.source) onSource?.(tabla.source);
  }, [tabla.source, onSource]);

  // Cambiar de pestaña dispara un nuevo fetch, pero React repinta con el
  // `tab` nuevo antes de que ese fetch resuelva: por un instante `tabla.data`
  // todavía trae la forma de la pestaña anterior (sin "definition", por
  // ejemplo). status==='loading' no basta para cubrir ese instante porque el
  // efecto que lo pone a 'loading' tampoco ha corrido aún — hay que
  // comprobar que la forma de los datos coincide con la pestaña activa.
  const formaListaPara = { lideres: 'leaders', clutch: 'definition', faltas: 'foulOutThreshold' };
  const datosListos = tabla.status === 'ready' && tabla.data && formaListaPara[tab] in tabla.data;
  if (!datosListos) {
    if (tabla.status === 'error') {
      return <ErrorState detail={tabla.error?.message} onRetry={tabla.retry} />;
    }
    return <Loading />;
  }

  const { meta } = tabla.data;
  const contexto = { competition: meta.competitionKey, season: meta.seasonKey,
                     group: meta.groupKey ?? undefined };

  let hint = HINTS[tab];
  let players; let total;
  if (tab === 'lideres') {
    players = tabla.data.leaders; total = tabla.data.leadersTotal;
  } else if (tab === 'clutch') {
    const { definition } = tabla.data;
    const minutos = Math.round(definition.lastSeconds / 60);
    hint = `Últimos ${minutos}' del último cuarto o cualquier prórroga, con el marcador a `
      + `${definition.marginPoints} puntos o menos en ese instante · mínimo ${definition.minGames} partidos en esa situación`;
    players = tabla.data.players; total = tabla.data.playersTotal;
  } else {
    hint = `${hint} · elimina a las ${tabla.data.foulOutThreshold} personales en un mismo partido`;
    players = tabla.data.players; total = tabla.data.playersTotal;
  }

  const maxVal = tab === 'lideres' && players.length ? players[0].perGame.val : 1;

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
            Jugadores · Temporada {meta.season}
          </p>
        </div>
        <ContextPicker catalogo={catalogo.data?.competitions ?? []} contexto={contexto} onChange={onContextChange} />
      </div>

      <div
        className="grid grid--split"
        style={{ gridTemplateColumns: tab === 'faltas' ? 'minmax(0, 1.85fr) minmax(0, 1fr)' : 'minmax(0, 1fr)', gap: 24 }}
      >
        <Panel>
          <Tabs tabs={TABS} active={tab} onChange={setTab} />
          <p style={{ margin: '0 0 18px', fontSize: '0.8125rem', color: 'var(--muted)' }}>{hint}</p>

          {players.length === 0 ? (
            <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
              Nadie llega todavía al mínimo para este ranking.
            </p>
          ) : (
            <div className="table--scroll-sm">
              <table className="table">
                <thead>
                  {tab === 'lideres' && (
                    <tr>
                      <th className="is-left" style={{ width: 34 }}>#</th>
                      <th className="is-left">Jugador</th>
                      <th style={{ width: 46 }}>PJ</th>
                      <th style={{ width: 54 }}>MIN</th>
                      <th style={{ width: 54 }}>PTS</th>
                      <th style={{ width: 50 }}>REB</th>
                      <th style={{ width: 50 }}>AST</th>
                      <th className="is-left" style={{ paddingLeft: 20, width: 190 }}>Valoración</th>
                    </tr>
                  )}
                  {tab === 'clutch' && (
                    <tr>
                      <th className="is-left" style={{ width: 34 }}>#</th>
                      <th className="is-left">Jugador</th>
                      <th style={{ width: 46 }}>PJ*</th>
                      <th style={{ width: 54 }}>PTS</th>
                      <th style={{ width: 58 }}>T2+T3</th>
                      <th style={{ width: 54 }}>T3</th>
                      <th style={{ width: 54 }}>TL</th>
                      <th style={{ width: 50 }}>AST</th>
                      <th style={{ width: 50 }}>PER</th>
                      <th style={{ width: 50 }}>FP</th>
                    </tr>
                  )}
                  {tab === 'faltas' && (
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
                  )}
                </thead>
                <tbody>
                  {tab === 'lideres' && players.map((player, index) => (
                    <LeaderRow key={player.slug} player={player} max={maxVal} rank={offset + index + 1}
                               onNavigate={onNavigate} context={contexto} />
                  ))}
                  {tab === 'clutch' && players.map((player, index) => (
                    <ClutchRow key={player.slug} player={player} rank={offset + index + 1}
                               onNavigate={onNavigate} context={contexto} />
                  ))}
                  {tab === 'faltas' && players.map((player, index) => (
                    <FoulRow key={player.slug} player={player} rank={offset + index + 1}
                             onNavigate={onNavigate} context={contexto} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === 'clutch' && (
            <p style={{ margin: '10px 0 0', fontSize: '0.75rem', color: 'var(--faint)' }}>
              * Partidos con jugadas en momentos ajustados, no partidos jugados en total.
            </p>
          )}
          {total > 0 && <Pager offset={offset} total={total} size={PAGE_SIZE} onMove={setOffset} />}
        </Panel>

        {tab === 'faltas' && (
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
                  {tabla.data.teams.map((team) => (
                    <TeamFoulRow key={team.teamKey} team={team} context={contexto} />
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </div>
    </>
  );
}
