"""Canonical graph export: all retrieval indexes consume these same records."""
import hashlib
import json
from collections import Counter
from pathlib import PurePosixPath

import yaml

from src.ingest.storage import ROOT, digest, read_rows, save, write_rows

LABELS = ['Repository', 'File', 'Commit', 'Issue', 'PullRequest', 'Developer']
DIRECTIONS = {'CONTAINS_FILE': ('Repository', 'File'), 'COMMITTED_TO': ('Commit', 'Repository'),
              'MODIFIED_FILE': ('Commit', 'File'), 'AUTHORED_COMMIT': ('Developer', 'Commit'),
              'HAS_ISSUE': ('Repository', 'Issue'), 'HAS_PR': ('Repository', 'PullRequest'),
              'OPENED_ISSUE': ('Developer', 'Issue'), 'AUTHORED_PR': ('Developer', 'PullRequest'),
              'ASSIGNED_TO': ('Issue', 'Developer'), 'MERGED_AS': ('PullRequest', 'Commit')}


def synthetic(config):
    spec = config['synthetic']; slug = spec['repo']
    snapshot = spec['commit_sha']
    stamp = spec['commit_date']
    directory=ROOT/'data/snapshots'/config['dataset_id']/slug.replace('/','__')
    fs=read_rows(directory/'files.jsonl');cs=read_rows(directory/'commits.jsonl')
    def items(n):
        return [dict(id=i+1, number=i+1, title=f'Controlled request {i+1}', body=f'Review component {i}',
                     state='open' if i % 2 else 'closed', created_at=stamp, updated_at=stamp,
                     closed_at=stamp if not i % 2 else None, author={'id': i % 5, 'login': f'synthetic-{i%5}'},
                     assignees=[], observed_at=stamp) for i in range(n)]
    return dict(repo=slug, commit_sha=snapshot, commit_date=stamp, synthetic=True), dict(files=fs, commits=cs, issues=items(spec['issues']), pulls=items(spec['pulls']))


