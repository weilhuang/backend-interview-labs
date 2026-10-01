#!/usr/bin/env python3
"""Validate pinned official distribution archives before bounded extraction."""
import argparse
from pathlib import Path, PurePosixPath
import os
import posixpath
import shutil
import stat
import tarfile
import zipfile
from safe_io import validate_directory, write_new, regular_reader

def require(ok,message):
    if not ok:raise ValueError(message)

def normalized(name):
    name=name.rstrip('/')
    require(name and not name.startswith('/') and '\\' not in name and ':' not in name,'unsafe archive member')
    require(all(p not in ('','.','..') for p in name.split('/')),'unsafe archive path')
    return name

def validate_members(rows,root,max_bytes):
    require(0<len(rows)<=20000,'archive entry count exceeds bound')
    seen=set();total=0;links=set()
    for name,kind,size,target in rows:
        normalized(name);require(name not in seen,'duplicate archive path');seen.add(name);total+=size
        require(name.split('/')[0]==root,'unexpected archive root')
        require(kind in {'dir','file','symlink'},'special/hardlink archive member rejected')
        if kind=='symlink':
            require(target and not target.startswith('/') and '\\' not in target,'unsafe symlink target')
            resolved=posixpath.normpath(posixpath.join(posixpath.dirname(name),target))
            require(resolved==root or resolved.startswith(root+'/'),'distribution symlink escapes root');links.add(name)
    require(total<=max_bytes,'unpacked archive exceeds bound')
    for name,kind,size,target in rows:
        require(not any('/'.join(name.split('/')[:i]) in links for i in range(1,len(name.split('/')))),'member beneath symlink parent')

def extract_tar(source,dest):
    validate_directory(source.parent);validate_directory(dest);require(not any(dest.iterdir()),'IDE output is not empty')
    with regular_reader(source) as stream, tarfile.open(fileobj=stream,mode='r:gz') as archive:
        members=archive.getmembers();rows=[]
        for m in members:
            kind='dir' if m.isdir() else 'file' if m.isfile() else 'symlink' if m.issym() else 'other'
            rows.append((normalized(m.name),kind,m.size,m.linkname))
        validate_members(rows,'idea-IU-261.27258.48',8*1024**3)
        for m,row in zip(members,rows):
            name,kind,size,target=row;parts=name.split('/')[1:]
            if not parts:continue
            path=dest.joinpath(*parts)
            if kind=='dir':path.mkdir(parents=True,exist_ok=True)
            elif kind=='file':
                path.parent.mkdir(parents=True,exist_ok=True);validate_directory(path.parent)
                with archive.extractfile(m) as data, path.open('xb') as output:shutil.copyfileobj(data,output,1024*1024)
                require(path.stat().st_size==size,'short extracted file');os.chmod(path,m.mode&0o777)
        for m,row in zip(members,rows):
            name,kind,size,target=row
            if kind=='symlink':
                path=dest.joinpath(*name.split('/')[1:]);path.parent.mkdir(parents=True,exist_ok=True);validate_directory(path.parent)
                path.symlink_to(target)
        for name,kind,size,target in rows:
            if kind=='symlink':
                path=dest.joinpath(*name.split('/')[1:]);require(path.resolve().is_relative_to(dest.resolve()) and path.exists(),'dangling/looping/escaping symlink')

def extract_zip(source,dest):
    validate_directory(source.parent);validate_directory(dest);require(not any(dest.iterdir()),'plugin output is not empty')
    with regular_reader(source) as stream, zipfile.ZipFile(stream) as archive:
        members=archive.infolist();rows=[]
        for m in members:
            mode=m.external_attr>>16
            require(not stat.S_ISLNK(mode) and not (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)),'plugin special member')
            rows.append((normalized(m.filename),'dir' if m.is_dir() else 'file',m.file_size,''))
        validate_members(rows,'JetBrainsAcademy',256*1024*1024);require(archive.testzip() is None,'plugin CRC failure')
        for m,row in zip(members,rows):
            name,kind,size,_=row;path=dest/name
            if kind=='dir':path.mkdir(parents=True,exist_ok=True)
            else:
                path.parent.mkdir(parents=True,exist_ok=True);validate_directory(path.parent);write_new(path,archive.read(m))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['idea','academy']);p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    (extract_tar if a.kind=='idea' else extract_zip)(a.source,a.destination)
