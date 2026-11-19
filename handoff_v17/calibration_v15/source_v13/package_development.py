"""Package completed, audited v9 deliverables without changing frozen runs."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
DEST = ROOT.parent/'deliverables'
REPORT = 'TRADE_DEVELOPMENT_REVIEW_V9_KO.html'
ARCHIVE = 'trade_game_development_revision_v9.zip'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    results = ROOT/'development_results'
    manifest = json.loads((results/'run_manifest.json').read_text())
    tests = json.loads((results/'tests_manifest.json').read_text())
    audit = json.loads((results/'independent_audit.json').read_text())
    numeric_qa = json.loads((results/'report_numeric_qa.json').read_text())
    assert manifest['completed_games'] == manifest['planned_games'] == 3080
    assert tests['passed'] and tests['test_count'] == 260 and tests['failures'] == tests['errors'] == tests['skipped'] == 0
    assert audit['status'] == 'passed' and not audit['errors']
    assert numeric_qa['status'] == 'passed' and not numeric_qa['errors']
    assert numeric_qa['report_sha256'] == sha(ROOT/REPORT)
    assert numeric_qa['summary_sha256'] == sha(results/'summary.json')
    for filename, digest in manifest['source_sha256'].items():
        assert sha(ROOT/filename) == digest, filename
    for filename, digest in tests['test_sha256'].items():
        assert sha(ROOT/filename) == digest, filename
    provenance = json.loads((ROOT/'V8_PROVENANCE.json').read_text())
    for filename, digest in provenance['files'].items():
        assert sha(ROOT/filename) == digest, ('inherited code changed', filename)
    assert (ROOT/REPORT).is_file()
    files = sorted(p for p in ROOT.rglob('*.py') if '__pycache__' not in p.parts)
    files += [ROOT/'README_V9_KO.txt', ROOT/REPORT, ROOT/'V8_PROVENANCE.json']
    files += sorted(p for p in results.iterdir() if p.is_file() and '.partial.' not in p.name)
    if (ROOT/'pilot.log').exists():
        files.append(ROOT/'pilot.log')
    assert len(files) == len(set(files))
    inventory = {'description': 'Frozen v9 source, all formal results, separate exploratory pilot, Korean report.',
                 'inherited_python_files_unchanged': len(provenance['files']),
                 'formal_games': 3080, 'files': {str(p.relative_to(ROOT)): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files}}
    (ROOT/'PACKAGE_CONTENTS.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
    files.append(ROOT/'PACKAGE_CONTENTS.json')
    DEST.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/REPORT, DEST/REPORT)
    archive = DEST/ARCHIVE
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, str(Path('trade_game_development_revision_v9')/p.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(files)
    receipt = {'files': [{'path': str(DEST/name), 'bytes': (DEST/name).stat().st_size, 'sha256': sha(DEST/name)} for name in (REPORT, ARCHIVE)],
               'zip_members': len(files), 'inherited_python_files_unchanged': len(provenance['files']), 'zip_crc_passed': True}
    (DEST/'trade_v9_package_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
