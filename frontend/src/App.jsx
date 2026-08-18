import React, { useState, useEffect } from 'react';
import { Container, Header, Nav, Section, MetricGrid, Loading, Error } from './Components';

function App() {
  const [section, setSection] = useState('jugadores');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const loadData = async (endpoint) => {
    try {
      setError(null);
      const res = await fetch(`/api/v1${endpoint}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      setData(result);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    loadData('/jugadores/1/estadisticas?temporada=2024');
  }, []);

  return (
    <Container>
      <Header />
      <nav class="nav">
        <a href="#" onClick={e => { e.preventDefault(); setSection('jugadores'); }}>Jugadores</a>
        <a href="#" onClick={e => { e.preventDefault(); setSection('lineups'); }}>Quintetos</a>
        <a href="#" onClick={e => { e.preventDefault(); setSection('estadisticas'); }}>Líderes</a>
        <a href="#" onClick={e => { e.preventDefault(); setSection('partidos'); }}>Partidos</a>
      </nav>

      <Section>
        {error && <div className="error">Error: {error}</div>}
        {data && <MetricGrid data={data} />}
        {!data && !error && <p className="loading">Cargando datos...</p>}
      </Section>
    </Container>
  );
}

export default App;
