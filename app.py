import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import plotly.graph_objects as go
import json
from datetime import datetime
import sys
import os

# Librerías para mapas interactivos
try:
    from streamlit_folium import st_folium
    import folium
except ImportError:
    st.error("Falta instalar 'streamlit-folium'. Ejecuta: pip install streamlit-folium")
    st.stop()

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(
    page_title="🍄 Detector Pro V2",
    page_icon="🍄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. IMPORTACIÓN DE MÓDULOS PROPIOS ---
try:
    # Intentamos importar la versión PRO del scraper
    from wikiloc_scraper import WikilocScraperPro, HotZone, SPANISH_HOT_ZONES, TrackDetails
    # Importamos los analizadores originales
    from wikiloc_analyzer import HotZoneAnalyzer
    from mushroom_detector import MushroomTrackDetector
except ImportError as e:
    st.error(f"❌ Error crítico importando módulos: {e}")
    st.info("Asegúrate de tener: wikiloc_scraper.py (versión nueva), wikiloc_analyzer.py y mushroom_detector.py")
    st.stop()

# --- 3. FUNCIONES AUXILIARES ---

def init_filesystem():
    """Crea las carpetas necesarias."""
    Path("gpx_files").mkdir(parents=True, exist_ok=True)
    Path("descargas_wikiloc").mkdir(parents=True, exist_ok=True)
    Path("analysis_plots").mkdir(parents=True, exist_ok=True)

@st.cache_data(ttl=60)
def get_database_stats(db_path="wikiloc_cache.db"):
    """Estadísticas rápidas de la BD (recuperado de V1)."""
    if not Path(db_path).exists():
        return 0, 0, 0, 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tracks")
        track_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT province) FROM tracks")
        province_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tracks WHERE gpx_content IS NOT NULL")
        gpx_db_count = cursor.fetchone()[0]
        conn.close()
        gpx_files_count = len(list(Path("gpx_files").glob("*.gpx")))
        return track_count, province_count, gpx_db_count, gpx_files_count
    except:
        return 0, 0, 0, 0

# Inicializar sistema
init_filesystem()

# --- 4. ESTILOS CSS ---
st.markdown("""
<style>
    .main-header { font-size: 2.5rem; color: #2E7D32; text-align: center; margin-bottom: 1rem; }
    .stButton>button { border-radius: 8px; font-weight: bold; width: 100%; }
    .metric-card { background-color: #f0f2f6; padding: 1rem; border-radius: 10px; text-align: center; }
    .status-box { padding: 10px; border-radius: 5px; margin-bottom: 10px; background-color: #e8f5e9; border: 1px solid #c3e6cb; }
</style>
""", unsafe_allow_html=True)

# --- 5. SESSION STATE ---
if 'scraped_tracks' not in st.session_state: st.session_state.scraped_tracks = []
if 'custom_zone_coords' not in st.session_state: st.session_state.custom_zone_coords = None
if 'analysis_done' not in st.session_state: st.session_state.analysis_done = False

# --- 6. SIDEBAR Y NAVEGACIÓN ---
st.sidebar.title("🍄 Detector Pro V2")
page = st.sidebar.radio(
    "Menú Principal:",
    ["🏠 Inicio", "🕷️ Scraper Avanzado", "📊 Análisis Histórico", "🔍 Detector", "⚙️ Configuración"]
)

st.sidebar.markdown("---")
st.sidebar.info("**Versión:** 2.0.1 (Full Stack)\n\nIncluye 5 estrategias de scraping y análisis forense de tracks.")

