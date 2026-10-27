import gzip,json,re
from collections import defaultdict
C=json.load(gzip.open('/home/claude/covalent_onchain_compute/data/frozen/collateral.json.gz'))
L=json.load(open('loans_mine.json'))
bund=defaultdict(set)
for w in C['wrapped']: bund[w['bundle_id']].add(w['token_id'])
def attr(r,n):
    for a in r['metadata']['attributes']:
        if a['trait_type']==n: return a['value']
tv=0;tg=0;tu=0;tout=0;ltvs=[];lives=set();missing=[];rows=[]
for h,x in L.items():
    if x['repaid'] or x['out']<=0: continue
    ids=set()
    for i in x['ids']:
        i=int(i)
        if i in bund: ids|=bund[i]
        else: ids.add(i)
    v=g=u=0
    for i in ids:
        r=C['records'].get(str(i))
        if r is None: missing.append((h[:10],i));continue
        val=attr(r,'Collateral Value USD');q=attr(r,'Quantity') or 0
        name=r['metadata']['name']+' '+r['metadata'].get('description','')
        v+=float(val);u+=q;lives.add(attr(r,'Useful Life (days)'))
        if re.search(r'B200|B300|H200',name): g+=8*q
    rows.append((h[:10],x['borrower'][:8],round(x['out']/1e6,2),round(v/1e6,2),u,g,round(x['out']/v,3) if v else None, sorted(ids)[:3], x['cur'][:10]))
    tv+=v;tg+=g;tu+=u;tout+=x['out']
    if v: ltvs.append(x['out']/v)
for r in sorted(rows,key=lambda r:-r[2]): print(r)
print('active',len(rows),'value',tv,'units',tu,'gpus',tg,'out',tout,'bookLTV',tout/tv,'min',min(ltvs),'max',max(ltvs),'lives',lives,'missing',missing)
# compare repo by_terms_hash ids
for h,x in L.items():
    if x['repaid']: continue
    rb=C['by_terms_hash'].get(x['cur'])
    mine=set()
    for i in x['ids']:
        i=int(i); mine|= bund[i] if i in bund else {i}
    if rb is None or set(map(int,rb))!=mine: print('DIFF ids',h[:10],x['cur'][:10],rb and sorted(rb)[:5],sorted(mine)[:5])
