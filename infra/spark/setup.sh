#!/bin/bash
# Instala paquetes de Spark para acceso a MinIO (S3) y Delta Lake
set -e

SPARK_HOME=/opt/bitnami/spark
JARS_DIR=$SPARK_HOME/jars

# Delta Lake (necesario para escribir tablas Delta)
DELTA_VERSION=3.2.0
SCALA_VERSION=2.12

wget -q -O $JARS_DIR/delta-core_${SCALA_VERSION}-${DELTA_VERSION}.jar \
  https://repo1.maven.org/maven2/io/delta/delta-core_${SCALA_VERSION}/${DELTA_VERSION}/delta-core_${SCALA_VERSION}-${DELTA_VERSION}.jar || true
wget -q -O $JARS_DIR/delta-storage-${DELTA_VERSION}.jar \
  https://repo1.maven.org/maven2/io/delta/delta-storage/${DELTA_VERSION}/delta-storage-${DELTA_VERSION}.jar || true

# Hadoop AWS (acceso a S3/MinIO)
HADOOP_AWS_VERSION=3.3.4
AWS_SDK_VERSION=1.12.262
wget -q -O $JARS_DIR/hadoop-aws-${HADOOP_AWS_VERSION}.jar \
  https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar || true
wget -q -O $JARS_DIR/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar \
  https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar || true

echo "JARs descargados: $(ls $JARS_DIR/*delta* $JARS_DIR/*aws* 2>/dev/null | wc -l) archivos"