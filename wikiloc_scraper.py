import time
import json
import random
from dataclasses import dataclass
from typing import List, Dict
import pandas as pd
import folium
from pathlib import Path

# Simulación de datos para que la app funcione si no hay scraping real
@dataclass
class Track:
    track_id: str
    title: str
    url: str
    distance_km: float
    province: str
    lat: float
    lon: float
    author: str = "Unknown"

@dataclass
class HotZone:
    name: str
    lat: float
    lon: float
    radius: int
    province: str
    keywords: List[str]

# Lista de zonas calientes
SPANISH_HOT_ZONES = [
    HotZone("Sierra de Guadarrama", 40.79, -3.96, 20, "Madrid/Segovia", ["boletus", "níscalos"]),
    HotZone("Montseny", 41.77, 2.40, 15, "Barcelona", ["rovellons", "seps"]),
    HotZone("Serranía de Cuenca", 40.20, -2.13, 25, "Cuenca", ["setas", "rebollones"]),
    HotZone("Sierra de Albarracín", 40.41, -1.44, 20, "Teruel", ["rebollones", "porro"]),
    HotZone("Ultzama", 43.00, -1.68, 10, "Navarra", ["hongos", "perretxikos"]),
    HotZone("Sierra de Aracena", 37.89, -6.56, 15, "Huelva", ["tanas", "tentullos"]),
    HotZone("Picos de Europa", 43.19, -4.83, 20, "Asturias/Cantabria", ["setas"])
]

class WikilocScraperAdvanced:
    def __init__(self, use_selenium=False):
        self.use_selenium = use_selenium
        
    def scrape_hot_zone(self, zone: HotZone, strategies: List[str]) -> List[Track]:
        """
        Simula el scraping. En un entorno real, aquí iría requests/selenium.
        Devuelve datos simulados para probar la app.
        """
        time.sleep(1) # Simular delay de red
        print(f"Scrapeando zona: {zone.name} con estrategias: {strategies}")
        
        # Generar datos simulados alrededor del centro de la zona
        found_tracks = []
        num_tracks = random.randint(5, 15)
        
        for i in range(num_tracks):
            # Variación aleatoria de coordenadas
            lat_offset = random.uniform(-0.05, 0.05)
            lon_offset = random.uniform(-0.05, 0.05)
            
            track = Track(
                track_id=f"{zone.name[:3]}_{i}_{int(time.time())}",
                title=f"Ruta de setas en {zone.name} #{i+1}",
                url=f"https://www.wikiloc.com/wikiloc/view.do?id={i}",
                distance_km=random.uniform(3.0, 12.0),
                province=zone.province,
                lat=zone.lat + lat_offset,
                lon=zone.lon + lon_offset,
                author=f"Setero_{random.randint(100,999)}"
            )
            found_tracks.append(track)
            
        return found_tracks

    def create_heatmap(self, tracks: List[Track], filename="tracks_heatmap.html"):
        """Genera un mapa HTML con los tracks encontrados."""
        if not tracks:
            return
            
        start_lat = sum(t.lat for t in tracks) / len(tracks)
        start_lon = sum(t.lon for t in tracks) / len(tracks)
        
        m = folium.Map(location=[start_lat, start_lon], zoom_start=10)
        
        for t in tracks:
            folium.Marker(
                [t.lat, t.lon], 
                popup=f"{t.title} ({t.distance_km:.1f}km)",
                icon=folium.Icon(color="green", icon="leaf")
            ).add_to(m)
            
        m.save(filename)

    def download_all_gpx(self, tracks):
        """Simula la descarga de GPX creando archivos dummy."""
        Path("gpx_files").mkdir(exist_ok=True)
        for t in tracks:
            # Creamos un GPX válido mínimo
            gpx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="MushroomBot">
  <trk>
    <name>{t.title}</name>
    <trkseg>
      <trkpt lat="{t.lat}" lon="{t.lon}"><ele>100</ele><time>2023-10-20T10:00:00Z</time></trkpt>
      <trkpt lat="{t.lat+0.001}" lon="{t.lon+0.001}"><ele>110</ele><time>2023-10-20T10:10:00Z</time></trkpt>
      <trkpt lat="{t.lat+0.002}" lon="{t.lon+0.001}"><ele>105</ele><time>2023-10-20T10:20:00Z</time></trkpt>
      <trkpt lat="{t.lat}" lon="{t.lon}"><ele>100</ele><time>2023-10-20T10:40:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>"""
            
            safe_title = "".join([c for c in t.title if c.isalnum() or c in (' ','-','_')]).strip()
            filename = f"gpx_files/{safe_title}.gpx"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(gpx_content)

    def cleanup(self):
        pass
