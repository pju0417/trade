"""Independent source-pointer/format validation of the static Korean v17 report."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPORT=ROOT/'TRADE_NATIONAL_RESOURCES_V17_KO.html'


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.spans=[];self.active=None;self.depth=0;self.tables=0
        self.ids=[];self.hrefs=[];self.external=[];self.headings=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if 'href' in a:self.hrefs.append(a['href'])
        if tag in ('img','script','link') and any(str(a.get(k,'')).startswith(('http:','https:','//')) for k in ('src','href')):
            self.external.append(a)
        if tag=='table':self.tables+=1
        if tag in ('h1','h2','h3'):self.headings.append(tag)
        if self.active is not None:self.depth+=1
        elif tag=='span' and 'data-file' in a:
            self.active={'attrs':a,'text':''};self.depth=1
    def handle_data(self,data):
        if self.active is not None:self.active['text']+=data
    def handle_endtag(self,tag):
        if self.active is not None:
            self.depth-=1
            if self.depth==0:
                self.spans.append(self.active);self.active=None


def main():
    parser=ReportParser();parser.feed(REPORT.read_text())
    errors=[];cache={};sources={}
    for index,span in enumerate(parser.spans):
        a=span['attrs'];source=(ROOT/a['data-file']).resolve()
        try:
            if not source.is_relative_to(ROOT):raise ValueError('Source outside package')
            if source not in cache:
                cache[source]=json.loads(source.read_text());sources[str(source.relative_to(ROOT))]=digest(source)
            value=cache[source];pointer=a['data-pointer']
            if pointer:
                if not pointer.startswith('/'):raise ValueError('Invalid JSON pointer')
                for item in pointer[1:].split('/'):
                    key=item.replace('~1','/').replace('~0','~')
                    value=value[int(key)] if isinstance(value,list) else value[key]
            if type(value) not in (int,float):raise ValueError('Not a numeric source')
            scale=float(a.get('data-scale','1'));digits=int(a.get('data-digits','2'))
            sign='+' if a.get('data-sign','false')=='true' else ''
            expected=format(value*scale,f'{sign},.{digits}f')
            if span['text'].strip()!=expected:
                errors.append({'index':index,'source':a['data-file'],'pointer':pointer,
                               'expected':expected,'actual':span['text']})
        except Exception as exc:
            errors.append({'index':index,'attrs':a,'error':str(exc)})
    if parser.active is not None:errors.append({'error':'Unclosed numeric span'})
    if len(parser.spans)<50:errors.append({'error':'Insufficient source-wired numeric results'})
    if len(set(parser.ids))!=len(parser.ids):errors.append({'error':'Duplicate HTML ids'})
    missing=[href for href in parser.hrefs if href.startswith('#') and href[1:] not in parser.ids]
    if missing:errors.append({'error':'Missing local anchors','values':missing})
    if parser.external:errors.append({'error':'Report depends on external assets'})
    if parser.tables<6:errors.append({'error':'Expected comparison tables missing'})
    out={'schema':'v17-report-numeric-qa-1','status':'PASS' if not errors else 'FAIL',
         'report_sha256':digest(REPORT),'validator_sha256':digest(__file__),
         'source_sha256':sources,'source_wired_numbers':len(parser.spans),
         'tables':parser.tables,'headings':len(parser.headings),
         'errors':errors,'economic_games':0,
         'scope':'Validate actual displayed numeric source references/formatting and HTML structure; no classroom or live game UI claim.'}
    target=ROOT/'operating_results/report_numeric_qa.json'
    with target.open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in out.items() if k!='source_sha256'},ensure_ascii=False))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
