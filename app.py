import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import plotly.graph_objects as go
import json
from streamlit_folium import st_folium
import folium

# --- 1. CONFIGURACIÓN E IMPORTS ---
st.set_page_config(page_title="🍄 Detector Pro V2", page_icon="🍄", layout="wide")

try:
    from wikiloc_scraper import WikilocScraperPro, HotZone, SPANISH_HOT_ZONES, TrackDetails
    from wikiloc_analyzer import HotZoneAnalyzer
    from mushroom_detector import MushroomTrackDetector
except ImportError as e:
    st.error(f"❌ Error importando módulos: {e}")
    st.stop()

# --- 2. ESTILOS Y ESTADO ---
st.markdown("""
<style>
    .stButton>button { border-radius: 8px; font-weight: bold; }
    .status-box { padding: 10px; border-radius: 5px; margin-bottom: 10px; }
    .success { background-color: #d4edda; color: #155724; }
    .warning { background-color: #fff3cd; color: #856404; }
</style>
""", unsafe_allow_html=True)

if 'scraped_tracks' not in st.session_state: st.session_state.scraped_tracks = []
if 'custom_zone_coords' not in st.session_state: st.session_state.custom_zone_coords = None

# --- 3. UI PRINCIPAL ---
st.sidebar.title("🍄 Detector Pro V2")
page = st.sidebar.radio("Menú", ["🏠 Inicio", "🕷️ Scraper Avanzado", "📊 Análisis", "🔍 Detector", "⚙️ Config"])

if page == "🏠 Inicio":
    st.title("🍄 Sistema de Inteligencia Micológica")
    st.info("Nueva versión con 5 estrategias de scraping y detección de tracks ocultos.")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Estrategias Activas", "5")
    c2.metric("Motor", "Selenium + Heurística")
    c3.metric("Modo Ofuscación", "Activado")

