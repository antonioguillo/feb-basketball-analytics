/** Formato de números y nombres tal y como se presentan en la interfaz. */

// Solo las partículas de enlace van en minúscula. "El" y "La" no entran: en un
// nombre de club suelen ser parte del propio nombre ("El Pilar", "La Salle").
const CONECTORES = new Set(['de', 'del', 'y', 'i', 'da', 'do']);

const VOCALES = /[aeiouáéíóúàèìòùäëïöüy]/i;

/**
 * Distingue una sigla de una palabra corta.
 *
 * La regla anterior era "cuatro letras o menos, en mayúsculas", y convertía
 * THE en "THE" y GIL en "GIL". Una sigla no tiene vocales (CB, NB, CMG) o
 * lleva puntos (C.B., C.A.).
 */
function esSigla(palabra) {
  if (palabra.includes('.')) return true;
  const letras = palabra.replace(/[^\p{L}]/gu, '');
  return letras.length > 0 && letras.length <= 4 && !VOCALES.test(letras);
}

/** Capitaliza también tras guion y apóstrofo: l'eliana -> L'Eliana. */
function capitalizarSegmentos(palabra) {
  return palabra.replace(/(^|[-'’])(\p{L})/gu,
    (_, separador, letra) => separador + letra.toLocaleUpperCase('es-ES'));
}

/** Un decimal fijo: 13.8, 8.0. Las medias siempre se leen con la misma precisión. */
export function decimal(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toFixed(digits);
}

/**
 * Entero con separador de millar español: 8.800
 * Se agrupa a mano en vez de con toLocaleString porque este depende de los
 * datos ICU del entorno, que no siempre están completos.
 */
export function integer(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const rounded = Math.round(Number(value));
  const sign = rounded < 0 ? '-' : '';
  return sign + String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

/** Ratio 0-1 como porcentaje: 0.641 -> "64.1%". null cuando no hubo intentos. */
export function percent(ratio, digits = 1) {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return '—';
  return `${(ratio * 100).toFixed(digits)}%`;
}

/** Signo explícito para el plus/minus: +6.9 / -2.1 */
export function signed(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const n = Number(value);
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`;
}

export function madeOfAttempts(made, attempts) {
  if (!attempts) return '0/0';
  return `${made}/${attempts}`;
}

/**
 * Los nombres de equipo llegan de la FEB en mayúsculas ("CB MORVEDRE").
 * Se pasan a capital inicial para leerlos, respetando siglas de 1-3 letras
 * (CB, BC, C.B.) y minúsculas de enlace.
 */
export function teamName(raw) {
  if (!raw) return '';
  return raw
    .split(/\s+/)
    .map((palabra, indice) => {
      if (esSigla(palabra)) return palabra.toLocaleUpperCase('es-ES');
      const minuscula = palabra.toLocaleLowerCase('es-ES');
      if (indice > 0 && CONECTORES.has(minuscula)) return minuscula;
      return capitalizarSegmentos(minuscula);
    })
    .join(' ');
}

/** "04/10/2025" -> "4 oct" */
const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

export function shortDate(ddmmyyyy) {
  if (!ddmmyyyy) return '—';
  const [day, month] = ddmmyyyy.split('/');
  const index = Number(month) - 1;
  if (Number.isNaN(index) || !MONTHS[index]) return ddmmyyyy;
  return `${Number(day)} ${MONTHS[index]}`;
}

/** Proporción 0-100 para el ancho de una barra, acotada. */
export function barWidth(value, max) {
  if (!max || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, (value / max) * 100));
}
