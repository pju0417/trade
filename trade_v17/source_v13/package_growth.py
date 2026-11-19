"""Package the completed, independently checked v12 scoring experiment."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'growth_results'
DEST=ROOT.parent/'deliverables'
REPORT='TRADE_GROWTH_SCORE_REVIEW_V12_KO.html'
ARCHIVE='trade_game_growth_score_review_v12.zip'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    manifest=read(RESULTS/'run_manifest.json')
    tests=read(RESULTS/'tests_manifest.json')
    audit=read(RESULTS/'independent_audit.json')
    qa=read(RESULTS/'report_numeric_qa.json')
    assert manifest['completed_games']==4180
    assert manifest['calibration_games']==780
    assert manifest['holdout_games']==3100
    assert manifest['stress_games']==300
    assert manifest['representative_traces']==54
    assert manifest['holdout_cash_ledger_rows']==manifest['holdout_raw_ledger_rows']==251100
    assert manifest['verification_failures']==0 and manifest['source_unchanged']
    assert tests['passed'] and tests['test_count']>337
    assert tests['failures']==tests['errors']==tests['skipped']==0
    assert audit['status']=='passed' and not audit['errors']
    assert qa['status']=='passed' and not qa['errors']
    assert qa['report_sha256']==sha(ROOT/REPORT)
    assert qa['summary_sha256']==sha(RESULTS/'summary.json')
    for name,digest in manifest['source_sha256'].items():
        assert sha(ROOT/name)==digest,('frozen source changed',name)
    for name,digest in tests['test_sha256'].items():
        assert sha(ROOT/name)==digest,('frozen test changed',name)
    for field,name in (
        ('goals_sha256','goals.json'),('freeze_sha256','freeze_manifest.json'),
        ('protocol_sha256','pre_run_plan.json'),('tests_manifest_sha256','tests_manifest.json'),
        ('selection_sha256','frozen_selection.json'),
        ('calibration_runs_sha256','calibration_runs.jsonl.gz'),
        ('calibration_manifest_sha256','calibration_manifest.json'),
        ('holdout_start_sha256','holdout_start.json'),
    ):
        assert manifest[field]==sha(RESULTS/name),(field,'artifact changed')
    provenance=read(ROOT/'V11_PROVENANCE.json')
    assert len(provenance['files'])==69
    for name,digest in provenance['files'].items():
        assert sha(ROOT/name)==digest,('inherited source changed',name)
    files=sorted(p for p in ROOT.rglob('*.py') if '__pycache__' not in p.parts)
    files += [ROOT/'README_V12_KO.txt',ROOT/REPORT,ROOT/'V11_PROVENANCE.json']
    files += sorted(p for p in RESULTS.iterdir() if p.is_file() and '.partial.' not in p.name)
    assert len(files)==len(set(files))
    inventory={
        'description':'v12 target/ceiling 2x2 scoring views; no physical economic change.',
        'formal_economic_games':4180,
        'calibration_games':780,'untouched_holdout_games':3100,'stress_games':300,
        'score_views_per_trajectory':4,'inherited_python_files_unchanged':69,
        'files':{str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in files},
    }
    (ROOT/'PACKAGE_CONTENTS.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files.append(ROOT/'PACKAGE_CONTENTS.json')
    DEST.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/REPORT,DEST/REPORT)
    archive=DEST/ARCHIVE
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,str(Path('trade_game_growth_score_review_v12')/p.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(files)
    receipt={'files':[{'path':str(DEST/name),'bytes':(DEST/name).stat().st_size,'sha256':sha(DEST/name)}
                      for name in (REPORT,ARCHIVE)],
             'zip_members':len(files),'inherited_python_files_unchanged':69,'zip_crc_passed':True}
    (DEST/'trade_v12_package_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
