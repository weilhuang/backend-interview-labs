#!/usr/bin/env python3
"""登记全部可见课程资产；不会打包或宣称生成官方Academy归档。"""
from pathlib import Path
import yaml
root=Path(__file__).resolve().parents[1]
files=[]
for p in sorted(root.rglob('*')):
 if not p.is_file() or any(x in p.relative_to(root).parts for x in ('build','.gradle','__pycache__')):continue
 rel=p.relative_to(root).as_posix()
 if rel.startswith('capstone/') or rel=='course-info.yaml':continue
 item={'name':rel}
 if p.suffix=='.jar':item['is_binary']=True
 files.append(item)
course={'type':'marketplace','title':'C14后端综合项目：订单库存与可恢复消息','language':'Chinese','summary':'五阶段独立编码检查点，真实MySQL、Redis、Kafka和gRPC，公开源码、调用方、全部测试、标准答案与中文前端。验收状态见阶段报告。','programming_language':'Java','content':['capstone'],'environment_settings':{'jvm_language_level':'JDK_21'},'additional_files':files,'yaml_version':2}
(root/'course-info.yaml').write_text(yaml.safe_dump(course,allow_unicode=True,sort_keys=False))
