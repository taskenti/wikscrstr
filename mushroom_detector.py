import gpxpy
import gpxpy.gpx
import pandas as pd
import numpy as np
from geopy.distance import geodesic

class MushroomTrackDetector:
    def __init__(self):
        # Pesos por defecto
        self.weights = {
            'tortuosity': 0.3,
            'avg_speed': 0.3,
            'stops': 0.2,
            'duration': 0.2
        }

    def analyze_gpx(self, file_path):
        """Analiza un archivo GPX y devuelve métricas micológicas."""
        try:
            with open(file_path, 'r', encoding='utf-8') as gpx_file:
                gpx = gpxpy.parse(gpx_file)
            
            points = []
            for track in gpx.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        points.append({
                            'lat': point.latitude,
                            'lon': point.longitude,
                            'ele': point.elevation,
                            'time': point.time
                        })
            
            if not points:
                raise ValueError("GPX vacío")

            df = pd.DataFrame(points)
            
            # --- CÁLCULO DE MÉTRICAS ---
            
            # 1. Distancia Total
            total_dist = 0
            for i in range(1, len(df)):
                p1 = (df.iloc[i-1]['lat'], df.iloc[i-1]['lon'])
                p2 = (df.iloc[i]['lat'], df.iloc[i]['lon'])
                total_dist += geodesic(p1, p2).km
            
            # 2. Duración y Velocidad
            if df['time'].iloc[-1] and df['time'].iloc[0]:
                duration_hours = (df['time'].iloc[-1] - df['time'].iloc[0]).total_seconds() / 3600
                avg_speed = total_dist / duration_hours if duration_hours > 0 else 0
            else:
                duration_hours = 0
                avg_speed = 0

            # 3. Tortuosidad (Distancia real / Distancia línea recta inicio-fin)
            start_point = (df.iloc[0]['lat'], df.iloc[0]['lon'])
            end_point = (df.iloc[-1]['lat'], df.iloc[-1]['lon'])
            displacement = geodesic(start_point, end_point).km
            
            # Si displacement es cercano a 0 (ruta circular), tortuosidad es alta
            if displacement < 0.1:
                tortuosity = 10.0 # Valor alto arbitrario para rutas circulares
            else:
                tortuosity = total_dist / displacement

            # 4. Paradas (Simuladas con velocidad < 0.5 km/h)
            stops = int(duration_hours * 2) # Dummy calculation simple

            # --- SCORE ---
            # Un setero va lento (aprox 1-3 km/h), para mucho y da vueltas (tortuosity alta)
            
            score_speed = 100 if 1 <= avg_speed <= 3.5 else max(0, 100 - abs(avg_speed - 2)*30)
            score_tortuosity = min(100, tortuosity * 10)
            
            total_score = (score_speed * 0.4) + (score_tortuosity * 0.6)
            
            interpretation = "Posible Setero" if total_score > 60 else "Senderismo normal"

            return {
                'filename': file_path,
                'total_score': int(total_score),
                'interpretation': interpretation,
                'metrics': {
                    'total_distance_km': round(total_dist, 2),
                    'tortuosity_index': round(tortuosity, 2),
                    'avg_speed_kmh': round(avg_speed, 2),
                    'stop_count': stops,
                    'total_duration_hours': round(duration_hours, 2),
                    'direction_changes_per_km': 15, # Dummy
                    'spatial_density': 0.8 # Dummy
                },
                'component_scores': {
                    'speed': int(score_speed),
                    'pattern': int(score_tortuosity),
                    'stops': 70
                }
            }
            
        except Exception as e:
            return {
                'total_score': 0, 
                'interpretation': f"Error: {str(e)}", 
                'metrics': {'total_distance_km': 0, 'tortuosity_index': 0, 'avg_speed_kmh': 0, 'stop_count': 0, 'total_duration_hours': 0, 'direction_changes_per_km': 0, 'spatial_density': 0},
                'component_scores': {'speed': 0, 'pattern': 0, 'stops': 0}
            }
