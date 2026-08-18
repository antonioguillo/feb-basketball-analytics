"""Job Spark - Export para ClickHouse
Lee las tablas Delta de las capas silver/gold (estado lógico, sin archivos obsoletos)
y las materializa como Parquet plano limpio en s3a://staging/<tabla> (overwrite).

Al escribir Parquet plano (no Delta) con mode=overwrite, Spark elimina el contenido
previo del directorio, por lo que ClickHouse siempre lee el snapshot actual sin
duplicados y sin necesidad de VACUUM.

Uso: spark-submit export_clickhouse.py [minio_endpoint] [access_key] [secret_key]
"""
import os
import sys
from pyspark.sql import SparkSession, functions as F

MINIO_ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://minio:9000"
ACCESS_KEY = sys.argv[2] if len(sys.argv) > 2 else "minioadmin"
SECRET_KEY = sys.argv[3] if len(sys.argv) > 3 else "minioadmin"

# Por defecto el data lake vive en MinIO y las tablas son Delta. Los tests
# redirigen ambas cosas a disco local con parquet para ejecutar el job sin
# Docker; ver tests/test_pipeline_local.py.
LAKE_ROOT = os.environ.get("FEB_LAKE_ROOT", "s3a://")
TABLE_FORMAT = os.environ.get("FEB_TABLE_FORMAT", "delta")

_builder = (SparkSession.builder.appName("FEB Export ClickHouse")
            .config("spark.sql.shuffle.partitions", "8"))
if TABLE_FORMAT == "delta":
    _builder = (_builder
                .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
                .config("spark.sql.catalog.spark_catalog",
                        "org.apache.spark.sql.delta.catalog.DeltaCatalog"))
if LAKE_ROOT.startswith("s3a://"):
    _builder = (_builder
                .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
                .config("spark.hadoop.fs.s3a.access.key", ACCESS_KEY)
                .config("spark.hadoop.fs.s3a.secret.key", SECRET_KEY)
                .config("spark.hadoop.fs.s3a.path.style.access", "true")
                .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
                .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false"))
spark = _builder.getOrCreate()

# (tabla Delta origen, tabla parquet destino)
EXPORTS = [
    ("silver/players", "jugadores"),
    ("silver/playbyplay", "playbyplay"),
    ("gold/fact_tiros", "tiros"),
    ("silver/teamstats", "equipos_partido"),
    ("gold/fact_partidos", "partidos"),
]


def export(src: str, dst: str):
    df = spark.read.format(TABLE_FORMAT).load("s3a://" + src)
    df.write.mode("overwrite").format("parquet").save("s3a://staging/" + dst)
    print(f"export {dst}: {df.count()} filas")


if __name__ == "__main__":
    for src, dst in EXPORTS:
        export(src, dst)
    spark.stop()