import gzip,json,sys
from collections import defaultdict
from Crypto.Hash import keccak
from eth_abi import decode
D='/home/claude/covalent_onchain_compute/data/frozen/'
def k(s):
    h=keccak.new(digest_bits=256);h.update(s.encode());return '0x'+h.hexdigest()
LR1='0x0c2ed170f2bb1df1a44292ad621b577b3c9597d1';LR2='0x1c2ed170de32846316784c4fd58a5e3c7563e12f'
VAULT='0x0b2b2b2076d95dda7817e785989fe353fe955ef9'
USDAI='0x0a1a1a107e45b7ced86833863f482bc5f4ed82ef'
T={'O1':k('LoanOriginated(bytes32,address,address,uint256,uint256)'),
   'O2':k('LoanOriginated(bytes32,bytes)'),
   'R6':k('LoanRefinanced(bytes32,bytes32,bytes,uint256,uint256,uint256)'),
   'R3':k('LoanRefinanced(bytes32,bytes32,bytes)'),
   'M':k('LoanMigrated(bytes32,bytes32,bytes)'),
   'REP':k('LoanRepaid(bytes32,address,uint256,uint256,uint256,uint256,bool)'),
   'LREP':k('LenderRepaid(bytes32,address,uint8,uint256,uint256,uint256)'),
   'RA':k('ReserveAccountCreated(address,address)'),
   'BR':k('LoanBreached(bytes32)'),'LIQ':k('LoanLiquidated(bytes32)')}
LT2="(uint64,address,address,address,(uint16,uint8,int32),(address,bytes),uint256[],(address,uint256,uint256)[],(uint8,address,address,bytes)[],address[],bytes)"
P=json.load(gzip.open(D+'protocol_txs.json.gz'))
logs={}
for grp,txs in P.items():
    for tx in txs:
        for l in tx.get('logs') or []:
            key=(l['h'],tuple(l['tp']),l['d'])
            logs[key]=l
logs=sorted(logs.values(),key=lambda l:(l['b'],l['i']))
B=lambda x:bytes.fromhex(x[2:])
addr=lambda t:'0x'+t[-40:]
dec={'0xaf88d065e77c8cc2239327c5edb3a432268e5831':6,'0x46850ad61c2b7d64d08c9c754f45254596696984':6,USDAI:18}
ra={}
for l in logs:
    if l['tp'] and l['tp'][0]==T['RA'] and len(l['tp'])==3: ra[addr(l['tp'][1])]=addr(l['tp'][2])
def terms(blob):
    t=decode([LT2],B(blob))[0]
    return dict(borrower=t[1].lower(),ccy=t[2].lower(),dur=t[4][0],ids=[int(x) for x in t[6]],tr=[(x[0].lower(),x[1],x[2]) for x in t[7]])
loans={};root={};cur={};ccy={};prin={}; repaid_cur=defaultdict(float); counts=defaultdict(int)
interest=0;principal_rep=0;fees=0;vault_int=0;breach=0;nmig=0;nref=0
for l in logs:
    tp=l['tp']
    if not tp: continue
    t0=tp[0];a=l['a'].lower()
    if a not in (LR1,LR2): continue
    if t0==T['O1'] and len(tp)==4:
        h=tp[1];b=addr(tp[2]);c=addr(tp[3]);p,fee=decode(['uint256','uint256'],B(l['d']))
        u=10**dec.get(c,18)
        loans[h]=dict(v=1,t=l['t'],borrower=ra.get(b,b),principal=p/u,cur=h,repaid=False,ids=[]);root[h]=h;ccy[h]=u;prin[h]=p/u
    elif t0==T['O2'] and len(tp)==2:
        h=tp[1];blob=decode(['bytes'],B(l['d']))[0];tt=terms('0x'+blob.hex());u=10**dec.get(tt['ccy'],18)
        p=sum(x[1] for x in tt['tr'])/u
        loans[h]=dict(v=2,t=l['t'],borrower=ra.get(tt['borrower'],tt['borrower']),principal=p,cur=h,repaid=False,ids=tt['ids'],tr=tt['tr'],dur=tt['dur'])
        root[h]=h;ccy[h]=u;prin[h]=p
    elif t0 in (T['M'],T['R3'],T['R6']) and len(tp)==3:
        old,new=tp[1],tp[2]
        if t0==T['M']:
            blob=decode(['bytes'],B(l['d']))[0];nmig+=1
        elif t0==T['R3']: blob=decode(['bytes'],B(l['d']))[0];nref+=1
        else: blob=decode(['bytes','uint256','uint256','uint256'],B(l['d']))[0];nref+=1
        tt=terms('0x'+blob.hex());u=10**dec.get(tt['ccy'],18)
        r=root[old];root[new]=r;ccy[new]=u;prin[new]=sum(x[1] for x in tt['tr'])/u
        loans[r]['cur']=new;loans[r]['ids']=tt['ids'];loans[r]['tr']=tt['tr'];loans[r]['dur']=tt['dur']
    elif t0==T['REP'] and len(tp)==3:
        h=tp[1];pp,ii,pre,fe,isr=decode(['uint256']*4+['bool'],B(l['d']));u=ccy[h]
        repaid_cur[h]+=(pp+pre)/u
        interest+=ii/u;principal_rep+=(pp+pre)/u;fees+=fe/u
        if isr: loans[root[h]]['repaid']=True
        loans[root[h]].setdefault('last',l['t']);loans[root[h]]['last']=l['t']
    elif t0==T['LREP'] and len(tp)==4:
        h=tp[1];lender=addr(tp[2]);pp,ii,pre=decode(['uint256']*3,B(l['d']))
        if lender==VAULT: vault_int+=ii/ccy[h]
    elif t0 in (T['BR'],T['LIQ']): breach+=1
real={h:L for h,L in loans.items() if L['principal']>=1000}
test=len(loans)-len(real)
for L in real.values():
    h=L['cur'];L['out']=0 if L['repaid'] else max(prin[h]-repaid_cur[h],0)
orig=sum(L['principal'] for L in real.values());out=sum(L['out'] for L in real.values())
byb=defaultdict(float);byo=defaultdict(float)
for L in real.values(): byb[L['borrower']]+=L['principal'];byo[L['borrower']]+=L['out']
sh=sorted([v/orig for v in byb.values()],reverse=True)
sho=sorted([v/out for v in byo.values()],reverse=True)
print('loans',len(real),'test',test,'borrowers',len(byb),'migrations',nmig,'refi',nref)
print('originated',orig,'outstanding',out,'nrepaid',sum(L['repaid'] for L in real.values()),'active',sum(1 for L in real.values() if not L['repaid']))
print('top1',sh[0],'top3',sum(sh[:3]),'HHI',sum(s*s for s in sh),'HHIout',sum(s*s for s in sho),'top1out',sho[0],'top3out',sum(sho[:3]))
print('interest',interest,'principal repaid',principal_rep,'fees',fees,'vault interest',vault_int,'breach/liq',breach)
# check prepayment field included? also print prepay
json.dump({h:dict(L,ids=L['ids'],tr=[list(map(str,x)) for x in L.get('tr',[])]) for h,L in real.items()},open(sys.argv[1],'w'),default=str,indent=1)