def build(config, local_preview=False):
    dataset = config['dataset_id']; raw = ROOT / 'data/snapshots' / dataset
    nodes, edges = {}, {}
    counts = Counter(); inputs = {}
    def node(label, repo, snapshot, key, **props):
        cid = f'{repo}:{label.lower()}:{key}'
        ident = f'{dataset}:{snapshot}:{cid}'
        value = dict(id=ident, canonical_id=cid, label=label, repo=repo, snapshot=snapshot, dataset=dataset, **props)
        if ident in nodes and nodes[ident] != value:
            raise ValueError('Conflicting canonical entity: ' + cid)
        nodes[ident] = value
        return ident
    def edge(kind, start, end, repo):
        key = hashlib.sha256(f'{kind}|{start}|{end}'.encode()).hexdigest()
        edges[key] = dict(id=key, type=kind, start=start, end=end, repo=repo, dataset=dataset)
    sources = []
    for spec in config['repositories']:
        directory = raw / spec['repo'].replace('/', '__')
        records = {}
        for kind in ['files', 'commits', 'issues', 'pulls']:
            path = directory / (kind + '.jsonl')
            if local_preview and kind in {'issues','pulls'}:
                records[kind]=[]
                continue
            manifest = json.loads((directory / (kind + '.manifest.json')).read_text())
            if manifest['sha256'] != digest(path) or manifest['commit_sha'] != spec['commit_sha']:
                raise ValueError('Snapshot integrity mismatch')
            inputs[path.relative_to(ROOT).as_posix()] = digest(path)
            records[kind] = read_rows(path)
        sources.append((spec, records))
    synthetic_dir=raw/config['synthetic']['repo'].replace('/','__')
    for kind in ['files','commits']:
        path=synthetic_dir/(kind+'.jsonl')
        marker=json.loads((synthetic_dir/(kind+'.manifest.json')).read_text())
        if marker['sha256']!=digest(path) or marker['commit_sha']!=config['synthetic']['commit_sha']:
            raise ValueError('Synthetic snapshot integrity mismatch')
        inputs[path.relative_to(ROOT).as_posix()]=digest(path)
    sources.append(synthetic(config))
    for spec, records in sources:
        repo, snapshot = spec['repo'], spec['commit_sha']
        rid = node('Repository', repo, snapshot, repo, name=repo, commit_date=spec['commit_date'], synthetic=spec.get('synthetic', False))
        def developer(key, name='', email='', login=''):
            # Repo-scoped identities make per-repo totals additive; no unverified identity merges.
            return node('Developer', repo, snapshot, key, name=name, email=email, login=login)
        file_ids = {}
        for r in records['files']:
            path = PurePosixPath(r['path'].replace('\\', '/')).as_posix()
            fid = node('File', repo, snapshot, path, path=path, extension=PurePosixPath(path).suffix,
                       content=r['content'], content_sha256=hashlib.sha256(r['content'].encode()).hexdigest(), blob_sha=r.get('blob_sha', ''))
            file_ids[path] = fid; edge('CONTAINS_FILE', rid, fid, repo)
        commit_ids = {}
        for r in records['commits']:
            cid = node('Commit', repo, snapshot, r['sha'], sha=r['sha'], timestamp=r['timestamp'],
                       author_date=r['author_date'], message=r['message'], modified_paths=r['modified_files'])
            commit_ids[r['sha']] = cid; edge('COMMITTED_TO', cid, rid, repo)
            email = (r.get('author_email') or '').strip().lower()
            # Author names are not canonical identities; fallback gets a stable explicit anonymous key.
            key = 'email:' + email if email else 'anonymous:' + hashlib.sha256(str(r.get('author_name')).encode()).hexdigest()
            did = developer(key, email=email)
            edge('AUTHORED_COMMIT', did, cid, repo)
            for path in r['modified_files']:
                if path in file_ids:
                    edge('MODIFIED_FILE', cid, file_ids[path], repo)
                else:
                    counts['modifications_outside_retained_tree'] += 1
        for kind, label in [('issues', 'Issue'), ('pulls', 'PullRequest')]:
            for r in records[kind]:
                props = {k:r.get(k) for k in ['number', 'title', 'body', 'state', 'created_at', 'updated_at', 'closed_at', 'merged_at', 'observed_at']}
                eid = node(label, repo, snapshot, str(r['number']), **props)
                edge('HAS_ISSUE' if kind == 'issues' else 'HAS_PR', rid, eid, repo)
                author = r.get('author')
                if author:
                    did = developer('github:' + str(author['id']), login=author.get('login', '').lower())
                    edge('OPENED_ISSUE' if kind == 'issues' else 'AUTHORED_PR', did, eid, repo)
                if kind == 'issues':
                    for a in r.get('assignees', []):
                        did = developer('github:' + str(a['id']), login=a.get('login', '').lower())
                        edge('ASSIGNED_TO', eid, did, repo)
                if r.get('merge_commit_sha') in commit_ids:
                    edge('MERGED_AS', eid, commit_ids[r['merge_commit_sha']], repo)
    out = ROOT / 'data/graph_exports' / (dataset+'-local-preview' if local_preview else dataset)
    write_rows(out / 'nodes.jsonl', sorted(nodes.values(), key=lambda r:r['id']))
    write_rows(out / 'relationships.jsonl', sorted(edges.values(), key=lambda r:r['id']))
    save(out / 'manifest.json', dict(dataset=dataset, incomplete_metadata=local_preview, config_sha256=digest(ROOT/'configs/snapshots.yaml'),
         input_hashes=inputs, nodes_sha256=digest(out/'nodes.jsonl'), relationships_sha256=digest(out/'relationships.jsonl'),
         builder_sha256=digest(ROOT/'src/kg/build.py'),
         scope_counts=dict(counts), node_count=len(nodes), relationship_count=len(edges)))
    print('Canonical export', len(nodes), 'nodes', len(edges), 'relationships', flush=True)


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--local-preview',action='store_true');args=parser.parse_args()
    build(yaml.safe_load((ROOT/'configs/snapshots.yaml').read_text()),args.local_preview)
