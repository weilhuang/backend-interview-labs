# C11-01 starter：可以构建运行，但单阶段带编译器且默认root，故验收预期失败。
ARG JAVA_BUILD_IMAGE
FROM ${JAVA_BUILD_IMAGE}
WORKDIR /opt/app
COPY src/ src/
COPY web/ web/
RUN mkdir -p classes && javac --release 21 -encoding UTF-8 -d classes src/labs/*.java
EXPOSE 8080
ENTRYPOINT ["java", "-cp", "/opt/app/classes", "labs.CloudNativeApp"]
