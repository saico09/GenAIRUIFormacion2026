# De dónde salió java-api

28/10/2026: proyecto descargado de [Spring Initializr](https://start.spring.io/) con Maven, Java 27 y Spring Boot 4.1.2. Se eligieron Spring Web, Validation, Spring Data JPA y PostgreSQL Driver.

- URL: `https://start.spring.io/starter.zip?type=maven-project&language=java&bootVersion=4.1.2&baseDir=java-api&groupId=com.conkord.genai&artifactId=java-api&name=JavaApi&description=Microservicio%20Java%20de%20la%20formacion%20GenAI&packageName=com.conkord.genai&packaging=jar&javaVersion=27&dependencies=web,validation,data-jpa,postgresql`
- SHA-256 del ZIP recibido: `CDFDCBF2D50CDA6FBB10E444E4280075A81760BF3FFC337B4934CDFD00B5E808`.
- Se conservaron el proyecto, Maven Wrapper 3.3.4 / Maven 3.10.0 y sus archivos de Git. Se quitaron metadatos vacíos y dependencias de test del ejemplo; las comprobaciones funcionales se ejecutan contra los contenedores y PostgreSQL.
- Se añadieron `schema.sql`, la entidad y repositorio `Patient`, lectura del conteo al iniciar y `GET /health`. Esta HDU todavía no publica el CRUD.
- Docker usa imágenes oficiales de Maven 3.10.0 / Temurin 27 y Temurin 27 JRE, fijadas por digest. La versión disponible consultada en Adoptium es 27.0.1; comprobar el binario con `java -version` al construir.
- La tabla vive en `java.patients`. `CREATE IF NOT EXISTS` conserva filas y `ddl-auto=validate` evita cambios automáticos de Hibernate.

Uso y comprobaciones: [GUIA.md](../GUIA.md) y [evidencias](../evidencias/).
