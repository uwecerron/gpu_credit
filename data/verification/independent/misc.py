import gzip,json
from collections import Counter,defaultdict
from eth_abi import decode
from Crypto.Hash import keccak
def k(s):
    h=keccak.new(digest_bits=256);h.update(s.encode());return '0x'+h.hexdigest()
D='/home/claude/covalent_onchain_compute/data/frozen/'
B=lambda x:bytes.fromhex(x[2:])
H=json.load(gzip.open(D+'hub_events.json.gz'))['events']
c=Counter((l['h'],tuple(l['tp']),l['d']) for l in H['sUSDai.Deposit'])
dups=[x for x,n in c.items() if n>1]
ex=dups[0]; same=[(l['i'],l['b']) for l in H['sUSDai.Deposit'] if (l['h'],tuple(l['tp']),l['d'])==ex]
print('deposit dup keys',len(dups),'example idx',same)
ci=Counter((l['h'],l['i']) for l in H['sUSDai.Deposit']); print('dups by (tx,idx)',sum(1 for n in ci.values() if n>1))
# are dup logs with distinct index?
distinct_idx=sum(1 for x in dups if len({l['i'] for l in H['sUSDai.Deposit'] if (l['h'],tuple(l['tp']),l['d'])==x})>1)
print('dup keys with distinct indexes',distinct_idx)
P=json.load(gzip.open(D+'protocol_txs.json.gz'))
logs={}
for g,txs in P.items():
    for tx in txs:
        for l in tx.get('logs') or []: logs[(l['h'],tuple(l['tp']),l['d'])]=l
VAULT='0x0b2b2b2076d95dda7817e785989fe353fe955ef9'
fee=k('FeePaid(bytes32,uint8,address,address,uint256)'); ec=k('LoanEscrowTimelockCancelled(bytes32,uint256,uint256)')
ew=k('LoanEscrowTimelockWithdrawn(bytes32,uint256)'); ed=k('LoanEscrowTimelockDeposited(bytes32,uint256,uint256)')
fk=defaultdict(float); ecs=[];ews=[];eds=[]
for l in logs.values():
    tp=l['tp']
    if not tp: continue
    if tp[0]==fee and len(tp)==4:
        fm,amt=decode(['address','uint256'],B(l['d'])); rec='0x'+tp[3][-40:]
        fk[(int(tp[2],16),rec==VAULT)]+=amt/1e18
    if tp[0]==ec and l['a'].lower()==VAULT: ecs.append((l['t'],tp[1][:10],*[x/1e18 for x in decode(['uint256','uint256'],B(l['d']))]))
    if tp[0]==ew and l['a'].lower()==VAULT: ews.append((l['t'],tp[1][:10],decode(['uint256'],B(l['d']))[0]/1e18))
    if tp[0]==ed and l['a'].lower()==VAULT: eds.append((l['t'],tp[1][:10],*[x/1e18 for x in decode(['uint256','uint256'],B(l['d']))]))
print('FeePaid by (kind,to vault)',dict(fk))
print('escrow deposits',len(eds),sum(x[2] for x in eds));[print(' ',x) for x in sorted(eds)]
print('escrow cancels',ecs);print('escrow withdrawn',ews)
tot=sum(x[3] for x in ecs)+sum(x[2] for x in ews); print('escrow interest gross',tot,'net90',tot*0.9)
