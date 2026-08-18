"""Ejecuta bronze -> silver -> gold sobre partidos reales, en disco local.

Los jobs se escribieron para MinIO + Delta, pero leen `FEB_LAKE_ROOT` y
`FEB_TABLE_FORMAT` del entorno, así que aquí se apuntan a un directorio
temporal en parquet y se ejecutan de verdad. Esto cubre exactamente el fallo
que tuvo el proyecto: columnas que un job produce con un nombre y el siguiente
consume con otro, que solo se manifiesta al ejecutar.

Requiere pyspark y una JVM. Si no están, los tests se omiten.

Ejecutar:  python -m unittest tests.test_pipeline_local -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "raw"


def _jvm_opts():
    """Hadoop llama a getSubject(), que desde Java 18 exige habilitar el gestor
    de seguridad. En JVMs anteriores la opción no existe y aborta el arranque,
    así que solo se pasa cuando hace falta."""
    try:
        out = subprocess.run(["java", "-version"], capture_output=True, text=True).stderr
    except OSError:
        return ""
    match = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not match:
        return ""
    major = int(match.group(1))
    if major == 1:                     # esquema antiguo: 1.8 = Java 8
        major = int(match.group(2) or 8)
    return "-Djava.security.manager=allow" if major >= 18 else ""

try:
    import pyspark  # noqa: F401
    HAS_PYSPARK = True
except ImportError:
    HAS_PYSPARK = False


class JobFailed(Exception):
    """Fallo de un job, conservando la salida completa para poder inspeccionarla."""

    def __init__(self, name, stdout, stderr, code):
        self.name, self.stdout, self.stderr, self.code = name, stdout, stderr, code
        super().__init__(
            f"{name} falló ({code})\n"
            f"--- stdout ---\n{stdout[-3000:]}\n"
            f"--- stderr ---\n{stderr[-3000:]}"
        )


def _run_job(name, env):
    """Lanza un job en un proceso aparte: cada uno crea su propia SparkSession."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "jobs" / name)],
        env=env, capture_output=True, text=True, cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise JobFailed(name, result.stdout, result.stderr, result.returncode)
    return result.stdout


