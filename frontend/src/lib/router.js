import { useState, useEffect, useCallback } from 'react';

/**
 * Enrutado por hash, sin dependencias.
 * Rutas de las pantallas diseñadas:
 *   #/                        -> dashboard
 *   #/jugador/<slug>          -> ficha de jugador
 *   #/comparar?jugadores=a,b  -> comparador de jugadores
 *   #/equipos                 -> clasificación
 *   #/equipo/<slug>           -> ficha de equipo
 * El hash evita tener que configurar rewrites en el servidor que sirva el build.
 */
function currentRoute() {
  const raw = window.location.hash.replace(/^#/, '') || '/';
  // El contexto (competición, temporada, grupo) viaja en la propia ruta: una
  // ficha de jugador solo tiene sentido dentro de una competición concreta.
  const [path, search = ''] = raw.split('?');
  const query = Object.fromEntries(new URLSearchParams(search));
  const parts = path.split('/').filter(Boolean);

  if (parts[0] === 'jugador' && parts[1]) {
    return { name: 'player', slug: decodeURIComponent(parts[1]), context: query };
  }
  if (parts[0] === 'comparar') {
    // Los slugs no llevan comas (ver src/naming.py:player_slug), así que
    // separarlos por coma es seguro sin tener que escaparlas.
    const { jugadores, ...context } = query;
    const slugs = jugadores ? jugadores.split(',').filter(Boolean) : [];
    return { name: 'compare', slugs, context };
  }
  if (parts[0] === 'equipo' && parts[1]) {
    return { name: 'team', slug: decodeURIComponent(parts[1]), context: query };
  }
  if (parts[0] === 'equipos') {
    return { name: 'teams', context: query };
  }
  if (parts.length === 0) {
    return { name: 'dashboard', context: query };
  }
  return { name: 'notFound', path };
}

export function useRoute() {
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  return route;
}

export function useNavigate() {
  return useCallback((path) => {
    if (window.location.hash === `#${path}`) return;
    window.location.hash = path;
    window.scrollTo({ top: 0 });
  }, []);
}

function contextQuery({ competition, season, group } = {}) {
  const query = new URLSearchParams();
  if (competition) query.set('competition', competition);
  if (season) query.set('season', season);
  if (group) query.set('group', group);
  return query.toString() ? `?${query}` : '';
}

export const href = {
  dashboard: (context) => `#/${contextQuery(context)}`,
  player: (slug, context) => `#/jugador/${encodeURIComponent(slug)}${contextQuery(context)}`,
  compare: (slugs = [], context) => {
    const query = new URLSearchParams(contextQuery(context).replace(/^\?/, ''));
    if (slugs.length) query.set('jugadores', slugs.join(','));
    const search = query.toString();
    return `#/comparar${search ? `?${search}` : ''}`;
  },
  teams: (context) => `#/equipos${contextQuery(context)}`,
  team: (slug, context) => `#/equipo/${encodeURIComponent(slug)}${contextQuery(context)}`,
};
