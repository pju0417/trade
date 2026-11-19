"""Package the completed v13 review and all nonredundant reproducible evidence."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'causal_results'
DEST = ROOT.parent / 'deliverables'
REPORT = 'TRADE_CAUSAL_REVIEW_V13_KO.html'
ARCHIVE = 'trade_game_causal_review_v13.zip'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    manifest = read(RESULTS / 'run_manifest.json')
    tests = read(RESULTS / 'tests_manifest.json')
    audit = read(RESULTS / 'independent_audit.json')
    qa = read(RESULTS / 'report_numeric_qa.json')
    assert manifest['completed_games'] == 5100 and manifest['formal_games'] == 4920
    assert manifest['pilot_games'] == 180 and manifest['representative_traces'] == 156
    assert manifest['formal_cash_ledger_rows'] == manifest['formal_raw_ledger_rows'] == 398520
    assert manifest['verification_failures'] == 0 and manifest['source_unchanged']
    assert tests['passed'] and tests['test_count'] > 375
    assert tests['failures'] == tests['errors'] == tests['skipped'] == 0
    assert audit['status'] == 'passed' and not audit['errors']
    assert qa['status'] == 'passed' and not qa['errors']
    assert qa['report_sha256'] == sha(ROOT / REPORT)
    assert qa['summary_sha256'] == sha(RESULTS / 'summary.json')
    for name, digest in manifest['source_sha256'].items():
        assert sha(ROOT / name) == digest, ('frozen source changed', name)
    for name, digest in tests['test_sha256'].items():
        assert sha(ROOT / name) == digest, ('frozen test changed', name)
    for key, path in (
        ('goals_sha256', ROOT / 'V12_FROZEN_GOALS.json'),
        ('declared_protocol_sha256', ROOT / 'CAUSAL_PROTOCOL_V13.json'),
        ('run_plan_sha256', RESULTS / 'pre_run_plan.json'),
        ('tests_manifest_sha256', RESULTS / 'tests_manifest.json'),
        ('freeze_sha256', RESULTS / 'freeze_manifest.json'),
        ('formal_start_sha256', RESULTS / 'formal_start.json'),
    ):
        assert manifest[key] == sha(path), ('fixed artifact changed', key)
    provenance = read(ROOT / 'V12_PROVENANCE.json')
    assert len(provenance['files']) == 76
    for name, digest in provenance['files'].items():
        assert sha(ROOT / name) == digest, ('inherited v12 source changed', name)
    # All runs and all representative traces are in the combined final files.
    # The intermediate formal-only duplicates are not additional evidence.
    excluded_duplicates = {'formal_runs.jsonl.gz', 'formal_traces.json.gz'}
    files = sorted(p for p in ROOT.rglob('*.py') if '__pycache__' not in p.parts)
    files += [ROOT / name for name in (
        REPORT, 'README_V13_KO.txt', 'RULES_AUDIT_V13_KO.txt', 'rules_audit.json',
        'V11_PROVENANCE.json', 'V12_PROVENANCE.json', 'V12_FROZEN_GOALS.json',
        'CAUSAL_PROTOCOL_V13.json')]
    files += sorted(p for p in RESULTS.iterdir() if p.is_file()
                    and '.partial.' not in p.name and p.name not in excluded_duplicates)
    assert len(files) == len(set(files)) and all(p.is_file() for p in files)
    inventory = {
        'description': 'v13 controlled AI-budget/investment and electronics-input experiments',
        'actual_executions': 5100, 'formal_games': 4920, 'pilot_games': 180,
        'original_python_files_unchanged': 76,
        'redundant_intermediate_files_omitted': sorted(excluded_duplicates),
        'combined_complete_runs': 'causal_results/runs.jsonl.gz',
        'combined_representative_traces': 'causal_results/first_seed_traces.json.gz',
        'files': {str(p.relative_to(ROOT)): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files},
    }
    contents = ROOT / 'PACKAGE_CONTENTS.json'
    contents.write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    files.append(contents)
    DEST.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / REPORT, DEST / REPORT)
    with zipfile.ZipFile(DEST / ARCHIVE, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in files:
            archive.write(p, str(Path('trade_game_causal_review_v13') / p.relative_to(ROOT)))
    with zipfile.ZipFile(DEST / ARCHIVE) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)
    receipt = {'files': [{'path': str(DEST/name), 'bytes': (DEST/name).stat().st_size,
                          'sha256': sha(DEST/name)} for name in (REPORT, ARCHIVE)],
               'zip_members': len(files), 'zip_crc_passed': True,
               'inherited_python_files_unchanged': 76}
    (DEST/'trade_v13_package_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
