"""Reproduce v10 report numeric QA from saved results and HTML data-qa cells.

No engine imports, game execution, source modification or pilot fallbacks.
Each marked numeric value is independently resolved from the frozen summary or
raw formal game rows. Unmarked prose is outside the numeric coverage claim.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MODES=('baseline','quick','patient','market_first')
MAIN_SCENARIOS=((None,'normal'),('Mechania','idle'))


class MarkerParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.markers=[];self.active=None;self.tables=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='table':self.tables+=1
        if 'data-qa' in attrs:
            if self.active is not None:raise ValueError('Nested numeric markers are not supported')
            if tag not in ('td','th','span'):raise ValueError('Numeric marker must be on a table cell or span')
            self.active={'tag':tag,'descriptor':json.loads(attrs['data-qa']),'parts':[],'line':self.getpos()[0]}
    def handle_data(self,data):
        if self.active is not None:self.active['parts'].append(data)
    def handle_endtag(self,tag):
        if self.active is not None and self.active['tag']==tag:
            self.markers.append({'descriptor':self.active['descriptor'],
                                 'text':''.join(self.active['parts']).strip(),'line':self.active['line']})
            self.active=None


def nested(obj,path):
    if not isinstance(path,str) or not path:raise ValueError('Metric path must be a nonempty string')
    for key in path.split('.'):
        obj=obj[key]
    return obj


def read_json(path):
    with path.open() as stream:return json.load(stream)


def verify_report(results,report,output):
    summary=read_json(results/'summary.json');manifest=read_json(results/'run_manifest.json')
    assert summary['metadata']==manifest,'Summary/manifest mismatch'
    assert manifest['completed_games']==4000 and manifest['main_games']==1600 and manifest['stress_games']==2400
    assert manifest['main_seed_range']==[68000,68199] and manifest['stress_seed_range']==[70000,70029]
    assert manifest['source_unchanged'] and manifest['verification_failures']==0
    assert manifest['rounds']==9 and manifest['countries']==9
    assert manifest['main_scenarios']==[[None,'normal'],['Mechania','idle']]
    groups=defaultdict(list);seen=set()
    with gzip.open(results/'runs.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line)
            key=(row['phase'],row['mode'],row['seed'],row['focal'],row['style'])
            assert key not in seen,'Duplicate formal run identity'
            seen.add(key)
            group=':'.join(map(str,(row['phase'],row['mode'],row['focal'],row['style'])))
            groups[group].append(row)
    expected={('main',mode,seed,focal,style) for mode in MODES for focal,style in MAIN_SCENARIOS for seed in range(68000,68200)}
    expected.update(('stress',mode,seed,focal,style) for mode in MODES for focal,style in manifest['stress_scenarios'] for seed in range(70000,70030))
    assert len(seen)==4000 and seen==expected,'Formal schedule coverage mismatch'
    assert set(groups)==set(summary['experiments'])
    for group,rows in groups.items():assert len(rows)==summary['experiments'][group]['n']
    html=report.read_text(encoding='utf-8');parser=MarkerParser();parser.feed(html);parser.close()
    assert parser.active is None,'Unclosed numeric marker'
    coverage=set();numeric_leaves=0

    def digits(d):
        n=d.get('digits',2)
        if type(n) is not int or not 0<=n<=8:raise ValueError('Invalid numeric precision')
        return n

    def render(d):
        nonlocal numeric_leaves
        if not isinstance(d,dict) or 'kind' not in d:raise ValueError('Malformed numeric descriptor')
        kind=d['kind']
        if kind=='literal':
            if not isinstance(d.get('text'),str):raise ValueError('Literal text must be a string')
            return d['text']
        if kind=='concat':
            if not isinstance(d.get('parts'),list) or not d['parts']:raise ValueError('Empty numeric concatenation')
            return ''.join(render(part) for part in d['parts'])
        if kind=='mean':
            experiment=d['experiment'];metric=d['metric'];precision=digits(d)
            stats=summary['experiments'][experiment]['metrics'][metric]
            assert stats['n']==len(groups[experiment])
            coverage.add((experiment,metric));numeric_leaves+=1
            return f'{stats["mean"]:,.{precision}f}'
        if kind=='ci':
            precision=digits(d);key=d['pair'];metric=d['metric']
            stats=summary['paired'][key][metric]
            assert stats['n'] in (30,200)
            numeric_leaves+=1;coverage.add(('pair:'+key,metric))
            return f'{stats["mean"]:+,.{precision}f} [{stats["ci95"][0]:+,.{precision}f}, {stats["ci95"][1]:+,.{precision}f}]'
        if kind=='count':
            experiment=d['experiment'];metric=d['metric'];rows=groups[experiment]
            values=[nested(row,metric) for row in rows]
            assert all(type(v) in (int,float) for v in values)
            coverage.add((experiment,metric));numeric_leaves+=1
            return f'{sum(v>0 for v in values)}/{len(values)}'
        if kind=='economic_equal_count':
            left_key=d['left_experiment'];right_key=d['right_experiment']
            left={row['seed']:row for row in groups[left_key]}
            right={row['seed']:row for row in groups[right_key]}
            assert left.keys()==right.keys() and len(left)==len(groups[left_key])
            assert len(right)==len(groups[right_key])
            def economic(row):
                countries={name:{key:value for key,value in fields.items() if key!='routing'}
                           for name,fields in row['countries'].items()}
                world={key:value for key,value in row['world'].items()
                       if key not in ('routing','routing_policy','routing_variant','v10_note')}
                return {'countries':countries,'world':world}
            equal=sum(economic(left[seed])==economic(right[seed]) for seed in sorted(left))
            coverage.add((left_key,'__economic_summary_equality__'))
            coverage.add((right_key,'__economic_summary_equality__'))
            numeric_leaves+=1
            return f'{equal}/{len(left)}'
        if kind=='anycount':
            experiment=d['experiment'];metrics=d['metrics'];rows=groups[experiment]
            if not isinstance(metrics,list) or not metrics:raise ValueError('Any-count needs metric paths')
            numerator=sum(any(nested(row,metric)>0 for metric in metrics) for row in rows)
            for metric in metrics:coverage.add((experiment,metric))
            numeric_leaves+=1
            return f'{numerator}/{len(rows)}'
        raise ValueError('Unknown numeric marker kind: '+str(kind))

    errors=[]
    for i,cell in enumerate(parser.markers):
        try:
            wanted=render(cell['descriptor'])
            if cell['text']!=wanted:
                errors.append({'cell':i,'actual':cell['text'],'expected':wanted,'descriptor':cell['descriptor']})
        except Exception as exc:
            errors.append({'cell':i,'error':str(exc),'descriptor':cell['descriptor']})
    # Prevent an empty or sparsely labelled report from receiving a misleading
    # success receipt merely because the few remaining markers matched.
    if len(parser.markers)<150:errors.append({'coverage':'Fewer than150 numeric cells were labelled'})
    expected_main={f'main:{mode}:{focal}:{style}' for mode in MODES for focal,style in MAIN_SCENARIOS}
    covered_main={group for group,metric in coverage if group.startswith('main:')}
    if not expected_main<=covered_main:
        errors.append({'coverage':'Missing primary policy/cohort groups','missing':sorted(expected_main-covered_main)})
    for name in ('Technia','Novia'):
        metric=f'countries.{name}.routing.g3_electronics_used'
        for mode in MODES:
            key=(f'main:{mode}:Mechania:idle',metric)
            if key not in coverage:errors.append({'coverage':'Missing actual-use recovery endpoint','missing':key})
    receipt={'status':'passed' if not errors else 'failed','report':str(report),
        'report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),
        'summary_sha256':hashlib.sha256((results/'summary.json').read_bytes()).hexdigest(),
        'run_manifest_sha256':hashlib.sha256((results/'run_manifest.json').read_bytes()).hexdigest(),
        'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'checked_numeric_cells':len(parser.markers),'checked_numeric_values':numeric_leaves,
        'tables':parser.tables,'formal_games':len(seen),'errors':errors,
        'covered_experiments':sorted({g for g,k in coverage if not g.startswith('pair:')}),
        'scope':['Marked means from saved summary','Marked paired confidence intervals from saved paired results',
                 'Event-presence counts and any-country counts independently from raw formal runs',
                 'Concatenated comparisons and all primary cohort identities',
                 'Marked same-seed economic-summary equality excluding explicitly new routing diagnostics',
                 'Mandatory Technia/Novia actual-use recovery endpoints'],
        'limits':'Unmarked prose and table-label semantics are not exhaustively checked by this numeric validator.'}
    output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,json.dumps(errors,ensure_ascii=False)
    return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=ROOT/'routing_results')
    p.add_argument('--report',type=Path,default=ROOT/'TRADE_ROUTING_REVIEW_V10_KO.html')
    p.add_argument('--output',type=Path)
    a=p.parse_args();results=a.results.resolve();report=a.report.resolve()
    output=a.output.resolve() if a.output else results/'report_numeric_qa.json'
    print(json.dumps(verify_report(results,report,output),ensure_ascii=False))


if __name__=='__main__':main()
