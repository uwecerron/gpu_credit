import gzip,json,statistics as st
from collections import defaultdict
from datetime import date,timedelta
from eth_abi import decode
from Crypto.Hash import keccak
def k(s):
    h=keccak.new(digest_bits=256);h.update(s.encode());return '0x'+h.hexdigest()
D='/home/claude/covalent_onchain_compute/data/frozen/'
H=json.load(gzip.open(D+'hub_events.json.gz'))
E=H['events']
B=lambda x:bytes.fromhex(x[2:])
VAULT='0x0b2b2b2076d95dda7817e785989fe353fe955ef9'
def dd(lst):
    s={};
    for l in lst: s[(l['h'],l['i'])]=l
    return sorted(s.values(),key=lambda l:(l['b'],l['i']))
for n in E: print(n,len(E[n]),len(dd(E[n])))
# check topics
sig={'sUSDai.Deposit':'Deposit(address,address,uint256,uint256)','sUSDai.RedeemRequest':'RedeemRequest(address,address,uint256,address,uint256)',
'sUSDai.RedemptionProcessed':'RedemptionProcessed(uint256,address,uint256,uint256,uint256)','sUSDai.BaseYieldDeposited':'BaseYieldDeposited(uint256,uint256)',
'sUSDai.LoanEscrowTimelockDeposited':'LoanEscrowTimelockDeposited(bytes32,uint256,uint256)','sUSDai.LoanEscrowTimelockWithdrawn':'LoanEscrowTimelockWithdrawn(bytes32,uint256)',
'USDai.Deposited':'Deposited(address,address,address,uint256,uint256)','USDai.Withdrawn':'Withdrawn(address,address,address,uint256,uint256)'}
for n,s in sig.items():
    bad=[l for l in E[n] if l['tp'][0]!=k(s)]; print('topic check',n,len(bad))
dep=defaultdict(list); mint=defaultdict(float); req=defaultdict(float)
for l in dd(E['sUSDai.Deposit']):
    if len(l['tp'])!=3: continue
    a,s=decode(['uint256','uint256'],B(l['d'])); d=l['t'][:10]
    if s>0: dep[d].append(a/s)
    mint[d]+=s/1e18
reqs={}
for l in dd(E['sUSDai.RedeemRequest']):
    if len(l['tp'])!=4: continue
    sender,s=decode(['address','uint256'],B(l['d'])); rid=int(l['tp'][3],16)
    req[l['t'][:10]]+=s/1e18; reqs[rid]=(l['t'],s/1e18)
d0=date(2025,5,12);d1=date(2026,10,21)
nav=None;S=0;Y=0;navs={}
d=d0
while d<=d1:
    ds=d.isoformat()
    newnav=st.median(dep[ds]) if dep[ds] else nav
    if nav is not None and newnav is not None: Y+=S*(newnav-nav)
    nav=newnav;navs[ds]=nav
    S+=mint[ds]-req[ds]
    d+=timedelta(1)
first=min(k for k in dep if dep[k]); print('NAV first',first,navs[first],'NAV end',nav,'S end',S,'Accrued Y',Y)
yrs=(d1-date.fromisoformat(first)).days/365
print('ann total (from first dep)',(nav/navs[first])**(1/yrs)-1, 'simple',(nav/navs[first]-1)/yrs)
yrs2=(d1-d0).days/365; print('ann over study window', (nav/navs[first])**(1/yrs2)-1)
# base yield
by=0;fee=0
for l in dd(E['sUSDai.BaseYieldDeposited']):
    a,f=decode(['uint256','uint256'],B(l['d'])); by+=a/1e18; fee+=f/1e18
print('base yield deposited',by,'admin fee',fee,'net',by-fee)
ew=0
for l in dd(E['sUSDai.LoanEscrowTimelockWithdrawn']):
    ew+=decode(['uint256'],B(l['d']))[0]/1e18
print('escrow withdrawn interest',ew, [n for n in E if 'Cancel' in n])
# queue
proc={}
for l in dd(E['sUSDai.RedemptionProcessed']):
    rid=int(l['tp'][1],16); fs,am,pend=decode(['uint256']*3,B(l['d']))
    proc.setdefault(rid,[]).append((l['t'],fs/1e18,pend/1e18))
from datetime import datetime
P=lambda t:datetime.fromisoformat(t.replace('Z','+00:00'))
waits=[];pending=0;done=0
for rid,(t,s) in reqs.items():
    ps=proc.get(rid)
    if ps:
        last=ps[-1]
        if last[2]==0:
            waits.append((P(last[0])-P(t)).total_seconds()/86400);done+=1
        else: pending+=last[2]
    else: pending+=s
waits.sort()
print('requests',len(reqs),'redeemers',len({1 for _ in []}),'completed',done,'median wait',st.median(waits),'p90',waits[int(0.9*len(waits))] ,'max',max(waits),'pending',pending,'requested',sum(s for t,s in reqs.values()))
own=set()
for l in dd(E['sUSDai.RedeemRequest']): own.add(l['tp'][2])
print('distinct owners',len(own))
json.dump(navs,open('navs.json','w'))
