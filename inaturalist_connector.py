import requests
import pandas as pd
import folium
from folium.plugins import HeatMap
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class BioObservation:
    id: int
    species_name: str
    lat: float
    lon: float
    date: str
    quality: str
    image_url: str

class INaturalistConnector:
    def __init__(self):
        self.base_url = "https://api.inaturalist.org/v1"

    def get_taxon_id(self, species_name: str) -> Optional[int]:
        """Busca el ID numérico de una especie por su nombre."""
        url = f"{self.base_url}/taxa"
        params = {
            "q": species_name,
            "rank": "species",
            "per_page": 1
        }
        try:
            response = requests.get(url, params=params)
            data = response.json()
            if data['results']:
                return data['results'][0]['id']
            return None
        except Exception as e:
            print(f"Error buscando taxón: {e}")
            return None

    def get_observations(self, species_name: str, lat: float, lon: float, radius_km: int = 20) -> List[BioObservation]:
        """Descarga observaciones de esa especie en la zona."""
        taxon_id = self.get_taxon_id(species_name)
        if not taxon_id:
            print(f"Especie '{species_name}' no encontrada.")
            return []

        url = f"{self.base_url}/observations"
        params = {
            "taxon_id": taxon_id,
            "lat": lat,
            "lng": lon,
            "radius": radius_km,
            "quality_grade": "research,needs_id", # Filtrar por calidad
            "per_page": 200, # Máximo por página
            "order": "desc",
            "order_by": "created_at"
        }

        observations = []
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            for res in data['results']:
                # Solo nos interesan las que tienen coordenadas
                if res.get('geojson'):
                    coords = res['geojson']['coordinates']
                    # GeoJSON es [lon, lat], nosotros usamos [lat, lon]
                    obs = BioObservation(
                        id=res['id'],
                        species_name=res['taxon']['preferred_common_name'] or res['taxon']['name'],
                        lat=coords[1],
                        lon=coords[0],
                        date=res.get('observed_on', 'Unknown'),
                        quality=res['quality_grade'],
                        image_url=res['photos'][0]['url'] if res['photos'] else None
                    )
                    observations.append(obs)
            
            return observations
        except Exception as e:
            print(f"Error obteniendo observaciones: {e}")
            return []

    def create_bio_heatmap(self, observations: List[BioObservation], center_lat, center_lon) -> folium.Map:
        """Genera un mapa de calor biológico."""
        m = folium.Map(location=[center_lat, center_lon], zoom_start=11)
        
        # Datos para el HeatMap [[lat, lon, weight], ...]
        heat_data = [[obs.lat, obs.lon, 1.0] for obs in observations]
        
        # Capa de Calor
        HeatMap(heat_data, radius=15, blur=10, max_zoom=13).add_to(m)
        
        # Puntos individuales con foto
        for obs in observations:
            popup_html = f"""
            <b>{obs.species_name}</b><br>
            📅 {obs.date}<br>
            <img src='{obs.image_url}' width='100px'>
            """
            folium.CircleMarker(
                location=[obs.lat, obs.lon],
                radius=4,
                color="blue",
                fill=True,
                popup=folium.Popup(popup_html, max_width=200)
            ).add_to(m)
            
        return m
