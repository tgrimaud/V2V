# Voice Support Bot - conversation backend image (TASK-DEPLOY-001, ADR-0038).
# Multi-stage: Maven/JDK 17 build stage -> slim JRE 17 runtime stage, non-root.
# There is no Maven wrapper (mvnw) in this repo, so the build stage pins a Maven image.
# All runtime configuration is environment-driven (see application.yml / deployment doc);
# no secret is baked into the image.

# ---- Build stage -------------------------------------------------------------
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build

# Resolve dependencies first so this layer is cached until pom.xml changes.
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline

# Build the executable jar (tests run in CI, not in the image build).
COPY src ./src
RUN mvn -B -q -DskipTests clean package \
    && cp target/voice-support-backend-*.jar /build/app.jar

# ---- Runtime stage -----------------------------------------------------------
FROM eclipse-temurin:17-jre AS runtime

# curl is used by the container HEALTHCHECK (the JRE image ships neither curl nor wget).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app

COPY --from=build --chown=app:app /build/app.jar /app/app.jar

USER app
EXPOSE 8080

# JAVA_OPTS lets the deployment tune heap/GC without rebuilding.
ENV JAVA_OPTS=""

# Container health = Spring Boot actuator health (includes DB readiness). The long
# start-period covers JVM boot + KB sync before the endpoint is expected to answer UP.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/app.jar"]