# ==========================================
# PÁGINA: INICIO (Recuperado y mejorado)
# ==========================================
if page == "🏠 Inicio":
    st.markdown('<h1 class="main-header">🍄 Sistema de Inteligencia Micológica</h1>', unsafe_allow_html=True)
    
    st.markdown("""
    ### Panel de Control
    Bienvenido al sistema avanzado de detección de rutas. Esta versión combina **scraping profundo** con **análisis de patrones**.
    """)
    
    # KPIs
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Motor de Búsqueda", "Selenium Pro", delta="Activo")
    with c2: st.metric("Estrategias", "5 Niveles", delta="Mejorado")
    with c3: st.metric("Modo Ocultación", "Detectando", delta="ON")
    
    st.markdown("---")
    
    # Estadísticas de Base de Datos (V1)
    st.subheader("📦 Estado del Almacén")
    track_count, province_count, gpx_db, gpx_files = get_database_stats()
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Tracks BD", track_count)
    k2.metric("Provincias", province_count)
    k3.metric("GPX BD", gpx_db)
    k4.metric("Archivos GPX", gpx_files)

# ==========================================
# PÁGINA: SCRAPER PRO (Nuevo V2)
# ==========================================
elif page == "🕷️ Scraper Avanzado":
    st.header("🕷️ Scraper Multi-Estrategia")
    
    # 1. Configuración de Zona
    st.subheader("1. Definir Zona de Búsqueda")
    method = st.radio("Método:", ["📍 Zonas Predefinidas", "🗺️ Mapa Interactivo"], horizontal=True)
    
    target_zone = None
    
    if method == "📍 Zonas Predefinidas":
        z_names = [z.name for z in SPANISH_HOT_ZONES]
        sel_name = st.selectbox("Elige zona:", z_names)
        # Buscar objeto zona
        target_zone = next((z for z in SPANISH_HOT_ZONES if z.name == sel_name), None)
        
        if target_zone:
            m = folium.Map([target_zone.lat, target_zone.lon], zoom_start=9)
            folium.Circle([target_zone.lat, target_zone.lon], radius=target_zone.radius*1000, color="green").add_to(m)
            st_folium(m, height=200, width=500)

    else: # Mapa Interactivo
        st.info("Haz clic en el mapa para fijar el centro del rastreo.")
        start_coords = [40.416, -3.703]
        if st.session_state.custom_zone_coords:
            start_coords = st.session_state.custom_zone_coords
            
        m = folium.Map(location=start_coords, zoom_start=6)
        if st.session_state.custom_zone_coords:
             folium.Marker(st.session_state.custom_zone_coords, icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")).add_to(m)
        
        output = st_folium(m, height=400, width="100%")
        
        if output['last_clicked']:
            lat, lon = output['last_clicked']['lat'], output['last_clicked']['lng']
            st.session_state.custom_zone_coords = [lat, lon]
            
            c1, c2 = st.columns(2)
            rad = c1.slider("Radio (km)", 5, 50, 15)
            name = c2.text_input("Nombre de Zona", "Zona Custom")
            target_zone = HotZone(name, lat, lon, rad, "Custom", [])
            st.success(f"📍 Objetivo fijado: {name}")

    st.markdown("---")

    # 2. Ejecución
    st.subheader("2. Ejecutar Protocolos")
    col_exec, col_info = st.columns([3, 2])
    
    with col_info:
        st.info("""
        **Estrategias Activadas:**
        1. 🍄 **Keywords Micológicas**
        2. 🌿 **Flora y Botánica**
        3. 🕵️ **Caza de Ofuscados** ("aaaa", "...")
        4. 🕸️ **Grid Scan** (Barrido)
        5. 🌐 **Google Dorking**
        """)

    with col_exec:
        if st.button("🚀 INICIAR BÚSQUEDA PROFUNDA", type="primary", disabled=target_zone is None):
            scraper = WikilocScraperPro(use_selenium=True)
            
            with st.status("🕷️ Operación en curso...", expanded=True) as status:
                st.write("📡 Inicializando drivers...")
                time.sleep(1)
                st.write(f"🎯 Escaneando {target_zone.name}...")
                
                # Ejecutar scraping
                tracks = scraper.scrape_zone_multi_strategy(target_zone)
                st.write(f"✅ Encontrados {len(tracks)} candidatos.")
                
                st.write("💾 Descargando metadatos completos y GPX...")
                scraper.download_complete_data(tracks)
                
                status.update(label="✅ Misión completada", state="complete", expanded=False)
            
            st.session_state.scraped_tracks = tracks
            st.success(f"¡Éxito! {len(tracks)} rutas procesadas.")

    # 3. Resultados
    if st.session_state.scraped_tracks:
        st.markdown("---")
        st.subheader("3. Resultados de la Misión")
        
        tracks = st.session_state.scraped_tracks
        
        # Mapa de resultados
        viz_scraper = WikilocScraperPro()
        res_map = viz_scraper.create_interactive_map(tracks)
        if res_map:
            st_folium(res_map, width="100%", height=500)
        
        # Tabla Detallada
        st.subheader("📋 Base de Datos")
        from dataclasses import asdict
        df = pd.DataFrame([asdict(t) for t in tracks])
        
        # Configuración de columnas para Data Editor
        st.data_editor(
            df[['title', 'date_recorded', 'distance_km', 'difficulty', 'is_obfuscated', 'download_method']],
            column_config={
                "is_obfuscated": st.column_config.CheckboxColumn("¿Sospechoso?", help="Intento de ocultación detectado"),
                "url": st.column_config.LinkColumn("Link"),
            },
            use_container_width=True,
            hide_index=True
        )

# ==========================================
# PÁGINA: ANÁLISIS HISTÓRICO (Recuperado V1)
# ==========================================
elif page == "📊 Análisis Histórico":
    st.header("📊 Análisis de Base de Datos")
    
    db_path = "wikiloc_cache.db"
    # Nota: El análisis V1 usa la base de datos SQL. El Scraper V2 guarda JSONs.
    # Para no romper la funcionalidad, mantenemos el análisis de la BD si existe.
    
    if not Path(db_path).exists():
        st.warning("⚠️ No se encuentra 'wikiloc_cache.db'. Esta sección analiza datos históricos almacenados en SQL.")
    else:
        try:
            analyzer = HotZoneAnalyzer(db_path)
            if analyzer.df.empty:
                st.warning("La base de datos está vacía.")
            else:
                st.success(f"Analizando {len(analyzer.df)} registros históricos.")
                
                tab1, tab2, tab3, tab4 = st.tabs(["📈 Estadísticas", "🌍 Clusters", "👥 Usuarios", "🔤 Keywords"])
                
                with tab1:
                    stats = analyzer.analyze_track_characteristics()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Distancia Media", f"{stats['distance']['mean']:.1f} km")
                    c2.metric("Distancia Máx", f"{stats['distance']['max']:.1f} km")
                    c3.metric("Popularidad", f"{stats['popularity']['avg_downloads']:.0f}")
                    
                    fig = go.Figure(data=[go.Histogram(x=analyzer.df['distance_km'], nbinsx=30, marker_color='green')])
                    fig.update_layout(title="Distribución de Distancias", height=300)
                    st.plotly_chart(fig, use_container_width=True)

                with tab2:
                    clusters = analyzer.find_clustering_patterns()
                    if clusters:
                        for c in clusters:
                            st.info(f"📍 Cluster en {c['center_lat']:.3f}, {c['center_lon']:.3f} | {c['track_count']} tracks | Densidad: {c['density_score']}")
                    else:
                        st.info("Necesitas más datos para detectar clusters.")

                with tab3:
                    ub = analyzer.analyze_user_behavior()
                    if ub:
                        st.metric("Ratio Tracks/Usuario", f"{ub['avg_tracks_per_user']:.2f}")
                        if 'top_contributors' in ub:
                            st.write("Top Usuarios:", ub['top_contributors'])

                with tab4:
                    kw = analyzer.identify_keywords_patterns()
                    if kw and 'keyword_frequency' in kw:
                        data = kw['keyword_frequency']
                        fig = go.Figure([go.Bar(x=list(data.keys()), y=list(data.values()), marker_color='orange')])
                        st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"Error en análisis: {e}")

