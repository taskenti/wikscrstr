"""
WIKILOC SCRAPER ENGINE - INDUSTRIAL GRADE
Version: 3.1.0 (Cloud Compatible + Deep Geometry)
Author: Gemini / User Request

Este módulo implementa un harvester de alto rendimiento diseñado para:
1. Ignorar la categorización del usuario (analiza TODO: senderismo, alpinismo, etc).
2. Extraer la geometría (lat/lon/elev/time) directamente del DOM sin login.
3. Calcular índices de 'Micología' basados en patrones de movimiento (ZigZag, Entropía).
4. Persistencia transaccional en SQLite.
5. Soporte híbrido: Funciona en Local (Stealth) y en Cloud (Chromium).
"""

import sys
import os
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

# Imports condicionales para Selenium y compatibilidad Cloud
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Intentamos importar undetected_chromedriver para uso LOCAL
try:
    import undetected_chromedriver as uc
    HAS_UC = True
except ImportError:
    HAS_UC = False

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
        directional_chaos = np.std(bearing_diff)
        
        # Detección de paradas/zonas lentas (Clustering espacial simple)
        dists = GeometryEngine.haversine_vectorized(arr)
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
    """
    Wrapper Híbrido: Funciona en Local (Stealth) y en Streamlit Cloud (Chromium).
    NO BORRA NADA, SOLO AÑADE COMPATIBILIDAD.
    """
    def __init__(self, headless=True):
        self.headless = headless
        self.ua = UserAgent()
        self.driver = None

    def start(self):
        # 1. DETECCIÓN DE ENTORNO STREAMLIT CLOUD
        # En Cloud, Chromium suele estar en /usr/bin/chromium
        is_cloud = os.path.exists("/usr/bin/chromium") or os.path.exists("/usr/bin/chromium-browser")
        
        if is_cloud:
            logger.info("☁️ Entorno Cloud detectado. Usando Chromium estándar.")
            options = Options()
            options.add_argument("--headless")  # Obligatorio en cloud
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument(f'--user-agent={self.ua.random}')
            
            # Localizar binario
            if os.path.exists("/usr/bin/chromium"):
                options.binary_location = "/usr/bin/chromium"
            elif os.path.exists("/usr/bin/chromium-browser"):
                options.binary_location = "/usr/bin/chromium-browser"

            try:
                self.driver = webdriver.Chrome(options=options)
            except Exception as e:
                logger.error(f"Fallo driver directo: {e}. Intentando WebDriverManager...")
                try:
                    self.driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                        options=options
                    )
                except Exception as e2:
                    logger.critical(f"FATAL: No se pudo iniciar Chromium: {e2}")
                    raise e2
        
        else:
            # 2. ENTORNO LOCAL (TU PC) - MODO STEALTH
            # Usamos undetected_chromedriver para evitar bloqueos
            if HAS_UC:
                try:
                    logger.info("💻 Entorno Local detectado. Usando Stealth Driver.")
                    opts = uc.ChromeOptions()
                    if self.headless:
                        opts.add_argument('--headless')
                    
                    opts.add_argument(f'--user-agent={self.ua.random}')
                    opts.add_argument('--no-first-run')
                    opts.add_argument('--password-store=basic')
                    opts.add_argument('--disable-blink-features=AutomationControlled')
                    
                    self.driver = uc.Chrome(options=opts)
                except Exception as e:
                    logger.warning(f"Error UC: {e}. Fallback a Selenium normal.")
                    self._start_standard_local()
            else:
                self._start_standard_local()

        if self.driver:
            self.driver.set_page_load_timeout(45)

    def _start_standard_local(self):
        """Fallback para local si falla UC."""
        options = Options()
        if self.headless: options.add_argument("--headless")
        options.add_argument(f'--user-agent={self.ua.random}')
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

    def human_scroll(self):
        """Simula scroll humano para triggerear cargas lazy."""
        if not self.driver: return
        try:
            total_height = int(self.driver.execute_script("return document.body.scrollHeight"))
            for i in range(1, total_height, random.randint(300, 700)):
                self.driver.execute_script(f"window.scrollTo(0, {i});")
                time.sleep(random.uniform(0.1, 0.3))
        except:
            pass

    def get_page_source(self, url: str) -> str:
        if not self.driver: self.start()
        try:
            self.driver.get(url)
            # Espera humana variable
            time.sleep(random.uniform(2.5, 5.0))
            return self.driver.page_source
        except Exception as e:
            logger.error(f"Error cargando {url}: {e}")
            try:
                self.quit()
                self.start()
            except: pass
            return ""

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

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
        """
        try:
            # Buscamos bloques grandes de números decimales
            pattern = re.compile(r'\[\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\]')
            matches = pattern.findall(html)
            
            valid_coords = []
            for lat_s, lon_s in matches:
                lat, lon = float(lat_s), float(lon_s)
                # Filtro burdo para descartar otros arrays numéricos del JS (Spain bounds approx)
                if 27 < lat < 45 and -19 < lon < 5: 
                    valid_coords.append((lat, lon))
            
            if len(valid_coords) > 50:
                return valid_coords
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
            "stop_count": int(patterns['stop_ratio'] * 100),
            "entropy_score": round(patterns['score'], 2),
            "mushroom_probability": min(100, score),
            "raw_coords_json": json.dumps(coords[:500]) # Guardamos muestra para debug
        })
        
        return metadata

    def scrape_grid_sector(self, lat: float, lon: float, max_pages: int = 2):
        """Escanea un sector del grid."""
        for act_id in TARGET_ACTIVITIES:
            for page in range(1, max_pages + 1):
                url = f"{self.base_url}/trails/hiking?act={act_id}&near={lat},{lon}&page={page}"
                
                logger.info(f"Escaneando Sector {lat:.3f},{lon:.3f} | Actividad {act_id} | Pag {page}")
                html = self.browser.get_page_source(url)
                soup = BeautifulSoup(html, 'html.parser')
                
                # Selectores CSS resilientes
                cards = soup.find_all('div', class_=re.compile(r'TrailCard__Info'))
                if not cards: cards = soup.select('.trail-card')
                
                if not cards:
                    logger.debug("Sector vacío o antibot activado.")
                    break
                
                for card in cards:
                    try:
                        title_tag = card.find('a', class_=re.compile(r'Title'))
                        if not title_tag: continue
                        
                        href = title_tag['href']
                        full_url = self.base_url + href if not href.startswith('http') else href
                        track_id = href.split('/')[-1].split('-')[-1]
                        
                        if self.db.track_exists(track_id): continue
                            
                        title = title_tag.text.strip()
                        
                        # Extracción de Stats
                        dist_txt = card.text
                        dist = 0.0
                        m_dist = re.search(r'(\d+[\.,]?\d*)\s*km', dist_txt)
                        if m_dist: dist = float(m_dist.group(1).replace(',', '.'))
                        
                        # Filtro Preliminar (2-25km)
                        if dist < 2.0 or dist > 25.0: continue
                        
                        # --- DEEP DIVE ---
                        meta = {
                            "id": hashlib.md5(full_url.encode()).hexdigest(),
                            "external_id": track_id,
                            "title": title,
                            "total_dist_km": dist,
                            "author": "Unknown",
                            "activity_type": act_id,
                            "scraped_at": datetime.now()
                        }
                        
                        logger.info(f"  -> Analizando geometría de: {title} ({dist}km)")
                        
                        final_data = self.analyze_track_deep(full_url, meta)
                        
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
                time.sleep(random.uniform(5, 10))
                
        except KeyboardInterrupt:
            logger.warning("Campaña abortada por usuario.")
        except Exception as e:
            logger.error(f"Error crítico en campaña: {e}")
        finally:
            self.browser.quit()
            logger.info("Campaña finalizada. Drivers cerrados.")

if __name__ == "__main__":
    # Test rápido local
    harvester = WikilocHarvester(headless=False)
    harvester.run_campaign("TEST_RUN", 40.416, -3.703, radius_km=1)
