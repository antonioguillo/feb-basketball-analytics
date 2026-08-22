import { BallIcon, InfoIcon } from './Icons.jsx';
import { href } from '../lib/router.js';

/* La sección de Partidos aparece en la navegación porque forma parte del
   producto, pero todavía no tiene pantalla diseñada: se muestra desactivada
   en vez de enlazar a una página vacía. */
const NAV = [
  { key: 'dashboard', label: 'Dashboard', to: href.dashboard() },
  { key: 'players', label: 'Jugadores', to: null },
  { key: 'compare', label: 'Comparar', to: href.compare() },
  { key: 'teams', label: 'Equipos', to: href.teams() },
  { key: 'games', label: 'Partidos', to: null },
];

function NavItem({ item, active }) {
  const style = {
    fontSize: '0.9375rem',
    paddingBottom: 3,
    borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
    color: active ? 'var(--ink)' : 'var(--muted)',
    fontWeight: active ? 500 : 400,
  };

  if (!item.to) {
    return (
      <span
        style={{ ...style, color: 'var(--faint)', cursor: 'not-allowed' }}
        aria-disabled="true"
        title="Pendiente de diseño"
      >
        {item.label}
      </span>
    );
  }

  return (
    <a href={item.to} style={style} aria-current={active ? 'page' : undefined}>
      {item.label}
    </a>
  );
}

/** Aviso permanente cuando la interfaz está mostrando los datos de ejemplo. */
function FixtureNotice() {
  return (
    <div
      role="status"
      style={{
        background: 'var(--surface-2)',
        borderBottom: '1px solid var(--border)',
        color: 'var(--muted)',
        fontSize: '0.8125rem',
      }}
    >
      <div className="container row" style={{ gap: 9, padding: '9px 20px' }}>
        <InfoIcon />
        <span>
          Sin conexión con la API: se muestran <strong style={{ color: 'var(--ink)', fontWeight: 500 }}>datos de
          ejemplo</strong> incluidos en la aplicación (63 partidos reales del Grupo E-A 2025/2026).
        </span>
      </div>
    </div>
  );
}

export default function Layout({ children, activeNav, usingFixtures }) {
  return (
    <>
      <header
        style={{
          background: 'var(--surface-2)',
          borderBottom: '1px solid var(--border)',
          padding: '20px 0',
        }}
      >
        <div
          className="container row"
          style={{ justifyContent: 'space-between', gap: 24, flexWrap: 'wrap' }}
        >
          <a href={href.dashboard()} className="row" style={{ gap: 10, color: 'var(--accent)' }}>
            <BallIcon />
            <span style={{ fontSize: '1.5rem', fontWeight: 600 }}>FEB Basketball Scouting</span>
          </a>
          <nav className="row" style={{ gap: 20 }}>
            {NAV.map((item) => (
              <NavItem key={item.key} item={item} active={item.key === activeNav} />
            ))}
          </nav>
        </div>
      </header>

      {usingFixtures && <FixtureNotice />}

      <main className="container" style={{ padding: '32px 20px 48px' }}>{children}</main>
    </>
  );
}
