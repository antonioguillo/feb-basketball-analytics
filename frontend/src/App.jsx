import { useState, useCallback } from 'react';
import Layout from './components/Layout.jsx';
import Dashboard from './pages/Dashboard.jsx';
import PlayerPage from './pages/Player.jsx';
import { ErrorState } from './components/Primitives.jsx';
import { useRoute, useNavigate, href } from './lib/router.js';

export default function App() {
  const route = useRoute();
  const navigate = useNavigate();
  const [source, setSource] = useState(null);

  const openPlayer = useCallback(
    (slug, context) => navigate(href.player(slug, context).slice(1)), [navigate]);
  // Cambiar competición, temporada o grupo se refleja en la ruta, así que el
  // estado se puede compartir por enlace y sobrevive a recargar la página.
  const cambiarContexto = useCallback(
    (context) => navigate(href.dashboard(context).slice(1)), [navigate]);
  const handleSource = useCallback((value) => setSource(value), []);

  let page;
  let activeNav;

  if (route.name === 'dashboard') {
    activeNav = 'dashboard';
    page = (
      <Dashboard
        context={route.context}
        onNavigate={openPlayer}
        onContextChange={cambiarContexto}
        onSource={handleSource}
      />
    );
  } else if (route.name === 'player') {
    activeNav = 'players';
    page = (
      <PlayerPage slug={route.slug} context={route.context} onSource={handleSource} />
    );
  } else {
    activeNav = null;
    page = (
      <ErrorState
        title="Página no encontrada"
        detail={`La ruta ${route.path} no existe.`}
        onRetry={() => {
          window.location.hash = href.dashboard().slice(1);
        }}
      />
    );
  }

  return (
    <Layout activeNav={activeNav} usingFixtures={source === 'fixtures'}>
      {page}
    </Layout>
  );
}
