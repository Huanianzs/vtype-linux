"""固定引擎版本的公共资源查询协议；不包含账户数据。"""
import fcntl,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import 官方同步探针 as p

ENGINE='0.45.0.weekly_release/2026.08.28.3dfdf30e'

def request(index,versions,hot):
    body=p.number(1,1)+p.blob(2,ENGINE)+p.number(5,431 if hot else 367)
    for item in index:
        record=p.blob(1,item['name'])+p.number(2,item['version'])+p.blob(6,item['uniqueID'])
        body+=p.blob(3,record)
    body+=p.blob(14,p.blob(3,ENGINE))
    names={1:'cell',2:'stroke',3:'wubi',4:'large',5:'e2e',6:'base',7:'second_level',8:'nnlm',9:'jianpin',10:'hand_writing'}
    for kind,name in names.items():body+=p.blob(14,p.number(1,kind)+p.number(2,versions[name]))
    if not hot:body+=p.blob(15,p.varint(2))
    return body

def summarize(raw):
    response=p.fields(raw);items=[]
    for blob in response.get(1,[]):
        item=p.fields(blob);full=p.fields(p.one(item,7,b''))
        items.append({'name':p.one(item,1,b'').decode(),'version':p.one(item,2),'type':p.one(item,3),'dict_type':p.one(item,4),'compatible':p.one(item,16),'delete':p.one(item,12),'full_available':bool(full),'full_bytes':p.one(full,10),'compression':p.one(full,5),'encryption':p.one(full,8)})
    return {'items':items,'interval':p.one(response,2),'response_bytes':len(raw)}
