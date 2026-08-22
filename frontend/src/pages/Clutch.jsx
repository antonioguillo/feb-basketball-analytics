import { useEffect, useState } from 'react';
import { getClutch, getCompetitions } from '../api/client.js';
import { useResource } from '../lib/useResource.js';
import { href } from '../lib/router.js';
import { Panel, Loading, ErrorState } from '../components/Primitives.jsx';
import { ContextPicker, Pager } from './Dashboard.jsx';
import { integer, percent, teamName } from '../lib/format.js';

const PAGE_SIZE = 15;

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

export default function Clutch({ context = {}, onNavigate, onContextChange, onSource }) {
  const [offset, setOffset] = useState(0);

  const catalogo = useResource(() => getCompetitions(), []);
  const tabla = useResource(
    () => getClutch({ ...context, limit: PAGE_SIZE, offset }),
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

  const { meta, definition, players, playersTotal } = tabla.data;
  const contexto = { competition: meta.competitionKey, season: meta.seasonKey,
                     group: meta.groupKey ?? undefined };
  const minutos = Math.round(definition.lastSeconds / 60);

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
            Clutch · Temporada {meta.season}
          </p>
        </div>
        <ContextPicker catalogo={catalogo.data?.competitions ?? []} contexto={contexto} onChange={onContextChange} />
      </div>

      <Panel
        title="Ranking en momentos ajustados"
        hint={`Últimos ${minutos}' del último cuarto o cualquier prórroga, con el marcador a `
          + `${definition.marginPoints} puntos o menos en ese instante · mínimo ${definition.minGames} `
          + 'partidos en esa situación'}
      >
        {players.length === 0 ? (
          <p style={{ margin: '24px 0 8px', fontSize: '0.875rem', color: 'var(--muted)' }}>
            Ningún jugador llega todavía al mínimo de partidos en momentos ajustados.
          </p>
        ) : (
          <div className="table--scroll-sm">
            <table className="table">
              <thead>
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
              </thead>
              <tbody>
                {players.map((player, index) => (
                  <ClutchRow
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
        <p style={{ margin: '10px 0 0', fontSize: '0.75rem', color: 'var(--faint)' }}>
          * Partidos con jugadas en momentos ajustados, no partidos jugados en total.
        </p>
        {playersTotal > 0 && (
          <Pager offset={offset} total={playersTotal} size={PAGE_SIZE} onMove={setOffset} />
        )}
      </Panel>
    </>
  );
}
