if not __debug__: raise SystemExit("拒绝Python优化模式，不能移除静态契约断言")
#!/usr/bin/env python3
"""Materialize learner source from the actual UTF16 task regions; never compiles or runs Java."""
from pathlib import Path
import json,shutil
import yaml
R=Path(__file__).resolve().parents[1]
variants=json.loads((R/'manifest/variants.json').read_text())
for slug,test in [('safe-events','SafeEventsTest'),('metrics','RequestMetricsTest'),('trace-context','TraceBridgeTest')]:
 task=R/'academy-overlay/observability/first-slice'/slug
 target=R/'academy-learner-variants'/slug/'src'
 shutil.copytree(task/'src',target,dirs_exist_ok=True)
 data=yaml.safe_load((task/'task-info.yaml').read_text())
 for entry in data['files']:
  if not entry.get('placeholders'):continue
  source=target/Path(entry['name']).relative_to('src')
  raw=source.read_text().encode('utf-16-le')
  for region in sorted(entry['placeholders'],key=lambda x:x['offset'],reverse=True):
   start=region['offset']*2;end=(region['offset']+region['length'])*2
   raw=raw[:start]+region['placeholder_text'].encode('utf-16-le')+raw[end:]
  source.write_text(raw.decode('utf-16-le'))
 variants['native-starter-'+slug]={'path':str(target.relative_to(R)),'tests':['labs.observability.'+test],'expected':'EXPECTED_TEST_FAILURE'}
from variant_contracts import enrich
variants=enrich(variants,R)
(R/'manifest/variants-extended.json').write_text(json.dumps(variants,ensure_ascii=False,indent=2)+'\n')
print('3 starter source trees materialized; compilation and test execution NOT_RUN')
