"""Bundle completed v11 evidence; reject changed code or unchecked report."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parent
DEST=ROOT.parent/'deliverables'
REPORT='TRADE_PRICE_SCORE_REVIEW_V11_KO.html'
ARCHIVE='trade_game_price_score_review_v11.zip'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    results=ROOT/'evaluation_results'
    manifest=read(results/'run_manifest.json')
    tests=read(results/'tests_manifest.json')
    audit=read(results/'independent_audit.json')
    qa=read(results/'report_numeric_qa.json')
    assert manifest['completed_games']==manifest['planned_games']==4400
    assert manifest['main_games']==3800 and manifest['stress_games']==600
    assert manifest['representative_traces']==39
    assert manifest['main_cash_ledger_rows']==manifest['main_raw_ledger_rows']==307800
    assert manifest['source_unchanged'] and manifest['verification_failures']==0
    assert tests['passed'] and tests['test_count']>298 and tests['inherited_tests']==298
    assert tests['failures']==tests['errors']==tests['skipped']==0
    assert audit['status']=='passed' and not audit['errors']
    assert qa['status']=='passed' and not qa['errors']
    assert qa['report_sha256']==sha(ROOT/REPORT)
    assert qa['summary_sha256']==sha(results/'summary.json')
    for name,digest in manifest['source_sha256'].items():
        assert sha(ROOT/name)==digest,('frozen source changed',name)
    for name,digest in tests['test_sha256'].items():
        assert sha(ROOT/name)==digest,('frozen test changed',name)
    provenance=read(ROOT/'V10_PROVENANCE.json')
    assert len(provenance['files'])==61
    for name,digest in provenance['files'].items():
        assert sha(ROOT/name)==digest,('inherited source changed',name)
    files=sorted(p for p in ROOT.rglob('*.py') if '__pycache__' not in p.parts)
    files += [ROOT/'README_V11_KO.txt',ROOT/REPORT,ROOT/'V10_PROVENANCE.json']
    files += sorted(p for p in results.iterdir() if p.is_file() and '.partial.' not in p.name)
    if (ROOT/'evaluation_pilot.log').is_file():files.append(ROOT/'evaluation_pilot.log')
    assert len(files)==len(set(files))
    inventory={'description':'Frozen v11 public-minimum price trajectories and four shadow score views; pilots excluded from formal evidence.',
        'formal_games':4400,'score_views_per_game':4,'inherited_python_files_unchanged':61,
        'files':{str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in files}}
    (ROOT/'PACKAGE_CONTENTS.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files.append(ROOT/'PACKAGE_CONTENTS.json')
    DEST.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/REPORT,DEST/REPORT)
    archive=DEST/ARCHIVE
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,str(Path('trade_game_price_score_review_v11')/p.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(files)
    receipt={'files':[{'path':str(DEST/name),'bytes':(DEST/name).stat().st_size,'sha256':sha(DEST/name)} for name in (REPORT,ARCHIVE)],
        'zip_members':len(files),'inherited_python_files_unchanged':61,'zip_crc_passed':True}
    (DEST/'trade_v11_package_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
