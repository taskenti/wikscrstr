import gpxpy
import gpxpy.gpx
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime
import math
import re

class MushroomTrackDetector:
    def __init__(self):
        # Pesos CALIBRADOS con tus datos de ejemplo (Moncayo/Bronchales)
        self.weights = {
            'tortuosity': 0.35,      # La forma de andar es lo más importante
            'avg_speed': 0.25,       # Velocidad muy lenta
            'seasonality': 0.15,     # Otoño
            'entropy_name': 0.15,    # Nombres raros "ghgh"
            'stops': 0.10            # Paradas frecuentes
        }

    def _calculate_name_entropy(self, text):
        """Detecta nombres aleatorios como 'ghgh', 'asdf', 'anon'."""
        text = text.lower().strip()
        # Lista de sospechosos habituales
        suspicious_list = ['anon', 'track', 'ruta', 'actividad', 'ghgh', 'asdf', 'temp']
        if any(s in text for s in suspicious_list):
            return 1.0 # Muy sospechoso
        
        # Cálculo de entropía de Shannon para detectar tecleo aleatorio
        if not text: return 0
        prob = [float(text.count(c)) / len(text) for c in dict.fromkeys(list(text))]
        entropy = - sum([p * math.log(p) / math.log(2.0) for p in prob])
        
        # Si la entropía es muy baja (repetición "aaaa") o muy alta (random "xkcd"), es sospechoso
        if entropy < 1.5 or len(text) < 5: 
            return 0.8
        return 0.0

    def _check_seasonality(self, date_obj):
        """Retorna score alto si es temporada de setas (Sep-Dic o Primavera)."""
        if not date_obj: return 0
        month = date_obj.month
        # Temporada Alta (Otoño): Sep, Oct, Nov
        if month in [9, 10, 11]: return 1.0
        # Temporada Media (Diciembre, Mayo): 
        if month in [12, 5, 6]: return 0.6
        return 0.1

    def analyze_gpx(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as gpx_file:
                gpx = gpxpy.parse(gpx_file)
            
            # Extraer metadatos
            track_name = gpx.tracks[0].name if gpx.tracks else (gpx.name or "Unknown")
            track_time = gpx.get_time_bounds().start_time
            
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
            
            if len(points) < 10: raise ValueError("Track insuficiente")
            df = pd.DataFrame(points)
            
            # --- MÉTRICAS FÍSICAS ---
            
            # 1. Distancia y Desplazamiento
            total_dist = 0
            for i in range(1, len(df)):
                p1 = (df.iloc[i-1]['lat'], df.iloc[i-1]['lon'])
                p2 = (df.iloc[i]['lat'], df.iloc[i]['lon'])
                total_dist += geodesic(p1, p2).km
            
            start_p = (df.iloc[0]['lat'], df.iloc[0]['lon'])
            end_p = (df.iloc[-1]['lat'], df.iloc[-1]['lon'])
            displacement = geodesic(start_p, end_p).km
            
            # Tortuosidad: Tus tracks tienen mucha vuelta. 
            # Si displacement es bajo pero dist es alta -> Setas.
            if displacement < 0.1: displacement = 0.1 # Evitar div/0
            tortuosity = total_dist / displacement

            # 2. Velocidad
            duration_h = (df.iloc[-1]['time'] - df.iloc[0]['time']).total_seconds() / 3600
            avg_speed = total_dist / duration_h if duration_h > 0 else 0

            # 3. Paradas (Micro-stops)
            # Un setero se para cada poco tiempo.
            # Calculamos varianza de velocidad en ventanas de 1 min.
            
            # --- PUNTUACIÓN (SCORING) ---
            
            # A. Score Velocidad (Ideal: 0.5 - 2.5 km/h)
            if 0.5 <= avg_speed <= 3.0: score_speed = 100
            elif avg_speed < 0.5: score_speed = 80 # Muy lento, mirando mucho
            else: score_speed = max(0, 100 - (avg_speed - 3)*40) # Senderismo rápido baja nota
            
            # B. Score Tortuosidad (Tus ejemplos > 3.0 casi seguro)
            # Normalizamos: tortuosity 1.5 es bajo, 5.0 es alto.
            score_tort = min(100, (tortuosity - 1.2) * 25)
            if score_tort < 0: score_tort = 0
            
            # C. Score Nombre (Ofuscación)
            is_obfuscated = self._calculate_name_entropy(track_name)
            score_name = is_obfuscated * 100
            
            # D. Score Estacionalidad
            season_factor = self._check_seasonality(track_time)
            score_season = season_factor * 100
            
            # E. Palabras Clave (Bonus/Malus)
            track_name_lower = track_name.lower()
            bonus = 0
            if any(w in track_name_lower for w in ['seta', 'boletus', 'hongo', 'cesta', 'rebollon']):
                bonus = 100 # Jackpot
            if 'nada' in track_name_lower and score_tort > 50:
                bonus += 50 # Buscó pero no encontró (sigue siendo spot)
            
            # SCORE FINAL PONDERADO
            total_score = (
                (score_speed * self.weights['avg_speed']) +
                (score_tort * self.weights['tortuosity']) +
                (score_name * self.weights['entropy_name']) +
                (score_season * self.weights['seasonality'])
            )
            
            # Aplicar bonus (sin pasar de 100 excepto casos muy claros)
            total_score = min(100, total_score + (bonus * 0.5))
            if bonus == 100: total_score = 100 # Si dice "setas", es setas.

            interpretation = "Senderismo"
            if total_score > 85: interpretation = "🎯 SETERO CONFIRMADO"
            elif total_score > 65: interpretation = "🔍 Búsqueda probable"
            elif total_score > 40: interpretation = "Posible recolección"

            return {
                'filename': file_path,
                'track_name': track_name,
                'total_score': int(total_score),
                'interpretation': interpretation,
                'metrics': {
                    'total_distance_km': round(total_dist, 2),
                    'tortuosity_index': round(tortuosity, 2),
                    'avg_speed_kmh': round(avg_speed, 2),
                    'total_duration_hours': round(duration_h, 2),
                    'season': track_time.strftime("%B") if track_time else "Unknown"
                },
                'component_scores': {
                    'speed': int(score_speed),
                    'pattern (tortuosity)': int(score_tort),
                    'name_suspicion': int(score_name),
                    'seasonality': int(score_season)
                }
            }
            
        except Exception as e:
            return {'total_score': 0, 'interpretation': f"Error: {str(e)}", 'metrics': {}, 'component_scores': {}}
