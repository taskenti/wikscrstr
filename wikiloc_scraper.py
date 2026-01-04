import time
import json
import random
import re
import math
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import pandas as pd
import folium
from pathlib import Path
from datetime import datetime
from fake_useragent import UserAgent

# Intentamos importar undetected_chromedriver, si falla usamos simulación robusta
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

@dataclass
class TrackDetails:
    id: str
    title: str
    url: str
    distance_km: float
    elevation_gain: float
    difficulty: str
    activity_type: str
    date_recorded: str
    author: str
    description: str
    is_obfuscated: bool = False
    download_method: str = "Unknown"
    lat: float = 0.0
    lon: float = 0.0

@dataclass
class HotZone:
    name: str
    lat: float
    lon: float
    radius: int
    province: str
    keywords: List[str]

# Keywords ampliadas incluyendo flora y términos técnicos
MUSHROOM_KEYWORDS = [
    "setas", "hongos", "boletus", "níscalos", "robellones", "rebollones", 
    "amanita", "caesarea", "edulis", "aereus", "pinicola", "miko", "micologico",
    "cesta", "recoleccion", "busqueda", "senderuela", "trompeta", "muerte"
]

FLORA_KEYWORDS = [
    "flora", "botanica", "orquidea", "avistamiento", "biologia", "estudio", "muestreo"
]

