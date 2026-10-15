"""Build the selected full-snapshot index without retuning on held-out questions."""
import yaml
from src.ingest.storage import ROOT,digest,save
from src.retrieval.build_indexes import build
from src.systems.rebuild.engine import write_configs


def main():
    selected=yaml.safe_load((ROOT/'configs/vector_selected.yaml').read_text())
    if not selected.get('selected') or selected['selection_split']!='development':raise ValueError('No completed development selection')
    config=yaml.safe_load((ROOT/'configs/snapshots.yaml').read_text())
    if selected['chunk_size']==1200 and selected['overlap']==180:
        directory=ROOT/'data/indexes'/config['dataset_id']
    else:
        directory=ROOT/'data/indexes/vector-selected'
        build(config,chunk_size=selected['chunk_size'],overlap=selected['overlap'],output_directory=directory)
    from analysis.validate_indexes import main as validate
    validate(directory,report_name='vector_selected_validation.md')
    selected['full_index_directory']=str(directory.relative_to(ROOT)).replace('\\','/')
    selected['full_index_manifest_sha256']=digest(directory/'manifest.json')
    (ROOT/'configs/vector_selected.yaml').write_text(yaml.safe_dump(selected),encoding='utf-8')
    write_configs(selected)
    print('Selected full-snapshot vector index ready:',selected['full_index_directory'])


if __name__=='__main__':main()
