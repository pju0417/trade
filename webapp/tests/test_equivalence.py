"""With no students, a Session advanced phase by phase must equal sim_lib.make_game(seed, fee=1.0,
l3_flat=True) run in one go: every country's run_metrics fields and the full transaction list.
Usage: python3 test_equivalence.py <first_seed> <n_games>"""
import json
import sys

import paths  # noqa: F401
import sim_lib as L
import classroom as C


def compare(seed):
    ref = L.make_game(seed, fee=1.0, l3_flat=True)
    m_ref = L.run_metrics(ref)
    s = C.Session(seed, [])
    steps = 0
    while s.phase != 'finished':
        assert s.apply({'type': 'advance'})['ok']
        steps += 1
    assert steps == 27, steps
    m_new = L.run_metrics(s.g)
    assert json.dumps(m_ref, sort_keys=True) == json.dumps(m_new, sort_keys=True), seed
    assert json.dumps(ref.transactions, sort_keys=True) == json.dumps(s.g.transactions, sort_keys=True), seed
    assert ref.prices == s.g.prices and ref.round_history == s.g.round_history, seed
    for n in C.ORIGINAL:
        assert abs(s.results[n]['total'] - C.total_score(m_ref, n)) < 1e-12
    return True



def check_targets_and_total():
    import final_validation as FV
    assert FV.targets() == C.SIM_TARGETS, (FV.targets(), C.SIM_TARGETS)
    m = L.run_metrics(L.make_game(7, fee=1.0, l3_flat=True))
    for n in C.ORIGINAL:
        for T in (C.SIM_TARGETS, C.TARGETS):
            assert C.total_score(m, n, T) == FV.total(m, n, T)
            assert C.grade(C.total_score(m, n, T)) == 'DCBA'[FV.grade(C.total_score(m, n, T)) - 1]
    print('targets and total() match final_validation')


if __name__ == "__main__" and len(sys.argv) == 2 and sys.argv[1] == "targets":
    check_targets_and_total(); sys.exit()
if __name__ == "__main__":
    a, k = int(sys.argv[1]), int(sys.argv[2])
    for seed in range(a, a + k):
        compare(seed)
    print(f'equivalence ok: seeds {a}..{a + k - 1} ({k} games)')

