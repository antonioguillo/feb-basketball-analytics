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

## Cobertura del histórico

Medido contra feb.es en agosto de 2026, muestreando partidos reales por
competición y temporada.

### Hasta dónde llega y qué trae

| Periodo | Qué hay | Temporadas |
|---|---|---|
| **2020-2025** | ficha + **play-by-play + carta de tiros** + stats de equipo | 6 |
| **1996-2019** | solo ficha y box score por jugador | hasta 30 |

La API interna de estadísticas en vivo (`intrafeb.feb.es`) no devuelve nada
anterior a la temporada 2020. De 2019 hacia atrás el scraper guarda el partido
igual, pero con `play_by_play` y `shots` vacíos.

El índice publica **24 competiciones**. Las de formación (cadete, infantil,
mini…) **también tienen play-by-play** desde 2020 — un partido junior trae unas
590 jugadas —, pero están organizadas como torneos, sin grupo de «Liga
Regular», así que solo aparecen con `--all-groups`.

| Alcance | Temporadas | Partidos | Peso en raw | Tiempo (6 hilos) |
|---|---|---|---|---|
| `moderno` | 2020-2025 | ~20.000 | ~7,2 GB | ~2 h |
| `completo` | 1996-2025 | ~100.000 | ~8,0 GB | ~10 h |

Un partido con play-by-play ocupa ~375 KB; uno sin él, ~10 KB. De ahí que
multiplicar por cinco el número de partidos apenas aumente el peso total.

### Descarga inicial

```bash
./run_pipeline.sh up                       # imprescindible: raw vive en MinIO
./run_pipeline.sh backfill moderno         # 2020-2025 con play-by-play
./run_pipeline.sh backfill completo        # todo el histórico, todas las categorías
./run_pipeline.sh backfill 2024,2025       # temporadas sueltas
./run_pipeline.sh backfill 2025 tercerafeb # una competición

WORKERS=6 DELAY=0.5 ./scripts/backfill_historico.sh completo
```

Se puede cortar y reanudar: lo ya descargado se omite.

`--workers N` descarga en paralelo. El ritmo real contra feb.es es
aproximadamente `workers / delay` peticiones por segundo; con los valores por
defecto (4 hilos, 1 s) son 4 req/s. Medido: 6 hilos bajan un lote 3,6 veces
más rápido que en secuencial.

### Mantener la temporada al día

```bash
./run_pipeline.sh actualizar               # temporada en curso + reconstruye las capas
./scripts/actualizar_temporada.sh --solo-scraping
```

En cron, los lunes a las 4:00:

```cron
0 4 * * 1 cd /ruta/al/proyecto && ./scripts/actualizar_temporada.sh >> logs/actualizar.log 2>&1
```

La temporada en curso se deduce de la fecha (de septiembre a mayo), así que el
script no hay que tocarlo al cambiar de año.

> **Los partidos aún no jugados no se guardan.** Si se guardaran vacíos, la
> comprobación de idempotencia los daría por hechos y no volverían a bajarse
> nunca al disputarse. Se cuentan como «sin jugar» y la siguiente ejecución los
> recoge en cuanto la FEB publica el acta.

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

> Ojo: el comando antiguo `liga` sí sube a raw los partidos sin jugar. Usa
> `backfill` / `actualizar`, que los dejan pendientes para la siguiente pasada.

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
`raw/competition=tercerafeb/year=<2022-2025>/group=<E-A|E-B>/game_id=<id>.json`

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

Un objeto JSON por partido, particionado por **competición, temporada y grupo**:

```
raw/competition=tercerafeb/year=2025/group=E-A/game_id=2484526.json
raw/competition=lfendesa/year=2024/group=Unico/game_id=2412372.json
raw/competition=segundafeb/year=2023/group=ESTE/game_id=2345035.json
```

La clave de competición es la misma que usa la web en su parámetro `nm=`, y el
grupo sale del nombre del selector (`Liga Regular "E-A"` → `E-A`). Así se puede
reprocesar una liga o un grupo sueltos sin tocar el resto.

Cada fichero contiene: ficha del partido (`meta`), `players_home` y
`players_away`, `play_by_play`, `shots` (coordenadas x/y) y `team_stats`.

### bronze (MinIO `bronze/`, Delta)
- `bronze_games`: game_id, date, venue, home_team, away_team, home_score, away_score, group
- `bronze_players`: game_id, date, is_home, **team**, home_team, away_team, jersey, player_name, minutes, points, t2m/t2a, t3m/t3a, ftm/fta, reb, ast, stl, blk, to, pf, plus_minus, val

> El acta solo dice si un jugador es local o visitante; el nombre del equipo
> vive en la cabecera del JSON. Sin arrastrarlo hasta aquí, ninguna capa
> posterior puede decir con qué equipo juega nadie.
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

`jugadores` lleva `team` e `is_home`; `partidos` lleva `home_team`, `away_team`
y `game_date` (Date, para ordenar); `tiros` llega desde `gold/fact_tiros` con
`zone`, `shot_distance_m`, `is_three` y `shot_points` ya calculados, de modo que
la geometría de la cancha se define en un solo sitio.

