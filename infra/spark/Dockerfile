FROM apache/spark:3.5.1

USER root

# Copia de los jobs y configuración
COPY jobs/ /opt/jobs/
COPY infra/spark/setup.sh /opt/conf/setup.sh

# JARs para S3 (MinIO) y Delta Lake (con el nombre de artifact correcto: delta-spark)
RUN wget -q -P /opt/spark/jars \
        https://repo1.maven.org/maven2/io/delta/delta-spark_2.12/3.2.0/delta-spark_2.12-3.2.0.jar \
    && wget -q -P /opt/spark/jars \
        https://repo1.maven.org/maven2/io/delta/delta-storage/3.2.0/delta-storage-3.2.0.jar \
    && wget -q -P /opt/spark/jars \
        https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
    && wget -q -P /opt/spark/jars \
        https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
    && chmod +x /opt/conf/setup.sh \
    && mkdir -p /opt/spark-data

WORKDIR /opt/spark
CMD ["/opt/spark/bin/spark-class", "org.apache.spark.deploy.master.Master"]