"""Create a controlled, deterministic real Git history and pin its final commit."""
import os
import subprocess
from datetime import datetime, timedelta, timezone

import yaml

from .storage import ROOT, digest, save, write_rows
from .snapshots import files, commits


def build():
    config_path=ROOT/'configs/snapshots.yaml';config=yaml.safe_load(config_path.read_text())
    spec=config['synthetic'];slug=spec['repo']
    directory=ROOT/'data/snapshots'/config['dataset_id']/slug.replace('/','__')
    local=directory/'git_source';local.mkdir(parents=True,exist_ok=True)
    def call(*args,env=None):
        return subprocess.check_output(['git','-c','safe.directory='+local.as_posix(),'-C',str(local),*args],env=env,stderr=subprocess.DEVNULL).decode().strip()
    if not (local/'.git').exists():call('init','--initial-branch=main')
    base=datetime(2026,1,1,tzinfo=timezone.utc)
    # An interruption resumes at the existing commit count, without rewriting history.
    try:completed=int(call('rev-list','--count','HEAD'))
    except subprocess.CalledProcessError:completed=0
    for i in range(completed,spec['commits']):
        selected=range(spec['files']) if i==0 else [i % spec['files']]
        for number in selected:
            path=local/f'src/module_{number//10}/component_{number}.py';path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(f'"""Controlled component {number} for reproducible repository question answering."""\ndef component_{number}():\n    return {number+i}\n',encoding='utf-8',newline='\n')
        stamp=(base+timedelta(minutes=i)).isoformat();identity=i%5
        env=dict(os.environ,GIT_AUTHOR_NAME=f'Developer {identity}',GIT_COMMITTER_NAME=f'Developer {identity}',
                 GIT_AUTHOR_EMAIL=f'developer{identity}@example.invalid',GIT_COMMITTER_EMAIL=f'developer{identity}@example.invalid',
                 GIT_AUTHOR_DATE=stamp,GIT_COMMITTER_DATE=stamp)
        call('add','src');call('-c','commit.gpgsign=false','commit','-m',f'Controlled update {i}',env=env)
    sha=call('rev-parse','HEAD');date=call('log','-1','--format=%cI')
    if spec.get('commit_sha') and spec['commit_sha']!=sha:raise ValueError('Synthetic pinned Git SHA changed')
    repo=dict(repo=slug,local_path=local.relative_to(ROOT).as_posix(),commit_sha=sha,commit_date=date)
    for kind,rows in [('files',list(files(repo,config['limits']['max_file_bytes']))),('commits',commits(repo,directory,spec['commits']))]:
        path=directory/(kind+'.jsonl');write_rows(path,rows)
        save(directory/(kind+'.manifest.json'),dict(commit_sha=sha,commit_date=date,sha256=digest(path),count=len(rows),synthetic=True))
    spec.update(repo)
    config_path.write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8')
    print('Pinned synthetic Git snapshot',sha,date)


if __name__=='__main__':build()
