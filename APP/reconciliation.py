import re,unicodedata,math
from decimal import Decimal
from datetime import date,datetime
import pandas as pd
def ref(v):
    if v is None:return ''
    if isinstance(v,(int,float)):v=str(int(v)) if float(v).is_integer() else str(v)
    return re.sub(r'[^A-Z0-9]','',str(v).upper())

def money(v):return Decimal(str(v or 0)).quantize(Decimal('.01'))

def name(v):
    s=unicodedata.normalize('NFKD',str(v or '').upper())
    s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]','',s)

def similar(a,b):
    ca,cb=name(a),name(b)
    if ca and cb and (ca in cb or cb in ca):return True
    def tokens(s):return re.findall(r'[A-Z0-9]+',unicodedata.normalize('NFKD',str(s).upper()).encode('ascii','ignore').decode())
    aa=[t for t in tokens(a) if t not in {'SA','S','A','SAS','SRL','LTDA'}]
    bb=tokens(b)
    def close(x,y):
        if x==y:return True
        if min(len(x),len(y))<5 or abs(len(x)-len(y))>1:return False
        if len(x)==len(y):return sum(c!=d for c,d in zip(x,y))<=1
        short,long=sorted([x,y],key=len)
        return any(long[:i]+long[i+1:]==short for i in range(len(long)))
    return len(aa)>=2 and all(any(close(x,y) for y in bb) for x in aa)
norm=name

