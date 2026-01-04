import time
import json
import random
import re
from dataclasses import dataclass, asdict
from typing import List
import pandas as pd
import folium
from pathlib import Path
from fake_useragent import UserAgent

# Intentamos importar undetected_chromedriver
try:
    import undetected_chromedriver as uc
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

# --- CLASES DE DATOS (IMPORTANTE: Esto faltaba o dio error) ---

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

# --- CONSTANTES ---

SPANISH_HOT_ZONES = [
    HotZone("Sierra de Guadarrama", 40.79, -3.96, 20, "Madrid/Segovia", ["boletus", "níscalos"]),
    HotZone("Montseny", 41.77, 2.40, 15, "Barcelona", ["rovellons", "seps"]),
    HotZone("Serranía de Cuenca", 40.20, -2.13, 25, "Cuenca", ["setas", "rebollones"]),
    HotZone("Sierra de Albarracín", 40.41, -1.44, 20, "Teruel", ["rebollones", "porro"]),
    HotZone("Ultzama", 43.00, -1.68, 10, "Navarra", ["hongos", "perretxikos"]),
    HotZone("Sierra de Aracena", 37.89, -6.56, 15, "Huelva", ["tanas", "tentullos"]),
    HotZone("Picos de Europa", 43.19, -4.83, 20, "Asturias/Cantabria", ["setas"])
]

MUSHROOM_KEYWORDS = [
    "setas", "hongos", "boletus", "níscalos", "robellones", "rebollones", 
    "amanita", "caesarea", "edulis", "aereus", "pinicola", "miko", "micologico",
    "cesta", "recoleccion", "busqueda", "senderuela", "trompeta", "muerte"
]

FLORA_KEYWORDS = [
    "flora", "botanica", "orquidea", "avistamiento", "biologia", "estudio", "muestreo"
]

# --- CLASE PRINCIPAL DEL SCRAPER ---

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
        """Detecta nombres sospechosos (intentos de ocultación)."""
        title = title.lower().strip()
        if len(title) < 4: return True
        if re.match(r'^(.)\1+$', title): return True # "aaaaa"
        generic_names = ["ruta", "track", "camino", "paseo", "vuelta", "sin titulo", "unnamed", "malo", "no ir"]
        if title in generic_names: return True
        unique_chars = len(set(title))
        if len(title) > 6 and unique_chars < 3: return True
        return False

    def scrape_zone_multi_strategy(self, zone: HotZone) -> List[TrackDetails]:
        """Implementa las 5 estrategias de búsqueda."""
        all_tracks = {}
        
        # Simulación robusta para demostración (Aquí iría la lógica Selenium real)
        print(f"🚀 Iniciando scraping en {zone.name}...")
        
        # Estrategia 1: Keywords
        for t in self._strategy_keyword_search(zone, MUSHROOM_KEYWORDS): all_tracks[t.id] = t
        # Estrategia 2: Flora
        for t in self._strategy_keyword_search(zone, FLORA_KEYWORDS, "Flora"): all_tracks[t.id] = t
        # Estrategia 3: Ofuscados
        for t in self._strategy_obfuscated_hunting(zone): all_tracks[t.id] = t
        # Estrategia 4: Grid
        if zone.radius > 10:
            for t in self._strategy_grid_scan(zone): all_tracks[t.id] = t
        # Estrategia 5: External
        for t in self._strategy_external_index(zone): all_tracks[t.id] = t

        return list(all_tracks.values())

    # --- Métodos simulados de estrategias ---
    def _strategy_keyword_search(self, zone, keywords, activity="SetaSearch"):
        results = []
        for _ in range(random.randint(2, 5)):
            kw = random.choice(keywords)
            results.append(self._generate_dummy_track(zone, f"Ruta de {kw} en {zone.name}", activity))
        return results

    def _strategy_obfuscated_hunting(self, zone):
        results = []
        names = ["asdf", "...", "aaaa", "ruta 1", "malo", "no ir", "secreto", "x"]
        for _ in range(random.randint(1, 3)):
            t = self._generate_dummy_track(zone, random.choice(names), "Obfuscated Hunter")
            t.is_obfuscated = True
            results.append(t)
        return results

    def _strategy_grid_scan(self, zone):
        results = []
        for i in range(2):
            results.append(self._generate_dummy_track(zone, f"Scan Cuadrante {i}", "Grid Scan"))
        return results

    def _strategy_external_index(self, zone):
        return [self._generate_dummy_track(zone, "Antigua senda 2018", "External Index")]

    def _generate_dummy_track(self, zone, title, method):
        lat_offset = random.uniform(-0.02, 0.02)
        lon_offset = random.uniform(-0.02, 0.02)
        return TrackDetails(
            id=str(random.randint(100000, 999999)),
            title=title,
            url="https://wikiloc.com/track/fake",
            distance_km=round(random.uniform(2.0, 15.0), 2),
            elevation_gain=round(random.uniform(100, 800), 0),
            difficulty=random.choice(["Fácil", "Moderado", "Difícil"]),
            activity_type="Senderismo",
            date_recorded=random.choice(["2023-10-12", "2023-11-01", "2024-01-15"]),
            author=f"User_{random.randint(1,500)}",
            description=f"Método: {method}",
            download_method=method,
            lat=zone.lat + lat_offset,
            lon=zone.lon + lon_offset,
            is_obfuscated=self.is_obfuscated_title(title)
        )

    def download_complete_data(self, tracks: List[TrackDetails]):
        base_path = Path("descargas_wikiloc")
        base_path.mkdir(exist_ok=True)
        Path("gpx_files").mkdir(exist_ok=True)
        
        for track in tracks:
            safe_name = "".join([c for c in track.title if c.isalnum() or c in (' ','-','_')]).strip()
            folder_name = f"{track.date_recorded}_{safe_name}_{track.id}"
            track_path = base_path / folder_name
            track_path.mkdir(exist_ok=True)
            
            # JSON
            with open(track_path / "info.json", "w", encoding="utf-8") as f:
                json.dump(asdict(track), f, indent=4, ensure_ascii=False)
            
            # GPX
            gpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="WikiPro">
  <trk><name>{track.title}</name>
    <trkseg>
      <trkpt lat="{track.lat}" lon="{track.lon}"><time>{track.date_recorded}T10:00:00Z</time></trkpt>
      <trkpt lat="{track.lat+0.01}" lon="{track.lon+0.01}"><time>{track.date_recorded}T12:00:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>"""
            with open(track_path / "track.gpx", "w", encoding="utf-8") as f: f.write(gpx)
            with open(Path("gpx_files") / f"{folder_name}.gpx", "w", encoding="utf-8") as f: f.write(gpx)

    def create_interactive_map(self, tracks):
        if not tracks: return None
        center = [sum(t.lat for t in tracks)/len(tracks), sum(t.lon for t in tracks)/len(tracks)]
        m = folium.Map(location=center, zoom_start=11)
        for t in tracks:
            color = "red" if t.is_obfuscated else "green"
            icon = "eye-slash" if t.is_obfuscated else "tree"
            folium.Marker(
                [t.lat, t.lon],
                popup=f"<b>{t.title}</b><br>{t.download_method}",
                icon=folium.Icon(color=color, icon=icon, prefix='fa')
            ).add_to(m)
        return m

    def cleanup(self):
        if self.driver: self.driver.quit()
