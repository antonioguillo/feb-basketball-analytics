#!/usr/bin/env bash
# ============================================================
# Pipeline completo FEB Big Data
# Scrap -> MinIO(raw) -> Spark(bronze) -> Spark(silver) -> Spark(gold) -> ClickHouse
#
# Uso:
#   ./run_pipeline.sh up                       # levanta la infraestructura
#   ./run_pipeline.sh scrap [game_id]          # scrapea un partido y lo sube a raw
#   ./run_pipeline.sh liga <comp> [--limit N] [--force] [--delay S]
#                                              # escanea una competición completa a raw
#   ./run_pipeline.sh bronze                   # ejecuta el job bronze
#   ./run_pipeline.sh silver                   # ejecuta el job silver
#   ./run_pipeline.sh gold                     # ejecuta el job gold
#   ./run_pipeline.sh export                   # gold/silver Delta -> staging parquet
#   ./run_pipeline.sh clickhouse               # carga staging en ClickHouse
#   ./run_pipeline.sh backfill [moderno|completo|temporadas]
#                                              # histórico inicial (ver scripts/backfill_historico.sh)
#   ./run_pipeline.sh actualizar               # baja lo que falte de la temporada en curso
#   ./run_pipeline.sh api                      # levanta la API REST (puerto 8000)
#   ./run_pipeline.sh front                    # levanta el frontend (puerto 3000)
#   ./run_pipeline.sh vacuum                   # VACUUM Delta (mantenimiento opcional)
#   ./run_pipeline.sh all [game_id]            # flujo completo de un partido
#   ./run_pipeline.sh liga-all <comp> [--limit N]
#                                              # flujo completo de una competición
#   ./run_pipeline.sh down                     # apaga todo
# ============================================================
set -e

MINIO="http://minio:9000"
ACCESS="minioadmin"
SECRET="minioadmin"
GAME_ID="${2:-2484886}"

cmd="$1"

# JARs necesarios para Delta + S3 (se instalan dentro del contenedor si faltan)
JARS="/opt/spark/jars/delta-spark_2.12-3.2.0.jar,/opt/spark/jars/delta-storage-3.2.0.jar,/opt/spark/jars/hadoop-aws-3.3.4.jar,/opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar"

