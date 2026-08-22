import { BallIcon, InfoIcon, LigasIcon, PlayersIcon, TeamsIcon, CompareIcon } from './Icons.jsx';
import { href } from '../lib/router.js';

const NAV = [
  { key: 'ligas', label: 'Ligas', to: href.ligas(), Icon: LigasIcon },
  { key: 'players', label: 'Jugadores', to: href.players(), Icon: PlayersIcon },
  { key: 'teams', label: 'Equipos', to: href.teams(), Icon: TeamsIcon },
  { key: 'compare', label: 'Comparar', to: href.compare(), Icon: CompareIcon },
];

/** Item de la navegación: agrupados en una píldora, el activo lleva fondo
    sólido en vez de solo un subrayado — se lee como una app, no como una
    lista de enlaces de una página cualquiera. */
function NavItem({ item, active }) {
  const { Icon } = item;
  return (
    <a
      href={item.to}
      aria-current={active ? 'page' : undefined}
      className="row"
      style={{
        gap: 7,
        padding: '8px 14px',
        borderRadius: 7,
        background: active ? 'var(--surface-2)' : 'transparent',
        color: active ? 'var(--ink)' : 'var(--muted)',
        fontSize: '0.8438rem',
        fontWeight: active ? 600 : 500,
      }}
    >
      <Icon color={active ? 'var(--accent)' : 'var(--muted)'} />
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
          ejemplo</strong> incluidos en la aplicación (615 partidos reales de Tercera FEB 2025/2026).
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
          background: 'var(--surface)',
          borderBottom: '1px solid var(--border)',
          padding: '16px 0',
        }}
      >
        <div
          className="container row"
          style={{ justifyContent: 'space-between', gap: 28, flexWrap: 'wrap' }}
        >
          <a href={href.ligas()} className="row" style={{ gap: 9 }}>
            <BallIcon />
            <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.01em' }}>
              FEB Basketball Scouting
            </span>
          </a>
          <nav
            className="row"
            style={{ gap: 2, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: 4 }}
          >
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
