import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import plotly.graph_objects as go
import json
import time
from dataclasses import asdict

# Librerías para mapas
try:
    from streamlit_folium import st_folium
    import folium
except ImportError:
    st.error("Falta instalar librerías. Ejecuta: pip install streamlit-folium folium")
    st.stop()

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="🍄 Detector Pro V2",
    page_icon="🍄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- IMPORTS DE MÓDULOS PROPIOS ---
try:
    # Scraper Pro y definiciones de Zonas
    from wikiloc_scraper import WikilocScraperPro, HotZone, SPANISH_HOT_ZONES, TrackDetails
    # Analizador de BD
    from wikiloc_analyzer import HotZoneAnalyzer
    # Detector Forense
    from mushroom_detector import MushroomTrackDetector
    # Conector Biológico (iNaturalist)
    from inaturalist_connector import INaturalistConnector
except ImportError as e:
    st.error(f"❌ Error crítico importando módulos: {e}")
    st.info("Asegúrate de tener en la carpeta: wikiloc_scraper.py, wikiloc_analyzer.py, mushroom_detector.py e inaturalist_connector.py")
    st.stop()

# --- FUNCIONES AUXILIARES ---
def init_filesystem():
    """Crea estructura de directorios."""
    Path("gpx_files").mkdir(parents=True, exist_ok=True)
    Path("descargas_wikiloc").mkdir(parents=True, exist_ok=True)
    Path("analysis_plots").mkdir(parents=True, exist_ok=True)

@st.cache_data(ttl=60)
def get_db_stats(db_path="wikiloc_cache.db"):
    """Estadísticas rápidas."""
    if not Path(db_path).exists(): return 0, 0, 0, 0
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        tc = cur.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        pc = cur.execute("SELECT COUNT(DISTINCT province) FROM tracks").fetchone()[0]
        gc = cur.execute("SELECT COUNT(*) FROM tracks WHERE gpx_content IS NOT NULL").fetchone()[0]
        conn.close()
        fc = len(list(Path("gpx_files").glob("*.gpx")))
        return tc, pc, gc, fc
    except: return 0, 0, 0, 0

init_filesystem()

