"""Package complete v17 simulations, validation, report and reproduction code."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parent


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def load(rel):return json.loads((ROOT/rel).read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,default=ROOT.parent/'deliverables')
    args=parser.parse_args();args.destination.mkdir(parents=True,exist_ok=True)
    receipts={name:load('operating_results/'+name) for name in
              ('freeze_manifest.json','run_manifest.json','analysis_manifest.json',
               'independent_audit.json','report_numeric_qa.json')}
    assert all(v['status']=='PASS' for v in receipts.values())
    frozen=receipts['freeze_manifest.json']['source_snapshot']
    for rel,digest in frozen['inherited_source_sha256'].items():assert sha(ROOT/'source_v13'/rel)==digest
    for rel,digest in frozen['new_source_sha256'].items():assert sha(ROOT/rel)==digest
    for n in ('run_manifest.json','analysis_manifest.json'):
        for rel,digest in receipts[n]['output_sha256'].items():assert sha(ROOT/'operating_results'/rel)==digest
    tests=load('semantic_tests.json');smoke=load('operating_results/smoke/smoke_manifest.json')
    assert tests['status']==smoke['status']=='PASS'
    assert tests['new_economic_games']==12 and smoke['new_economic_games']==24
    assert receipts['run_manifest.json']['new_economic_games']==6740
    assert receipts['analysis_manifest.json']['new_economic_games']==0
    for rel,digest in receipts['report_numeric_qa.json']['source_sha256'].items():assert sha(ROOT/rel)==digest
    report=ROOT/'TRADE_NATIONAL_RESOURCES_V17_KO.html'
    assert sha(report)==receipts['report_numeric_qa.json']['report_sha256']
    assert (ROOT/'README_V17_KO.txt').is_file()
    selected=load('CANDIDATE_SELECTION_V17.json')
    for rel,digest in selected.get('evidence_sha256',{}).items():assert sha(ROOT/rel)==digest
    files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
           and p.suffix not in ('.pyc','.zip') and '.partial.' not in p.name
           and p.name not in ('PACKAGE_CONTENTS.json','package_receipt.json')]
    manifest={'schema':'v17-package-contents-1','formal_economic_games':6740,
              'smoke_economic_games':24,'semantic_economic_games':12,'total_economic_executions':6776,
              'note':'Manifest excludes itself. All source code, inputs, frozen design, full formal results, ledgers, representative traces and report are included.',
              'files':{str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in files}}
    mp=ROOT/'PACKAGE_CONTENTS.json'
    with mp.open('x') as out:json.dump(manifest,out,ensure_ascii=False,indent=2);out.write('\n')
    files.append(mp)
    target=args.destination/'trade_game_national_resources_v17.zip'
    assert not target.exists()
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,'trade_v17/'+str(p.relative_to(ROOT)))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.infolist())==len(files)
        for p in files:
            assert hashlib.sha256(z.read('trade_v17/'+str(p.relative_to(ROOT)))).hexdigest()==sha(p)
    html=args.destination/report.name;assert not html.exists();shutil.copyfile(report,html)
    result={'schema':'v17-package-receipt-1','status':'PASS','members':len(files),
            'zip_crc':'PASS','member_hashes_match':True,'new_packaging_games':0,
            'deliverables':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in (html,target)]}
    with (ROOT/'package_receipt.json').open('x') as out:json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result))


if __name__=='__main__':main()
