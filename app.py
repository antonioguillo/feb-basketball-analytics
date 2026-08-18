"""Frontend de scouting de baloncesto FEB - Interfaz Streamlit.

Conecta con la API REST y muestra datos de jugadores, equipos y partidos
de la Tercera FEB de manera interactiva.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional, Dict, Any
import requests
import time

# Configuración de página
st.set_page_config(
    page_title="FEB Basketball Scouting",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configuración de la API
API_BASE = "http://localhost:8000/api"


def api_get(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """Hace una petición GET a la API con manejo de errores."""
    url = f"{API_BASE}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            st.error(f"Error {resp.status_code} de la API: {resp.text}")
            return None
    except requests.RequestException as e:
        st.error(f"Error conectando con la API: {e}")
        return None


@st.cache_data(ttl=300)
def cargar_partidos(skip: int = 0, limit: int = 50, year: Optional[int] = None, winner: Optional[str] = None) -> pd.DataFrame:
    """Carga datos de partidos desde la API."""
    params = {"skip": skip, "limit": limit}
    if year:
        params["year"] = year
    if winner:
        params["winner"] = winner
    data = api_get("partidos", params)
    if data and "partidos" in data:
        return pd.DataFrame(data["partidos"])
    return pd.DataFrame()


@st.cache_data(ttl=300)
def cargar_equipos() -> pd.DataFrame:
    """Carga la lista de equipos."""
    data = api_get("equipos")
    if data and "equipos" in data:
        return pd.DataFrame(data["equipos"])
    return pd.DataFrame()


@st.cache_data(ttl=300)
def cargar_jugadores(skip: int = 0, limit: int = 100, team_id: Optional[int] = None) -> pd.DataFrame:
    """Carga la lista de jugadores."""
    params = {"skip": skip, "limit": limit}
    if team_id:
        params["team_id"] = team_id
    data = api_get("jugadores", params)
    if data and "jugadores" in data:
        return pd.DataFrame(data["jugadores"])
    return pd.DataFrame()


@st.cache_data(ttl=300)
def cargar_scouting_jugador(player_id: int) -> Optional[Dict[str, Any]]:
    """Carga las estadísticas de scouting de un jugador."""
    data = api_get(f"scouting/player/{player_id}")
    return data


def main():
    """Función principal de la aplicación."""
    st.title("🏀 FEB Basketball Scouting")
    st.markdown("Aplicación de scouting para la Tercera FEB 2026")
    
    # Menú lateral
    st.sidebar.title("Menú")
    page = st.sidebar.radio(
        "Navegar a",
        ["Dashboard", "Jugadores", "Equipos", "Partidos"],
    )
    
    if page == "Dashboard":
        mostrar_dashboard()
    elif page == "Jugadores":
        mostrar_jugadores()
    elif page == "Equipos":
        mostrar_equipos()
    elif page == "Partidos":
        mostrar_partidos()


def mostrar_dashboard():
    """Página dashboard general."""
    st.header("Dashboard General")
    
    # KPIs rápidos
    col1, col2, col3 = st.columns(3)
    
    with col1:
        partidos_data = cargar_partidos(limit=1)
        st.metric("Total de partidos cargados", len(partidos_data) if not partidos_data.empty else 0)
    
    with col2:
        equipos_data = cargar_equipos()
        num_equipos = len(equipos_data) if not equipos_data.empty else 0
        st.metric("Equipos participantes", num_equipos)
    
    with col3:
        jugadores_data = cargar_jugadores(limit=1)
        num_jugadores = len(jugadores_data) if not jugadores_data.empty else 0
        st.metric("Jugadores en base", num_jugadores)
    
    st.markdown("---")
    
    # Gráfico de puntos por año
    st.subheader("Puntos por año")
    partidos_data = cargar_partidos(limit=200)
    if not partidos_data.empty and "year" in partidos_data.columns:
        # Convertir year a numérico
        partidos_data["year"] = pd.to_numeric(partidos_data["year"], errors="coerce")
        fig = px.histogram(
            partidos_data,
            x="year",
            title="Distribución de partidos por temporada",
            nbins=5,
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Top equipos
    st.subheader("Equipos más frecuentes")
    if not equipos_data.empty:
        top_equipos = equipos_data.head(10)
        fig = px.bar(
            top_equipos,
            x="team_name",
            y="team_id",
            title="Equipos con más participaciones",
            orientation="h",
        )
        st.plotly_chart(fig, use_container_width=True)


def mostrar_jugadores():
    """Página de lista y búsqueda de jugadores."""
    st.header("👥 Buscar Jugadores")
    
    # Filtros
    col1, col2 = st.columns([2, 1])
    with col1:
        search_term = st.text_input("Buscar jugador por nombre", placeholder="Ej: ALARCON")
    with col2:
        equipos_data = cargar_equipos()
        equipo_opts = ["Todos"] + list(equipos_data["team_name"].unique()) if not equipos_data.empty else ["Todos"]
        selected_equipo = st.selectbox("Filtrar por equipo", equipo_opts)
    
    # Cargar jugadores con filtros
    team_id_filter = None
    if selected_equipo and selected_equipo != "Todos":
        equipo_row = equipos_data[equipos_data["team_name"] == selected_equipo]
        if not equipo_row.empty:
            team_id_filter = int(equipo_row.iloc[0]["team_id"])
    
    jugadores_df = cargar_jugadores(limit=200, team_id=team_id_filter)
    
    # Filtrar por término de búsqueda
    if search_term:
        mask = jugadores_df["player_name"].str.contains(search_term, case=False, na=False)
        jugadores_df = jugadores_df[mask]
    
    st.markdown(f"**Resultado: {len(jugadores_df)} jugadores encontrados**")
    
    # Tabla de jugadores
    if not jugadores_df.empty:
        # Formatear para display
        display_df = jugadores_df[[
            "player_name", "jersey", "year", "puntos", "minutes_played"
        ]].copy()
        display_df.columns = ["Nombre", "Nº", "Temporada", "Puntos", "Minutos"]
        display_df = display_df.sort_values("Puntos", ascending=False)
        
        st.dataframe(
            display_df,
            column_config={
                "Nombre": st.column_config.TextColumn("Nombre del jugador"),
                "Nº": st.column_config.NumberColumn("Nº Jersey"),
                "Temporada": st.column_config.NumberColumn("Temporada"),
                "Puntos": st.column_config.NumberColumn("Puntos por juego"),
                "Minutos": st.column_config.NumberColumn("Minutos por juego"),
            },
            height=400,
        )
        
        # Selector para ver scouting de jugador
        st.markdown("---")
        st.subheader("Ver scouting detallado")
        player_names = jugadores_df["player_name"].tolist()
        if player_names:
            selected_player_name = st.selectbox("Seleccionar jugador para scouting", player_names)
            # Encontrar el player_id
            player_row = jugadores_df[jugadores_df["player_name"] == selected_player_name]
            if not player_row.empty:
                player_id = int(player_row.iloc[0]["player_id"])
                scouting_data = cargar_scouting_jugador(player_id)
                
                if scouting_data:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("**Resumen de carrera**")
                        if scouting_data.get("career_averages"):
                            avg = scouting_data["career_averages"]
                            st.write(f"- **Puntos promedio**: {avg.get('points', 0):.1f}")
                            st.write(f"- **Minutos promedio**: {avg.get('minutes', 0):.1f}")
                            st.write(f"- **Rebotes promedio**: {avg.get('rebounds', 0):.1f}")
                            st.write(f"- **Asistencias promedio**: {avg.get('assists', 0):.1f}")
                    
                    with col_b:
                        st.markdown("**Estadísticas por juego**")
                        if scouting_data and "games" in scouting_data:
                            games_df = pd.DataFrame(scouting_data["games"])[
                                ["game_id", "date", "puntos", "minutes_played", "plus_minus"]
                            ]
                            games_df.columns = ["ID", "Fecha", "Puntos", "Minutos", "+/-"]
                            st.dataframe(games_df.head(10), height=200)
    else:
        st.info("No hay jugadores encontrados con los filtros aplicados.")


def mostrar_equipos():
    """Página de estadísticas de equipos."""
    st.header("🏀 Estadísticas de Equipos")
    
    equipos_data = cargar_equipos()
    if not equipos_data.empty:
        st.dataframe(equipos_data, use_container_width=True)
        
        st.markdown("---")
        st.subheader("Jugadores por equipo")
        
        # Seleccionar un equipo para ver sus jugadores
        equipo_names = ["Todos"] + list(equipos_data["team_name"].unique())
        selected_equipo = st.selectbox("Seleccionar equipo", equipo_names)
        
        if selected_equipo != "Todos":
            equipo_row = equipos_data[equipos_data["team_name"] == selected_equipo]
            team_id = int(equipo_row.iloc[0]["team_id"])
            jugadores_df = cargar_jugadores(team_id=team_id)
            
            if not jugadores_df.empty:
                st.write(f"**Jugadores del {selected_equipo}** ({len(jugadores_df)}):")
                st.dataframe(
                    jugadores_df[["player_name", "jersey", "puntos", "minutes_played"]],
                    column_config={
                        "player_name": "Jugador",
                        "jersey": "Nº",
                        "puntos": "Puntos",
                        "minutes_played": "Minutos",
                    },
                    height=300,
                )
    
    # Shot charts o análisis de tiros
    st.markdown("---")
    st.subheader("Análisis de tiros")
    shot_data = st.file_uploader("Subir datos de tiros (CSV)", type=["csv"])
    if shot_data:
        df_shots = pd.read_csv(shot_data)
        st.write("Vista previa de datos de tiros:", df_shots.head())


def mostrar_partidos():
    """Página de listado y detalle de partidos."""
    st.header("⚽ Partidos de Tercera FEB")
    
    # Filtros
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_term = st.text_input("Buscar partido", placeholder="Por fecha o resultado")
    with col2:
        year_opts = ["Todos"] + [2022, 2023, 2024, 2025, 2026]
        selected_year = st.selectbox("Temporada", year_opts)
    with col3:
        winner_opts = ["Todos", "local", "visitante"]
        selected_winner = st.selectbox("Ganador", winner_opts)
    
    # Cargar partidos
    partidos_df = cargar_partidos(
        limit=200,
        year=selected_year if selected_year != "Todos" else None,
        winner=selected_winner if selected_winner != "Todos" else None,
    )
    
    if not partidos_df.empty:
        # Aplicar búsqueda de texto
        if search_term:
            mask = (
                partidos_df["date"].str.contains(search_term, na=False, case=False)
                | (partidos_df["home_score"].astype(str) + "-" + partidos_df["away_score"].astype(str)).str.contains(search_term, na=False)
            )
            partidos_df = partidos_df[mask]
        
        st.markdown(f"**{len(partidos_df)} partidos encontrados**")
        
        # Formatear para display
        display_df = partidos_df[[
            "date", "home_score", "away_score", "total_points", "winner", "year"
        ]].copy()
        display_df.columns = ["Fecha", "Local", "Visitante", "Total Puntos", "Ganador", "Temporada"]
        display_df = display_df.sort_values("Fecha", ascending=False)
        
        st.dataframe(display_df, use_container_width=True, height=400)
        
        # Detalle de partido seleccionado
        st.markdown("---")
        st.subheader("Detalle del partido")
        
        if not partidos_df.empty:
            # Crear opción de selección
            partido_options = [
                f"{row['date']} - {row['home_score']}-{row['away_score']} ({row['winner']})"
                for _, row in partidos_df.iterrows()
            ]
            selected_idx = st.selectbox(
                "Seleccionar partido para ver detalle",
                range(len(partido_options)),
                format_func=lambda x: partido_options[x],
            )
            
            selected_partido = partidos_df.iloc[selected_idx]
            st.write(f"**Fecha**: {selected_partido['date']}")
            st.write(f"**Local**: {selected_partido['home_score']} - **Visitante**: {selected_partido['away_score']}")
            st.write(f"**Total**: {selected_partido['total_points']} | **Ganador**: {selected_partido['winner']}")
    else:
        st.info("No hay partidos con los filtros aplicados.")


if __name__ == "__main__":
    main()