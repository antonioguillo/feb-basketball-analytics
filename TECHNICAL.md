# Documentación Técnica - FEB Basketball Big Data

## Arquitectura General

Sistema Big Data completo para scrapeo, procesamiento y análisis de datos de baloncesto
tercera categoría (Tercera FEB / Liga EBA). Arquitectura medallón (medallion pattern):

```
Raw (MinIO)  →  Bronze (Delta en S3)  →  Silver (Delta en S3)  →  Gold (Delta en S3)
                                         ↓
                                    ClickHouse
```

### Componentes

| Componente | Puerto/Ubicación | Descripción |
|---|---|---|
| MinIO | `localhost:9000` | Almacenamiento de objetos S3-compatible. Datos crudos en `raw/`, staging en `staging/`. |
| Spark Master | `spark-master:7077` | Cluster Spark para procesamiento distribuido. |
| Spark Worker | `localhost:8081` | Worker del cluster Spark. |
| ClickHouse | `localhost:8123` (HTTP), `9000` (TCP) | Data warehouse para consultas analíticas. |
| API FEB | `www.feb.es` | Web scrapping de resultados y estadísticas. |

---

## Infraestructura

### Docker Compose

Levantar toda la infraestructura:

```bash
cd /home/anton/proyectos/feb-basketball-analytics
docker compose up -d --build
```

Primera vez que tarda en descargar e instalar JARs de Delta/S3 dentro de los contenedores. Los logs muestran "Esperando a que MinIO y Spark estén listos..." y luego `ensure_jars` instala las dependencias.

### Imágenes Custom

Las imágenes Docker (`infra/spark/Dockerfile`, `infra/clickhouse/Dockerfile`) incluyen jobs de Spark y configuración listos para usar, evitando bind mounts WSL lentos. La imagen Spark tiene pre-instalado:
- `delta-spark_2.12-3.2.0.jar`
- `delta-storage-3.2.0.jar`
- `hadoop-aws-3.3.4.jar`
- `aws-java-sdk-bundle-1.12.262.jar`
- `delta-spark==3.2.0` (pip)

---

## Pipeline de Datos

### 1. Raw Layer (MinIO)

Entrada: scrapings HTTP a `www.feb.es`. Almacenamiento: `s3a://raw/`.

**Estructura de paths:**
```
competition=tercerafeb/year=2022/group=ungrouped/game_id=2274271.json
competition=tercerafeb_e/year=2023/group=E-A/game_id=2274272.json
competition=liga_femenina/year=2024/group=primary/game_id=...
```

**Subida de partidos individuales:**
```bash
python main.py partido <game_id> --upload
# O via orquestador:
./run_pipeline.sh scrap <game_id>
```

**Subida completa de una competición:**
```bash
./run_pipeline.sh liga tercerafeb --upload --force --delay 0.5
# O grupo E completo:
./run_pipeline.sh grupo-e --upload --force --delay 0.4 --max-journeys 26
```

**Comando `grupo-e` en main.py:**
```
Opciones:
  --upload       : subir a raw (obligatorio para scrape)
  --force        : re-escribir aunque ya existan (útil para rescrape)
  --delay S      : segundos de espera entre requests (default 1.0, baja = más rápido pero más errores)
  --seasons 2022,2023 : temporadas a scrapear (default: todas las 4)
  --max-journeys N : máximo de jornadas por grupo (default = todas = 26)
  --limit N      : límite de partidos a procesar
  --help         : mostrar ayuda
```

**Detalle técnico del scrapeo:**
- Flujo de 2 pasos por cada jornada:
  1. POST al selector de grupos (`gruposDropDownList`) fijando el grupo y temporada
  2. POST al selector de jornadas (`jornadasDropDownList`) fijando la jornada
  3. Regex `Partido\.aspx\?p=(\d+)` extrae los game IDs
- `get_game_links_by_group(group_id, season, max_journeys=None)` en `scraper.py:line_x` itera todas las jornadas. Sin parámetro, usa `max_journeys=None` → todas las 26 jornadas.
- ~7 partidos por jornada × 26 jornadas × 2 subgrupos × 4 temporadas = **1275 partidos** por temporada completa.

### 2. Bronze Layer (Spark)

Job: `jobs/spark_bronze.py`. Lee TODO `s3a://raw/` (incluye tercerafeb, tercerafeb_e, liga, copa) y escribe Delta partitionado por `year`.

**Extracción de año:**
- Se extrae de `meta.date` (formato DD/MM/YYYY) usando `substring(col, 7, 4)`.
- Esto funciona tanto para paths `competencia=tercerafeb/year=2022/...` como `competencia=tercerafeb_e/year=2025/...` porque el año viene del campo `meta.date` del JSON, no del path S3.

**Jobs bronze:**
- `bronze_players` - stats de jugadores (28107 filas tras pipeline completo)
- `bronze_playbyplay` - jugada a jugada (619208 filas)
- `bronze_shots` - coordenadas de tiros (176264 filas)
- `bronze_teamstats` - stats de equipo (2648 filas)

**Comando:**
```bash
./run_pipeline.sh bronze
```

