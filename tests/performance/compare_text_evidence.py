"""Exige documentos, geometria e pixels exatos por canal antes/depois."""
import argparse,json
from pathlib import Path

def difference(a,b,path=''):
    if type(a)!=type(b):return path
    if isinstance(a,dict):
        if a.keys()!=b.keys():return path+'(keys)'
        for k in a:
            d=difference(a[k],b[k],path+'/'+k)
            if d:return d
    elif isinstance(a,list):
        if len(a)!=len(b):return path+'(length)'
        for i,(x,y) in enumerate(zip(a,b)):
            d=difference(x,y,path+'/'+str(i))
            if d:return d
    elif a!=b:return path
    return None

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('before',type=Path);p.add_argument('after',type=Path);a=p.parse_args()
    x=json.loads(a.before.read_text());y=json.loads(a.after.read_text());assert x.keys()==y.keys()
    for name in x:
        d=difference(x[name],y[name]);assert d is None,(name,d)
        print(name+': estado, geometria e pixels por canal idênticos')
    print('TOTAL:',len(x),'cenários; igualdade exata, sem tolerância raster/geométrica.')
if __name__=='__main__':main()