ensure_jars() {
    docker exec feb-spark-master bash -c '
        if ! ls /opt/spark/jars/delta-spark_2.12-3.2.0.jar >/dev/null 2>&1; then
            echo "Instalando JARs de Delta/S3 en spark-master..."
            cd /tmp
            wget -q https://repo1.maven.org/maven2/io/delta/delta-spark_2.12/3.2.0/delta-spark_2.12-3.2.0.jar
            wget -q https://repo1.maven.org/maven2/io/delta/delta-storage/3.2.0/delta-storage-3.2.0.jar
            wget -q https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar
            wget -q https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar
            cp /tmp/*.jar /opt/spark/jars/
            echo "JARs instalados."
        fi
        if ! python3 -c "import delta" >/dev/null 2>&1; then
            echo "Instalando delta-spark (pip) en spark-master..."
            pip install -q delta-spark==3.2.0
        fi'
}

sync_jobs() {
    # Copia los jobs locales al contenedor (la imagen los congela en build)
    docker cp jobs/spark_bronze.py feb-spark-master:/opt/jobs/spark_bronze.py
    docker cp jobs/spark_silver.py feb-spark-master:/opt/jobs/spark_silver.py
    docker cp jobs/spark_gold.py feb-spark-master:/opt/jobs/spark_gold.py
    docker cp jobs/export_clickhouse.py feb-spark-master:/opt/jobs/export_clickhouse.py
}

run_spark() {
    local job=$1
    ensure_jars
    sync_jobs
    # FEB_REBUILD reescribe esquema y particiones (necesario si cambia el
    # particionado). FEB_COMPETITIONS y FEB_SEASONS acotan la ejecución a unas
    # particiones concretas, que es lo que hace incremental el pipeline.
    docker exec \
        -e FEB_REBUILD="${FEB_REBUILD:-}" \
        -e FEB_COMPETITIONS="${FEB_COMPETITIONS:-}" \
        -e FEB_SEASONS="${FEB_SEASONS:-}" \
        feb-spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --jars ${JARS} \
        --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
        --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
        /opt/jobs/${job} "$MINIO" "$ACCESS" "$SECRET"
}

vacuum() {
    # Elimina archivos parquet obsoletos de las tablas Delta (los overwrite los dejan en disco)
    ensure_jars
    cat > /tmp/vacuum_pipeline.py << 'PYEOF'
from pyspark.sql import SparkSession
from delta.tables import DeltaTable
spark = (SparkSession.builder.appName('vacuum')
  .config('spark.sql.extensions','io.delta.sql.DeltaSparkSessionExtension')
  .config('spark.sql.catalog.spark_catalog','org.apache.spark.sql.delta.catalog.DeltaCatalog')
  .config('spark.hadoop.fs.s3a.endpoint','http://minio:9000')
  .config('spark.hadoop.fs.s3a.access.key','minioadmin')
  .config('spark.hadoop.fs.s3a.secret.key','minioadmin')
  .config('spark.hadoop.fs.s3a.path.style.access','true')
  .config('spark.hadoop.fs.s3a.impl','org.apache.hadoop.fs.s3a.S3AFileSystem')
  .config('spark.hadoop.fs.s3a.connection.ssl.enabled','false')
  .config('spark.databricks.delta.retentionDurationCheck.enabled','false').getOrCreate())
for t in ['bronze/games','bronze/players','bronze/playbyplay','bronze/shots','bronze/teamstats',
          'silver/games','silver/players','silver/playbyplay','silver/shots','silver/teamstats',
          'gold/dim_jugadores','gold/dim_equipos','gold/fact_partidos',
          'gold/fact_equipo_estadisticas','gold/fact_tiros']:
    try:
        DeltaTable.forPath(spark, 's3a://'+t).vacuum(0)
        print('vacuum OK', t)
    except Exception as e:
        print('vacuum ERR', t, str(e)[:80])
PYEOF
    docker cp /tmp/vacuum_pipeline.py feb-spark-master:/tmp/vacuum_pipeline.py
    docker exec feb-spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --jars ${JARS} /tmp/vacuum_pipeline.py
}

case "$cmd" in
    up)
        docker compose up -d --build
        echo "Esperando a que MinIO y Spark estén listos..."
        sleep 20
        ensure_jars
        docker compose ps
        ;;
    scrap)
        echo "Scraping partido $GAME_ID y subiendo a raw..."
        source venv/bin/activate
        python main.py partido "$GAME_ID" --upload
        ;;
    liga)
        COMP="${2:-tercerafeb}"
        shift 2
        echo "Escaneando competición $COMP a raw..."
        source venv/bin/activate
        python main.py liga "$COMP" --upload "$@"
        ;;
    grupo-e)
        shift
        echo "Escaneando Grupo E (Tercera FEB/Liga EBA) a raw..."
        source venv/bin/activate
        python main.py grupo-e --upload "$@"
        ;;
    historico)
        COMP="${2:-tercerafeb}"
        shift 2 2>/dev/null || shift
        echo "Descargando histórico completo de $COMP a raw..."
        source venv/bin/activate
        python main.py historico "$COMP" --upload "$@"
        ;;
    bronze)
        run_spark spark_bronze.py
        ;;
    silver)
        run_spark spark_silver.py
        ;;
    gold)
        run_spark spark_gold.py
        ;;
    export)
        echo "Exportando silver/gold Delta -> staging (parquet plano)..."
        run_spark export_clickhouse.py
        ;;
    clickhouse)
        echo "Cargando staging -> ClickHouse..."
        source venv/bin/activate
        python jobs/load_clickhouse.py
        ;;
    vacuum)
        echo "VACUUM de tablas Delta (mantenimiento, opcional)..."
        vacuum
        ;;
    all)
        ./run_pipeline.sh up
        ./run_pipeline.sh scrap "$GAME_ID"
        ./run_pipeline.sh bronze
        ./run_pipeline.sh silver
        ./run_pipeline.sh gold
        ./run_pipeline.sh export
        ./run_pipeline.sh clickhouse
        echo "Pipeline completado."
        ;;
    liga-all)
        COMP="${2:-tercerafeb}"
        LIMIT=""
        for a in "$@"; do
            if [ "$a" = "--limit" ]; then LIMIT="--limit"; fi
            if [ "$LIMIT" = "--limit" ] && [[ "$a" =~ ^[0-9]+$ ]]; then LIMIT="--limit $a"; fi
        done
        # si no se especificó límite, LIMIT queda vacío y no se pasa flag
        ./run_pipeline.sh up
        if [ -z "$LIMIT" ]; then
            ./run_pipeline.sh liga "$COMP"
        else
            ./run_pipeline.sh liga "$COMP" "$LIMIT"
        fi
        ./run_pipeline.sh bronze
        ./run_pipeline.sh silver
        ./run_pipeline.sh gold
        ./run_pipeline.sh export
        ./run_pipeline.sh clickhouse
        echo "Pipeline de competición completado."
        ;;
    actualizar)
        shift
        echo "Actualizando la temporada en curso..."
        ./scripts/actualizar_temporada.sh "$@"
        ;;
    backfill)
        echo "Descargando el histórico de las competiciones absolutas..."
        ./scripts/backfill_historico.sh "${2:-moderno}" "${3:-}"
        ;;
    api)
        echo "Levantando la API en http://localhost:8000 (docs en /docs)..."
        source venv/bin/activate
        uvicorn api:app --host 0.0.0.0 --port 8000 --reload
        ;;
    front)
        echo "Levantando el frontend en http://localhost:3000..."
        cd frontend && npm run dev
        ;;
    down)
        docker compose down
        ;;
    *)
        echo "Uso: ./run_pipeline.sh {up|scrap|liga|grupo-e|historico|backfill|actualizar|bronze|silver|gold|export|clickhouse|api|front|vacuum|all|liga-all|down} [game_id|comp] [--limit N] [--force]"
        ;;
esac