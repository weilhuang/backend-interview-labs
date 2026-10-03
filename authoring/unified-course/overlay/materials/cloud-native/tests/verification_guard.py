"""验证器边界：空选择、陈旧产物和基础设施错误都不能变成课程通过。"""
import datetime,hashlib,json,pathlib,uuid

class VerificationSetupError(RuntimeError):
    """工具、产物或证据不满足前置条件，不能归类为已杀死错误解。"""

class VerificationInfrastructureError(VerificationSetupError):
    """请求传输、依赖或服务不可用；保留观测但不能证明目标业务错误。"""
    def __init__(self,case_id,detail):
        self.case_id=case_id
        self.detail=detail
        super().__init__(case_id,detail)

class ContractViolation(AssertionError):
    """只用于实际观察到的、可命名的课程行为违约。"""
    def __init__(self,case_id,detail):
        self.case_id=case_id
        self.detail=detail
        super().__init__(case_id,detail)

def require_contract(condition,case_id,detail):
    if not condition:raise ContractViolation(case_id,detail)

def require_selection(selected,allowed,label='verification'):
    values=list(selected)
    if not values:raise VerificationSetupError(label+': empty selection is not a successful run')
    if len(values)!=len(set(values)):raise VerificationSetupError(label+': duplicate selection')
    unknown=set(values)-set(allowed)
    if unknown:raise VerificationSetupError(label+': unknown selection '+','.join(sorted(unknown)))
    return values

def claim_evidence(directory):
    directory=pathlib.Path(directory)
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise VerificationSetupError('Evidence directory must be new or empty; previous artifacts are not current results')
    directory.mkdir(parents=True,exist_ok=True)
    context={'run_id':uuid.uuid4().hex,'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'RUNNING'}
    try:
        with (directory/'run-context.json').open('x',encoding='utf-8') as stream:json.dump(context,stream,indent=2)
    except FileExistsError:raise VerificationSetupError('Concurrent or stale evidence writer') from None
    return context

def java_source_manifest(root):
    root=pathlib.Path(root)
    sources=sorted((root/'src').rglob('*.java'))
    if not sources:raise VerificationSetupError('No Java sources selected')
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}

def class_manifest(classes):
    classes=pathlib.Path(classes)
    files=sorted(classes.rglob('*.class'))
    if not files:raise VerificationSetupError('No compiled classes exist')
    return {p.relative_to(classes).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def verify_compilation(classes,root):
    classes=pathlib.Path(classes)
    receipt=classes/'compile-receipt.json'
    if not receipt.is_file():raise VerificationSetupError('Missing compilation receipt; compile into a fresh output directory')
    try:data=json.loads(receipt.read_text(encoding='utf-8'))
    except (ValueError,OSError):raise VerificationSetupError('Unreadable compilation receipt') from None
    if data.get('status')!='COMPILED' or data.get('release')!=21:raise VerificationSetupError('Compilation did not complete for Java 21')
    if data.get('sources')!=java_source_manifest(root):raise VerificationSetupError('Java sources changed after compilation')
    if data.get('classes')!=class_manifest(classes):raise VerificationSetupError('Compiled output is stale, incomplete or contains extra classes')
    return data

def claim_report(path):
    path=pathlib.Path(path)
    if path.exists():raise VerificationSetupError('Report already exists; use a fresh result path')
    path.parent.mkdir(parents=True,exist_ok=True)
    context=claim_evidence(path.parent/(path.name+'.run'))
    try:
        with path.open('x',encoding='utf-8') as stream:json.dump(context,stream,indent=2)
    except FileExistsError:raise VerificationSetupError('Concurrent report writer') from None
    return context
