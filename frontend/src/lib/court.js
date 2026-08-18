/**
 * Geometría de la cancha, compartida por el mapa de tiro.
 *
 * La API interna de la FEB devuelve x/y como porcentaje (0-100) sobre la pista
 * completa, con las dos canastas en extremos opuestos del eje x. Estos valores
 * son los mismos que usa `jobs/spark_gold.py` para clasificar las zonas: se
 * calibraron contra los intentos de 3 del box score (6 partidos, 836 tiros,
 * 0,8 % de discrepancia). Si se cambian allí, hay que cambiarlos aquí.
 */
export const COURT_LENGTH_M = 28;
export const COURT_WIDTH_M = 15;
export const HOOP_X_PCT = 5;
export const THREE_POINT_M = 6.6;
export const RESTRICTED_AREA_M = 1.25;

/** Lienzo en centésimas de metro: 1500 x 1400 = media pista de 15 x 14 m. */
export const VIEW_W = COURT_WIDTH_M * 100;
export const VIEW_H = (COURT_LENGTH_M / 2) * 100;

const HOOP_SVG_Y = VIEW_H - HOOP_X_PCT * (COURT_LENGTH_M / 100) * 100;
export const HOOP = { x: VIEW_W / 2, y: HOOP_SVG_Y };
export const THREE_R = THREE_POINT_M * 100;

/**
 * Proyecta un tiro a coordenadas del SVG, plegando las dos mitades de la pista
 * sobre la misma media cancha (los tiros de la canasta lejana se reflejan).
 */
export function projectShot(shot) {
  const lengthPct = shot.x < 50 ? shot.x : 100 - shot.x;
  return {
    cx: shot.y * (COURT_WIDTH_M / 100) * 100,
    cy: VIEW_H - lengthPct * (COURT_LENGTH_M / 100) * 100,
  };
}

/** Claves tal y como las escribe jobs/spark_gold.py, no una traducción aparte. */
export const ZONE_LABEL = {
  aro: 'Cerca del aro',
  media: 'Media distancia',
  triple: 'Triple',
};

/** Orden de lectura de las zonas: de la más cercana a la más lejana. */
export const ZONE_ORDER = ['aro', 'media', 'triple'];
