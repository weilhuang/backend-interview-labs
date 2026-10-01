#!/usr/bin/env python3
"""云端无 Java 网络时下载严格编译所需的官方 Maven 构件；正常学生流程仍使用 Gradle。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'build/manual-deps'
DEST.mkdir(parents=True, exist_ok=True)
ARTIFACTS = [
    ('org.apache.kafka', 'kafka-clients', '3.9.1'),
    ('com.h2database', 'h2', '2.3.232'),
    ('org.apache.rocketmq', 'rocketmq-client-java', '5.0.8'),
    ('org.testcontainers', 'testcontainers', '1.20.6'),
    ('org.testcontainers', 'kafka', '1.20.6'),
    ('org.testcontainers', 'mysql', '1.20.6'),
    ('org.testcontainers', 'jdbc', '1.20.6'),
    ('org.testcontainers', 'database-commons', '1.20.6'),
    ('com.github.docker-java', 'docker-java-api', '3.4.1'),
    ('com.github.docker-java', 'docker-java-transport', '3.4.1'),
    ('org.slf4j', 'slf4j-api', '2.0.16'),
    ('org.slf4j', 'slf4j-simple', '2.0.16'),
    ('junit', 'junit', '4.13.2'),
    ('org.hamcrest', 'hamcrest-core', '1.3'),
    ('com.mysql', 'mysql-connector-j', '9.2.0'),
    ('org.apache.commons', 'commons-compress', '1.24.0'),
    ('org.junit.platform', 'junit-platform-console-standalone', '1.11.4'),
]
def download(item):
    group, name, version = item
    path = f'{group.replace(".", "/")}/{name}/{version}/{name}-{version}.jar'
    target = DEST / path.rsplit('/', 1)[-1]
    if not target.exists():
        with urllib.request.urlopen('https://repo.maven.apache.org/maven2/' + path, timeout=90) as response:
            target.write_bytes(response.read())
    return target.name
with ThreadPoolExecutor(max_workers=6) as executor:
    for name in executor.map(download, ARTIFACTS): print('已准备', name, flush=True)
