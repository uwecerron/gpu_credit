import requests,json,time
from Crypto.Hash import keccak
from eth_abi import decode,encode
CA='/root/.ccr/ca-bundle.crt';RPC='https://arb1.arbitrum.io/rpc'
def sel(s):
    h=keccak.new(digest_bits=256);h.update(s.encode());return h.hexdigest()[:8]
def rpc(m,p):
    for i in range(8):
        r=requests.post(RPC,json={'jsonrpc':'2.0','id':1,'method':m,'params':p},verify=CA,timeout=60)
        if r.status_code==429 or 'Too Many' in r.text: time.sleep(2**i);continue
        j=r.json()
        if 'error' in j: raise Exception(j)
        return j['result']
def call(to,sig,types=(),args=()):
    data='0x'+sel(sig)+encode(list(types),list(args)).hex()
    return rpc('eth_call',[{'to':to,'data':data},'latest'])
V='0x0b2b2b2076d95dda7817e785989fe353fe955ef9';U='0x0a1a1a107e45b7ced86833863f482bc5f4ed82ef';PY='0x46850ad61c2b7d64d08c9c754f45254596696984';NFT='0xb31f04f920f24eda3ad276d55c5afefad6230c5d'
out={}
bn=int(rpc('eth_blockNumber',[]),16);out['block']=bn
blk=rpc('eth_getBlockByNumber',[hex(bn),False]);out['block_time']=int(blk['timestamp'],16)
out['selector_depositTimelockBalance']=sel('depositTimelockBalance()')
out['depositTimelockBalance']=int(call(V,'depositTimelockBalance()'),16)/1e18
out['totalAssets']=int(call(V,'totalAssets()'),16)/1e18
out['usdai_totalSupply']=int(call(U,'totalSupply()'),16)/1e18
out['pyusd_balanceOf_usdai']=int(call(PY,'balanceOf(address)',['address'],[U]),16)/1e6
out['ownerOf_1006']='0x'+call(NFT,'ownerOf(uint256)',['uint256'],[1006])[-40:]
out['tokenURI_1002']=decode(['string'],bytes.fromhex(call(NFT,'tokenURI(uint256)',['uint256'],[1002])[2:]))[0]
out['tokenURI_1006']=decode(['string'],bytes.fromhex(call(NFT,'tokenURI(uint256)',['uint256'],[1006])[2:]))[0]
for t in (1002,1006):
    r=requests.get(out[f'tokenURI_{t}'],verify=CA,timeout=60); out[f'meta_{t}']=r.json() if r.ok else r.status_code
out['retrieved_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
print(json.dumps(out,indent=1))
json.dump(out,open('live_checks.json','w'),indent=1)
