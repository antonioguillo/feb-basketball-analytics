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
