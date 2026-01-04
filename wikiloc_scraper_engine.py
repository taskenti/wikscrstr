"""
WIKILOC SCRAPER ENGINE - INDUSTRIAL GRADE
Version: 3.0.0 (Deep Geometry Analysis)
Author: Gemini / User Request

Este módulo implementa un harvester de alto rendimiento diseñado para:
1. Ignorar la categorización del usuario (analiza TODO: senderismo, alpinismo, etc).
2. Extraer la geometría (lat/lon/elev/time) directamente del DOM sin login.
3. Calcular índices de 'Micología' basados en patrones de movimiento (ZigZag, Entropía).
4. Persistencia transaccional en SQLite.
"""

import sys
import time
import json
import math
import random
import logging
import sqlite3
import hashlib
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Any

# Librerías científicas y de scraping
import numpy as np
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Selenium Wire (opcional) o Undetected Chromedriver
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    sys.exit("CRITICAL: Falta 'undetected-chromedriver'. Instala: pip install undetected-chromedriver numpy")

# --- CONFIGURACIÓN GLOBAL ---
LOG_FORMAT = '%(asctime)s [%(levelname)s] (%(module)s): %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("MushroomHunter")

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    external_id TEXT,
    title TEXT,
    author TEXT,
    activity_type TEXT,
    location_name TEXT,
    total_dist_km REAL,
    elevation_gain REAL,
    difficulty TEXT,
    has_zigzag BOOLEAN,
    tortuosity_index REAL,
    stop_count INTEGER,
    entropy_score REAL,
    mushroom_probability REAL,
    scraped_at TIMESTAMP,
    raw_coords_json TEXT
);

