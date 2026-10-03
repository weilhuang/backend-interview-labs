"""Linux no-follow file operations for small CI evidence; no implicit overwrites."""
import os
from pathlib import Path
import stat
import uuid
from contextlib import contextmanager

class BoundaryError(ValueError): pass

def absolute(path):
    path=Path(path).absolute()
    if '..' in path.parts: raise BoundaryError('parent traversal forbidden')
    return path

@contextmanager
def directory_fd(path):
    path=absolute(path);fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
        yield fd
    finally:os.close(fd)

def validate_directory(path):
    with directory_fd(path):pass

def new_directory(path):
    path=absolute(path)
    with directory_fd(path.parent) as fd:os.mkdir(path.name,0o700,dir_fd=fd)
    validate_directory(path)

def read_regular(path,limit=None,tail=False):
    path=absolute(path)
    with directory_fd(path.parent) as directory:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):raise BoundaryError('evidence is not a regular file')
            if limit is not None and info.st_size>limit and not tail:raise BoundaryError('evidence exceeds size limit')
            if tail and limit is not None:os.lseek(fd,max(0,info.st_size-limit),os.SEEK_SET)
            with os.fdopen(fd,'rb',closefd=False) as stream:return stream.read(limit if limit is not None else -1)
        finally:os.close(fd)

def write_new(path,data):
    path=absolute(path)
    with directory_fd(path.parent) as directory:
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:
            with os.fdopen(fd,'wb',closefd=False) as stream:stream.write(data)
        finally:os.close(fd)

def replace_regular(path,data):
    """Atomically replace an owned regular report; reject any existing symlink."""
    path=absolute(path)
    with directory_fd(path.parent) as directory:
        try:
            info=os.stat(path.name,dir_fd=directory,follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):raise BoundaryError('refuse replacing non-regular report')
        except FileNotFoundError:pass
        temporary='.'+path.name+'.'+uuid.uuid4().hex
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:
            with os.fdopen(fd,'wb',closefd=False) as stream:stream.write(data)
        finally:os.close(fd)
        try:os.replace(temporary,path.name,src_dir_fd=directory,dst_dir_fd=directory)
        except BaseException:
            os.unlink(temporary,dir_fd=directory);raise

@contextmanager
def exclusive_writer(path):
    path=absolute(path)
    with directory_fd(path.parent) as directory:
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as stream:yield stream

@contextmanager
def regular_reader(path):
    path=absolute(path)
    with directory_fd(path.parent) as directory:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):os.close(fd);raise BoundaryError('not a regular input')
        with os.fdopen(fd,'rb') as stream:yield stream
