FROM eclipse-temurin:21-jdk

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

MAINTAINER Ling Li

# Download and install dockerize.
# Needed so the web container will wait for MariaDB to start.
ENV DOCKERIZE_VERSION v0.19.0
RUN curl -sfL https://github.com/powerman/dockerize/releases/download/"$DOCKERIZE_VERSION"/dockerize-`uname -s`-`uname -m` | install /dev/stdin /usr/local/bin/dockerize

EXPOSE 8180
EXPOSE 8443
WORKDIR /code

VOLUME ["/code"]

# Copy Maven wrapper and pom.xml first to leverage Docker layer caching for dependencies
COPY pom.xml mvnw ./
COPY .mvn/ .mvn/

# Fix potential Windows line endings and pre-download all Maven dependencies
RUN tmp_mvnw=$(mktemp) && tr -d '\r' < ./mvnw > "$tmp_mvnw" && chmod +x "$tmp_mvnw" && \
    MAVEN_BASEDIR=/code "$tmp_mvnw" dependency:go-offline -Pdocker,mariadb && \
    rm -f "$tmp_mvnw"

# Now copy the application's source code (changes frequently)
COPY . /code

# Wait for the db to startup (via dockerize), then build and run steve.
# Build happens at runtime because the mariadb profile triggers Flyway migrations
# which require a live database connection.
CMD dockerize -wait tcp://db:3306 -timeout 60s && \
	tmp_mvnw=$(mktemp) && tr -d '\r' < ./mvnw > "$tmp_mvnw" && MAVEN_BASEDIR=/code bash "$tmp_mvnw" package -Pdocker,mariadb -Djdk.tls.client.protocols="TLSv1,TLSv1.1,TLSv1.2" && rm -f "$tmp_mvnw" && \
	java -XX:MaxRAMPercentage=85 -jar target/steve.war
