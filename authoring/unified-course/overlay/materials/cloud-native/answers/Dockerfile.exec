# 不设置浮动默认值；统一环境入口必须从 shared/versions.env 注入两项。
ARG JAVA_BUILD_IMAGE
ARG JAVA_RUNTIME_IMAGE
FROM ${JAVA_BUILD_IMAGE} AS build
WORKDIR /build
COPY src/ src/
RUN mkdir -p classes && javac --release 21 -encoding UTF-8 -d classes src/labs/*.java

FROM ${JAVA_RUNTIME_IMAGE} AS runtime
WORKDIR /opt/app
COPY --from=build --chown=10001:10001 /build/classes ./classes
COPY --chown=10001:10001 web/ ./web/
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65.0", "-cp", "/opt/app/classes", "labs.CloudNativeApp"]
