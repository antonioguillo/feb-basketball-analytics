# feb-basketball-analytics

Proyecto de Big Data para el análisis de estadísticas de baloncesto de la FEB (Federación Española de Baloncesto).

Scrapea partidos de la web oficial de la FEB (incluida la API interna de estadísticas en vivo: play-by-play, tiros con coordenadas y estadísticas por equipo), y los procesa a través de una arquitectura **medallion** (raw → bronze → silver → gold) con **Spark + Delta Lake** sobre **MinIO** (S3), con **ClickHouse** como capa de consumo OLAP.

## Arquitectura

```
                    ┌─────────────────────────────────────────────────────┐
                    │                 MINIO (S3)                         │
  Scraper FEB ─────▶│  raw/    JSON crudo por partido (con API interna)  │
                    │  bronze/  Delta - tipado y desanidado               │
                    │  silver/  Delta - limpio, normalizado, sin dups     │
                    │  gold/    Delta - dims y facts listos para consumo   │
                    └─────────────────────────────────────────────────────┘
                              │                 │
                              │ Spark jobs      │ ClickHouse s3() table function
                              ▼                 ▼
                    bronze → silver → gold ──▶  ClickHouse (feb.*)
```

- **raw/**: JSON tal cual scrapeado, particionado por `competition`/`year`/`group`/`game_id`.
- **bronze/**: tablas Delta tipadas (players, playbyplay, shots, teamstats), particionadas por `year`.
- **silver/**: normalización (tipos, fechas ISO, deduplicación, filtrado de nulos), particionada por `year`.
- **gold/**: esquema estrella (dim_jugadores, dim_equipos, fact_partidos, fact_equipo_estadisticas, fact_tiros), particionada por `year`.
- **ClickHouse**: tablas de consumo SQL, cargadas leyendo directamente los Parquet de MinIO vía `s3()`.

## Requisitos

- Docker Desktop (Windows) con integración WSL habilitada para la distro Ubuntu, o Docker nativo en Linux.
- Python 3.10+ con `venv`.

> En WSL/Windows el wrapper `infra/docker-wrapper.sh` apunta al `docker.exe` de Docker Desktop.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Levantar la infraestructura (MinIO + Spark + ClickHouse)
./run_pipeline.sh up
```

## Uso del pipeline

```bash
./run_pipeline.sh up           # levanta la infraestructura
./run_pipeline.sh scrap        # scrapea un partido (default 2484886) y lo sube a raw
./run_pipeline.sh liga <comp> [--limit N] [--force] [--delay S]
                               # escanea una competición completa y la sube a raw
./run_pipeline.sh bronze       # raw -> bronze (Delta tipado)
./run_pipeline.sh silver       # bronze -> silver (limpio)
./run_pipeline.sh gold         # silver -> gold (dims + facts)
./run_pipeline.sh export       # gold/silver Delta -> staging (parquet plano)
./run_pipeline.sh clickhouse   # staging -> ClickHouse (lectura directa s3)
./run_pipeline.sh vacuum       # VACUUM Delta (mantenimiento opcional)
./run_pipeline.sh all          # flujo completo de un partido
./run_pipeline.sh liga-all <comp> [--limit N]   # flujo completo de una competición
./run_pipeline.sh grupo-e [--limit N] [--force] [--seasons año1,año2]
                               # escanea el Grupo E (Tercera FEB/Liga EBA) a raw
./run_pipeline.sh down         # apaga todo
```

### Histórico completo (recomendado)

`historico` descubre en la propia web los grupos de cada temporada y recorre
**todas las jornadas** de cada uno, sin ids codificados a mano:

```bash
# Todo el histórico de Tercera FEB que publique la web (28 temporadas disponibles)
./run_pipeline.sh historico tercerafeb

# Temporadas concretas, y solo unas jornadas por grupo (prueba rápida)
./run_pipeline.sh historico segundafeb --seasons 2023,2024 --max-journeys 2

# Incluir play-offs y copas además de la liga regular
./run_pipeline.sh historico tercerafeb --all-groups

# Sin subir a raw (solo listar/scrapear), directamente por Python
python main.py historico primerafeb --seasons 2024 --limit 10
```

Opciones: `--seasons a,b` · `--limit N` · `--delay S` · `--max-journeys N` ·
`--force` (re-scrapea lo ya presente) · `--all-groups`.

Es idempotente: consulta los `game_id` ya en raw y los omite salvo `--force`.

> Volumen orientativo: un grupo de liga regular son 26 jornadas × ~7 partidos
> ≈ **175 partidos**. Tercera FEB tiene 10 grupos de liga regular por temporada.

### Escaneo de competiciones completas

```bash
# Escanear una liga completa y subirla a raw (idempotente: omite partidos ya presentes)
./run_pipeline.sh liga primerafeb

# Con límite (para pruebas), forzando re-scrape y con delay reducido
./run_pipeline.sh liga tercerafeb --limit 2 --force --delay 0.3

# Flujo completo de una competición (scrap + bronze + silver + gold + export + clickhouse)
./run_pipeline.sh liga-all copaespaa --limit 4

# Alternativa directa desde Python
python main.py liga primerafeb --upload
```

> Los partidos aún no jugados (fixtures) se suben a raw sin stats y no rompen el pipeline.

### Grupo E - Tercera FEB / antigua Liga EBA (4 temporadas)

La Tercera FEB (antigua Liga EBA) se divide en grupos A-E. El grupo E abarca la
Comunitat Valenciana / Levante. Se pueden descargar las últimas 4 temporadas:

```bash
# Escanear el grupo E completo (4 temporadas x 2 subgrupos, ~51 partidos) a raw
./run_pipeline.sh grupo-e

# Opciones
./run_pipeline.sh grupo-e --limit 2                # solo 2 partidos (prueba)
./run_pipeline.sh grupo-e --force                  # re-scrape ignorando idempotencia
python main.py grupo-e --upload --seasons 2023,2024   # temporadas específicas
```

Los partidos subidos a raw siguen la partición:
`raw/competition=tercerafeb_e/year=<2022-2025>/group=<E-A|E-B>/game_id=<id>.json`

Los datos de la API interna (play-by-play, tiros, stats) están disponibles incluso
para partidos de 2022, por lo que se conserva información completa por encima de la ficha.

Scraping de un partido concreto:

```bash
source venv/bin/activate
python main.py partido 2484886 --upload
```

## Servicios Docker

| Servicio        | Imagen                        | Puertos                       |
|-----------------|-------------------------------|-------------------------------|
| `minio`         | `minio/minio`                 | 9000 (S3), 9001 (consola)     |
| `minio-init`    | `minio/mc`                    | crea buckets (raw/bronze/...) |
| `spark-master`  | `apache/spark:3.5.1` (custom) | 8080 (UI), 7077              |
| `spark-worker`  | `apache/spark:3.5.1` (custom) | 8081 (UI)                     |
| `clickhouse`    | `clickhouse/clickhouse-server`| 8123 (HTTP), 9004 (nativo)    |

Credenciales MinIO/S3: `minioadmin` / `minioadmin`. Consola: http://localhost:9001

## Capas de datos (medallion)

### raw (MinIO `raw/`)
```json
raw/competition=<comp>/year=<año>/game_id=<id>.json
```
Contiene: ficha del partido, `players` (locales y visitantes), `play_by_play`, `shots` (coordenadas x/y), `team_stats`.

### bronze (MinIO `bronze/`, Delta)
- `bronze_players`: game_id, date, is_home, jersey, player_name, minutes, points, t2m/t2a, t3m/t3a, ftm/fta, reb, ast, stl, blk, to, pf, plus_minus, val
- `bronze_playbyplay`: game_id, num, quarter, time, text, team, action, scoreA, scoreB
- `bronze_shots`: game_id, quarter, time, player, team, made, x, y
- `bronze_teamstats`: game_id, team_id, team_name, points, t2m…pf

### silver (MinIO `silver/`, Delta, particionado por `year`)
Tipos correctos, `game_date` en ISO, deduplicado y sin nulos.

### gold (MinIO `gold/`, Delta)
- `dim_jugadores`: perfil **por jugador y temporada** — totales, medias por partido
  (`ppg`/`rpg`/`apg`/`mpg`), dobles-dobles y ratios de tiro. Los porcentajes se
  calculan sumando aciertos e intentos y dividiendo al final, no promediando los
  porcentajes de cada partido (eso daría el mismo peso a un 1/1 que a un 8/15).
- `dim_equipos`: equipos por temporada con totales y porcentajes.
- `fact_partidos`: uno por partido, con `winner`, `total_points` y `margin`.
- `fact_equipo_estadisticas`: por equipo y partido, con `possessions` estimadas
  (`FGA - ORB + TO + 0.44·FTA`) y `offensive_rating` por 100 posesiones.
- `fact_tiros`: tiro a tiro con `shot_distance_m`, `zone` (aro/media/triple) e
  `is_three`.

**Coordenadas de tiro**: la API interna devuelve `x`/`y` como porcentaje (0-100)
sobre la pista completa, con las dos canastas en extremos opuestos del eje `x`.
Se convierten a metros sobre una pista FIBA de 28×15 m. La posición del aro
(5% del largo) y el radio del triple (6.6 m) se calibraron contra los intentos
de 3 del box score de 6 partidos (836 tiros): 0,8 % de discrepancia.

## ClickHouse (consumo SQL)

Tablas en BD `feb`: `jugadores`, `playbyplay`, `tiros`, `equipos_partido`, `partidos`.

La carga se hace en dos pasos:
1. `jobs/export_clickhouse.py` materializa el estado lógico de las tablas Delta
   (silver/gold) como Parquet plano limpio en `s3a://staging/<tabla>` (overwrite,
   sin archivos obsoletos, sin necesidad de VACUUM).
2. `jobs/load_clickhouse.py` lee esos Parquet vía la función `s3()` de ClickHouse
   e inserta en las tablas de consumo (con `TRUNCATE` previo, por lo que es idempotente).

Así el **data lake es la fuente de verdad** y no hay ETL de copia pesada.

Consultas de ejemplo:

```sql
-- Resumen del partido
SELECT game_id, home_score, away_score, winner FROM feb.partidos;

-- Top jugadores por valoración
SELECT player_name, points, reb, ast, val
FROM feb.jugadores ORDER BY val DESC LIMIT 5;

-- Eficiencia en el tiro por equipo
SELECT team_name, round(t2m/t2a,3) AS t2_pct, round(t3m/t3a,3) AS t3_pct
FROM feb.equipos_partido;
```

## Stack Tecnológico

- **Scraping**: `requests` + `BeautifulSoup4` (token Bearer JWT de la API interna de FEB).
- **Storage**: MinIO (S3) como data lake; Parquet/Delta como formato.
- **Procesamiento**: Apache Spark 3.5 + Delta Lake 3.2 (jobs en `jobs/`).
- **Consumo**: ClickHouse (OLAP/SQL).
- **Orquestación**: `run_pipeline.sh` (scripts, migrable a Airflow/Prefect).

## Estructura

```
feb-basketball-analytics/
├── src/
│   ├── __init__.py           # Exports
│   ├── models.py             # Competiciones FEB
│   ├── scraper.py            # Scraper FEB (web + API interna)
│   ├── pipeline.py           # Pipeline de ingesta a parquet local
│   └── raw_store.py          # Subida de raw a MinIO (S3)
├── jobs/
│   ├── spark_bronze.py       # raw -> bronze (Delta)
│   ├── spark_silver.py       # bronze -> silver
│   ├── spark_gold.py         # silver -> gold (dims/facts)
│   ├── export_clickhouse.py  # silver/gold Delta -> staging (parquet plano)
│   └── load_clickhouse.py    # staging -> ClickHouse
├── infra/
│   ├── spark/Dockerfile      # Imagen Spark con JARs Delta+S3
│   ├── clickhouse/Dockerfile # Imagen con schema init
│   ├── clickhouse/init/01_schema.sql
│   └── docker-wrapper.sh     # Wrapper docker.exe para WSL
├── docker-compose.yml        # MinIO + Spark + ClickHouse
├── run_pipeline.sh           # Orquestador de todo el flujo
├── main.py                   # CLI de scraping
├── tests/
│   └── test_scraper_parsing.py  # Tests sin red del recorrido de jornadas
└── data/processed/           # Parquets locales (cache de scraping)
```

## Frontend (React + Vite)

Aplicación de scouting con dos pantallas: **Dashboard** del grupo y **ficha de
jugador** con mapa de tiro.

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
npm run build    # dist/
npm run check    # render de los componentes con datos reales, sin navegador
```

`npm run dev` proxya `/api` a `http://localhost:8000` (configurable con
`VITE_API_TARGET`). **Si la API no responde, la interfaz cae a los datos de
ejemplo** de `src/api/fixtures.json` — 63 partidos reales del Grupo E-A
2025/2026 — y lo anuncia con un aviso permanente, de modo que nunca se
presentan datos de ejemplo como si fueran vivos. Los fixtures se cargan con
import dinámico: no entran en el bundle inicial.

### Contrato con el backend

El frontend espera dos endpoints (la forma exacta es la de `fixtures.json`):

| Endpoint | Devuelve |
|---|---|
| `GET /api/dashboard?season=&group=` | `{ meta, summary, leaders[], recentGames[] }` |
| `GET /api/players/<slug>` | perfil: `totals`, `perGame`, `shooting`, `per36`, `zones`, `bests`, `gameLog[]`, `shots[]` |

> `api.py` **todavía no los sirve**: sus consultas usan columnas que no existen
> en el esquema real (`player_id`, `equipo_id`, `minutos_played`), y las tablas
> `feb.*` guardan una fila por jugador y partido, sin las agregaciones por
> temporada que necesitan estas pantallas.

### Sistema visual

Tokens en `src/styles.css`, heredados del `index.html` original: `#0d1117`
fondo, `#161b22` tarjeta, `#30363d` borde, `#e6e04c` acento, Inter, radios
8/4 px, contenedor 1200 px. Se añade `--ink: #e6edf3` porque el CSS anterior
usaba `var(--white)` sin definirla y los títulos quedaban en gris apagado.

La geometría del mapa de tiro vive en `src/lib/court.js` y usa las mismas
constantes que `jobs/spark_gold.py`; si se cambian allí, hay que cambiarlas aquí.

Los diseños de origen están en `design/` (`*.dc.html` + `canvas.json`).

## Tests

```bash
python -m unittest discover -s tests -v   # pipeline y scraper
cd frontend && npm run check              # componentes de la interfaz
```

No requieren red ni Spark: simulan las respuestas del WebForm de la FEB para
comprobar que se encadenan los postbacks de grupo y jornada.