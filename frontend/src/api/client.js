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
 * Endpoints del backend:
 *   GET /api/competitions
 *        -> { competitions[] } — qué hay cargado
 *   GET /api/dashboard?competition=&season=&group=&limit=&offset=
 *        -> { meta, summary, leaders[], leadersTotal, recentGames[] }
 *   GET /api/players/<slug>?competition=&season=&group=
 *        -> perfil (meta, totals, perGame, shooting, per36, zones,
 *           bests, gameLog[], shots[])
 *
 * Toda respuesta se refiere a una sola competición; `meta` dice cuál.
 *
 * La forma exacta de cada objeto es la de `fixtures.json`.
 */

const BASE = import.meta.env.VITE_API_BASE ?? '/api';
const TIMEOUT_MS = 8000;

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

function queryString(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') query.set(key, value);
  }
  return query.toString() ? `?${query}` : '';
}

export function getDashboard({ competition, season, group, limit, offset } = {}) {
  const suffix = queryString({ competition, season, group, limit, offset });

  // Los datos de ejemplo describen una sola competición: si se pide otra, se
  // devuelven igualmente los que hay, y la interfaz ya avisa de que no son vivos.
  return withFallback(`/dashboard${suffix}`, (fixtures) => ({
    meta: fixtures.meta,
    summary: fixtures.summary,
    leaders: fixtures.leaders.slice(offset ?? 0, (offset ?? 0) + (limit ?? fixtures.leaders.length)),
    leadersTotal: fixtures.leadersTotal ?? fixtures.leaders.length,
    leadersOffset: offset ?? 0,
    recentGames: fixtures.recentGames,
  }));
}

export function getPlayer(slug, { competition, season, group } = {}) {
  // El contexto viaja en la URL para que la ficha sea la del mismo grupo y
  // temporada que el listado desde el que se llegó.
  const suffix = queryString({ competition, season, group });
  return withFallback(`/players/${encodeURIComponent(slug)}${suffix}`,
                      (fixtures) => fixtures.players[slug]);
}

/** Competiciones, temporadas y grupos con datos cargados. */
export function getCompetitions() {
  return withFallback('/competitions', (fixtures) => ({
    competitions: fixtures.competitions,
  }));
}

/** Slugs disponibles en los datos de ejemplo (para navegación y pruebas). */
export async function knownPlayerSlugs() {
  return Object.keys((await loadFixtures()).players);
}