### 3. Silver Layer (Spark)

Job: `jobs/spark_silver.py` (no mostrado completamente, visto en orquestador). LEE de bronze y hace limpieza/transformación básica, escribe Delta partitionado por `year` en `s3a://silver/`.

**Comando:**
```bash
./run_pipeline.sh silver
```

### 4. Gold Layer (Spark)

Job: `jobs/spark_gold.py`. Agrega modelos dimensionalizados y tablas de hechos.

**Tablas gold:**
| Tabla | Filas | Descripción |
|---|---|---|
| `gold_dim_jugadores` | 1124 | Jugadores únicos con estadísticas agregadas |
| `gold_dim_equipos` | 112 | Equipos únicos |
| `gold_fact_partidos` | 1325 | Hechos de partidos (1325 partidos únicos) |
| `gold_fact_equipo_estadisticas` | 2648 | Estadísticas por equipo-partido |
| `gold_fact_tiros` | 176264 | Tiros individualizados |

**Comando:**
```bash
./run_pipeline.sh gold
```

### 5. Export to Staging

Job: `jobs/export_clickhouse.py`. Convierte Delta parquet plano en `s3a://staging/<tabla>` para lectura directa por ClickHouse.

**Tablas staging:**
- `staging/jugadores`, `staging/playbyplay`, `staging/tiros`, `staging/equipos_partido`, `staging/partidos`

**Comando:**
```bash
./run_pipeline.sh export
```

### 6. ClickHouse Load

Script: `jobs/load_clickhouse.py`. Lee parquet de staging y carga a tablas ClickHouse `feb.*`.

**Tablas CH:**
| Tabla | Filas | Columnas clave |
|---|---|---|
| `feb.jugadores` | 28107 | game_id, year, jersey, player_name, points |
| `feb.playbyplay` | 619208 | game_id, year, quarter, time, text, action, scoreA, scoreB |
| `feb.tiros` | 176264 | game_id, year, quarter, made, x, y |
| `feb.equipos_partido` | 2648 | game_id, team_id, team_name, points |
| `feb.partidos` | 1325 | game_id, year, date, home_score, away_score, total_points, winner |

**Comando:**
```bash
./run_pipeline.sh clickhouse
```

### 7. Pipeline Completo

```bash
./run_pipeline.sh all
# O secuencia manual:
./run_pipeline.sh up              # levanta infra
./run_pipeline.sh scraper         # (opcional: scrap específico)
./run_pipeline.sh bronze
./run_pipeline.sh silver
./run_pipeline.sh gold
./run_pipeline.sh export
./run_pipeline.sh clickhouse
echo "Pipeline completado."
```

---

## Módulo de Scraping

### `src/scraper.py` - `FEBBasketballScraper`

Clase principal para scrapeo web.

**Método clave: `get_game_links_by_group(group_id, season, max_journeys=None)`**

```
Firma actualizada: incluye max_journeys parameter
- max_journeys=None (default): itera TODAS las 26 jornadas
- max_journeys=N: solo primeras N jornadas (útil para test/depurar)

Detalle de implementación (scraper.py línea ~120):
- Flujo de POST 2 pasos confirmado por investigación (invest3.py)
- Paso 1: fijar grupo y temporada → POST `__EVENTTARGET=gruposDropDownList`
- Paso 2: fijar jornada → POST `__EVENTTARGET=jornadasDropDownList`
- Regex: re.findall(r"Partido\\.aspx\\?p=(\d+)", html) extrae game IDs
- Debugeo previo confirmó: 7 partidos/jornada × 26 jornadas = ~182 por subgrupo
```

**Método: `scrape_game(game_id, delay)`**
- Obtiene ficha del partido + llama a API interna para stats (play-by-play, shotchart, teamstats)
- Manejo de errores: si API falla (404 = partido futuro), guarda solo la ficha del partido
- Subida a raw: `raw_store.upload_game(group, ...)` con ruta `competition=tercerafeb_e/year=<season>/group=<E-A|E-B>/game_id=<id>.json`

**Método auxiliar: `get_all_seasons_links(group_id, max_journeys=None)`**
- Agrupa por temporada y subgrupo (E-A, E-B)
- Devuelve dict `{season: {group_id: [list_of_game_links]}}`

### `main.py` - Comandos CLI

**Comandos disponibles:**
```
python main.py partido <game_id> [--upload] [--force] [--delay S]
python main.py liga <competition> [--upload] [--force] [--delay S] [--limit N] [--seasons X,Y]
python main.py grupo-e [--upload] [--force] [--delay S] [--seasons X,Y] [--max-journeys N] [--limit N]
```

**Lógica de `scrape_grupo_e`:**
- Itera temporadas (default: 2022,2023,2024,2025)
- Por cada temporada, subgrupo E-A y E-B
- Llama `get_game_links_by_group(3, season, group_id, max_journeys=max_journeys)` (índice 3 = grupo E)
- Para cada link: `scrape_game(link, delay)` → subida a raw

---

## Modelos de Datos

### `src/models.py` - `EBA_GROUP_E`

