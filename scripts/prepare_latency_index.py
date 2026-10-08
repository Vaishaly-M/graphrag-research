"""Create a manifest-bearing legacy copy ONLY for the latency diagnostic.

Unknown historical build settings stay null. This is not a replacement for a
manifest written by VectorStore.build; the evaluation entry point rejects it.
"""
import collections
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import faiss
import numpy as np
from src.common import ROOT
from src.evaluation.reproducibility import sha256


def main():
    source = ROOT / 'data/vector_index'
    checkpoints = ROOT / 'results/v2/vector_index'
    target = ROOT / 'results/v2/latency_probe/diagnostic_index'
    config = json.loads((checkpoints/'config_snapshot.json').read_text())
    docs = json.loads((source/'docs.json').read_text(encoding='utf-8'))
    import hashlib
    if hashlib.sha256(json.dumps(docs, sort_keys=True).encode()).hexdigest() != config['docs_hash']:
        raise RuntimeError('Legacy corpus differs from the explicit rebuild corpus')
    index = faiss.read_index(str(source/'index.faiss'))
    checks = []
    for path in sorted(checkpoints.glob('embeddings_*.npy')):
        start = int(path.stem.split('_')[1])
        block = np.load(path, allow_pickle=False)
        error = float(np.max(np.abs(block-index.reconstruct_n(start, len(block)))))
        if error > 2e-6:
            raise RuntimeError('Recomputed embeddings do not match the legacy index')
        checks.append(dict(start=start, count=len(block), max_absolute_difference=error, checkpoint_sha256=sha256(path)))
    if not checks:
        raise RuntimeError('No recomputed embeddings available for compatibility checks')
    target.mkdir(parents=True, exist_ok=True)
    for name in ['index.faiss', 'docs.json']:
        if (target/name).exists() and sha256(target/name) != sha256(source/name):
            raise RuntimeError('Diagnostic destination already differs')
        shutil.copyfile(source/name, target/name)
    manifest = dict(schema_version=2, diagnostic_only=True,
        provenance='byte-identical legacy import; original build metadata unavailable',
        created_at=datetime.now(timezone.utc).isoformat(),
        embedding_model=config['embedding_model'],
        embedding_model_basis='compatible with recomputed checkpoint subset; not an attestation of historical build settings',
        compatibility_checks=checks, verified_vector_count=sum(c['count'] for c in checks),
        chunk_size=None, chunk_overlap=None, original_source_dirs=None,
        source_dirs=[str(source)], doc_count=len(docs),
        counts_per_repo=dict(collections.Counter(d['repo'] for d in docs)),
        counts_per_kind=dict(collections.Counter(d['kind'] for d in docs)),
        synthetic_included=any(d.get('repo') == 'synthetic-org/platform' for d in docs),
        synthetic_basis='synthetic repository documents present; original ingestion directory unrecorded',
        index_sha256=sha256(target/'index.faiss'), docs_sha256=sha256(target/'docs.json'))
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Diagnostic copy only: {len(docs)} chunks, {manifest["verified_vector_count"]} compatibility checks. No historical build provenance inferred.')


if __name__ == '__main__':
    main()
