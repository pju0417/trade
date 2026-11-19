"""Package completed, audited v10 outputs without rerunning or changing the economy."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
DEST = ROOT.parent / 'deliverables'
REPORT = 'TRADE_ROUTING_REVIEW_V10_KO.html'
ARCHIVE = 'trade_game_routing_revision_v10.zip'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    results = ROOT / 'routing_results'
    manifest = read(results / 'run_manifest.json')
    tests = read(results / 'tests_manifest.json')
    audit = read(results / 'independent_audit.json')
    numeric_qa = read(results / 'report_numeric_qa.json')
    assert manifest['completed_games'] == manifest['planned_games'] == 4000
    assert manifest['main_games'] == 1600 and manifest['stress_games'] == 2400
    assert manifest['representative_traces'] == 32
    assert manifest['main_cash_ledger_rows'] == manifest['main_raw_ledger_rows'] == 129600
    assert manifest['source_unchanged'] and manifest['verification_failures'] == 0
    assert tests['passed'] and tests['test_count'] == 298
    assert tests['inherited_tests'] == 260 and tests['new_tests'] == 38
    assert tests['failures'] == tests['errors'] == tests['skipped'] == 0
    assert audit['status'] == 'passed' and not audit['errors']
    assert numeric_qa['status'] == 'passed' and not numeric_qa['errors']
    assert numeric_qa['report_sha256'] == sha(ROOT / REPORT)
    assert numeric_qa['summary_sha256'] == sha(results / 'summary.json')
    for filename, digest in manifest['source_sha256'].items():
        assert sha(ROOT / filename) == digest, ('frozen source changed', filename)
    for filename, digest in tests['test_sha256'].items():
        assert sha(ROOT / filename) == digest, ('frozen test changed', filename)
    provenance = read(ROOT / 'V9_PROVENANCE.json')
    for filename, digest in provenance['files'].items():
        assert sha(ROOT / filename) == digest, ('inherited code changed', filename)
    files = sorted(p for p in ROOT.rglob('*.py') if '__pycache__' not in p.parts)
    files += [ROOT / 'README_V10_KO.txt', ROOT / REPORT, ROOT / 'V9_PROVENANCE.json']
    files += sorted(p for p in results.iterdir() if p.is_file() and '.partial.' not in p.name)
    if (ROOT / 'pilot.log').is_file():
        files.append(ROOT / 'pilot.log')
    assert len(files) == len(set(files))
    inventory = {
        'description': 'Frozen v10 source, formal results, separately labelled exploratory pilots, Korean report and reproducible checks.',
        'formal_games': 4000,
        'inherited_python_files_unchanged': len(provenance['files']),
        'files': {str(p.relative_to(ROOT)): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files},
    }
    (ROOT / 'PACKAGE_CONTENTS.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    files.append(ROOT / 'PACKAGE_CONTENTS.json')
    DEST.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / REPORT, DEST / REPORT)
    archive = DEST / ARCHIVE
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in files:
            z.write(path, str(Path('trade_game_routing_revision_v10') / path.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(files)
    receipt = {
        'files': [{'path': str(DEST / name), 'bytes': (DEST / name).stat().st_size, 'sha256': sha(DEST / name)} for name in (REPORT, ARCHIVE)],
        'zip_members': len(files), 'inherited_python_files_unchanged': len(provenance['files']), 'zip_crc_passed': True,
    }
    (DEST / 'trade_v10_package_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
