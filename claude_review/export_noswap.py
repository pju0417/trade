"""Experiment: same-good swap rule for the export measure (Claude, 2026-11-19).

Pre-registered before running (do not change after seeing results)
  One factor   export measure 'useful_export' -> 'useful_export_noswap': a unit does not count
               as an export when, in the same round, the buyer also sold the SAME good to the
               seller (either channel). Everything else as in export_revenue.py (economy, seeds,
               target method, validation scenarios). Targets are re-derived for the new measure.
  Expectation  the Tropia-Grainia wash pair swaps bananas both ways and should be caught; the
               Oilia-Mineria pair mostly exchanges different goods (banana <-> fuel), which this
               rule deliberately does not touch.
  Criteria     F1 each wash-pair member's mean economic attainment rise <= 0.10.
               F2 normal play (seeds 130000-130099): each country's mean economic attainment
                  differs from the 'useful_export' measure by <= 0.02 (genuine trade unaffected).
               F3 E1, E2, E3, E4 and E6 of export_revenue.py still pass.
Games: re-runs export_revenue.py 'cal' (780) and 'valid' (610) so the new field is recorded.
Usage: python3 export_noswap.py run ; python3 export_noswap.py report
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_revenue as E
import sim_lib as L

if __name__ == '__main__':
    if sys.argv[1] == 'run':
        E.run('cal'); E.run('valid')
    else:
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            old = E.report('useful_export', 'export_report_rerun.json')
            new = E.report('useful_export_noswap', 'export_noswap_report.json')
        prev = json.load(open(os.path.join(E.OUT, 'export_report.json')))
        same = (prev['targets_useful_export'] == old['targets_useful_export'] and
                all(abs(prev['normal'][n]['attain'] - old['normal'][n]['attain']) < 1e-12 for n in L.NAMES))
        d_attain = {n: new['normal'][n]['attain'] - old['normal'][n]['attain'] for n in L.NAMES}
        crit = {'F1_wash_rise_le_0.10': new['criteria']['E5_wash_rise_le_0.10'],
                'F2_normal_attain_change_le_0.02': all(abs(v) <= .02 for v in d_attain.values()),
                'F3_E1_E2_E3_E4_E6': all(new['criteria'][k] for k in new['criteria'] if not k.startswith('E5'))}
        summary = {'rerun_reproduces_previous_report': same, 'targets_old': old['targets_useful_export'],
                   'targets_new': new['targets_useful_export'], 'normal_attain_change': d_attain,
                   'normal_reach_new': {n: new['normal'][n]['reach'] for n in L.NAMES},
                   'reach_range_new': new['reach_range'],
                   'wash_old': old['wash'], 'wash_new': new['wash'],
                   'criteria_new_all': new['criteria'], 'criteria': crit}
        json.dump(summary, open(os.path.join(E.OUT, 'export_noswap_summary.json'), 'w'), ensure_ascii=False, indent=1)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
