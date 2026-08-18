import { useState, useEffect, useCallback } from 'react';

/**
 * Enrutado por hash, sin dependencias.
 * Dos rutas bastan para las pantallas diseñadas:
 *   #/                        -> dashboard
 *   #/jugador/<slug>          -> ficha de scouting
 * El hash evita tener que configurar rewrites en el servidor que sirva el build.
 */
function currentRoute() {
  const hash = window.location.hash.replace(/^#/, '') || '/';
  const parts = hash.split('/').filter(Boolean);

  if (parts[0] === 'jugador' && parts[1]) {
    return { name: 'player', slug: decodeURIComponent(parts[1]) };
  }
  if (parts.length === 0) {
    return { name: 'dashboard' };
  }
  return { name: 'notFound', path: hash };
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

export const href = {
  dashboard: () => '#/',
  player: (slug) => `#/jugador/${encodeURIComponent(slug)}`,
};