# ==========================================
# PÁGINA: DETECTOR (Recuperado V1 Completo)
# ==========================================
elif page == "🔍 Detector":
    st.header("🔍 Detector Forense de Tracks")
    st.markdown("Analiza archivos GPX individuales para encontrar patrones de comportamiento de recolectores.")
    
    gpx_dir = Path("gpx_files")
    files = list(gpx_dir.glob("*.gpx"))
    
    if not files:
        st.warning("⚠️ No hay archivos GPX en la carpeta 'gpx_files'. Usa el Scraper primero.")
    else:
        selected_file = st.selectbox("Seleccionar Archivo GPX:", files, format_func=lambda x: x.name)
        
        if st.button("🔬 Analizar Track", type="primary"):
            with st.spinner("Procesando geometría y timestamps..."):
                detector = MushroomTrackDetector()
                res = detector.analyze_gpx(str(selected_file))
                
                # --- VISUALIZACIÓN DEL RESULTADO ---
                score = res['total_score']
                color = "#28a745" if score >= 60 else "#ffc107" if score >= 40 else "#dc3545"
                
                # Score Card
                st.markdown(f"""
                <div style="background-color: {color}20; padding: 20px; border-radius: 15px; border: 2px solid {color}; text-align: center; margin-bottom: 20px;">
                    <h2 style="color: {color}; margin:0;">SCORE: {score}/100</h2>
                    <h3 style="margin:0;">{res['interpretation']}</h3>
                </div>
                """, unsafe_allow_html=True)
                
                # Métricas
                m = res['metrics']
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Tortuosidad", m.get('tortuosity_index', 0))
                c2.metric("Vel. Media", f"{m.get('avg_speed_kmh', 0)} km/h")
                c3.metric("Paradas", m.get('stop_count', 0))
                c4.metric("Duración", f"{m.get('total_duration_hours', 0)} h")
                
                # Radar Chart
                if 'component_scores' in res:
                    cats = list(res['component_scores'].keys())
                    vals = list(res['component_scores'].values())
                    # Cerrar el loop del radar
                    cats.append(cats[0])
                    vals.append(vals[0])
                    
                    fig = go.Figure(go.Scatterpolar(r=vals, theta=cats, fill='toself', line_color=color))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), title="Huella Biométrica del Track")
                    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# PÁGINA: CONFIGURACIÓN (Recuperado V1)