def reconcile(mav, bank, banco):
    def clean(x):
        return '' if pd.isna(x) else x
    def identifier(x):
        x=clean(x)
        return str(int(x)) if isinstance(x,(int,float)) and float(x).is_integer() else str(x)
    rows=[]
    for i,r in mav.iterrows():
        rows.append(['',int(i),r['Maveric_Fecha'].isoformat(),identifier(r['Maveric Ref.']),str(clean(r['Maveric_Origen'])),str(clean(r['Maveric_Destino'])),str(clean(r['Maveric Cliente/Proveedor'])),str(clean(r['Maveric Detalle'])),r['Maveric_Ingreso'],r['Maveric_Egreso'],None,None,'','','',None,None,None,None,''])
    bank=[dict(row=int(i),date=r['Banco_Fecha'].isoformat(),ref=identifier(r['Banco_Movimiento']),operation=str(clean(r['Banco_Cheque_Ref'])),detail=str(clean(r['Banco_Detalle'])),debit=r['Banco_Debito'],credit=r['Banco_Credito'],sheet=r['Banco_Hoja']) for i,r in bank.iterrows()]
    used=set();done=set();groups=[]
    for r in rows:
        if norm(r[5])=='ARQUEO':
            r[0]='ARQUEO';r[19]='Movimiento de arqueo; no requiere conciliación bancaria.';done.add(r[1])
        elif (r[8]>0 and r[9]!=0) or (r[9]>0 and r[8]!=0) or r[8]<0 or r[9]<0:
            r[0]='INGRESO/EGRESO INVALIDO';r[19]='Debe existir un importe positivo en una sola columna.';done.add(r[1])
    # Pair cancellations before other rules; card pairs stay inside their daily bag.
    for r in rows:
        if r[1] in done or not r[3] or r[8]<=0 or r[9]!=0:continue
        if 'LIQ' in r[3].upper() or re.search(r'\bTC\s',r[6].upper()):continue
        opposite=[x for x in rows if x[1] not in done and x[1]!=r[1] and x[3]==r[3] and x[2]==r[2] and x[8]==0 and x[9]==r[8] and x[4]==r[5] and x[5]==r[4] and norm(x[6])==norm(r[6])]
        if len(opposite)==1:
            for x in [r,opposite[0]]:x[0]='ANULADO MAVERIC';x[19]='Ingreso y egreso opuestos con igual referencia e importe.';done.add(x[1])
    def netm(r):return money(r[8])-money(r[9])
    def netb(b):return money(b['credit'])-money(b['debit'])
    def gap(a,b):return abs((date.fromisoformat(a)-date.fromisoformat(b)).days)
    def put(rr,bb,status,note,group=False):
        for i,r in enumerate(rr):
            r[0]=status;r[19]=note;done.add(r[1]);r[10]=bb[0]['row'] if bb else None;r[11]=bb[0]['date'] if bb else None
            r[12]=' / '.join(str(b['ref'] or '') for b in bb);r[13]=' / '.join(str(b['operation'] or '') for b in bb);r[14]=' / '.join(str(b['detail'] or '') for b in bb)
            r[15]=float(sum(money(b['debit']) for b in bb)) if i==0 else 0.0;r[16]=float(sum(money(b['credit']) for b in bb)) if i==0 else 0.0
            if not bb:r[15]=r[16]=None
            if group:r[19]+=' Total bancario mostrado solo en la primera fila de la bolsa, sin duplicarlo.'
        if status.startswith('OK') or status=='TRASPASO OK':used.update(b['row'] for b in bb)
        if group:groups.append([rr[0][2],note,float(sum(netm(r) for r in rr)),float(sum(netb(b) for b in bb)),status,' / '.join(str(b['row']) for b in bb)])
    for day in sorted({r[2] for r in rows}):
        card=[r for r in rows if r[1] not in done and r[2]==day and (norm(r[4])=='TARJETASCOBRADAS' or 'LIQ' in str(r[3]).upper() or re.search(r'\bTC\s',r[6].upper()) or 'RETENCION' in r[7].upper())]
        cb=[]
        for b in bank:
            if norm(b['ref'])!='RETENCIONTC':continue
            dates=re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b',str(b['detail']))
            if any(date(int(y)+2000 if len(y)==2 else int(y),int(m),int(d)).isoformat()==day for d,m,y in dates):cb.append(b)
        if card:
            a=sum(netm(r) for r in card);b=sum(netb(x) for x in cb);ok=bool(cb) and abs(a-b)<=Decimal('.50')
            put(card,cb,'OK TARJETA' if ok else 'NO COINCIDE TARJETA',f'Bolsa tarjetas {day}: Maveric {a:.2f}; banco {b:.2f}; diferencia banco − Maveric {b-a:.2f}; margen ±0,50.',True)
    for r in rows:
        if r[1] in done:continue
        if norm(r[5])=='ARQUEO':
            put([r],[],'ARQUEO','Movimiento de arqueo; no requiere conciliación bancaria.');continue
        # Acepta CHEQUE y la abreviatura CH del detalle, con número completo.
        nums=set(re.findall(r'\bCHEQUE\s*(\d+)\b',r[3].upper()+' '+r[7].upper()))
        if not nums and re.search(r'\bCH\s*:',r[7].upper()):nums=set(re.findall(r'\b\d{5,}\b',r[7]))
        if nums:
            cand=[b for b in bank if b['row'] not in used and nums.intersection(re.findall(r'\d+',str(b['operation'])+' '+str(b['detail'])))]
            near=[b for b in cand if gap(r[2],b['date'])<=5];valid=[b for b in near if netm(r)==netb(b)]
            if len(valid)==1:put([r],valid,'OK CHEQUE','Número de cheque, fecha ±5 días, importe y sentido coinciden.')
            else:put([r],near[:1],'CHEQUE AMBIGUO' if len(valid)>1 else 'NO COINCIDE IMPORTE BANCOS' if near else 'NO COINCIDE FECHA' if cand else 'NO ESTA CHEQUE EN BANCOS','Cheque: revisar número, fecha o importe.')
    for day in sorted({r[2] for r in rows}):
        expenses=[r for r in rows if r[1] not in done and r[2]==day and norm(r[6])=='GASTOBANCARIO']
        bb=[b for b in bank if b['row'] not in used and b['date']==day and 'GASTOBANCARIO' in norm(b['detail'])]
        if expenses:put(expenses,bb,'OK GASTO BANCARIO' if bb and sum(netm(r) for r in expenses)==sum(netb(b) for b in bb) else 'NO COINCIDE GASTO BANCARIO','Bolsa gasto bancario: misma fecha y total de importes con el mismo sentido.',True)
    for r in rows:
        if r[1] in done:continue
        if 'INTSCREDITOACORDADO' in norm(r[7]):
            bb=[b for b in bank if b['row'] not in used and 'INTSCREDITOACORDADO' in norm(b['operation']) and gap(r[2],b['date'])<=1]
            valid=[b for b in bb if netm(r)==netb(b)]
            put([r],valid[:1] or bb[:1],'OK INTERESES' if len(valid)==1 else 'NO COINCIDE INTERESES','Intereses: Maveric F contra banco B; fecha ±1 día e importe.');continue
        if re.search(r'\bDEV[\w.]*',r[7].upper()):
            bb=[b for b in bank if b['row'] not in used and norm(b['ref'])=='DEVOLUCION' and gap(r[2],b['date'])<=5 and similar(r[6],b['detail'])]
            valid=[b for b in bb if netm(r)==netb(b)]
            put([r],valid[:1] or bb[:1],'OK DEVOLUCION' if len(valid)==1 else 'NO COINCIDE DEVOLUCION','Devolución: categoría bancaria, nombre contenido/similar, fecha ±5 días e importe.');continue
        if r[5].upper()=='PROVEEDORES':
            rr=[x for x in rows if x[1] not in done and x[2]==r[2] and x[5].upper()=='PROVEEDORES' and (('PALLADIUM' in norm(x[6]) and 'PALLADIUM' in norm(r[6])) or norm(x[6])==norm(r[6]))]
            bb=[b for b in bank if b['row'] not in used and b['date']==r[2] and (similar(r[6],b['detail']) or 'PALLADIUM' in norm(r[6]) and 'PALLADIUM' in norm(b['detail'])) and b['debit']>0]
            put(rr,bb,'OK PROVEEDOR' if bb and sum(netm(x) for x in rr)==sum(netb(b) for b in bb) else 'NO COINCIDE PROVEEDOR','Proveedor: nombre en Maveric E contra banco D, misma fecha y suma de importes G/H.',len(rr)>1 or len(bb)>1);continue
        candidates=[b for b in bank if str(b['ref'])==r[3]] if r[3] else []
        near=[b for b in candidates if gap(r[2],b['date'])<=5]
        bb=[b for b in near if b['row'] not in used and netb(b)==netm(r)]
        if len(bb)==1:put([r],bb,'OK EN BANCO' if similar(r[6],bb[0]['detail']) else 'OK, check detalle','Referencia, fecha ±5 días e importe coinciden; comparación final del nombre.')
        elif len(bb)>1:put([r],[],'REFERENCIA AMBIGUA','Más de un candidato válido; requiere revisión.')
        elif near:put([r],near[:1],'MOVIMIENTO BANCO YA ASIGNADO' if any(netb(b)==netm(r) for b in near) else 'NO COINCIDE IMPORTE BANCOS','Referencia y fecha coinciden; revisar importe/sentido o asignación previa.')
        elif candidates:put([r],candidates[:1],'NO COINCIDE FECHA','Referencia encontrada, pero fuera de ±5 días.')
        else:put([r],[],'SIN REFERENCIA MAVERIC' if not r[3] else 'NO ESTA EN BANCOS','Sin referencia/candidato suficiente para conciliar.')
    result=[]
    lookup={b['row']:b for b in bank}
    for values,(_,original) in zip(rows,mav.iterrows()):
        o=original.to_dict();o.update(Estado=values[0],Motivo=values[19],Tipo='Ingreso' if values[8]>0 and values[9]==0 else 'Egreso' if values[9]>0 and values[8]==0 else 'Otros')
        o.update({'Fecha en Bancos':date.fromisoformat(values[11]) if values[11] else '', 'Banco_Fecha':date.fromisoformat(values[11]) if values[11] else '', 'Banco_Hoja':lookup[values[10]]['sheet'] if values[10] is not None else '', 'Banco_Cheque_Ref':values[13], 'Banco_Movimiento':values[12], 'Banco_Detalle':values[14], 'Banco_Debito':values[15] or 0, 'Banco_Credito':values[16] or 0})
        o['Es_Tarjeta']='SI' if ('TARJETA' in values[0] or re.search(r'\bTC\s',values[6].upper()) or norm(values[4])=='TARJETASCOBRADAS' or 'RETENCION' in values[7].upper() or 'LIQ' in values[3].upper()) else 'NO'
        o['Es_Gasto_Bancario']='SI' if 'GASTOBANCARIO' in norm(values[5]+values[6]+values[7]) else 'NO'
        o['Es_Pago_Proveedor']='SI' if 'PROVEEDORES' in values[5].upper() and o['Es_Tarjeta']=='NO' and o['Es_Gasto_Bancario']=='NO' else 'NO'
        result.append(o)
    df=pd.DataFrame(result);df.attrs['bolsas']=groups
    return df,used