@unittest.skipUnless(HAS_PYSPARK, "pyspark no instalado")
class PipelineLocalTest(unittest.TestCase):
    lake = None
    spark = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="feb-lake-")
        cls.lake = Path(cls.tmp)
        raw = cls.lake / "raw"
        raw.mkdir(parents=True)
        for src in FIXTURES.glob("*.json"):
            shutil.copy(src, raw / src.name)

        env = dict(os.environ)
        env["FEB_LAKE_ROOT"] = cls.lake.as_uri().rstrip("/") + "/"
        env["FEB_TABLE_FORMAT"] = "parquet"
        env["PYSPARK_PYTHON"] = sys.executable
        env["PYSPARK_DRIVER_PYTHON"] = sys.executable
        jvm_opts = _jvm_opts()
        if jvm_opts:
            env["JDK_JAVA_OPTIONS"] = jvm_opts
            os.environ["JDK_JAVA_OPTIONS"] = jvm_opts

        cls.output = {}
        try:
            for job in ("spark_bronze.py", "spark_silver.py", "spark_gold.py"):
                cls.output[job] = _run_job(job, env)
        except JobFailed as error:
            # Hadoop necesita winutils.exe/hadoop.dll para tocar el sistema de
            # ficheros en Windows. No es un fallo del pipeline: en WSL o Linux
            # estos mismos tests se ejecutan enteros.
            output = error.stdout + error.stderr
            if "NativeIO" in output or "winutils" in output:
                shutil.rmtree(cls.tmp, ignore_errors=True)
                raise unittest.SkipTest(
                    "Hadoop no puede usar el sistema de ficheros local en Windows "
                    "(falta winutils.exe). Ejecuta estos tests en WSL o Linux."
                ) from error
            raise

        from pyspark.sql import SparkSession
        cls.spark = (SparkSession.builder.appName("FEB tests")
                     .config("spark.sql.shuffle.partitions", "2")
                     .getOrCreate())

    @classmethod
    def tearDownClass(cls):
        if cls.spark is not None:
            cls.spark.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def table(self, layer, name):
        return self.spark.read.parquet(str(self.lake / layer / name))

    # --- bronze -------------------------------------------------------------

    def test_bronze_genera_todas_las_tablas(self):
        for name in ("games", "players", "playbyplay", "shots", "teamstats"):
            self.assertGreater(self.table("bronze", name).count(), 0, f"bronze/{name} vacía")

    def test_bronze_players_lleva_el_equipo(self):
        players = self.table("bronze", "players")
        for column in ("team", "home_team", "away_team"):
            self.assertIn(column, players.columns)
        self.assertEqual(
            players.filter(players.team.isNull()).count(), 0,
            "hay jugadores sin equipo: la ficha solo dice local/visitante, "
            "el nombre tiene que venir de la cabecera del JSON")

    def test_el_equipo_concuerda_con_local_visitante(self):
        players = self.table("bronze", "players")
        mismatched = players.filter(
            (players.is_home & (players.team != players.home_team))
            | (~players.is_home & (players.team != players.away_team))
        ).count()
        self.assertEqual(mismatched, 0)

    # --- silver -------------------------------------------------------------

    def test_silver_renombra_al_contrato_de_consumo(self):
        players = self.table("silver", "players")
        for column in ("minutes", "points", "game_date", "team", "fgm", "fga"):
            self.assertIn(column, players.columns)
        for legacy in ("minutes_played", "puntos"):
            self.assertNotIn(legacy, players.columns)

    def test_silver_calcula_las_metricas_avanzadas(self):
        row = (self.table("silver", "players")
               .filter("t2a > 0 AND t3a > 0 AND fta > 0 AND points > 0")
               .first())
        self.assertIsNotNone(row, "sin filas con tiros para comprobar")
        fga = row["t2a"] + row["t3a"]
        fgm = row["t2m"] + row["t3m"]
        self.assertAlmostEqual(row["effective_fg_pct"], (fgm + 0.5 * row["t3m"]) / fga, places=6)
        self.assertAlmostEqual(
            row["true_shooting_pct"], row["points"] / (2 * (fga + 0.44 * row["fta"])), places=6)

    def test_silver_no_inventa_porcentajes_sin_intentos(self):
        sin_triples = self.table("silver", "players").filter("t3a = 0")
        if sin_triples.count():
            self.assertEqual(sin_triples.filter("three_point_pct IS NOT NULL").count(), 0,
                             "un 0/0 no es un 0 %, tiene que quedar nulo")

    def test_silver_tipa_la_fecha(self):
        row = self.table("silver", "games").first()
        # `year` es columna de partición: al releerla, Spark infiere su tipo,
        # así que se compara como número y no como texto.
        self.assertEqual(row["game_date"].year, int(row["year"]))

    # --- gold ---------------------------------------------------------------

    def test_gold_genera_el_modelo_dimensional(self):
        for name in ("dim_jugadores", "dim_equipos", "fact_partidos",
                     "fact_equipo_estadisticas", "fact_tiros"):
            self.assertGreater(self.table("gold", name).count(), 0, f"gold/{name} vacía")

    def test_dim_jugadores_lleva_equipo_y_ratios_sobre_totales(self):
        dim = self.table("gold", "dim_jugadores")
        self.assertIn("team", dim.columns)
        self.assertEqual(dim.filter(dim.team.isNull()).count(), 0)

        row = dim.filter("total_2pa > 0").first()
        self.assertAlmostEqual(row["two_point_pct"], row["total_2pm"] / row["total_2pa"], places=6)

    def test_fact_partidos_nombra_a_los_dos_equipos(self):
        fact = self.table("gold", "fact_partidos")
        for column in ("home_team", "away_team", "home_score", "away_score", "winner", "margin"):
            self.assertIn(column, fact.columns)
        self.assertEqual(fact.filter("home_team IS NULL OR away_team IS NULL").count(), 0)

    def test_el_marcador_reconstruido_coincide_con_la_ficha(self):
        """La suma de puntos de los jugadores debe dar el marcador del acta."""
        expected = {}
        for path in FIXTURES.glob("*.json"):
            meta = json.load(open(path, encoding="utf-8"))["meta"]
            expected[int(meta["game_id"])] = (int(meta["home_score"]), int(meta["away_score"]))

        for row in self.table("gold", "fact_partidos").collect():
            self.assertIn(int(row["game_id"]), expected)
            self.assertEqual(
                (row["home_score"], row["away_score"]), expected[int(row["game_id"])],
                f"marcador reconstruido != acta en el partido {row['game_id']}")

    def test_fact_tiros_clasifica_zonas_y_distancias(self):
        tiros = self.table("gold", "fact_tiros")
        for column in ("shot_distance_m", "is_three", "zone", "shot_points"):
            self.assertIn(column, tiros.columns)
        zonas = {r["zone"] for r in tiros.select("zone").distinct().collect()}
        self.assertTrue(zonas <= {"aro", "media", "triple"}, f"zonas inesperadas: {zonas}")
        # Ningún tiro puede quedar más lejos que la pista entera
        self.assertEqual(tiros.filter("shot_distance_m > 28").count(), 0)
        # Un triple anotado vale 3
        anotado = tiros.filter("made = 1 AND is_three").first()
        if anotado:
            self.assertEqual(anotado["shot_points"], 3)


if __name__ == "__main__":
    unittest.main()
