import React from 'react';

const MetricGrid = ({ data }) => {
  if (!data) return <div>Sin datos</div>;
  
  const { total_partidos, metricas_promedio, per_36_stats, double_doubles, triple_doubles } = data;
  
  return (
    <div className="grid">
      <div className="card">
        <h3>Resumen</h3>
        <div className="metric">Partidos jugados: {total_partidos || 0}</div>
        <div className="metric">Puntos promedio: {metricas_promedio ? metricas_promedio.puntos_promedio.toFixed(1) : 'N/A'}</div>
        <div className="metric">Dobles dobles: {double_doubles || 0}</div>
        <div className="metric">Triple dobles: {triple_doubles || 0}</div>
      </div>
      
      <div className="card">
        <h3>Estadísticas por 36 minutos</h3>
        <div className="metric">Puntos: {per_36_stats && per_36_stats.points ? per_36_stats.points.toFixed(1) : 'N/A'}</div>
        <div className="metric">Rebotes: {per_36_stats && per_36_stats.rebounds ? per_36_stats.rebounds.toFixed(1) : 'N/A'}</div>
        <div className="metric">Asistencias: {per_36_stats && per_36_stats.assists ? per_36_stats.assists.toFixed(1) : 'N/A'}</div>
      </div>
      
      <div className="card">
        <h3>Eficiencia</h3>
        <div className="metric">TS%: {metricas_promedio && metricas_promedio.true_shooting_pct ? (metricas_promedio.true_shooting_pct * 100).toFixed(1) + '%' : 'N/A'}</div>
        <div className="metric">eFG%: {metricas_promedio && metricas_promedio.effective_fg_pct ? (metricas_promedio.effective_fg_pct * 100).toFixed(1) + '%' : 'N/A'}</div>
      </div>
    </div>
  );
}

export default MetricGrid;