Al actualizar un despliegue anterior, `01_schema.sql` incluye los
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`: `CREATE TABLE IF NOT EXISTS` no
añade columnas a una tabla que ya existe.

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

Capturas de la aplicación con datos reales en `docs/capturas/`:

| Fichero | Qué muestra |
|---|---|
| `01-dashboard.png` | Tercera FEB 2025/2026: 367 partidos, 671 jugadores, ranking paginado |
| `02-ficha-jugador.png` | Ficha completa con el mapa de 222 tiros reales |
| `03-lf-endesa-sin-ranking.png` | El selector cambiando de competición, y el estado vacío cuando nadie llega al mínimo |
| `04-movil.png` | Vista estrecha (430 px) |

Se regeneran con la aplicación levantada:

```bash
./run_pipeline.sh api & ./run_pipeline.sh front &
chrome --headless=new --window-size=1440,1250 --virtual-time-budget=15000 \
       --screenshot=docs/capturas/01-dashboard.png http://localhost:3000/
```

Aplicación de scouting con seis pantallas: **Dashboard** del grupo, **ficha de
jugador** con mapa de tiro, **comparador** de hasta 4 jugadores (tabla y radar
de percentiles), **clasificación** de equipos, **ficha de equipo** (plantilla
con tiro por zona y jugador, mapa de tiro agregado, ritmo y eficiencia por
partido).

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
npm run build    # dist/
npm run check    # render de los componentes con datos reales, sin navegador
```

`npm run dev` proxya `/api` a `http://localhost:8000` (configurable con
`VITE_API_TARGET`). **Si la API no responde, la interfaz cae a los datos de
ejemplo** de `src/api/fixtures.json` — Tercera FEB 2025/2026 completa (367
partidos, 3 grupos), con 60 fichas de jugador y 6 de equipo, generadas desde la
API real — y lo anuncia con un aviso permanente, de modo que nunca se
presentan datos de ejemplo como si fueran vivos. Los fixtures se cargan con
import dinámico: no entran en el bundle inicial.

## Procesado incremental

Las capas están particionadas por **competición y temporada**:

```
bronze/players/competition=tercerafeb/year=2025/...
gold/fact_tiros/competition=lfendesa/year=2024/...
```

Acotando la ejecución solo se reprocesan esas particiones, en vez del histórico
entero. Con `partitionOverwriteMode=dynamic`, la escritura toca únicamente las
particiones presentes en los datos escritos:

```bash
# Solo la temporada en curso de una liga
FEB_COMPETITIONS=tercerafeb FEB_SEASONS=2025 ./run_pipeline.sh bronze
FEB_COMPETITIONS=tercerafeb FEB_SEASONS=2025 ./run_pipeline.sh silver

# Reconstrucción completa (obligatoria si cambia el particionado o los tipos)
FEB_REBUILD=1 ./run_pipeline.sh bronze
```

> `year` es la **temporada**, no el año natural. La 2025/2026 se juega entre
> octubre de 2025 y mayo de 2026; derivar el año de la fecha del partido partía
> cada temporada en dos particiones. El año natural se conserva aparte en
> `bronze_games.calendar_year`.

### Mantenimiento del lago

```bash
./run_pipeline.sh vacuum                              # retira versiones antiguas de Delta
python scripts/migrar_raw.py                          # plan de limpieza de raw
python scripts/migrar_raw.py --apply
python scripts/migrar_raw.py --limpiar-marcadores --apply
```

`scripts/migrar_raw.py` retira de raw lo que no encaja en el particionado
—ficheros que no son partidos, fichas de encuentros sin jugar y claves ad-hoc
como `partido_suelto` o `group=ungrouped`— y unifica taxonomías antiguas. Por
defecto solo enseña el plan; lo que borra teniendo datos lo guarda antes en
`data/backup_raw/`.

`--limpiar-marcadores` retira los objetos de cero bytes que MinIO deja como
carpetas: tras un VACUUM hacen creer que sigue habiendo datos de una
competición ya retirada.

### Credenciales de ClickHouse

Sin contraseña, la imagen oficial solo admite al usuario `default` desde dentro
del contenedor y responde a cualquier petición del host con un
«Authentication failed» que despista. El compose fija una:

```bash
CH_USER=default CH_PASSWORD=feb        # valores por defecto, cambiables por entorno
```

## API REST (`api.py`)

```bash
./run_pipeline.sh api          # o: uvicorn api:app --reload --port 8000
```

Documentación interactiva en http://localhost:8000/docs.

| Endpoint | Devuelve |
|---|---|
| `GET /api/health` | estado de la conexión con ClickHouse |
| `GET /api/competitions` | qué hay cargado: competiciones, temporadas y grupos |
| `GET /api/dashboard?competition=&season=&group=&limit=&offset=` | `{ meta, summary, leaders[], leadersTotal, recentGames[] }` |
| `GET /api/players/<slug>?competition=&season=&group=` | perfil: `totals`, `perGame`, `shooting`, `per36`, `zones`, `bests`, `gameLog[]`, `shots[]` |
| `GET /api/teams?competition=&season=&group=` | `{ meta, standings[] }` — clasificación del grupo (récord y diferencial de puntos) |
| `GET /api/teams/<slug>?competition=&season=&group=` | ficha: `standing`, `pace` (posesiones/ORTG/DRTG estimados), `gameLog[]`, `roster[]` (tiro por zona por jugador), `shots[]` |

