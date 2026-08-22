/** Iconos en SVG trazado, sobre rejilla de 24, para que escalen y recoloreen. */

export function BallIcon({ size = 22, color = 'var(--accent)' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.6" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3v18M3 12h18M5.6 5.6c3.6 3.6 3.6 9.2 0 12.8M18.4 5.6c-3.6 3.6-3.6 9.2 0 12.8" />
    </svg>
  );
}

export function ChevronDown({ size = 12, color = 'var(--muted)' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.4" aria-hidden="true">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function ArrowLeft({ size = 14, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" aria-hidden="true">
      <path d="M19 12H5M11 18l-6-6 6-6" />
    </svg>
  );
}

export function InfoIcon({ size = 15, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 7.5v.5" strokeLinecap="round" />
    </svg>
  );
}

export function AlertIcon({ size = 18, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" aria-hidden="true">
      <path d="M12 4.5 2.8 20h18.4L12 4.5Z" strokeLinejoin="round" />
      <path d="M12 10v4M12 17.2v.3" strokeLinecap="round" />
    </svg>
  );
}

/* Iconos de la navegación principal: una barra por sección, no decoración. */

export function LigasIcon({ size = 16, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M4 20V13M12 20V8M20 20V4" />
    </svg>
  );
}

export function PlayersIcon({ size = 16, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="8" r="3.4" />
      <path d="M5.5 20c1-4.2 3.4-6.4 6.5-6.4s5.5 2.2 6.5 6.4" />
    </svg>
  );
}

export function TeamsIcon({ size = 16, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3.5l6.5 2.6v5.2c0 4.6-2.9 7.6-6.5 8.7-3.6-1.1-6.5-4.1-6.5-8.7V6.1L12 3.5z" />
    </svg>
  );
}

export function CompareIcon({ size = 16, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="6" width="11" height="14" rx="2" />
      <rect x="10" y="4" width="11" height="14" rx="2" />
    </svg>
  );
}
