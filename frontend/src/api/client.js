/**
 * Capa de datos de la aplicación.
 *
 * Define el contrato que necesita el frontend y, si la API no responde, cae a
 * los datos de ejemplo de `fixtures.json` (63 partidos reales del Grupo E-A
 * 2025/2026 scrapeados de feb.es) para que la interfaz sea navegable sin
 * backend. Cuando eso ocurre se devuelve `source: 'fixtures'` y la interfaz lo
 * anuncia, de modo que los datos de ejemplo nunca se presentan como si fueran
 * vivos.
 *
 * Los fixtures se cargan con import dinámico: pesan ~670 KB y no deben entrar
 * en el bundle inicial de quien sí tiene API.
 *
 * Endpoints esperados en el backend:
 *   GET /api/dashboard?season=<año>&group=<clave>
 *        -> { meta, summary, leaders[], recentGames[] }
 *   GET /api/players/<slug>
 *        -> perfil (meta?, totals, perGame, shooting, per36, zones,
 *           bests, gameLog[], shots[])
 *
 * La forma exacta de cada objeto es la de `fixtures.json`.
 */

const BASE = import.meta.env.VITE_API_BASE ?? '/api';
const TIMEOUT_MS = 8000;

/**
 * Contexto de la competición mostrada. Sirve de encabezado de la ficha de
 * jugador sin pedir otra vez el dashboard; si `/api/players/<slug>` devuelve su
 * propio `meta`, ese tiene prioridad.
 */
export const DEFAULT_CONTEXT = {
  competition: 'Tercera FEB',
  competitionKey: 'tercerafeb',
  season: '2025/2026',
  seasonKey: '2025',
  group: 'Liga Regular E-A',
  groupKey: 'E-A',
};

let fixturesPromise = null;
function loadFixtures() {
  if (!fixturesPromise) {
    fixturesPromise = import('./fixtures.json').then((module) => module.default);
  }
  return fixturesPromise;
}

async function request(path) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE}${path}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Pide un recurso a la API y, si falla, devuelve el equivalente de ejemplo.
 * `pick` recibe los fixtures ya cargados; si devuelve `undefined` (por ejemplo
 * un jugador que no existe) se propaga el error original en vez de inventar
 * una respuesta.
 */
async function withFallback(path, pick) {
  try {
    return { data: await request(path), source: 'api' };
  } catch (apiError) {
    const data = pick(await loadFixtures());
    if (data === undefined) throw apiError;
    return { data, source: 'fixtures', apiError };
  }
}

export function getDashboard({ season, group } = {}) {
  const query = new URLSearchParams();
  if (season) query.set('season', season);
  if (group) query.set('group', group);
  const suffix = query.toString() ? `?${query}` : '';

  return withFallback(`/dashboard${suffix}`, (fixtures) => ({
    meta: fixtures.meta,
    summary: fixtures.summary,
    leaders: fixtures.leaders,
    recentGames: fixtures.recentGames,
  }));
}

export function getPlayer(slug) {
  return withFallback(`/players/${encodeURIComponent(slug)}`, (fixtures) => fixtures.players[slug]);
}

/** Slugs disponibles en los datos de ejemplo (para navegación y pruebas). */
export async function knownPlayerSlugs() {
  return Object.keys((await loadFixtures()).players);
}
