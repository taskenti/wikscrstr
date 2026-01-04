import gpxpy
import pandas as pd
import numpy as np
import glob
import math
import os
from geopy.distance import geodesic
from datetime import datetime

# Configuración
TRAINING_FOLDER = "training_tracks"  # Carpeta donde pondras tus GPX
MIN_POINTS = 50                      # Ignorar tracks vacíos o corruptos

def calculate_shannon_entropy(text):
    """Calcula la entropía del texto para detectar nombres 'basura' (ghgh, asdf)."""
    if not text: return 0
    text = text.lower().strip()
    prob = [float(text.count(c)) / len(text) for c in dict.fromkeys(list(text))]
    entropy = - sum([p * math.log(p) / math.log(2.0) for p in prob])
    return entropy

def analyze_track_batch():
    # Buscar archivos en la carpeta de entrenamiento o en la raíz si no existe
    search_path = os.path.join(TRAINING_FOLDER, "*.gpx")
    files = glob.glob(search_path)
    
    # Fallback a directorio actual si la carpeta está vacía
    if not files:
        print(f"⚠️ No se encontraron archivos en '{TRAINING_FOLDER}'. Buscando en directorio raíz...")
        files = glob.glob("*.gpx")

    if not files:
        print("❌ No se encontraron archivos .gpx para analizar.")
        return

    print(f"🧬 INICIANDO ANÁLISIS MASIVO DE {len(files)} TRACKS...")
    print("=" * 80)
    print(f"{'NOMBRE':<30} | {'VEL (km/h)':<10} | {'TORTUOSIDAD':<12} | {'ENTROPÍA':<8} | {'MES':<5}")
    print("-" * 80)

    track_data = []

    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8') as gpx_file:
                gpx = gpxpy.parse(gpx_file)

            # Extraer puntos básicos
            points = []
            for track in gpx.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        points.append((point.latitude, point.longitude, point.time))

            if len(points) < MIN_POINTS:
                continue

            # Convertir a DataFrame para cálculo vectorial (más rápido)
            df = pd.DataFrame(points, columns=['lat', 'lon', 'time'])
            
            # --- CÁLCULOS FÍSICOS ---
            
            # 1. Distancia Total (Suma de segmentos)
            # Usamos shift para calcular distancia entre punto i e i-1
            # Nota: Para 100 tracks, un bucle simple es seguro, geopy es preciso.
            total_dist_km = 0
            for i in range(1, len(df)):
                total_dist_km += geodesic((df.iloc[i-1].lat, df.iloc[i-1].lon),
                                          (df.iloc[i].lat, df.iloc[i].lon)).km

            # 2. Desplazamiento Neto (Inicio a Fin)
            start_coord = (df.iloc[0].lat, df.iloc[0].lon)
            end_coord = (df.iloc[-1].lat, df.iloc[-1].lon)
            displacement_km = geodesic(start_coord, end_coord).km
            if displacement_km == 0: displacement_km = 0.001 # Evitar div/0

            # 3. Tortuosidad (El factor clave del setero)
            tortuosity = total_dist_km / displacement_km

            # 4. Tiempos y Velocidad
            start_time = df.iloc[0].time
            end_time = df.iloc[-1].time
            if start_time and end_time:
                duration_h = (end_time - start_time).total_seconds() / 3600
                avg_speed = total_dist_km / duration_h if duration_h > 0 else 0
                month = start_time.month
            else:
                avg_speed = 0
                month = 0

            # 5. Análisis de Texto (Nombre)
            track_name = gpx.tracks[0].name if gpx.tracks and gpx.tracks[0].name else Path(filepath).stem
            name_entropy = calculate_shannon_entropy(track_name)
            
            # Imprimir fila (truncando nombre)
            print(f"{track_name[:28]:<30} | {avg_speed:<10.2f} | {tortuosity:<12.2f} | {name_entropy:<8.2f} | {month:<5}")

            track_data.append({
                'filename': os.path.basename(filepath),
                'speed': avg_speed,
                'tortuosity': tortuosity,
                'distance': total_dist_km,
                'entropy': name_entropy,
                'month': month
            })

        except Exception as e:
            # Silencioso para no ensuciar la salida masiva, salvo error crítico
            pass

    # --- GENERACIÓN DEL PERFIL DEL SETERO ---
    
    if not track_data:
        print("❌ No se pudieron procesar datos válidos.")
        return

    df_results = pd.DataFrame(track_data)

    print("=" * 80)
    print("📊 PERFIL BIOMÉTRICO GENERADO (Calibration Data)")
    print("=" * 80)

    # Estadísticas Clave
    mean_speed = df_results['speed'].mean()
    std_speed = df_results['speed'].std()
    
    mean_tort = df_results['tortuosity'].mean()
    p75_tort = df_results['tortuosity'].quantile(0.75) # El 25% más tortuoso
    
    top_months = df_results['month'].value_counts().head(3).index.tolist()
    
    print(f"🏃 VELOCIDAD DE BÚSQUEDA:")
    print(f"   Media: {mean_speed:.2f} km/h")
    print(f"   Rango Óptimo (±1 std): {max(0, mean_speed - std_speed):.2f} - {mean_speed + std_speed:.2f} km/h")
    
    print(f"\n🌀 PATRÓN DE MOVIMIENTO (TORTUOSIDAD):")
    print(f"   Media: {mean_tort:.2f}")
    print(f"   Umbral Alto (Setero Experto): > {p75_tort:.2f}")
    if mean_tort > 3.0:
        print("   ✅ CONCLUSIÓN: Tus tracks confirman un patrón de movimiento altamente no lineal (búsqueda intensiva).")
    else:
        print("   ⚠️ CONCLUSIÓN: Los tracks son bastante lineales. ¿Seguro que son de recolección?")

    print(f"\n📅 ESTACIONALIDAD:")
    print(f"   Meses pico detectados: {top_months}")

    print(f"\n🔤 OFUSCACIÓN DE NOMBRES:")
    avg_entropy = df_results['entropy'].mean()
    print(f"   Entropía media: {avg_entropy:.2f}")
    if avg_entropy < 2.5:
        print("   ✅ DETECTADO: Uso frecuente de nombres cortos o repetitivos ('ghgh', 'anon').")

    print("=" * 80)
    print("💡 RECOMENDACIÓN PARA CONFIG.JSON:")
    print("Copia estos valores en tu configuración para máxima precisión:")
    print("{")
    print(f'  "max_mushroom_speed": {mean_speed + std_speed:.1f},')
    print(f'  "min_duration_hours": 1.5,')
    print(f'  "weights": {{')
    print(f'     "tortuosity": 0.40,') # Subimos peso si tus datos lo confirman
    print(f'     "avg_speed": 0.30,')
    print(f'     "entropy_name": 0.20')
    print("  }")
    print("}")
    print("=" * 80)

if __name__ == "__main__":
    analyze_track_batch()