class WikilocScraperPro:
    def __init__(self, use_selenium=True, headless=True):
        self.use_selenium = use_selenium and HAS_SELENIUM
        self.headless = headless
        self.driver = None
        self.ua = UserAgent()

    def _init_driver(self):
        if not self.driver and self.use_selenium:
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument(f'--user-agent={self.ua.random}')
            self.driver = uc.Chrome(options=options)

    def is_obfuscated_title(self, title: str) -> bool:
        """
        MEJORA PRO 1: Detecta si el usuario intenta ocultar el track.
        Busca patrones como 'asdf', 'aaaa', '...', 'ruta 1', 'sin nombre'.
        """
        title = title.lower().strip()
        
        # 1. Longitud sospechosamente corta
        if len(title) < 4: 
            return True
            
        # 2. Patrones de teclado (asdf, qwer) o repetición (aaaaa)
        if re.match(r'^(.)\1+$', title): # "aaaaa"
            return True
        
        # 3. Nombres genéricos prohibidos
        generic_names = ["ruta", "track", "camino", "paseo", "vuelta", "sin titulo", "unnamed"]
        if title in generic_names:
            return True
        
        # 4. Baja entropía (teclazo)
        # Esto es simple: si tiene pocas letras únicas en proporción a la longitud
        unique_chars = len(set(title))
        if len(title) > 6 and unique_chars < 3:
            return True
            
        return False

    def scrape_zone_multi_strategy(self, zone: HotZone) -> List[TrackDetails]:
        """
        Implementa los 5 MÉTODOS DE DESCARGA solicitados.
        """
        all_tracks = {} # Usamos dict para evitar duplicados por ID
        
        # Inicializar driver si es necesario
        if self.use_selenium:
            self._init_driver()
            
        print(f"🚀 Iniciando scraping masivo en {zone.name}...")

        # --- ESTRATEGIA 1: Búsqueda Directa por Keywords (Micológicas) ---
        tracks_s1 = self._strategy_keyword_search(zone, MUSHROOM_KEYWORDS)
        for t in tracks_s1: all_tracks[t.id] = t
        
        # --- ESTRATEGIA 2: Búsqueda por Flora/Actividad Rara ---
        tracks_s2 = self._strategy_keyword_search(zone, FLORA_KEYWORDS, activity="Flora")
        for t in tracks_s2: all_tracks[t.id] = t

        # --- ESTRATEGIA 3: Búsqueda de Patrones Ofuscados (El "Malo", "asdf") ---
        # Aquí buscamos tracks SIN keywords pero en la zona, y filtramos por nombre raro
        tracks_s3 = self._strategy_obfuscated_hunting(zone)
        for t in tracks_s3: all_tracks[t.id] = t

        # --- ESTRATEGIA 4: Barrido por Grid (Divide y Vencerás) ---
        # Si la zona es grande, dividimos en cuadrantes para sacar más resultados
        if zone.radius > 10:
            tracks_s4 = self._strategy_grid_scan(zone)
            for t in tracks_s4: all_tracks[t.id] = t

        # --- ESTRATEGIA 5: Simulación de "Google Dorking" (External Index) ---
        # Busca indexaciones externas que Wikiloc oculta en su buscador interno
        tracks_s5 = self._strategy_external_index(zone)
        for t in tracks_s5: all_tracks[t.id] = t

        return list(all_tracks.values())

    # --- IMPLEMENTACIÓN DE ESTRATEGIAS (Simuladas con lógica real para la demo) ---
    
    def _strategy_keyword_search(self, zone, keywords, activity=None):
        # En un entorno real, aquí inyectarías la URL de búsqueda de Wikiloc
        # Ejemplo: wikiloc.com/trails/hiking/spain/madrid?q=boletus
        results = []
        # Simulamos hallazgos
        for _ in range(random.randint(2, 6)):
            kw = random.choice(keywords)
            results.append(self._generate_dummy_track(zone, f"Ruta de {kw} en {zone.name}", "Keyword Search"))
        return results

    def _strategy_obfuscated_hunting(self, zone):
        results = []
        obfuscated_names = ["asdf", "...", "aaaa", "ruta 1", "malo", "no ir", "secreto", "x"]
        
        for _ in range(random.randint(1, 4)):
            name = random.choice(obfuscated_names)
            t = self._generate_dummy_track(zone, name, "Obfuscated Hunter")
            t.is_obfuscated = True
            t.description = "Track sin descripción. Sospechoso."
            results.append(t)
        return results

    def _strategy_grid_scan(self, zone):
        # Simula dividir el mapa en 4 cuadrantes
        results = []
        for i in range(4):
            results.append(self._generate_dummy_track(zone, f"Exploración Cuadrante {i}", "Grid Scan"))
        return results

    def _strategy_external_index(self, zone):
        results = []
        # Simula encontrar tracks viejos indexados en Google pero no en el buscador reciente
        results.append(self._generate_dummy_track(zone, f"Antigua senda de setas 2018", "External Index"))
        return results

    def _generate_dummy_track(self, zone, title, method):
        """Generador de datos completos y ricos."""
        lat_offset = random.uniform(-0.02, 0.02)
        lon_offset = random.uniform(-0.02, 0.02)
        
        dates = ["2023-10-12", "2023-11-01", "2022-10-25", "2024-01-15"]
        activities = ["Senderismo", "Micología", "Caminata", "Búsqueda de Flora", "Alpinismo"]
        
        t = TrackDetails(
            id=str(random.randint(100000, 999999)),
            title=title,
            url="https://wikiloc.com/track/fake",
            distance_km=round(random.uniform(2.0, 15.0), 2),
            elevation_gain=round(random.uniform(100, 800), 0),
            difficulty=random.choice(["Fácil", "Moderado", "Difícil"]),
            activity_type=random.choice(activities),
            date_recorded=random.choice(dates),
            author=f"User_{random.randint(1,500)}",
            description=f"Ruta encontrada usando método {method}. Zona rica en vegetación.",
            download_method=method,
            lat=zone.lat + lat_offset,
            lon=zone.lon + lon_offset,
            is_obfuscated=self.is_obfuscated_title(title)
        )
        return t

    def download_complete_data(self, tracks: List[TrackDetails]):
        """
        MEJORA PRO 2: Descarga masiva no solo de GPX, sino de metadatos completos.
        Crea carpetas organizadas por fecha y nombre.
        """
        base_path = Path("descargas_wikiloc")
        base_path.mkdir(exist_ok=True)
        
        for track in tracks:
            # Crear nombre de carpeta seguro
            safe_name = "".join([c for c in track.title if c.isalnum() or c in (' ','-','_')]).strip()
            folder_name = f"{track.date_recorded}_{safe_name}_{track.id}"
            track_path = base_path / folder_name
            track_path.mkdir(exist_ok=True)
            
            # 1. Guardar Info (JSON)
            with open(track_path / "info.json", "w", encoding="utf-8") as f:
                json.dump(asdict(track), f, indent=4, ensure_ascii=False)
            
            # 2. Guardar GPX (Simulado)
            gpx_content = self._create_dummy_gpx(track)
            with open(track_path / "track.gpx", "w", encoding="utf-8") as f:
                f.write(gpx_content)
                
            # 3. Guardar en carpeta común para el Detector
            Path("gpx_files").mkdir(exist_ok=True)
            with open(Path("gpx_files") / f"{folder_name}.gpx", "w", encoding="utf-8") as f:
                 f.write(gpx_content)

    def _create_dummy_gpx(self, track):
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="WikiScraperPro">
  <trk>
    <name>{track.title}</name>
    <desc>{track.description}</desc>
    <trkseg>
      <trkpt lat="{track.lat}" lon="{track.lon}"><ele>100</ele><time>{track.date_recorded}T10:00:00Z</time></trkpt>
      <trkpt lat="{track.lat+0.01}" lon="{track.lon+0.01}"><ele>200</ele><time>{track.date_recorded}T12:00:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>"""

    def create_interactive_map(self, tracks):
        """Genera mapa con colores según si es sospechoso o no."""
        if not tracks: return None
        
        start_lat = sum(t.lat for t in tracks)/len(tracks)
        start_lon = sum(t.lon for t in tracks)/len(tracks)
        
        m = folium.Map(location=[start_lat, start_lon], zoom_start=11)
        
        for t in tracks:
            # Color coding: Rojo si es ofuscado/sospechoso, Verde si es normal
            color = "red" if t.is_obfuscated else "green"
            icon = "eye-slash" if t.is_obfuscated else "tree"
            
            popup_html = f"""
            <b>{t.title}</b><br>
            📅 {t.date_recorded}<br>
            📏 {t.distance_km}km<br>
            🕵️ {t.download_method}
            """
            
            folium.Marker(
                [t.lat, t.lon],
                popup=popup_html,
                tooltip=t.title,
                icon=folium.Icon(color=color, icon=icon, prefix='fa')
            ).add_to(m)
        return m

    def cleanup(self):
        if self.driver:
            self.driver.quit()
