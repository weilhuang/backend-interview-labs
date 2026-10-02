ARG JAVA_BUILD_IMAGE
ARG JAVA_RUNTIME_IMAGE
FROM ${JAVA_BUILD_IMAGE} AS build
WORKDIR /build
COPY src/ src/
RUN mkdir classes && javac --release 21 --add-modules jdk.httpserver -d classes src/labs/*.java
FROM ${JAVA_RUNTIME_IMAGE}
ARG RELEASE=v1
WORKDIR /opt/app
COPY --from=build /build/classes classes
COPY web web
RUN printf '%s\n' "$RELEASE" > /opt/app/release
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-Xms32m", "-Xmx128m", "--add-modules", "jdk.httpserver", "-cp", "/opt/app/classes", "labs.KubernetesApp"]