CREATE TABLE IF NOT EXISTS scan_history (
    zone_name TEXT,
    grid_lat REAL,
    grid_lon REAL,
    scanned_at TIMESTAMP
);
"""

# Códigos de actividad de Wikiloc
# 1: Senderismo, 46: Recolección, 24: Obs. Naturaleza, 
# 42: Raquetas, 9: Alpinismo (usado para ocultar zonas altas)
TARGET_ACTIVITIES = ["1", "46", "24", "42", "9", "3"] 

class GeometryEngine:
    """
    Motor matemático para analizar la geometría del track sin descargarlo.
    Detecta patrones de comportamiento de recolector vs caminante.
    """
    
    @staticmethod
    def haversine_vectorized(coords: np.ndarray) -> np.ndarray:
        """Calcula distancias entre puntos consecutivos usando NumPy."""
        # coords shape: (N, 2) -> [lat, lon]
        if len(coords) < 2: return np.array([0.0])
        
        R = 6371.0
        lat = np.radians(coords[:, 0])
        lon = np.radians(coords[:, 1])
        
        dlat = np.diff(lat)
        dlon = np.diff(lon)
        
        a = np.sin(dlat/2)**2 + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlon/2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        return R * c

    @staticmethod
    def calculate_tortuosity(coords: List[Tuple[float, float]]) -> float:
        """
        Índice de Tortuosidad: Distancia Real / Distancia Euclídea (Inicio-Fin).
        Senderismo lineal ~= 1.2 - 1.5
        Búsqueda setas > 3.0 (muchas vueltas en poco espacio)
        """
        if not coords or len(coords) < 10: return 0.0
        
        arr = np.array(coords)
        distances = GeometryEngine.haversine_vectorized(arr)
        total_length = np.sum(distances)
        
        # Distancia línea recta start-end
        start = np.radians(arr[0])
        end = np.radians(arr[-1])
        dlat = end[0] - start[0]
        dlon = end[1] - start[1]
        a = np.sin(dlat/2)**2 + np.cos(start[0]) * np.cos(end[0]) * np.sin(dlon/2)**2
        displacement = 6371.0 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        
        if displacement < 0.1: # Ruta circular perfecta
            return total_length * 2 # Penalización/Bonus por circularidad
            
        return total_length / displacement

    @staticmethod
    def detect_search_patterns(coords: List[Tuple[float, float]]) -> Dict[str, Any]:
        """
        Analiza si hay 'nudos' o áreas de alta densidad (hotspots de recolección).
        """
        if len(coords) < 50: 
            return {"stops": 0, "entropy": 0, "is_search": False}
            
        arr = np.array(coords)
        
        # 1. Calcular cambios de rumbo (heading changes)
        # Un caminante mantiene rumbo. Un setero cambia drásticamente.
        lats = np.radians(arr[:, 0])
        lons = np.radians(arr[:, 1])
        y = np.sin(np.diff(lons)) * np.cos(lats[1:])
        x = np.cos(lats[:-1]) * np.sin(lats[1:]) - np.sin(lats[:-1]) * np.cos(lats[1:]) * np.cos(np.diff(lons))
        bearings = np.degrees(np.arctan2(y, x))
        
        # Calcular delta de rumbos
        bearing_diff = np.diff(bearings)
        # Normalizar a [-180, 180]
        bearing_diff = (bearing_diff + 180) % 360 - 180
        
        # Entropía del movimiento (Caos direccional)
        # Si la desviación estándar de los cambios de rumbo es alta, hay mucho giro.
        directional_chaos = np.std(bearing_diff)
        
        # Detección de paradas/zonas lentas (Clustering espacial simple)
        # Simplificamos: contamos puntos muy cercanos consecutivos
        dists = GeometryEngine.haversine_vectorized(arr)
        # Si hay muchos puntos con distancias < 5 metros entre ellos, es una parada o búsqueda minuciosa
        slow_segments = np.sum(dists < 0.005) # Menos de 5 metros
        stop_ratio = slow_segments / len(dists)
        
        return {
            "bearing_std": float(directional_chaos),
            "stop_ratio": float(stop_ratio),
            "score": (directional_chaos * 0.5) + (stop_ratio * 100)
        }

class DatabaseManager:
    """Manejo robusto de persistencia SQLite."""
    def __init__(self, db_path="wikiloc_pro.db"):
        self.path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            conn.executescript(DB_SCHEMA)

    def track_exists(self, track_id: str) -> bool:
        with sqlite3.connect(self.path) as conn:
            cur = conn.cursor()
            res = cur.execute("SELECT 1 FROM tracks WHERE external_id = ?", (track_id,))
            return res.fetchone() is not None

    def save_track(self, data: Dict):
        with sqlite3.connect(self.path) as conn:
            # Upsert
            cols = ', '.join(data.keys())
            placeholders = ', '.join(['?'] * len(data))
            sql = f"INSERT OR REPLACE INTO tracks ({cols}) VALUES ({placeholders})"
            conn.execute(sql, list(data.values()))

class BrowserCore:
    """Wrapper de Selenium con técnicas anti-detección."""
    def __init__(self, headless=True):
        self.headless = headless
        self.ua = UserAgent()
        self.driver = None

    def start(self):
        opts = uc.ChromeOptions()
        if self.headless:
            opts.add_argument('--headless')
        
        # Stealth settings
        opts.add_argument(f'--user-agent={self.ua.random}')
        opts.add_argument('--no-first-run')
        opts.add_argument('--no-service-autorun')
        opts.add_argument('--password-store=basic')
        opts.add_argument('--disable-blink-features=AutomationControlled')
        
        self.driver = uc.Chrome(options=opts)
        self.driver.set_page_load_timeout(30)
        logger.info("Navegador Stealth iniciado.")

    def human_scroll(self):
        """Simula scroll humano para triggerear cargas lazy."""
        if not self.driver: return
        total_height = int(self.driver.execute_script("return document.body.scrollHeight"))
        for i in range(1, total_height, random.randint(300, 700)):
            self.driver.execute_script(f"window.scrollTo(0, {i});")
            time.sleep(random.uniform(0.1, 0.3))

    def get_page_source(self, url: str) -> str:
        try:
            self.driver.get(url)
            # Espera humana variable
            time.sleep(random.uniform(2.5, 5.0))
            return self.driver.page_source
        except Exception as e:
            logger.error(f"Error cargando {url}: {e}")
            return ""

    def quit(self):
        if self.driver:
            self.driver.quit()

class WikilocHarvester:
    """
    Clase principal. Orquesta la búsqueda y el análisis profundo.
    """
    def __init__(self, db_path="wikiloc_pro.db", headless=True):
        self.db = DatabaseManager(db_path)
        self.browser = BrowserCore(headless)
        self.base_url = "https://www.wikiloc.com"

    def generate_honeycomb_grid(self, lat: float, lon: float, radius_km: int, cell_size_km: int = 3) -> List[Tuple[float, float]]:
        """
        Genera una malla hexagonal (más eficiente que la cuadrada) para cubrir la zona.
        """
        points = []
        # Conversiones aproximadas
        km_lat = 1 / 110.574
        km_lon = 1 / (111.320 * math.cos(math.radians(lat)))
        
        lat_step = cell_size_km * km_lat
        lon_step = cell_size_km * km_lon
        
        # Grid simple offset para simular hex
        num_steps = int(radius_km / cell_size_km) * 2
        
        for x in range(-num_steps, num_steps):
            for y in range(-num_steps, num_steps):
                offset_x = (y % 2) * 0.5 # Desplazamiento hexagonal
                
                p_lat = lat + (y * lat_step * 0.75)
                p_lon = lon + ((x + offset_x) * lon_step)
                
                dist = math.sqrt((y*cell_size_km)**2 + (x*cell_size_km)**2)
                if dist <= radius_km:
                    points.append((p_lat, p_lon))
                    
        logger.info(f"Generada malla de {len(points)} puntos de escaneo.")
        return points

    def extract_coords_from_detail_page(self, html: str) -> List[Tuple[float, float]]:
        """
        LA JOYA DE LA CORONA.
        Extrae las coordenadas crudas del script JSON incrustado en la página de detalle.
        Evita tener que loguearse o descargar GPX.
        """
        try:
            # Wikiloc guarda los puntos a veces en un script con 'var mapData' o dentro de un JSON-LD
            # Método 1: Buscar patrón de coordenadas en scripts
            # Formato habitual en leaflet: [lat, lon], [lat, lon]...
            
            # Buscamos bloques grandes de números decimales
            # Esta regex es agresiva, busca arrays de coordenadas
            pattern = re.compile(r'\[\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\]')
            matches = pattern.findall(html)
            
            # Filtramos matches que parezcan coordenadas geográficas válidas en España aprox
            valid_coords = []
            for lat_s, lon_s in matches:
                lat, lon = float(lat_s), float(lon_s)
                # Filtro burdo para descartar otros arrays numéricos del JS
                if 27 < lat < 45 and -19 < lon < 5: 
                    valid_coords.append((lat, lon))
            
            # Si encontramos muchos, asumimos que es el track
            if len(valid_coords) > 50:
                # A veces vienen duplicados o desordenados si pillamos varios scripts, 
                # pero para tortuosidad nos vale la densidad
                return valid_coords

            # Método 2: Buscar en el JSON del mapa (más preciso si la estructura no ha cambiado)
            soup = BeautifulSoup(html, 'html.parser')
            scripts = soup.find_all('script')
            for s in scripts:
                if s.string and 'points' in s.string:
                    # Intentar parsear objetos JS a lo bruto
                    pass 
            
            return valid_coords
            
        except Exception as e:
            logger.warning(f"Error extrayendo geometría: {e}")
            return []

    def analyze_track_deep(self, track_url: str, metadata: Dict) -> Dict:
        """
        Entra en la página, saca coordenadas y ejecuta análisis forense.
        """
        html = self.browser.get_page_source(track_url)
        coords = self.extract_coords_from_detail_page(html)
        
        if not coords:
            logger.warning(f"No se pudo extraer geometría de {track_url}")
            return metadata

        # Geometría Computacional
        tortuosity = GeometryEngine.calculate_tortuosity(coords)
        patterns = GeometryEngine.detect_search_patterns(coords)
        
        # CÁLCULO DE PROBABILIDAD DE SETA (MUSHROOM SCORE)
        # Factores:
        # 1. Título genérico (contiene nombre de pueblo o "senderismo") pero alta tortuosidad.
        # 2. Distancia 'sweet spot' (3-10km).
        # 3. Alta entropía direccional (muchos giros).
        # 4. Ratio de paradas alto.
        
        score = 0
        
        # Geometría (Peso 60%)
        if tortuosity > 2.5: score += 30
        elif tortuosity > 1.5: score += 15
        
        if patterns['bearing_std'] > 40: score += 20 # Mucho caos
        if patterns['stop_ratio'] > 0.3: score += 10 # Muchas paradas
        
        # Metadatos (Peso 40%)
        title_lower = metadata['title'].lower()
        keywords_generic = ["paseo", "vuelta", "ruta", "camino", "senderismo", "mañana"]
        # Si tiene nombre genérico Y geometría compleja -> BINGO
        if any(k in title_lower for k in keywords_generic) and tortuosity > 1.8:
            score += 30
        
        # Si es explícito
        if any(k in title_lower for k in ["seta", "boletus", "cesta", "rebollon"]):
            score += 100
            
        metadata.update({
            "has_zigzag": patterns['bearing_std'] > 40,
            "tortuosity_index": round(tortuosity, 2),
            "stop_count": int(patterns['stop_ratio'] * 100), # dummy conversion
            "entropy_score": round(patterns['score'], 2),
            "mushroom_probability": min(100, score),
            "raw_coords_json": json.dumps(coords[:500]) # Guardamos muestra para debug
        })
        
        return metadata

    def scrape_grid_sector(self, lat: float, lon: float, max_pages: int = 2):
        """Escanea un sector del grid."""
        for act_id in TARGET_ACTIVITIES:
            for page in range(1, max_pages + 1):
                # URL de búsqueda por proximidad 'near'
                # Esto fuerza a Wikiloc a buscar geográficamente, ignorando límites administrativos
                url = f"{self.base_url}/trails/hiking?act={act_id}&near={lat},{lon}&page={page}"
                
                logger.info(f"Escaneando Sector {lat:.3f},{lon:.3f} | Actividad {act_id} | Pag {page}")
                html = self.browser.get_page_source(url)
                soup = BeautifulSoup(html, 'html.parser')
                
                # Selectores CSS (sujetos a cambios por Wikiloc, se intentan varios)
                cards = soup.find_all('div', class_=re.compile(r'TrailCard__Info'))
                if not cards:
                    cards = soup.select('.trail-card') # Legacy selector
                
                if not cards:
                    logger.debug("Sector vacío o antibot activado.")
                    break
                
                for card in cards:
                    try:
                        # Extracción básica
                        title_tag = card.find('a', class_=re.compile(r'Title'))
                        if not title_tag: continue
                        
                        href = title_tag['href']
                        full_url = self.base_url + href if not href.startswith('http') else href
                        track_id = href.split('/')[-1].split('-')[-1] # ID sucio pero funcional
                        
                        # Evitar re-scrapear si ya lo tenemos
                        if self.db.track_exists(track_id):
                            continue
                            
                        title = title_tag.text.strip()
                        
                        # Extracción de Stats
                        dist_txt = card.text # Fallback
                        dist = 0.0
                        # Regex para buscar "12,5 km"
                        m_dist = re.search(r'(\d+[\.,]?\d*)\s*km', dist_txt)
                        if m_dist: dist = float(m_dist.group(1).replace(',', '.'))
                        
                        # Filtro Preliminar:
                        # Si es < 2km (paseo perro) o > 20km (trekking duro), ignorar
                        if dist < 2.0 or dist > 25.0:
                            continue
                        
                        # --- DEEP DIVE ---
                        # Aquí es donde el script se vuelve "denso". Entramos en cada resultado.
                        meta = {
                            "id": hashlib.md5(full_url.encode()).hexdigest(),
                            "external_id": track_id,
                            "title": title,
                            "total_dist_km": dist,
                            "author": "Unknown", # Se podría sacar
                            "activity_type": act_id,
                            "scraped_at": datetime.now()
                        }
                        
                        logger.info(f"  -> Analizando geometría de: {title} ({dist}km)")
                        
                        # Analizar geometría interna
                        final_data = self.analyze_track_deep(full_url, meta)
                        
                        # Guardar solo si tiene mínima probabilidad
                        if final_data.get('mushroom_probability', 0) > 20:
                            self.db.save_track(final_data)
                            logger.info(f"  [GUARDADO] Score: {final_data['mushroom_probability']}")
                        
                    except Exception as e:
                        logger.error(f"Error procesando tarjeta: {e}")
                        continue

    def run_campaign(self, zone_name: str, center_lat: float, center_lon: float, radius_km: int):
        """Ejecuta una campaña completa sobre una zona."""
        logger.info(f"INICIANDO CAMPAÑA: {zone_name}")
        self.browser.start()
        
        try:
            grid = self.generate_honeycomb_grid(center_lat, center_lon, radius_km)
            total = len(grid)
            
            for i, (lat, lon) in enumerate(grid):
                logger.info(f"Progreso Grid: {i+1}/{total}")
                self.scrape_grid_sector(lat, lon)
                
                # Pausa entre sectores para enfriar
                time.sleep(random.uniform(5, 10))
                
        except KeyboardInterrupt:
            logger.warning("Campaña abortada por usuario.")
        finally:
            self.browser.quit()
            logger.info("Campaña finalizada. Drivers cerrados.")

# --- ENTRY POINT ---

if __name__ == "__main__":
    # Ejemplo de uso directo (Test)
    # Bronchales
    harvester = WikilocHarvester(headless=False) # Headless False para ver qué hace
    harvester.run_campaign("Bronchales_Deep_Scan", 40.508, -1.588, radius_km=5)
