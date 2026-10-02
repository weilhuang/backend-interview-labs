#!/usr/bin/env bash
set -euo pipefail
# PREFIX must be a fresh directory under RUNNER_TEMP. Only downloaded temp
# archives owned by this invocation are removed; no global disk cleanup.
: "${RUNNER_TEMP:?}" "${1:?fresh install prefix required}"
prefix="$1"
python - "$prefix" "$RUNNER_TEMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]).resolve();r=Path(sys.argv[2]).resolve()
assert p!=r and p.is_relative_to(r) and not p.exists(), 'install prefix is not a fresh RUNNER_TEMP child'
p.mkdir()
PY
pins="$(dirname "$0")/toolchain.json"
readarray -t values < <(python - "$pins" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
for kind in ('idea','academy'):
 for key in ('url','sha256'):print(p[kind][key])
PY
)
curl --fail --location --retry 2 --connect-timeout 30 --max-time 480 "${values[0]}" -o "$prefix/idea.tar.gz"
printf '%s  %s\n' "${values[1]}" "$prefix/idea.tar.gz" | sha256sum --check --strict
mkdir "$prefix/idea"
python "$(dirname "$0")/extract_toolchain.py" idea "$prefix/idea.tar.gz" "$prefix/idea"
rm -- "$prefix/idea.tar.gz"
curl --fail --location --retry 2 --connect-timeout 30 --max-time 180 "${values[2]}" -o "$prefix/academy.zip"
printf '%s  %s\n' "${values[3]}" "$prefix/academy.zip" | sha256sum --check --strict
mkdir "$prefix/plugins"
python "$(dirname "$0")/extract_toolchain.py" academy "$prefix/academy.zip" "$prefix/plugins"
python - "$prefix" "$pins" <<'PY'
import json,sys,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
p=Path(sys.argv[1]);pins=json.load(open(sys.argv[2]));info=json.load(open(p/'idea/product-info.json'))
assert info['version']==pins['idea']['version'] and info['buildNumber']==pins['idea']['build'], 'IDEA identity mismatch'
jar=p/'plugins/JetBrainsAcademy/lib'/('JetBrainsAcademy-'+pins['academy']['version']+'.jar')
with zipfile.ZipFile(jar) as z:
 plugin=ET.fromstring(z.read('META-INF/plugin.xml'))
 assert plugin.findtext('version')==pins['academy']['version']
 assert plugin.findtext('id')=='com.jetbrains.edu'
assert (p/'idea/bin/idea').is_file() and (p/'idea/jbr').is_dir()
PY
rm -- "$prefix/academy.zip"
du -sh "$prefix/idea" "$prefix/plugins"
df -h "$prefix"
