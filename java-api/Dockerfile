# Imágenes oficiales fijadas por digest; Maven compila y el runtime solo lleva el JRE.
FROM maven:3.10.0-eclipse-temurin-27@sha256:bd2c0a2c430f787b7b6887826b6b1a43fe48f1e3ca4196b9ab886567bf54de58 AS build
WORKDIR /build
ENV MAVEN_OPTS="-Xmx384m"
COPY pom.xml .
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp package

FROM eclipse-temurin:27-jre@sha256:0dd0465f90d398fa3226b56a3973f5d3c47ac323934dceebdab45ac8910bee6e
WORKDIR /app
COPY --from=build /build/target/java-api.jar ./app.jar
ENV JAVA_TOOL_OPTIONS="-Xms64m -Xmx256m"
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
