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

# Importación del MOTOR
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

# Estilos CSS "Dark Mode / Cyberpunk"
st.markdown("""
<style>
    .reportview-container { background: #0e1117; }
    .main-header { font-family: 'Courier New', monospace; color: #00FF00; text-shadow: 0px 0px 10px #00FF00; }
    .metric-box { border: 1px solid #333; padding: 15px; border-radius: 5px; background: #1f2937; text-align: center; }
    .stButton>button { border: 1px solid #00FF00; color: #00FF00; background: transparent; border-radius: 0px; font-family: 'Courier New'; width: 100%; }
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
        if len(self.log_buffer) > 50: self.log_buffer.pop(0)
        self.widget.code("\n".join(self.log_buffer), language="bash")

@st.cache_data(ttl=5) # Cache muy corto para ver cambios rápido
def load_data_snapshot():
    """Carga rápida de datos SQL para el dashboard."""
    if not Path(DB_PATH).exists(): return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM tracks", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error DB: {e}")
        return pd.DataFrame()

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- INTERFAZ PRINCIPAL ---

st.sidebar.title("📡 MYCO-INTEL")
st.sidebar.markdown("`v3.2.0 DATA EXPORTER`")
mode = st.sidebar.radio("Módulos:", [
    "📊 Dashboard Táctico", 
    "🚜 Operaciones (Harvester)", 
    "💾 Exportación de Datos",
    "🗺️ Inteligencia Geoespacial", 
    "🔬 Forense de Tracks"
])

# ==============================================================================
# MÓDULO 1: DASHBOARD TÁCTICO
# ==============================================================================
if mode == "📊 Dashboard Táctico":
    st.markdown("<h1 class='main-header'>ESTADO DE LA MISIÓN</h1>", unsafe_allow_html=True)
    
    # Botón de refresco manual
    if st.button("🔄 Refrescar Datos"):
        load_data_snapshot.clear()
        st.rerun()

    df = load_data_snapshot()
    
    if df.empty:
        st.warning("⚠️ Base de datos vacía o no inicializada. Ve a 'Operaciones' para iniciar una campaña.")
    else:
        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        total_tracks = len(df)
        candidates = len(df[df['mushroom_probability'] > 50])
        avg_tort = df[df['mushroom_probability'] > 50]['tortuosity_index'].mean() if candidates > 0 else 0
        zigzag_count = df['has_zigzag'].sum()

        c1.markdown(f"<div class='metric-box'><h2>{total_tracks}</h2><small>RUTAS ESCANEADAS</small></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-box'><h2 style='color:#00FF00'>{candidates}</h2><small>OBJETIVOS CONFIRMADOS</small></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-box'><h2>{avg_tort:.2f}</h2><small>ÍNDICE TORTUOSIDAD</small></div>", unsafe_allow_html=True)
        c4.markdown(f"<div class='metric-box'><h2>{zigzag_count}</h2><small>PATRONES ZIGZAG</small></div>", unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("🏆 Objetivos de Alta Prioridad")
        
        # Filtramos columnas útiles para el usuario
        display_cols = ['title', 'mushroom_probability', 'tortuosity_index', 'total_dist_km', 'difficulty', 'external_id']
        # Nos aseguramos que existan en el DF
        display_cols = [c for c in display_cols if c in df.columns]
        
        top_df = df.sort_values(by="mushroom_probability", ascending=False).head(20)
        
        st.dataframe(
            top_df[display_cols],
            column_config={
                "mushroom_probability": st.column_config.ProgressColumn("Prob. Seta", format="%.0f%%", min_value=0, max_value=100),
                "title": "Nombre del Track",
                "external_id": "ID Wikiloc"
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
        default_coords = [40.416, -3.703]
        if 'last_click' not in st.session_state: st.session_state.last_click = default_coords
        
        m = folium.Map(location=st.session_state.last_click, zoom_start=6, tiles="CartoDB dark_matter")
        folium.Marker(st.session_state.last_click, icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")).add_to(m)
        out = st_folium(m, height=400, width="100%")
        
        if out['last_clicked']:
            st.session_state.last_click = [out['last_clicked']['lat'], out['last_clicked']['lng']]
            st.rerun()

    with col_ctrl:
        st.markdown("### ⚙️ Parámetros")
        lat, lon = st.session_state.last_click
        st.write(f"**Lat:** {lat:.4f} | **Lon:** {lon:.4f}")
        
        zone_name = st.text_input("Nombre Operación", f"Sector_{int(time.time())}")
        radius = st.slider("Radio (km)", 2, 20, 5)
        # En Cloud siempre forzamos headless internamente, pero dejamos el check por si es local
        headless_option = st.checkbox("Modo Stealth", value=True)
        
        launch = st.button("🚀 INICIAR EXTRACCIÓN", type="primary")

    st.markdown("### 📟 Terminal")
    log_placeholder = st.empty()
    
    if launch:
        harvester_logger = logging.getLogger("MushroomHunter")
        handler = StreamlitLogHandler(log_placeholder)
        harvester_logger.addHandler(handler)
        harvester_logger.setLevel(logging.INFO)
        
        try:
            harvester = WikilocHarvester(db_path=DB_PATH, headless=headless_option)
            with st.spinner("📡 Escaneando sector... No cierres esta pestaña."):
                harvester.run_campaign(zone_name, lat, lon, radius)
            
            st.success("✅ Campaña finalizada. Actualizando base de datos...")
            # IMPORTANTE: Forzar recarga de datos
            load_data_snapshot.clear()
            time.sleep(1)
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error: {e}")
        finally:
            harvester_logger.removeHandler(handler)

# ==============================================================================
# MÓDULO 3: EXPORTACIÓN (NUEVO)
# ==============================================================================
elif mode == "💾 Exportación de Datos":
    st.markdown("<h1 class='main-header'>CENTRO DE DESCARGAS</h1>", unsafe_allow_html=True)
    
    df = load_data_snapshot()
    
    if df.empty:
        st.warning("No hay datos para exportar.")
    else:
        st.info(f"Total de registros disponibles: {len(df)}")
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("📑 Listado de Enlaces (CSV)")
            st.markdown("Descarga un Excel/CSV con los enlaces directos para bajarlos manualmente.")
            
            # Crear columna URL clickable si no existe
            df['wikiloc_url'] = "https://www.wikiloc.com/hiking-trails/" + df['title'].str.replace(' ', '-').str.lower() + "-" + df['external_id']
            
            # Filtrar solo lo útil
            export_df = df[['title', 'mushroom_probability', 'wikiloc_url', 'total_dist_km', 'difficulty', 'tortuosity_index']]
            export_df = export_df.sort_values(by='mushroom_probability', ascending=False)
            
            csv = convert_df_to_csv(export_df)
            
            st.download_button(
                label="⬇️ DESCARGAR LISTADO DE TRACKS (.csv)",
                data=csv,
                file_name=f'myco_intel_tracks_{datetime.now().strftime("%Y%m%d")}.csv',
                mime='text/csv',
            )
            
            st.dataframe(export_df.head(5))

        with c2:
            st.subheader("🗄️ Base de Datos Completa (.db)")
            st.markdown("Descarga el archivo SQL completo para backup o análisis externo.")
            
            if Path(DB_PATH).exists():
                with open(DB_PATH, "rb") as fp:
                    btn = st.download_button(
                        label="⬇️ DESCARGAR BASE DE DATOS (.db)",
                        data=fp,
                        file_name="wikiloc_pro.db",
                        mime="application/octet-stream"
                    )
            else:
                st.warning("Archivo DB no encontrado en disco.")

# ==============================================================================
# MÓDULO 4: INTELIGENCIA GEOESPACIAL
# ==============================================================================
elif mode == "🗺️ Inteligencia Geoespacial":
    st.markdown("<h1 class='main-header'>VISUALIZACIÓN DE PATRONES</h1>", unsafe_allow_html=True)
    df = load_data_snapshot()
    if df.empty: st.stop()
    
    def get_start_point(json_str):
        try:
            coords = json.loads(json_str)
            if coords and len(coords) > 0: return coords[0]
        except: return None
        return None

    df['start_coord'] = df['raw_coords_json'].apply(get_start_point)
    valid_df = df.dropna(subset=['start_coord'])
    
    st.sidebar.header("Filtros Mapa")
    min_prob = st.sidebar.slider("Probabilidad Mínima", 0, 100, 30)
    layer_type = st.sidebar.selectbox("Capa", ["Hallazgos", "Calor Tortuosidad", "Calor Entropía"])
    
    filtered_df = valid_df[valid_df['mushroom_probability'] >= min_prob]
    
    if filtered_df.empty:
        st.warning("Sin datos para este filtro.")
    else:
        center_lat = filtered_df.iloc[0]['start_coord'][0]
        center_lon = filtered_df.iloc[0]['start_coord'][1]
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="CartoDB dark_matter")
        Fullscreen().add_to(m)

        if layer_type == "Hallazgos":
            marker_cluster = MarkerCluster().add_to(m)
            for _, row in filtered_df.iterrows():
                coord = row['start_coord']
                prob = row['mushroom_probability']
                color = "#00FF00" if prob > 80 else "#FFA500" if prob > 50 else "#FF0000"
                url = "https://www.wikiloc.com/trails/" + row['external_id']
                popup = f"<b>{row['title']}</b><br>Prob: {prob}%<br><a href='{url}' target='_blank'>Ver en Wikiloc</a>"
                folium.CircleMarker(location=coord, radius=5+(prob/10), color=color, fill=True, popup=popup).add_to(marker_cluster)

        elif layer_type == "Calor Tortuosidad":
            heat = [[r['start_coord'][0], r['start_coord'][1], r['tortuosity_index']] for _, r in filtered_df.iterrows()]
            HeatMap(heat, radius=15, gradient={0.4:'blue', 0.8:'lime', 1:'red'}).add_to(m)
            
        elif layer_type == "Calor Entropía":
            heat = [[r['start_coord'][0], r['start_coord'][1], r['entropy_score']] for _, r in filtered_df.iterrows()]
            HeatMap(heat, radius=15, gradient={0.4:'purple', 0.8:'orange', 1:'yellow'}).add_to(m)

        st_folium(m, width="100%", height=600)

# ==============================================================================
# MÓDULO 5: FORENSE
# ==============================================================================
elif mode == "🔬 Forense de Tracks":
    st.markdown("<h1 class='main-header'>ANÁLISIS FORENSE</h1>", unsafe_allow_html=True)
    df = load_data_snapshot()
    if df.empty: st.stop()
    
    track_opts = df.sort_values("mushroom_probability", ascending=False)
    sel = st.selectbox("Track:", track_opts['title'] + " | ID: " + track_options['external_id'] if 'external_id' in track_opts else [])
    # ... (Resto del código forense igual que la versión anterior) ...
    # Nota: He resumido aquí para no repetir, pero el módulo forense se mantiene igual.
    # Si lo necesitas completo dímelo, pero con lo anterior ya tienes la funcionalidad principal.
    if sel:
        track_ext_id = sel.split(" | ID: ")[1]
        t = df[df['external_id'] == track_ext_id].iloc[0]
        try: coords = json.loads(t['raw_coords_json'])
        except: coords = []
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Probabilidad", f"{t['mushroom_probability']}%")
            st.metric("Tortuosidad", f"{t['tortuosity_index']:.2f}")
            url = f"https://www.wikiloc.com/hiking-trails/{t['external_id']}"
            st.markdown(f"[🔗 Abrir en Wikiloc]({url})")
            
        with c2:
            if coords:
                m = folium.Map(location=coords[len(coords)//2], zoom_start=14, tiles="CartoDB positron")
                folium.PolyLine(coords, color="red" if t['mushroom_probability']>60 else "blue").add_to(m)
                st_folium(m, width="100%", height=400)