**Una respuesta habla siempre de una sola competición.** Sumar la Tercera FEB
masculina y la LF Endesa en un mismo ranking no significa nada, así que cuando
no se indica competición se elige la que más partidos tiene en esa temporada y
`meta` dice cuál. `group` filtra de verdad; si se omite, `meta.group` anuncia
cuántos grupos entran en la respuesta.

Configuración por entorno: `CH_URL` (por defecto `http://localhost:8123`),
`CH_USER`, `CH_PASSWORD`, `SLUG_CACHE_TTL`.

**Identificador de jugador**: las tablas `feb.*` no tienen id de jugador — el
acta de la FEB solo publica el nombre. El slug se deriva del nombre con
`src/naming.py:player_slug`, que es la definición canónica: cualquier cosa que
genere o resuelva URLs de jugador tiene que usar esa misma función, y se
resuelve contra un índice en memoria por competición y temporada.
**Identificador de equipo**: mismo mecanismo con `src/naming.py:team_slug` —
el nombre de equipo no viene invertido, así que no hace falta un
`display_name` aparte. El frontend recalcula el mismo slug en el cliente
(`src/lib/format.js:teamSlug`) para enlazar a una ficha de equipo desde sitios
que no lo traen ya resuelto (la fila de un líder, la cabecera de un jugador);
tiene que producir exactamente lo mismo que la función de Python.

**Ritmo y eficiencia de equipo**: las posesiones se estiman con
`FGA - RO + PER + 0,44·TL`, calculadas por separado para el equipo y su rival
en el mismo partido — el rating defensivo sale de los puntos del rival por
100 posesiones *del rival*, no una aproximación con las posesiones propias
para ambos lados. `feb.equipos_partido` no tiene columna de grupo, así que ese
filtro se aplica sobre `feb.partidos`, con quien de todos modos hay que
cruzar para la fecha de cada partido.

Los valores viajan siempre como parámetros de ClickHouse (`{nombre:Tipo}`),
nunca interpolados en el SQL.

### Rendimiento

Dos detalles que valen más que cualquier optimización de las consultas:

- **Un solo cliente HTTP para todo el proceso.** Crear uno por consulta costaba
  838 ms frente a 8 ms reutilizándolo; como la ficha de un jugador lanza seis
  consultas, era la diferencia entre 4 s y 140 ms.
- **Índice de slugs cacheado** (`SLUG_CACHE_TTL`, 15 min por defecto): resolver
  un slug pasa de 809 ms a 0,01 ms, y el coste ya no crece con el histórico.

Los líderes se paginan (`limit`, `offset`; 50 por defecto). Sin paginar, una
temporada devolvía 243 jugadores y 82 KB en cada carga.

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
python -m unittest discover -s tests -v   # scraper, pipeline, contrato e integración
cd frontend && npm run check              # interfaz, incluidas todas las pantallas
```

| Fichero | Qué cubre |
|---|---|
| `tests/test_scraper_parsing.py` | el recorrido de jornadas del WebForm, sin red |
| `tests/test_pipeline_local.py` | ejecuta bronze → silver → gold **de verdad** sobre dos partidos reales en disco local, y comprueba que el marcador reconstruido coincide con el acta |
| `tests/test_api_contract.py` | que la API devuelve las claves que consume el frontend (incluida la clasificación y la ficha de equipo), con un ClickHouse simulado |
| `tests/test_api_integracion.py` | ejecuta la API contra ClickHouse si está levantado: valida el SQL de verdad, que no se mezclen competiciones, que la paginación no solape y que la clasificación/plantilla/tiro de cada equipo cuadren entre sí |
| `frontend/npm run check` | renderiza fuera del navegador las piezas de todas las pantallas con los datos de ejemplo, comprueba que `teamSlug` (cliente) coincide con `team_slug` (servidor), y que los datos de ejemplo mantienen la forma de la API |

Los datos de ejemplo del frontend **se generan desde la API**, no a mano:

```bash
python scripts/generar_fixtures.py          # requiere ClickHouse con datos
python scripts/generar_fixtures.py --competition lfendesa --season 2024
python scripts/generar_fixtures.py --players 40 --teams 8
```

Escribirlos a mano los condena a desfasarse, y entonces el modo sin conexión
enseña una forma distinta justo cuando menos conviene una sorpresa.

> `test_pipeline_local.py` necesita `pyspark` y una JVM. En Windows se salta
> solo: Hadoop no puede usar el sistema de ficheros local sin `winutils.exe`.
> Ejecútalo en WSL o Linux para que corra entero.

No requieren red ni Spark: simulan las respuestas del WebForm de la FEB para
comprobar que se encadenan los postbacks de grupo y jornada.