# === PÁGINA: SCRAPER AVANZADO ===
elif page == "🕷️ Scraper Avanzado":
    st.header("🕷️ Scraper Multi-Estrategia")
    
    # --- SECCIÓN A: SELECCIÓN DE ZONA ---
    st.subheader("1. Definir Zona de Búsqueda")
    
    method = st.radio("Método de selección:", ["📍 Zonas Predefinidas", "🗺️ Seleccionar en Mapa"], horizontal=True)
    
    target_zone = None
    
    if method == "📍 Zonas Predefinidas":
        z_names = [z.name for z in SPANISH_HOT_ZONES]
        sel_name = st.selectbox("Elige zona:", z_names)
        target_zone = next(z for z in SPANISH_HOT_ZONES if z.name == sel_name)
        
        # Mostrar mapa estático pequeño de referencia
        m = folium.Map([target_zone.lat, target_zone.lon], zoom_start=9)
        folium.Circle([target_zone.lat, target_zone.lon], radius=target_zone.radius*1000).add_to(m)
        st_folium(m, height=200, width=400)

    else: # SELECCIÓN EN MAPA INTERACTIVO
        st.info("👆 Haz clic en el mapa para establecer el centro de la búsqueda.")
        
        # Mapa base (España)
        start_coords = [40.416, -3.703]
        if st.session_state.custom_zone_coords:
            start_coords = st.session_state.custom_zone_coords
            
        m = folium.Map(location=start_coords, zoom_start=6)
        
        if st.session_state.custom_zone_coords:
             folium.Marker(st.session_state.custom_zone_coords, icon=folium.Icon(color="red")).add_to(m)
        
        # Output del mapa
        output = st_folium(m, height=400, width="100%")
        
        if output['last_clicked']:
            lat, lon = output['last_clicked']['lat'], output['last_clicked']['lng']
            st.session_state.custom_zone_coords = [lat, lon]
            
            c1, c2 = st.columns(2)
            rad = c1.slider("Radio de búsqueda (km)", 5, 50, 15)
            name = c2.text_input("Nombre de la zona", "Zona Personalizada")
            
            target_zone = HotZone(name, lat, lon, rad, "Custom", [])
            st.success(f"📍 Zona fijada: {lat:.4f}, {lon:.4f}")

    st.markdown("---")

    # --- SECCIÓN B: EJECUCIÓN ---
    st.subheader("2. Ejecutar Scraping")
    
    c1, c2 = st.columns([3, 1])
    with c1:
        st.write("**Estrategias Activas:**")
        st.markdown("""
        1. 🔍 **Keywords Clásicas** (Boletus, Setas...)
        2. 🌿 **Actividades Raras** (Flora, Muestreo)
        3. 🕵️ **Caza de Ofuscados** (Nombres tipo 'asdf', '...', 'aaaa')
        4. 🕸️ **Grid Scan** (Barrido geográfico)
        5. 🔎 **External Index** (Google Dorking)
        """)
    
    if st.button("🚀 INICIAR BÚSQUEDA PROFUNDA", type="primary", disabled=target_zone is None):
        scraper = WikilocScraperPro(use_selenium=True)
        
        with st.status("🕷️ Ejecutando protocolos...", expanded=True) as status:
            st.write("📡 Conectando con satélites (iniciando driver)...")
            time.sleep(1)
            
            st.write(f"🎯 Objetivo: {target_zone.name}. Lanzando 5 estrategias...")
            tracks = scraper.scrape_zone_multi_strategy(target_zone)
            
            st.write("💾 Descargando metadatos completos y GPX...")
            scraper.download_complete_data(tracks)
            
            status.update(label="✅ Misión completada", state="complete", expanded=False)
        
        st.session_state.scraped_tracks = tracks
        st.success(f"Se han extraído {len(tracks)} rutas potenciales.")

    # --- SECCIÓN C: RESULTADOS DETALLADOS ---
    if st.session_state.scraped_tracks:
        tracks = st.session_state.scraped_tracks
        
        # 1. Mapa de Resultados
        st.subheader("🗺️ Mapa de Hallazgos")
        scraper_viz = WikilocScraperPro() # Instancia solo para pintar
        map_viz = scraper_viz.create_interactive_map(tracks)
        st_folium(map_viz, width="100%", height=500)
        
        # 2. Tabla Rica
        st.subheader("📋 Base de Datos de la Misión")
        
        # Convertir a DataFrame para visualización bonita
        df = pd.DataFrame([asdict(t) for t in tracks])
        
        # Filtrar columnas para la vista
        cols_to_show = ['title', 'date_recorded', 'distance_km', 'difficulty', 'activity_type', 'is_obfuscated', 'download_method', 'description']
        
        # Dar formato condicional (Pandas Styler no funciona bien en streamlit interactive table, usamos config de columnas)
        st.data_editor(
            df[cols_to_show],
            column_config={
                "is_obfuscated": st.column_config.CheckboxColumn(
                    "¿Sospechoso?",
                    help="Si está marcado, el nombre es raro (intento de ocultación)",
                ),
                "url": st.column_config.LinkColumn("Enlace"),
                "date_recorded": st.column_config.DateColumn("Fecha"),
            },
            use_container_width=True,
            hide_index=True,
        )
        
        # Botón de descarga CSV global
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Exportar CSV Completo", csv, "mision_setas.csv", "text/csv")

# === OTRAS PÁGINAS (Mantenemos simple para no alargar demasiado) ===
elif page == "🔍 Detector":
    st.header("🔍 Detector de Patrones")
    # (Lógica del detector igual que antes, pero leyendo de la carpeta nueva)
    gpx_files = list(Path("gpx_files").glob("*.gpx"))
    if not gpx_files:
        st.warning("No hay GPX descargados.")
    else:
        sel = st.selectbox("Analizar track:", gpx_files, format_func=lambda x: x.name)
        if st.button("Analizar"):
            detector = MushroomTrackDetector()
            res = detector.analyze_gpx(str(sel))
            st.json(res)

elif page == "⚙️ Config":
    st.header("Configuración")
    st.info("Las estrategias están hardcodeadas en modo PRO para esta demo.")
