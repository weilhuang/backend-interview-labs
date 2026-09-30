#!/usr/bin/env python3
"""从唯一台账生成独立作者工程所需镜像快照；不生成或伪称Academy官方ZIP。"""
from pathlib import Path
import hashlib
root=Path(__file__).resolve().parents[1];source=root.parents[1]/'infra/versions.env'
if not source.is_file():raise SystemExit('只能在完整仓库中从infra/versions.env生成快照')
raw=source.read_bytes();(root/'shared/versions.env').write_bytes(raw);(root/'shared/versions.sha256').write_text(hashlib.sha256(raw).hexdigest()+'  versions.env\n')
print('已从唯一台账生成快照，SHA-256：'+hashlib.sha256(raw).hexdigest())
