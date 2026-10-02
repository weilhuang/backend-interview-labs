"""Explicit class/method contracts for each variant. Generated metadata is an expectation, never a result."""
import fnmatch,re
FAILURES={
 'wrong-header-leak':('SafeEventsTest',['jsonHasTypedFieldsAndUtcTime','dropsAllHeadersIncludingPiiAndMixedCaseNames','rejectsDynamicPathAndCrlfDoesNotCreateAnEvent','eventIdStableWithinALineAndDistinctAcrossEvents','invalidTraceIdsCannotInjectJson','durationIsNotComputedFromWallClock']),
 'wrong-json-concatenation':('SafeEventsTest',['jsonHasTypedFieldsAndUtcTime','dropsAllHeadersIncludingPiiAndMixedCaseNames','rejectsDynamicPathAndCrlfDoesNotCreateAnEvent','eventIdStableWithinALineAndDistinctAcrossEvents','invalidTraceIdsCannotInjectJson','durationIsNotComputedFromWallClock']),
 'wrong-high-cardinality':('RequestMetricsTest',['tenThousandIdsCannotCreateTenThousandSeries']),
 'wrong-millisecond-unit':('RequestMetricsTest',['exactCountAndSecondsHistogram']),
 'wrong-double-count':('RequestMetricsTest',['exactCountAndSecondsHistogram','tenThousandIdsCannotCreateTenThousandSeries']),
 'wrong-new-trace-every-hop':('TraceBridgeTest',['propagationKeepsTraceAndParentChildIdsAcrossServiceBoundary','parentBasedSamplingLossCannotBeRecoveredByCollector']),
 'wrong-baggage-leak':('TraceBridgeTest',['headerNamesAreCanonicalAndBaggageNeverPropagates']),
 'wrong-retry-all-failures':('HttpCallChainTest',['failedInventoryMarksRealServerAndClientErrors'])
}
def enrich(variants,root):
 cases=set()
 for p in (root/'observability-lab/src/test/java').rglob('*.java'):
  s=p.read_text();package=re.search(r'package\s+([\w.]+)\s*;',s)
  for method in re.findall(r'@Test\s+void\s+(\w+)\s*\(',s):
   cases.add(package.group(1)+'.'+p.stem+'#'+method)
 for name,item in variants.items():
  selected={c for c in cases if any(fnmatch.fnmatchcase(c.split('#')[0],p) for p in item['tests'])}
  item['expected_test_cases']=sorted(selected)
  if name in FAILURES:
   klass,methods=FAILURES[name];item['expected_failure_cases']=['labs.observability.'+klass+'#'+m for m in methods]
  elif name=='starter' or name.startswith('native-starter-'):
   metric_failures={'exactCountAndSecondsHistogram','tenThousandIdsCannotCreateTenThousandSeries','invalidObservationDoesNotIncrement'}
   item['expected_failure_cases']=sorted(c for c in selected if (not c.startswith('labs.observability.RequestMetricsTest#') or c.split('#')[1] in metric_failures))
  else:item['expected_failure_cases']=[]
 return variants
