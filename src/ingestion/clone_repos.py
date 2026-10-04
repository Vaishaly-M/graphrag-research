from __future__ import annotations
import argparse, subprocess, yaml
from pathlib import Path
from src.common import ROOT, ensure_dirs

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config', default='config/repos.yaml'); a=ap.parse_args()
    ensure_dirs(); cfg=yaml.safe_load((ROOT/a.config).read_text())
    for x in cfg['repositories']:
        slug=x['slug']; dest=ROOT/'repos'/slug.replace('/','__')
        if dest.exists():
            subprocess.run(['git','-C',str(dest),'pull','--ff-only'], check=False)
        else:
            subprocess.run(['git','clone','--filter=blob:none',f'https://github.com/{slug}.git',str(dest)], check=True)
if __name__=='__main__': main()