# ==========================================
elif page == "⚙️ Configuración":
    st.header("⚙️ Configuración del Sistema")
    
    # Cargar config
    config_path = Path("config.json")
    if config_path.exists():
        with open(config_path, "r") as f: config = json.load(f)
    else:
        config = {}
    
    tab1, tab2 = st.tabs(["🕷️ Parámetros Scraper", "🔍 Calibración Detector"])
    
    with tab1:
        st.subheader("Opciones de Selenium")
        use_selenium = st.checkbox("Usar Selenium", value=True)
        headless = st.checkbox("Headless Mode (Sin ventana)", value=True)
        st.number_input("Max Tracks por zona", value=100)
    
    with tab2:
        st.subheader("Ponderación del Algoritmo")
        st.info("Ajusta qué tanto influye cada factor en el Score final.")
        w_tort = st.slider("Peso: Tortuosidad (Vueltas)", 0.0, 1.0, 0.4)
        w_speed = st.slider("Peso: Velocidad Lenta", 0.0, 1.0, 0.4)
        w_stop = st.slider("Peso: Paradas Frecuentes", 0.0, 1.0, 0.2)
        
    if st.button("💾 Guardar Cambios"):
        new_config = {
            "scraping": {"headless": headless, "use_selenium": use_selenium},
            "detector": {"weights": {"tortuosity": w_tort, "speed": w_speed, "stops": w_stop}}
        }
        with open("config.json", "w") as f:
            json.dump(new_config, f, indent=4)
        st.success("Configuración actualizada.")