# --- ESTILOS ---
st.markdown("""
<style>
    .main-header { font-size: 2.5rem; color: #2E7D32; text-align: center; margin-bottom: 1rem; }
    .stButton>button { border-radius: 8px; font-weight: bold; width: 100%; }
    .metric-card { background-color: #f0f2f6; padding: 1rem; border-radius: 10px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- ESTADO DE SESIÓN ---
if 'scraped_tracks' not in st.session_state: st.session_state.scraped_tracks = []
if 'custom_zone_coords' not in st.session_state: st.session_state.custom_zone_coords = None
if 'bio_obs' not in st.session_state: st.session_state.bio_obs = []

# --- SIDEBAR ---
st.sidebar.title("🍄 Detector Pro V2")
page = st.sidebar.radio(
    "Menú Principal:",
    ["🏠 Inicio", "🕷️ Scraper Avanzado", "🌿 Bio-Radar (iNaturalist)", "📊 Análisis Histórico", "🔍 Detector", "⚙️ Configuración"]
)
st.sidebar.markdown("---")
st.sidebar.info("**Versión:** 2.1 (Full Integration)\n\nScraping Pro + iNaturalist + Detector Forense")

# ==========================================
# 1. PÁGINA INICIO
# ==========================================
if page == "🏠 Inicio":
    st.markdown('<h1 class="main-header">🍄 Sistema de Inteligencia Micológica</h1>', unsafe_allow_html=True)
    st.markdown("### Panel de Control Unificado")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Motor Scraper", "Selenium V2", delta="Activo")
    col2.metric("Bio-Conexión", "iNaturalist API", delta="Online")
    col3.metric("Modo Ocultación", "Detectando", delta="ON")
    
    st.markdown("---")
    st.subheader("📦 Estado del Almacén de Datos")
    tc, pc, gc, fc = get_db_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracks BD", tc)
    c2.metric("Provincias", pc)
    c3.metric("GPX BD", gc)
    c4.metric("Archivos GPX", fc)

# ==========================================
# 2. PÁGINA SCRAPER PRO
# ==========================================
elif page == "🕷️ Scraper Avanzado":
    st.header("🕷️ Scraper Multi-Estrategia")
    
    # --- Configuración Zona ---
    st.subheader("1. Definir Zona")
    method = st.radio("Método:", ["📍 Zonas Predefinidas", "🗺️ Mapa Interactivo"], horizontal=True)
    target_zone = None
    
    if method == "📍 Zonas Predefinidas":
        z_names = [z.name for z in SPANISH_HOT_ZONES]
        sel_name = st.selectbox("Elige zona:", z_names)
        target_zone = next((z for z in SPANISH_HOT_ZONES if z.name == sel_name), None)
        if target_zone:
            m = folium.Map([target_zone.lat, target_zone.lon], zoom_start=9)
            folium.Circle([target_zone.lat, target_zone.lon], radius=target_zone.radius*1000, color="green").add_to(m)
            st_folium(m, height=200, width=500)
            
    else: # Mapa Interactivo
        st.info("Haz clic para fijar centro.")
        coords = st.session_state.custom_zone_coords or [40.416, -3.703]
        m = folium.Map(location=coords, zoom_start=6)
        if st.session_state.custom_zone_coords:
             folium.Marker(st.session_state.custom_zone_coords, icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")).add_to(m)
        output = st_folium(m, height=400, width="100%")
        if output['last_clicked']:
            lat, lon = output['last_clicked']['lat'], output['last_clicked']['lng']
            st.session_state.custom_zone_coords = [lat, lon]
            st.rerun()
            
        if st.session_state.custom_zone_coords:
            c1, c2 = st.columns(2)
            rad = c1.slider("Radio (km)", 5, 50, 15)
            name = c2.text_input("Nombre Zona", "Zona Personalizada")
            target_zone = HotZone(name, st.session_state.custom_zone_coords[0], st.session_state.custom_zone_coords[1], rad, "Custom", [])
            st.success(f"📍 Objetivo: {name}")

    st.markdown("---")
    
    # --- Ejecución ---
    st.subheader("2. Ejecutar Protocolos")
    if st.button("🚀 INICIAR BÚSQUEDA PROFUNDA", type="primary", disabled=target_zone is None):
        scraper = WikilocScraperPro(use_selenium=True)
        with st.status("🕷️ Operación en curso...", expanded=True) as status:
            st.write("📡 Inicializando drivers...")
            time.sleep(1)
            tracks = scraper.scrape_zone_multi_strategy(target_zone)
            st.write(f"✅ Encontrados {len(tracks)} candidatos.")
            st.write("💾 Descargando GPX y metadatos...")
            scraper.download_complete_data(tracks)
            status.update(label="✅ Completado", state="complete", expanded=False)
        st.session_state.scraped_tracks = tracks
    
    # --- Resultados ---
    if st.session_state.scraped_tracks:
        st.markdown("---")
        st.subheader("3. Resultados")
        tracks = st.session_state.scraped_tracks
        viz = WikilocScraperPro()
        res_map = viz.create_interactive_map(tracks)
        st_folium(res_map, width="100%", height=500)
        
        df = pd.DataFrame([asdict(t) for t in tracks])
        st.data_editor(
            df[['title', 'date_recorded', 'distance_km', 'difficulty', 'is_obfuscated', 'download_method']],
            column_config={
                "is_obfuscated": st.column_config.CheckboxColumn("¿Sospechoso?", help="Nombre oculto"),
                "url": st.column_config.LinkColumn("Link"),
            }, use_container_width=True
        )

# ==========================================
# 3. PÁGINA BIO-RADAR (iNaturalist) - NUEVO
# ==========================================
elif page == "🌿 Bio-Radar (iNaturalist)":
    st.header("🌿 Bio-Radar: Puntos Calientes Biológicos")
    st.markdown("Cruza datos de Wikiloc con avistamientos reales científicos.")
    
    c1, c2 = st.columns([1, 3])
    with c1:
        st.subheader("Configuración")
        species = st.text_input("Especie", "Boletus edulis")
        lat_def, lon_def = (st.session_state.custom_zone_coords if st.session_state.custom_zone_coords else (40.416, -3.703))
        slat = st.number_input("Lat", value=lat_def, format="%.4f")
        slon = st.number_input("Lon", value=lon_def, format="%.4f")
        rad = st.slider("Radio Bio (km)", 5, 50, 20)
        
        if st.button("📡 Escanear Biomasa", type="primary"):
            conn = INaturalistConnector()
            with st.spinner("Consultando API iNaturalist..."):
                obs = conn.get_observations(species, slat, slon, rad)
                st.session_state.bio_obs = obs
                if obs: st.success(f"✅ {len(obs)} avistamientos.")
                else: st.warning("⚠️ Sin datos recientes.")
    
    with c2:
        st.subheader("Mapa de Calor Biológico")
        if st.session_state.bio_obs:
            conn = INaturalistConnector()
            bio_map = conn.create_bio_heatmap(st.session_state.bio_obs, slat, slon)
            st_folium(bio_map, width="100%", height=600)
            with st.expander("Ver Datos Brutos"):
                st.dataframe(pd.DataFrame([{ 'Especie': o.species_name, 'Fecha': o.date, 'Lat': o.lat } for o in st.session_state.bio_obs]))
        else:
            st.info("Configura y pulsa Escanear.")
            m = folium.Map([slat, slon], zoom_start=10)
            folium.Circle([slat, slon], radius=rad*1000, color="green", fill=True, fill_opacity=0.1).add_to(m)
            st_folium(m, height=400)

# ==========================================
# 4. PÁGINA ANÁLISIS HISTÓRICO
# ==========================================
elif page == "📊 Análisis Histórico":
    st.header("📊 Análisis de Base de Datos SQL")
    if not Path("wikiloc_cache.db").exists():
        st.warning("⚠️ No se encuentra 'wikiloc_cache.db'.")
    else:
        try:
            ana = HotZoneAnalyzer("wikiloc_cache.db")
            if ana.df.empty: st.warning("BD vacía.")
            else:
                t1, t2, t3 = st.tabs(["Estadísticas", "Clusters", "Usuarios"])
                with t1:
                    s = ana.analyze_track_characteristics()
                    c1, c2 = st.columns(2)
                    c1.metric("Distancia Media", f"{s['distance']['mean']:.1f} km")
                    fig = go.Figure([go.Histogram(x=ana.df['distance_km'])])
                    st.plotly_chart(fig, use_container_width=True)
                with t2:
                    cl = ana.find_clustering_patterns()
                    if cl:
                        for c in cl: st.info(f"📍 Cluster: {c['track_count']} tracks en {c['center_lat']:.3f}, {c['center_lon']:.3f}")
                with t3:
                    ub = ana.analyze_user_behavior()
                    if ub: st.metric("Tracks/Usuario", f"{ub['avg_tracks_per_user']:.2f}")
        except Exception as e: st.error(f"Error: {e}")

# ==========================================
# 5. PÁGINA DETECTOR
# ==========================================
elif page == "🔍 Detector":
    st.header("🔍 Detector Forense")
    files = list(Path("gpx_files").glob("*.gpx"))
    if not files: st.warning("⚠️ No hay GPX descargados.")
    else:
        sel = st.selectbox("Archivo GPX:", files, format_func=lambda x: x.name)
        if st.button("🔬 Analizar"):
            det = MushroomTrackDetector()
            res = det.analyze_gpx(str(sel))
            
            score = res['total_score']
            color = "#28a745" if score >= 60 else "#dc3545"
            st.markdown(f"<div style='border:2px solid {color};padding:10px;border-radius:10px;text-align:center'><h2 style='color:{color}'>SCORE: {score}/100</h2><h3>{res['interpretation']}</h3></div>", unsafe_allow_html=True)
            
            m = res['metrics']
            c1, c2, c3 = st.columns(3)
            c1.metric("Tortuosidad", m.get('tortuosity_index', 0))
            c2.metric("Velocidad", f"{m.get('avg_speed_kmh', 0)} km/h")
            c3.metric("Paradas", m.get('stop_count', 0))
            
            if 'component_scores' in res:
                vals = list(res['component_scores'].values()); vals.append(vals[0])
                cats = list(res['component_scores'].keys()); cats.append(cats[0])
                fig = go.Figure(go.Scatterpolar(r=vals, theta=cats, fill='toself'))
                st.plotly_chart(fig)

# ==========================================
# 6. PÁGINA CONFIGURACIÓN
# ==========================================
elif page == "⚙️ Configuración":
    st.header("⚙️ Configuración")
    tab1, tab2 = st.tabs(["Parámetros", "Calibración"])
    with tab1:
        st.checkbox("Usar Selenium", True)
        st.checkbox("Headless", True)
    with tab2:
        st.slider("Peso Tortuosidad", 0.0, 1.0, 0.4)
        st.slider("Peso Velocidad", 0.0, 1.0, 0.4)
    if st.button("Guardar"): st.success("Guardado (Simulado)")
