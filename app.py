import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import plotly.graph_objects as go
import json
from datetime import datetime
import sys
import os

# --- 1. CONFIGURACIÓN INICIAL Y CARGA DE MÓDULOS ---

st.set_page_config(
    page_title="🍄 Detector de Tracks Micológicos",
    page_icon="🍄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Importar nuestras clases con manejo de errores
try:
    # Nota: Asegúrate de que estos archivos existan en el directorio
    from wikiloc_scraper import WikilocScraperAdvanced, HotZone, SPANISH_HOT_ZONES
    from wikiloc_analyzer import HotZoneAnalyzer
    from mushroom_detector import MushroomTrackDetector
except ImportError as e:
    st.error(f"❌ No se pudieron importar los módulos: {e}")
    st.info("Asegúrate de tener los archivos: wikiloc_scraper.py, wikiloc_analyzer.py y mushroom_detector.py en la misma carpeta.")
    st.stop()

# --- 2. FUNCIONES AUXILIARES Y CACHING ---

def init_filesystem():
    """Crea las carpetas necesarias si no existen."""
    Path("gpx_files").mkdir(parents=True, exist_ok=True)
    Path("analysis_plots").mkdir(parents=True, exist_ok=True)

@st.cache_data(ttl=60)  # Cachear resultados por 60 segundos
def get_database_stats(db_path="wikiloc_cache.db"):
    """Obtiene estadísticas de la BD de forma eficiente."""
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
        
        # Contar archivos físicos
        gpx_files_count = len(list(Path("gpx_files").glob("*.gpx")))
        
        return track_count, province_count, gpx_db_count, gpx_files_count
    except Exception:
        return 0, 0, 0, 0

def load_previous_session():
    """Intenta cargar tracks scrapeados de una sesión anterior."""
    if Path('tracks_found.json').exists() and not st.session_state.scraped_tracks:
        try:
            with open('tracks_found.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convertimos el JSON simple de vuelta a objetos (o diccionarios simples para visualización)
                # Para simplificar en este ejemplo, cargamos la data cruda si las clases no tienen método from_dict
                st.session_state.scraped_tracks_json = data 
                st.session_state.scraping_done = True
        except:
            pass

# Inicialización
init_filesystem()

# --- 3. ESTILOS CSS ---

st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #2E7D32;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        padding: 0.5rem 1rem;
        border: none;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- 4. SESSION STATE ---

if 'scraped_tracks' not in st.session_state:
    st.session_state.scraped_tracks = []
if 'scraped_tracks_json' not in st.session_state:
    st.session_state.scraped_tracks_json = []
if 'scraping_done' not in st.session_state:
    st.session_state.scraping_done = False
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False

# Intentar recuperar sesión
load_previous_session()

# --- 5. SIDEBAR ---

st.sidebar.title("🍄 Menú Principal")
page = st.sidebar.radio(
    "Selecciona una sección:",
    ["🏠 Inicio", "🕷️ Scraper", "📊 Análisis", "🔍 Detector", "⚙️ Configuración"]
)

st.sidebar.markdown("---")
st.sidebar.info("""
**Sistema de Detección de Tracks Micológicos**

Herramienta avanzada para encontrar y analizar rutas de búsqueda de setas en Wikiloc.

**Versión:** 1.0.1 (Optimized)
""")

# --- 6. PÁGINAS ---

# === PÁGINA: Inicio ===
if page == "🏠 Inicio":
    st.markdown('<h1 class="main-header">🍄 Sistema Detector de Tracks Micológicos</h1>', unsafe_allow_html=True)
    
    st.markdown("""
    ### ¡Bienvenido! 👋
    
    Este sistema te permite:
    
    - 🕷️ **Scrapear Wikiloc** - Buscar tracks en zonas específicas
    - 📊 **Analizar datos** - Encontrar patrones y clusters
    - 🔍 **Detectar tracks micológicos** - Identificar rutas de búsqueda de setas
    - 📈 **Visualizar resultados** - Mapas de calor y gráficos interactivos
    """)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**📍 Zonas Predefinidas**\n\n7 zonas calientes de España")
    with col2:
        st.success("**🎯 5 Estrategias**\n\nMúltiples métodos de scraping")
    with col3:
        st.warning("**🤖 IA Integrada**\n\nClustering y recomendaciones")
    
    st.markdown("---")
    
    # Estadísticas rápidas (Usando la función cacheada)
    st.subheader("📊 Estadísticas del Sistema")
    
    track_count, province_count, gpx_db_count, gpx_file_count = get_database_stats()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tracks en BD", track_count)
    c2.metric("Provincias", province_count)
    c3.metric("GPX en BD", gpx_db_count)
    c4.metric("Archivos GPX", gpx_file_count)
    
    st.markdown("---")
    st.info("💡 **Consejo:** Empieza por la sección **Scraper** para buscar tracks en Wikiloc.")

# === PÁGINA: Scraper ===
elif page == "🕷️ Scraper":
    st.header("🕷️ Scraper de Wikiloc")
    
    st.markdown("Buska tracks en zonas específicas usando diferentes estrategias de scraping.")
    
    # Tabs
    tab1, tab2 = st.tabs(["📍 Zonas Predefinidas", "✏️ Zona Personalizada"])
    
    selected_zones = []

    with tab1:
        st.subheader("Selecciona zonas calientes")
        # Mostrar zonas
        try:
            zone_options = {f"{zone.name} ({zone.province}) - {zone.radius}km": zone 
                           for zone in SPANISH_HOT_ZONES}
            
            selected_zone_names = st.multiselect(
                "Zonas a scrapear:",
                options=list(zone_options.keys()),
                default=[list(zone_options.keys())[0]] if zone_options else []
            )
            selected_zones = [zone_options[name] for name in selected_zone_names]
        except NameError:
            st.error("Error al cargar zonas. Verifica wikiloc_scraper.py")
    
    with tab2:
        st.subheader("Define tu propia zona")
        col1, col2 = st.columns(2)
        with col1:
            custom_name = st.text_input("Nombre de la zona", "Mi Zona")
            custom_lat = st.number_input("Latitud", value=40.4168, format="%.4f")
            custom_lon = st.number_input("Longitud", value=-3.7038, format="%.4f")
        with col2:
            custom_radius = st.number_input("Radio (km)", value=15, min_value=1, max_value=50)
            custom_province = st.text_input("Provincia", "Madrid")
            custom_keywords = st.text_input("Keywords (separadas por coma)", "setas,bosque,monte")
        
        if st.button("➕ Añadir zona personalizada"):
            try:
                custom_zone = HotZone(
                    name=custom_name,
                    lat=custom_lat,
                    lon=custom_lon,
                    radius=custom_radius,
                    province=custom_province,
                    keywords=[k.strip() for k in custom_keywords.split(',')]
                )
                selected_zones = [custom_zone]
                st.success(f"✅ Zona '{custom_name}' lista para usar (selecciona iniciar abajo).")
            except Exception as e:
                st.error(f"Error al crear zona: {e}")
    
    st.markdown("---")
    
    # Configuración de scraping
    st.subheader("⚙️ Configuración de Scraping")
    col1, col2 = st.columns(2)
    with col1:
        strategies = st.multiselect(
            "Estrategias a usar:",
            ["coordinates", "keywords", "api", "selenium", "users"],
            default=["coordinates", "keywords", "api"]
        )
    with col2:
        use_selenium = "selenium" in strategies
        download_gpx = st.checkbox("Descargar archivos GPX", value=False)
    
    st.markdown("---")
    
    # Botón de scraping
    if st.button("🚀 Iniciar Scraping", type="primary"):
        if not selected_zones:
            st.error("❌ Selecciona al menos una zona")
        else:
            with st.spinner("🕷️ Scrapeando Wikiloc..."):
                try:
                    scraper = WikilocScraperAdvanced(use_selenium=use_selenium)
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    all_tracks = []
                    
                    for i, zone in enumerate(selected_zones):
                        status_text.text(f"Scrapeando: {zone.name}...")
                        progress_bar.progress((i + 1) / len(selected_zones))
                        
                        tracks = scraper.scrape_hot_zone(zone, strategies)
                        all_tracks.extend(tracks)
                    
                    st.session_state.scraped_tracks = all_tracks
                    st.session_state.scraping_done = True
                    
                    # Guardar y Visualizar
                    if all_tracks:
                        # Exportar JSON
                        export_data = [{
                            'track_id': t.track_id,
                            'title': t.title,
                            'url': t.url,
                            'distance_km': t.distance_km,
                            'province': t.province,
                            'lat': t.lat,
                            'lon': t.lon
                        } for t in all_tracks]
                        
                        st.session_state.scraped_tracks_json = export_data
                        
                        with open('tracks_found.json', 'w', encoding='utf-8') as f:
                            json.dump(export_data, f, indent=2, ensure_ascii=False)
                        
                        # Mapa
                        scraper.create_heatmap(all_tracks)
                        
                        if download_gpx:
                            status_text.text("⬇️ Descargando GPX...")
                            scraper.download_all_gpx(all_tracks)
                    
                    scraper.cleanup()
                    progress_bar.progress(1.0)
                    status_text.text("✅ Scraping completado!")
                    st.success(f"🎉 ¡Scraping completado! Se encontraron {len(all_tracks)} tracks")
                    # Invalidar cache de BD para que se actualicen las métricas
                    get_database_stats.clear()
                    
                except Exception as e:
                    st.error(f"❌ Error durante el scraping: {str(e)}")
    
    # Mostrar resultados
    tracks_display = st.session_state.scraped_tracks if st.session_state.scraped_tracks else st.session_state.scraped_tracks_json
    
    if st.session_state.scraping_done and tracks_display:
        st.markdown("---")
        st.subheader("📋 Resultados")
        
        # Tabla simple
        try:
            # Adaptar dependiendo si es objeto o dict
            df_data = []
            for t in tracks_display:
                if isinstance(t, dict):
                    df_data.append(t)
                else:
                    df_data.append({
                        'track_id': t.track_id,
                        'title': t.title,
                        'distance_km': t.distance_km,
                        'province': t.province
                    })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.warning("No se pudo generar la tabla detallada.")

        # Mapa HTML
        if Path("tracks_heatmap.html").exists():
            st.subheader("🗺️ Mapa de Calor")
            with open("tracks_heatmap.html", "r", encoding="utf-8") as f:
                st.components.v1.html(f.read(), height=600)

# === PÁGINA: Análisis ===
elif page == "📊 Análisis":
    st.header("📊 Análisis de Datos")
    
    db_path = "wikiloc_cache.db"
    
    if not Path(db_path).exists():
        st.warning("⚠️ No hay base de datos. Ejecuta primero el Scraper.")
    else:
        try:
            analyzer = HotZoneAnalyzer(db_path)
            
            if analyzer.df.empty:
                st.warning("⚠️ La base de datos está vacía.")
            else:
                st.success(f"✅ Base de datos cargada: {len(analyzer.df)} tracks")
                
                tab1, tab2, tab3, tab4 = st.tabs(["📈 Estadísticas", "🌍 Clusters", "👥 Usuarios", "🔤 Keywords"])
                
                with tab1:
                    st.subheader("Estadísticas Generales")
                    characteristics = analyzer.analyze_track_characteristics()
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Distancia Media", f"{characteristics['distance']['mean']:.2f} km")
                    with col2:
                        st.metric("Distancia Mín", f"{characteristics['distance']['min']:.2f} km")
                    with col3:
                        st.metric("Distancia Máx", f"{characteristics['distance']['max']:.2f} km")
                    
                    st.subheader("Distribución de Distancias")
                    fig = go.Figure(data=[go.Histogram(x=analyzer.df['distance_km'], nbinsx=30)])
                    fig.update_layout(height=400, margin=dict(t=20, b=20))
                    st.plotly_chart(fig, use_container_width=True)
                
                with tab2:
                    st.subheader("🌍 Clusters Geográficos")
                    clusters = analyzer.find_clustering_patterns()
                    if clusters:
                        for i, cluster in enumerate(clusters[:5], 1):
                            with st.expander(f"Cluster {i} - {cluster['track_count']} tracks"):
                                st.write(f"**Centro:** {cluster['center_lat']:.4f}, {cluster['center_lon']:.4f}")
                                st.write(f"**Densidad:** {cluster['density_score']:.2f}")
                    else:
                        st.info("No se encontraron clusters o falta sklearn.")
                
                with tab3:
                    st.subheader("👥 Usuarios")
                    user_behavior = analyzer.analyze_user_behavior()
                    if user_behavior:
                        st.metric("Tracks por usuario", f"{user_behavior['avg_tracks_per_user']:.1f}")
                        if user_behavior.get('top_contributors'):
                            st.dataframe(pd.DataFrame.from_dict(user_behavior['top_contributors'], orient='index'))
                
                with tab4:
                    st.subheader("🔤 Keywords")
                    keywords = analyzer.identify_keywords_patterns()
                    if keywords and keywords.get('keyword_frequency'):
                        kw_data = keywords['keyword_frequency']
                        fig = go.Figure(data=[go.Bar(x=list(kw_data.keys()), y=list(kw_data.values()))])
                        st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"❌ Error al analizar: {str(e)}")

# === PÁGINA: Detector ===
elif page == "🔍 Detector":
    st.header("🔍 Detector de Tracks Micológicos")
    
    st.markdown("Analiza archivos GPX para determinar si son tracks de búsqueda de setas.")
    
    gpx_dir = Path("gpx_files")
    
    if not gpx_dir.exists() or not list(gpx_dir.glob("*.gpx")):
        st.warning("⚠️ No hay archivos GPX. Descarga GPX primero desde el Scraper.")
    else:
        gpx_files = list(gpx_dir.glob("*.gpx"))
        st.success(f"✅ Se encontraron {len(gpx_files)} archivos GPX")
        
        selected_file = st.selectbox(
            "Selecciona un archivo:",
            gpx_files,
            format_func=lambda x: x.name
        )
        
        if st.button("🔍 Analizar este Track"):
            with st.spinner("Analizando..."):
                try:
                    detector = MushroomTrackDetector()
                    result = detector.analyze_gpx(str(selected_file))
                    
                    # Resultado
                    score = result['total_score']
                    color = "green" if score >= 60 else "orange" if score >= 40 else "red"
                    
                    st.markdown(f"""
                    <div style='text-align: center; padding: 1rem; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 20px;'>
                        <h2>Score Total</h2>
                        <h1 style='color: {color}; font-size: 3rem; margin:0;'>{score}</h1>
                        <h3>{result['interpretation']}</h3>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Métricas Detalladas
                    metrics = result['metrics']
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Tortuosidad", f"{metrics['tortuosity_index']:.2f}")
                    c2.metric("Velocidad Media", f"{metrics['avg_speed_kmh']:.2f} km/h")
                    c3.metric("Paradas", metrics['stop_count'])
                    
                    # Radar Chart
                    categories = list(result['component_scores'].keys())
                    values = list(result['component_scores'].values())
                    
                    fig = go.Figure(data=go.Scatterpolar(
                        r=values + [values[0]],
                        theta=categories + [categories[0]],
                        fill='toself'
                    ))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), height=400)
                    st.plotly_chart(fig, use_container_width=True)
                    
                except Exception as e:
                    st.error(f"Error analizando GPX: {e}")

# === PÁGINA: Configuración ===
elif page == "⚙️ Configuración":
    st.header("⚙️ Configuración")
    st.markdown("Personaliza los parámetros del sistema.")
    
    # Cargar config actual
    if Path("config.json").exists():
        with open("config.json", "r") as f:
            config = json.load(f)
    else:
        config = {}
    
    tab1, tab2, tab3 = st.tabs(["🕷️ Scraper", "🔍 Detector", "📁 Archivos"])
    
    with tab1:
        st.subheader("🕷️ Configuración del Scraper")
        use_selenium = st.checkbox("Usar Selenium", value=config.get('scraping', {}).get('use_selenium', False))
        headless = st.checkbox("Modo headless", value=config.get('scraping', {}).get('headless', True))
        
        c1, c2 = st.columns(2)
        min_delay = c1.number_input("Delay min (s)", value=config.get('scraping', {}).get('min_delay', 2))
        max_delay = c2.number_input("Delay max (s)", value=config.get('scraping', {}).get('max_delay', 5))
        max_tracks = st.number_input("Máx. tracks por zona", value=config.get('scraping', {}).get('max_tracks_per_zone', 100))

    with tab2:
        st.subheader("Configuración del Detector")
        c1, c2 = st.columns(2)
        max_speed = c1.number_input("Vel. máx. setas (km/h)", value=config.get('detector', {}).get('max_mushroom_speed', 3.0))
        min_duration = c2.number_input("Duración mín. (h)", value=config.get('detector', {}).get('min_duration_hours', 2))
        
        st.subheader("Ponderaciones (0.0 - 1.0)")
        weights = config.get('detector', {}).get('weights', {})
        tortuosity = st.slider("Tortuosidad", 0.0, 1.0, weights.get('tortuosity', 0.20))
        avg_speed = st.slider("Velocidad media", 0.0, 1.0, weights.get('avg_speed', 0.15))
        stops = st.slider("Paradas", 0.0, 1.0, weights.get('stops', 0.10))

    with tab3:
        st.subheader("Rutas")
        gpx_dir_path = st.text_input("Carpeta GPX", value=config.get('output', {}).get('gpx_directory', 'gpx_files'))
        db_path_cfg = st.text_input("Base de datos", value=config.get('output', {}).get('database_path', 'wikiloc_cache.db'))

    if st.button("💾 Guardar Configuración"):
        new_config = {
            "scraping": {
                "use_selenium": use_selenium,
                "headless": headless,
                "min_delay": min_delay,
                "max_delay": max_delay,
                "max_tracks_per_zone": max_tracks
            },
            "detector": {
                "max_mushroom_speed": max_speed,
                "min_duration_hours": min_duration,
                "weights": {
                    "tortuosity": tortuosity,
                    "avg_speed": avg_speed,
                    "stops": stops
                }
            },
            "output": {
                "gpx_directory": gpx_dir_path,
                "database_path": db_path_cfg
            }
        }
        with open("config.json", "w") as f:
            json.dump(new_config, f, indent=2)
        st.success("✅ Configuración guardada!")
