import React from 'react';

const Header = () => {
  return (
    <header style={{
      background: '#21262d',
      padding: '20px 0',
      position: 'fixed',
      width: '100%',
      top: 0,
      zIndex: 100
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 600, color: '#e6e04c' }}>FEB Basketball Scouting</div>
        <nav style={{ display: 'flex', gap: '20px' }}>
          <a href="#" style={{ color: '#8b949e', textDecoration: 'none', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color = '#f2d049'} onMouseOut={e => e.target.style.color = '#8b949e'}>Jugadores</a>
          <a href="#" style={{ color: '#8b949e', textDecoration: 'none', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color = '#f2d049'} onMouseOut={e => e.target.style.color = '#8b949e'}>Quintetos</a>
          <a href="#" style={{ color: '#8b949e', textDecoration: 'none', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color = '#f2d049'} onMouseOut={e => e.target.style.color = '#8b949e'}>Líderes</a>
          <a href="#" style={{ color: '#8b949e', textDecoration: 'none', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color = '#f2d049'} onMouseOut={e => e.target.style.color = '#8b949e'}>Partidos</a>
        </nav>
      </div>
    </header>
  );
};

export default Header;
