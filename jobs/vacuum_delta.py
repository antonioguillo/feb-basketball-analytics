"""Job Spark - Mantenimiento de las tablas Delta.

Cada escritura con `overwrite` deja en disco los ficheros de la versión
anterior. Delta los marca como retirados pero no los borra, para poder viajar
en el tiempo. VACUUM es lo que los elimina de verdad.

Se ejecuta con retención 0, así que descarta el historial de versiones: es lo
que se quiere en este proyecto, donde raw es la fuente de verdad y cualquier
capa se puede reconstruir.

Uso: spark-submit vacuum_delta.py [minio_endpoint] [access_key] [secret_key]
"""
import os
import sys

from pyspark.sql import SparkSession

MINIO_ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://minio:9000"
ACCESS_KEY = sys.argv[2] if len(sys.argv) > 2 else "minioadmin"
SECRET_KEY = sys.argv[3] if len(sys.argv) > 3 else "minioadmin"

LAKE_ROOT = os.environ.get("FEB_LAKE_ROOT", "s3a://")

TABLAS = [
    "bronze/games", "bronze/players", "bronze/playbyplay",
    "bronze/shots", "bronze/teamstats",
    "silver/games", "silver/players", "silver/playbyplay",
    "silver/shots", "silver/teamstats",
    "gold/dim_jugadores", "gold/dim_equipos", "gold/fact_partidos",
    "gold/fact_equipo_estadisticas", "gold/fact_tiros",
]

spark = (SparkSession.builder.appName("FEB Vacuum")
         .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
         .config("spark.sql.catalog.spark_catalog",
                 "org.apache.spark.sql.delta.catalog.DeltaCatalog")
         .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
         .config("spark.hadoop.fs.s3a.access.key", ACCESS_KEY)
         .config("spark.hadoop.fs.s3a.secret.key", SECRET_KEY)
         .config("spark.hadoop.fs.s3a.path.style.access", "true")
         .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
         .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
         # Sin esto Delta se niega a vaciar con retención menor de 7 días.
         .config("spark.databricks.delta.retentionDurationCheck.enabled", "false")
         .getOrCreate())

if __name__ == "__main__":
    from delta.tables import DeltaTable

    limpiadas = omitidas = 0
    for tabla in TABLAS:
        ruta = LAKE_ROOT + tabla
        try:
            DeltaTable.forPath(spark, ruta).vacuum(0)
            print(f"vacuum OK   {tabla}")
            limpiadas += 1
        except Exception as error:
            # Una tabla que aún no existe no es un fallo: puede que esa capa
            # todavía no se haya construido.
            print(f"vacuum OMIT {tabla}: {str(error)[:90]}")
            omitidas += 1

    print(f"\n{limpiadas} tablas limpiadas, {omitidas} omitidas")
    spark.stop()
