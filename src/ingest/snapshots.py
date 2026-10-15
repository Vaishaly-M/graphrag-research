"""Resume-safe extraction of pinned Git trees/history and observed GitHub metadata."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests
import yaml
from dotenv import load_dotenv
from pydriller import Repository

from .storage import ROOT, digest, now, read_rows, save, write_rows

EXCLUDED_DIRS = {'.git', 'node_modules', 'vendor', 'dist', 'build', 'target', 'bin',
                 'obj', '.venv', 'venv', '__pycache__', '.next', 'coverage', 'generated',
                 'generated-sources', 'site-packages', '.idea', '.gradle'}
LOCK_NAMES = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock',
              'uv.lock', 'cargo.lock', 'gemfile.lock', 'packages.lock.json',
              'composer.lock', 'go.sum', 'pipfile.lock'}
BINARY_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.jar', '.gz',
              '.woff', '.woff2', '.ttf', '.exe', '.dll', '.so', '.pyc', '.class',
              '.mp4', '.mp3', '.parquet', '.pickle', '.pkl', '.sqlite', '.db'}


def allowed_path(path):
    p = PurePosixPath(path)
    return (not p.is_absolute() and '..' not in p.parts and
            not any(part.lower() in EXCLUDED_DIRS for part in p.parts) and
            p.name.lower() not in LOCK_NAMES and p.suffix.lower() not in BINARY_EXT and
            not re.search(r'(\.min\.(js|css)$|\.map$|\.generated\.|_pb2(?:_grpc)?\.py$|\.pb\.go$|\.lock$)', path.lower()))


def decode_text(blob):
    if b'\x00' in blob:
        return None
    try:
        text = blob.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    except UnicodeDecodeError:
        return None
    if not text.strip() or re.search(r'(automatically generated|auto-generated|@generated|do not edit)', text[:2048], re.I):
        return None
    if sum(ord(c) < 32 and c not in '\n\t' for c in text) > max(1, len(text) // 100):
        return None
    return text


def git(repo, *args):
    path = (ROOT / repo['local_path']).resolve()
    return subprocess.check_output(['git', '-c', 'safe.directory=' + path.as_posix(),
                                   '-C', str(path), *args])


def files(repo, limit):
    # Batch reading objects avoids one Git process per file and ignores dirty checkouts.
    tree = git(repo, 'ls-tree', '-rlz', repo['commit_sha'])
    candidates = []
    for entry in tree.split(b'\x00'):
        if not entry:
            continue
        meta, rawpath = entry.split(b'\t', 1)
        mode, kind, sha, size = meta.decode().split()
        path = rawpath.decode('utf-8')
        if kind == 'blob' and mode in {'100644', '100755'} and int(size) <= limit and allowed_path(path):
            candidates.append((path, sha))
    local = (ROOT / repo['local_path']).resolve()
    proc = subprocess.Popen(['git', '-c', 'safe.directory=' + local.as_posix(), '-C', str(local),
                             'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for path, sha in candidates:
            proc.stdin.write((sha + '\n').encode()); proc.stdin.flush()
            header = proc.stdout.readline().split()
            blob = proc.stdout.read(int(header[2])); proc.stdout.read(1)
            text = decode_text(blob)
            if text is not None:
                yield dict(path=path, content=text, blob_sha=sha)
    finally:
        proc.stdin.close(); proc.stdout.close(); proc.wait()


def commits(repo, directory, limit):
    selected = git(repo, 'rev-list', '--max-count=' + str(limit), repo['commit_sha']).decode().splitlines()
    # GitPython/PyDriller subprocesses inherit only this explicit safe-directory override.
    local = (ROOT / repo['local_path']).resolve()
    os.environ['GIT_CONFIG_COUNT'] = '1'
    os.environ['GIT_CONFIG_KEY_0'] = 'safe.directory'
    os.environ['GIT_CONFIG_VALUE_0'] = local.as_posix()
    cache = directory / 'commit_cache'
    cache.mkdir(exist_ok=True)
    missing = [sha for sha in selected if not (cache / (sha + '.json')).exists()]
    if missing:
        for i, c in enumerate(Repository(str(local), only_commits=missing, order='reverse').traverse_commits(), 1):
            # PyDriller supplies identities/dates; path-only Git diffs avoid materializing
            # enormous generated/binary patches merely to obtain filenames. As with
            # PyDriller, merge commits have no modification rows.
            modified = []
            if len(c.parents) <= 1:
                fields = git(repo, 'diff-tree', '--no-commit-id', '--name-status', '-r', '-z', '-M', '--root', c.hash).split(b'\x00')
                offset = 0
                while offset < len(fields) and fields[offset]:
                    status = fields[offset].decode(); offset += 1
                    path = fields[offset]; offset += 1
                    if status.startswith(('R','C')):
                        path = fields[offset]; offset += 1
                    modified.append(path.decode('utf-8'))
            row = dict(sha=c.hash, timestamp=c.committer_date.isoformat(), author_date=c.author_date.isoformat(),
                       message=c.msg, author_name=c.author.name, author_email=c.author.email,
                       modified_files=sorted(set(modified)))
            save(cache / (c.hash + '.json'), row)
            if i % 100 == 0:
                print(repo['repo'], 'commits checkpoint', i, '/', len(missing), flush=True)
    return [json.loads((cache / (sha + '.json')).read_text(encoding='utf-8')) for sha in selected]


class GitHubSnapshot:
    def __init__(self, directory, issue_search=False):
        self.directory = directory
        self.issue_search = issue_search
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        token = os.getenv('GITHUB_TOKEN')
        if token:
            self.session.headers['Authorization'] = 'Bearer ' + token

    def page(self, slug, endpoint, number, url=None):
        search = self.issue_search and endpoint == 'issues'
        path = self.directory / f'{"search_" if search else ""}{endpoint}_{number:04d}.json'
        if path.exists():
            value = json.loads(path.read_text(encoding='utf-8'))
            if value['sha256'] != hashlib.sha256(json.dumps(value['rows'], sort_keys=True).encode()).hexdigest():
                raise ValueError('API page integrity failure')
            if value['has_next'] and 'next_url' not in value:
                # Upgrade pre-cursor checkpoints without changing their observed rows.
                response = self.session.get(f'https://api.github.com/repos/{slug}/{endpoint}',
                    params=dict(state='all', sort='created', direction='desc', per_page=100, page=number), timeout=45)
                if response.status_code == 401:
                    self.session.headers.pop('Authorization', None)
                    response = self.session.get(response.url, timeout=45)
                response.raise_for_status()
                value['next_url'] = response.links.get('next', {}).get('url')
                save(path, value)
            return value
        for attempt in range(6):
            if url and (urlparse(url).scheme != 'https' or urlparse(url).netloc != 'api.github.com' or not urlparse(url).path.endswith('/'+endpoint)):
                raise ValueError('Unexpected pagination URL')
            try:
                base = 'https://api.github.com/search/issues' if search else f'https://api.github.com/repos/{slug}/{endpoint}'
                params = dict(q=f'repo:{slug} is:issue', sort='created', order='desc', per_page=100, page=number) if search else dict(state='all', sort='created', direction='desc', per_page=100, page=number)
                response = self.session.get(url or base, params=None if url else params, timeout=45)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 5: raise
                time.sleep(min(2 ** attempt, 32)); continue
            if response.status_code == 401 and 'Authorization' in self.session.headers:
                del self.session.headers['Authorization']
                print('GitHub token rejected; using public API', flush=True)
                continue
            if response.status_code in {403, 429}:
                delay = max(float(response.headers.get('Retry-After', 0)),
                            float(response.headers.get('X-RateLimit-Reset', 0)) - time.time() + 2, 2 ** attempt)
                # Never block an interactive run for an hour; checkpoint and resume later.
                if delay > 55:
                    raise RuntimeError(f'GitHub rate limited; resume after {int(delay)} seconds')
                print('GitHub rate-limit wait', round(delay), 'seconds', flush=True)
                time.sleep(delay); continue
            if response.status_code >= 500:
                time.sleep(min(2 ** attempt, 32)); continue
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get('incomplete_results'):
                time.sleep(min(2 ** attempt, 32)); continue
            rows = payload['items'] if isinstance(payload, dict) else payload
            value = dict(observed_at=now(), rows=rows, has_next='next' in response.links,
                         next_url=response.links.get('next', {}).get('url'),
                         sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest())
            save(path, value)
            return value
        raise RuntimeError('GitHub retry budget exhausted; cached pages preserved')

    def collect(self, slug, endpoint, limit):
        rows, seen = [], set()
        page = 1
        url = None
        while len(rows) < limit:
            value = self.page(slug, endpoint, page, url)
            for r in value['rows']:
                if endpoint == 'issues' and 'pull_request' in r:
                    continue
                if r['id'] in seen:
                    continue
                seen.add(r['id'])
                row = {k:r.get(k) for k in ['id', 'number', 'title', 'body', 'state', 'created_at', 'updated_at', 'closed_at', 'merged_at', 'merge_commit_sha']}
                row.update(author=r.get('user'), assignees=r.get('assignees', []), observed_at=value['observed_at'])
                rows.append(row)
                if len(rows) == limit:
                    break
            if not value['has_next']:
                break
            url = value['next_url']
            page += 1
        return rows


def run(config, only=None):
    load_dotenv(ROOT / '.env')
    root = ROOT / 'data/snapshots' / config['dataset_id']
    lock=root/'extraction_config.json'
    parameters=dict(repositories=config['repositories'],limits=config['limits'],filter_version=1)
    if lock.exists() and json.loads(lock.read_text())!=parameters:
        raise ValueError('Extraction settings are frozen; use a new dataset ID')
    if not lock.exists():save(lock,parameters)
    for repo in config['repositories']:
        if only and repo['repo'] != only:
            continue
        directory = root / repo['repo'].replace('/', '__')
        directory.mkdir(parents=True, exist_ok=True)
        for stage in ['files', 'commits', 'issues', 'pulls']:
            target = directory / (stage + '.jsonl')
            marker = directory / (stage + '.manifest.json')
            if marker.exists():
                prior = json.loads(marker.read_text())
                if prior['commit_sha'] != repo['commit_sha'] or prior['sha256'] != digest(target):
                    raise ValueError('Pinned extraction changed: ' + str(target))
                continue
            print(repo['repo'], stage, 'start', flush=True)
            if stage == 'files':
                rows = list(files(repo, config['limits']['max_file_bytes']))
            elif stage == 'commits':
                rows = commits(repo, directory, config['limits']['commits_per_repo'])
            else:
                # Issue search excludes PRs server-side; list-issues can otherwise need
                # thousands of PR pages to find a repository's handful of real issues.
                rows = GitHubSnapshot(directory / 'api_pages', issue_search=True).collect(repo['repo'], stage, config['limits'][stage + '_per_repo'])
            write_rows(target, rows)
            save(marker, dict(commit_sha=repo['commit_sha'], commit_date=repo['commit_date'],
                              observed_at=now(), count=len(rows), sha256=digest(target)))
            print(repo['repo'], stage, len(rows), 'complete', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo')
    args = parser.parse_args()
    run(yaml.safe_load((ROOT / 'configs/snapshots.yaml').read_text()), args.repo)