Diccionario mapeando años a IDs de grupo:

```python
EBA_GROUP_E = {
    "2022": {"E-A": "80019", "E-B": "80020"},
    "2023": {"E-A": "83112", "E-B": "83113"},
    "2024": {"E-A": "86387", "E-B": "86388"},
    "2025": {"E-A": "88891", "E-B": "88892"},
}
```

- Keys: años de temporada (2022-2025)
- Values: dicts con subgrupos E-A y E-B y sus IDs de competición FEB

### Estructura raw JSON (`game_id.json`)

Cada archivo subido a raw contiene metadatos del partido extraídos de la ficha FEB:
- `meta.game_id`: ID interno
- `meta.date`: fecha formato DD/MM/YYYY
- `meta.home_team`, `meta.away_team`: nombres
- `meta.home_score`, `meta.away_score`: resultados
- `players_home`, `players_away`: listas de jugadores con stats (minutes, points, rebounds, assists, etc.)
- `play_by_play`: array de eventos del partido
- `shots`: array de tiros con coordenadas (x,y)
- `team_stats`: stats de equipo (pts, p2m, p2a, p3m, p3a, ftm, fta, rebotes, asistencias, robos, tapones, pérdidas, faltas, eficiencia)

---

## Comandos de Operación

### Ver estado de raw

```bash
cd /home/anton/proyectos/feb-basketball-analytics
source venv/bin/activate
python -c "
import boto3
from collections import Counter
s3 = boto3.client('s3', endpoint_url='http://localhost:9000', aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin')
pag = s3.get_paginator('list_objects_v2')
total=0; by_season=Counter(); by_group=Counter()
for pg in pag.paginate(Bucket='raw', Prefix='competition=tercerafeb_e/'):
    for o in pg.get('Contents',[]):
        k=o['Key']; total+=1
        parts={p.split('=')[0]:p.split('=')[1] for p in k.split('/') if '=' in p}
        by_season[parts.get('year','?')]+=1; by_group[parts.get('group','?')]+=1
print('Total TerceraFEB_E en raw:', total)
print('Por temporada:', dict(sorted(by_season.items())))
print('Por grupo:', dict(sorted(by_group.items())))
"
```

### Ver estadísticas ClickHouse

```bash
docker exec feb-clickhouse clickhouse-client --query "SELECT year, count() FROM feb.partidos GROUP BY year ORDER BY year FORMAT PrettyCompact"
docker exec feb-clickhouse clickhouse-client --query "SELECT count() FROM feb.partidos FORMAT PrettyCompact"
docker exec feb-clickhouse clickhouse-client --query "SELECT count() FROM feb.jugadores FORMAT PrettyCompact"
```

### Re-run pipeline phase (idempotent)

```bash
./run_pipeline.sh bronze     # overwrite Delta tables
./run_pipeline.sh silver     # overwrite
./run_pipeline.sh gold       # overwrite
./run_pipeline.sh export     # overwrite staging parquet
./run_pipeline.sh clickhouse # TRUNCATE + INSERT CH (overwrite completo)
```

### Limpiar VACUUM (mantenimiento, opcional)

```bash
./run_pipeline.sh vacuum
# Ejecuta VACUUM 0 en todas tablas Delta para limpiar archivos antiguos
```

---

## Historia de Fixes y Bloqueos Resueltos

| Problema | Solución | Archivo |
|---|---|---|
| WSL bind mounts lentos | Imágenes Docker custom baked con jobs incluidos | `infra/Dockerfiles/` |
| Conflicto puerto ClickHouse 9004 | Configuración interna en imagen, no expuesto externamente | `infra/clickhouse/` |
| Nombre artifact Delta `delta-core` | Cambiar a `delta-spark` en pyproject/todas dependencias | `jobs/spark_bronze.py` línea imports |
| Vacuum Delta excesivamente lento | Sustituido por export Delta→staging parquet → ClickHouse load | `jobs/export_clickhouse.py` |
| Paginación FEB por jornadas (no solo página default) | `get_game_links_by_group` reescrito para iterar las 26 jornadas por subgrupo | `src/scraper.py` |
| Substring año en raw paths | `substring(indexOf('year=')+5, 4)` en lugar de `substring(7,4)` | `jobs/spark_bronze.py:37` (ver fix anterior) |

---

## Próximos Pasos Recomendados

1. **Documentación interna**: crear `AGENTS.md` con resumen para nuevos agentes que continúen el trabajo
2. **Paralelismo de scraper**: añadir `asyncio` o `concurrent.futures` para reducir tiempo de ~50 min a ~15 min
3. **Validación por subgrupo**: queries Ad-hoc en ClickHouse por `SELECT group, year, count() FROM feb.partidos GROUP BY group, year`
4. **API interna FEB**: explorar endpoints `intrafeb.feb.es` para reducir dependencia del scrapping web paginado
5. **Ampliación de temporadas**: el patrón actual soporta cualquier año en `EBA_GROUP_E` - añadir 2026/2027 cuando la temporada termine
6. **Tests unitarios**: validar que `get_game_links_by_group` devuelve esperado número de links por grupo/año