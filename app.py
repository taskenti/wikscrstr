import streamlit as st
import pandas as pd
import sqlite3
import json
import logging
import time
from pathlib import Path
from datetime import datetime

# Importación de librerías de mapeo
try:
    import folium
    from streamlit_folium import st_folium
    from folium.plugins import HeatMap, MarkerCluster, Fullscreen
except ImportError:
    st.error("⚠️ Faltan librerías críticas. Ejecuta: pip install streamlit-folium folium")
    st.stop()

# Importación del MOTOR (El script denso anterior)
try:
    from wikiloc_scraper_engine import WikilocHarvester, DB_SCHEMA
except ImportError:
    st.error("⚠️ CRITICAL: No se encuentra 'wikiloc_scraper_engine.py'. Asegúrate de que el backend está en la carpeta.")
    st.stop()

# --- CONFIGURACIÓN DE LA CONSOLA ---
st.set_page_config(
    page_title="🍄 MYCO-INTEL | Command Center",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS "Dark Mode / Cyberpunk" para sensación profesional
st.markdown("""
<style>
    .reportview-container { background: #0e1117; }
    .main-header { font-family: 'Courier New', monospace; color: #00FF00; text-shadow: 0px 0px 10px #00FF00; }
    .metric-box { border: 1px solid #333; padding: 15px; border-radius: 5px; background: #1f2937; text-align: center; }
    .stButton>button { border: 1px solid #00FF00; color: #00FF00; background: transparent; border-radius: 0px; font-family: 'Courier New'; }
    .stButton>button:hover { background: #00FF00; color: black; }
    .status-log { font-family: 'Courier New'; font-size: 12px; color: #00FF00; background: black; padding: 10px; height: 300px; overflow-y: scroll; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- UTILS & DB ---
DB_PATH = "wikiloc_pro.db"

class StreamlitLogHandler(logging.Handler):
    """Captura los logs del Backend y los muestra en la UI."""
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.log_buffer = []

    def emit(self, record):
        msg = self.format(record)
        self.log_buffer.append(msg)
        # Mantener solo las últimas 50 líneas
        if len(self.log_buffer) > 50: self.log_buffer.pop(0)
        self.widget.code("\n".join(self.log_buffer), language="bash")

@st.cache_data(ttl=10)
def load_data_snapshot():
    """Carga rápida de datos SQL para el dashboard."""
    if not Path(DB_PATH).exists(): return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM tracks", conn)
        conn.close()
        
        # Parsear JSON de coordenadas si es necesario para visualización masiva
        # (Lo hacemos lazy para no bloquear)
        return df
    except Exception as e:
        st.error(f"Error DB: {e}")
        return pd.DataFrame()

# --- INTERFAZ PRINCIPAL ---

st.sidebar.title("📡 MYCO-INTEL")
st.sidebar.markdown("`v3.0.0 INDUSTRIAL`")
mode = st.sidebar.radio("Módulos:", [
    "📊 Dashboard Táctico", 
    "🚜 Operaciones (Harvester)", 
    "🗺️ Inteligencia Geoespacial", 
    "🔬 Forense de Tracks"
])

# ==============================================================================
# MÓDULO 1: DASHBOARD TÁCTICO
# ==============================================================================
if mode == "📊 Dashboard Táctico":
    st.markdown("<h1 class='main-header'>ESTADO DE LA MISIÓN</h1>", unsafe_allow_html=True)
    
    df = load_data_snapshot()
    
    if df.empty:
        st.warning("⚠️ Base de datos vacía o no inicializada. Ve a 'Operaciones' para iniciar una campaña.")
    else:
        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        
        total_tracks = len(df)
        # Probabilidad > 50
        candidates = len(df[df['mushroom_probability'] > 50])
        # Tortuosidad media de los candidatos
        avg_tort = df[df['mushroom_probability'] > 50]['tortuosity_index'].mean() if candidates > 0 else 0
        # Tracks con ZigZag detectado
        zigzag_count = df['has_zigzag'].sum()

        c1.markdown(f"<div class='metric-box'><h2>{total_tracks}</h2><small>RUTAS ESCANEADAS</small></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-box'><h2 style='color:#00FF00'>{candidates}</h2><small>OBJETIVOS CONFIRMADOS</small></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-box'><h2>{avg_tort:.2f}</h2><small>ÍNDICE TORTUOSIDAD MEDIO</small></div>", unsafe_allow_html=True)
        c4.markdown(f"<div class='metric-box'><h2>{zigzag_count}</h2><small>PATRONES ZIGZAG</small></div>", unsafe_allow_html=True)

        st.markdown("---")
        
        # Top Targets
        st.subheader("🏆 Objetivos de Alta Prioridad (Top 10)")
        top_df = df.sort_values(by="mushroom_probability", ascending=False).head(10)
        
        st.dataframe(
            top_df[['title', 'mushroom_probability', 'tortuosity_index', 'stop_count', 'total_dist_km']],
            column_config={
                "mushroom_probability": st.column_config.ProgressColumn("Prob. Seta", format="%.0f%%", min_value=0, max_value=100),
                "tortuosity_index": st.column_config.NumberColumn("Tortuosidad", format="%.2f"),
                "title": "Nombre del Track"
            },
            use_container_width=True
        )

# ==============================================================================
# MÓDULO 2: OPERACIONES (LANZADOR)
# ==============================================================================
elif mode == "🚜 Operaciones (Harvester)":
    st.markdown("<h1 class='main-header'>CONSOLA DE EXTRACCIÓN</h1>", unsafe_allow_html=True)
    
    col_map, col_ctrl = st.columns([2, 1])
    
    with col_map:
        st.markdown("### 📍 Selector de Objetivo")
        # Mapa para seleccionar coordenadas
        default_coords = [40.416, -3.703]
        if 'last_click' not in st.session_state: st.session_state.last_click = default_coords
        
        m = folium.Map(location=st.session_state.last_click, zoom_start=6, tiles="CartoDB dark_matter")
        folium.Marker(st.session_state.last_click, icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")).add_to(m)
        
        out = st_folium(m, height=400, width="100%")
        
        if out['last_clicked']:
            st.session_state.last_click = [out['last_clicked']['lat'], out['last_clicked']['lng']]
            st.rerun()

    with col_ctrl:
        st.markdown("### ⚙️ Parámetros de Campaña")
        lat, lon = st.session_state.last_click
        st.write(f"**Lat:** {lat:.4f} | **Lon:** {lon:.4f}")
        
        zone_name = st.text_input("Nombre en Clave", f"Op_Sector_{int(time.time())}")
        radius = st.slider("Radio de Cobertura (km)", 2, 20, 5)
        headless = st.checkbox("Modo Stealth (Headless)", value=False, help="Desactiva para ver el navegador trabajar.")
        
        launch = st.button("🚀 INICIAR SECUENCIA DE EXTRACCIÓN", type="primary")

    # LOG TERMINAL
    st.markdown("### 📟 Terminal de Salida")
    log_placeholder = st.empty()
    
    if launch:
        # Configurar Logging redirect
        harvester_logger = logging.getLogger("MushroomHunter")
        handler = StreamlitLogHandler(log_placeholder)
        harvester_logger.addHandler(handler)
        harvester_logger.setLevel(logging.INFO)
        
        try:
            harvester = WikilocHarvester(db_path=DB_PATH, headless=headless)
            with st.spinner("📡 Desplegando Grid Hexagonal y Sondas..."):
                harvester.run_campaign(zone_name, lat, lon, radius)
            st.success("✅ Campaña finalizada. Datos asegurados en SQL.")
        except Exception as e:
            st.error(f"❌ Error en operación: {e}")
        finally:
            harvester_logger.removeHandler(handler)

# ==============================================================================
# MÓDULO 3: INTELIGENCIA GEOESPACIAL
# ==============================================================================
elif mode == "🗺️ Inteligencia Geoespacial":
    st.markdown("<h1 class='main-header'>VISUALIZACIÓN DE PATRONES</h1>", unsafe_allow_html=True)
    
    df = load_data_snapshot()
    if df.empty: st.stop()
    
    # Extraer coordenadas aproximadas (para el mapa general usamos la lat/lon del JSON o un promedio)
    # Como el scraper guarda JSON crudo, necesitamos extraer el primer punto de cada track para pintarlo
    
    def get_start_point(json_str):
        try:
            coords = json.loads(json_str)
            if coords and len(coords) > 0: return coords[0]
        except: return None
        return None

    # Procesamiento previo (cacheable en producción)
    df['start_coord'] = df['raw_coords_json'].apply(get_start_point)
    valid_df = df.dropna(subset=['start_coord'])
    
    # Filtros laterales
    st.sidebar.header("Filtros de Capa")
    min_prob = st.sidebar.slider("Probabilidad Mínima", 0, 100, 30)
    layer_type = st.sidebar.selectbox("Tipo de Capa", ["Mapa de Hallazgos", "Heatmap de Tortuosidad", "Heatmap de Entropía"])
    
    filtered_df = valid_df[valid_df['mushroom_probability'] >= min_prob]
    
    if filtered_df.empty:
        st.warning("No hay datos que cumplan los filtros.")
    else:
        # Centro del mapa
        center_lat = filtered_df.iloc[0]['start_coord'][0]
        center_lon = filtered_df.iloc[0]['start_coord'][1]
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="CartoDB dark_matter")
        Fullscreen().add_to(m)

        if layer_type == "Mapa de Hallazgos":
            marker_cluster = MarkerCluster().add_to(m)
            for _, row in filtered_df.iterrows():
                coord = row['start_coord']
                prob = row['mushroom_probability']
                
                # Color coding
                color = "#00FF00" if prob > 80 else "#FFA500" if prob > 50 else "#FF0000"
                
                popup_html = f"""
                <div style='font-family:monospace'>
                <b>{row['title']}</b><br>
                Prob: {prob:.1f}%<br>
                Tort: {row['tortuosity_index']:.2f}<br>
                Entropía: {row['entropy_score']:.2f}
                </div>
                """
                
                folium.CircleMarker(
                    location=coord,
                    radius=5 + (prob/10),
                    color=color,
                    fill=True,
                    fill_opacity=0.7,
                    popup=popup_html
                ).add_to(marker_cluster)

        elif layer_type == "Heatmap de Tortuosidad":
            # Ponderamos el heatmap por el índice de tortuosidad
            # Dónde la gente da más vueltas
            heat_data = [
                [row['start_coord'][0], row['start_coord'][1], row['tortuosity_index']] 
                for _, row in filtered_df.iterrows()
            ]
            HeatMap(heat_data, radius=15, blur=10, gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}).add_to(m)
            
        elif layer_type == "Heatmap de Entropía":
            # Ponderamos por entropía (caos direccional)
            heat_data = [
                [row['start_coord'][0], row['start_coord'][1], row['entropy_score']] 
                for _, row in filtered_df.iterrows()
            ]
            HeatMap(heat_data, radius=15, blur=10, gradient={0.4: 'purple', 0.65: 'orange', 1: 'yellow'}).add_to(m)

        st_folium(m, width="100%", height=600)

# ==============================================================================
# MÓDULO 4: FORENSE
# ==============================================================================
elif mode == "🔬 Forense de Tracks":
    st.markdown("<h1 class='main-header'>ANÁLISIS FORENSE DE GEOMETRÍA</h1>", unsafe_allow_html=True)
    
    df = load_data_snapshot()
    if df.empty: st.stop()
    
    # Selector de Track
    track_options = df.sort_values("mushroom_probability", ascending=False)
    selected_track_name = st.selectbox("Seleccionar Evidencia:", track_options['title'] + " | ID: " + track_options['external_id'])
    
    if selected_track_name:
        track_ext_id = selected_track_name.split(" | ID: ")[1]
        track_data = df[df['external_id'] == track_ext_id].iloc[0]
        
        # Parsear Geometría completa
        try:
            coords = json.loads(track_data['raw_coords_json'])
        except:
            coords = []
            st.error("Error corrompido de geometría.")

        # Panel de Detalles
        col_metrics, col_viz = st.columns([1, 2])
        
        with col_metrics:
            st.markdown("### 🧬 Biometría del Recorrido")
            st.info(f"Probabilidad Seta: {track_data['mushroom_probability']:.1f}%")
            
            st.metric("Tortuosidad", f"{track_data['tortuosity_index']:.2f}", help="> 1.5 indica patrón no lineal")
            st.metric("Entropía (Caos)", f"{track_data['entropy_score']:.2f}", help="Indica cambios bruscos de dirección")
            st.metric("Paradas/Nudos", int(track_data['stop_count']), help="Zonas de recolección potencial")
            st.markdown("---")
            st.write(f"**Distancia:** {track_data['total_dist_km']} km")
            st.write(f"**ZigZag:** {'DETECTADO' if track_data['has_zigzag'] else 'Negativo'}")

        with col_viz:
            st.markdown("### 🗺️ Reconstrucción de Ruta")
            if coords:
                center = coords[len(coords)//2]
                m = folium.Map(location=center, zoom_start=14, tiles="CartoDB positron")
                
                # Dibujar Polilínea
                # Colorcoding según tortuosidad para ver visualmente si es interesante
                color = "red" if track_data['mushroom_probability'] > 60 else "blue"
                folium.PolyLine(coords, color=color, weight=3, opacity=0.8).add_to(m)
                
                # Marcar Inicio y Fin
                folium.Marker(coords[0], popup="Inicio", icon=folium.Icon(color="green", icon="play")).add_to(m)
                folium.Marker(coords[-1], popup="Fin", icon=folium.Icon(color="red", icon="stop")).add_to(m)
                
                st_folium(m, width="100%", height=500)
            else:
                st.warning("Sin datos de geometría disponibles.")
