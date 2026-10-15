import io,math,textwrap
from datetime import date,datetime
import pandas as pd

def export_excel(full,bank,bank_range,used,banco,moneda,version,order_cols,is_tarj,is_prov,is_gasto):
    groups=full.attrs.get('bolsas',[]);full=order_cols(full)
    accepted=full.Estado.str.startswith('OK')|full.Estado.eq('TRASPASO OK')
    review=full[~accepted&~full.Estado.isin(['ARQUEO','ANULADO MAVERIC'])|full.Estado.eq('OK, check detalle')]
    missing=bank_range.loc[[i for i,r in bank_range.iterrows() if i not in used and (r.Banco_Debito or r.Banco_Credito) and not is_tarj(r) and not is_gasto(r)]].copy()
    missing['Estado']='Falta en Maveric'
    bankcols=['Banco_Hoja','Banco_Fecha','Banco_Cheque_Ref','Banco_Movimiento','Banco_Detalle','Banco_Debito','Banco_Credito']
    def category(flag,bankrule):
        a=full[full[flag].eq('SI')].copy();a['Origen']='Maveric'
        b=bank_range.loc[[i for i,r in bank_range.iterrows() if i not in used and bankrule(r)]].copy();b['Origen']='Banco';b['Estado']='Banco no usado en Maveric'
        return pd.concat([a,b],ignore_index=True).drop(columns=['Banco_Texto_Busqueda'],errors='ignore')
    summary=pd.DataFrame([['Banco',banco],['Moneda',moneda],['Versión',version],['Movimientos Maveric',len(full)],['OK',int(accepted.sum())],['Revisar',len(review)],['Faltan en Maveric',len(missing)],['Arqueo',int(full.Estado.eq('ARQUEO').sum())],*[[state,int(count)] for state,count in full.Estado.value_counts().items()]],columns=['Concepto','Valor'])
    notes=pd.DataFrame([
        ['Orden','Movimientos originales sin filas vacías; columnas del conciliador anterior.'],
        ['Referencias','Maveric B contra banco C: identificador completo, fecha ±5 días, importe al centavo y finalmente nombre.'],
        ['Tarjetas','Bolsa diaria: TARJETASCOBRADAS, LIQ, TC y retenciones. Neto ingreso menos egreso, sin contar dos veces una fila. Banco C retencion tc; fecha del texto en D; margen ±0,50.'],
        ['Cheques','Maveric B/F contra banco B/D: número completo, fecha ±5 días, importe y sentido; admite CH:.'],
        ['Proveedores','Nombre E contra banco D; misma fecha y suma de importes G/H; consolida Palladium.'],
        ['Gastos','Suma diaria de gasto bancario en Maveric E contra banco D.'],
        ['Intereses','INTS.CREDITOACORDADO en Maveric F contra banco B; fecha ±1 día e importe.'],
        ['Devoluciones','DEV en F contra devolucion en banco C; nombre E en banco D, fecha ±5 días e importe.'],
        ['Anulados','Pareja única de ingresos/egresos opuestos con igual referencia, fecha y nombre; dentro de tarjetas aporta cero al neto.'],
        ['Arqueo','Estado ARQUEO; excluido de conciliación y pendientes.'],
        ['Asignación','No se reutiliza banco entre parejas o bolsas. En bolsas, el importe bancario completo se muestra solo en la primera fila.'],
        ['Fechas','Las fechas bancarias erróneas se conservan para detectar NO COINCIDE FECHA.'],
    ],columns=['Regla','Detalle'])
    sheets=[('Espejo_Maveric',full),('Resumen',summary),('Ingresos Maveric',full[full.Tipo.eq('Ingreso')]),('Egresos Maveric',full[full.Tipo.eq('Egreso')]),('Otros movimientos Maveric',full[full.Tipo.eq('Otros')]),('Tarjetas',category('Es_Tarjeta',is_tarj)),('Revisar diferencias',review),('Pago a Proveedores',category('Es_Pago_Proveedor',lambda r:is_prov(r) and not is_tarj(r) and not is_gasto(r))),('Gasto Bancario',category('Es_Gasto_Bancario',is_gasto)),('Faltan en Maveric',missing),('Falta en bancos',full[full.Estado.eq('NO ESTA EN BANCOS')]),('Banco_Usado',bank.loc[sorted(used),bankcols] if used else bank[bankcols].iloc[:0]),('Banco_Rango_Maveric',bank_range[bankcols]),('Notas_Reglas',notes),('Control bolsas',pd.DataFrame(groups,columns=['Fecha','Motivo','Neto Maveric','Neto banco','Estado','Filas banco']))]
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='xlsxwriter',date_format='dd/mm/yyyy',datetime_format='dd/mm/yyyy') as writer:
        wb=writer.book
        common={'font_name':'Arial','font_size':10,'font_color':'#000000','align':'center','valign':'vcenter','border':1,'border_color':'#A6B4BE','text_wrap':True}
        body=wb.add_format(common);head=wb.add_format({**common,'bold':True,'bg_color':'#D9EAF7'});totalfmt=wb.add_format({**common,'bold':True});money=wb.add_format({**common,'num_format':'#,##0.00'});datefmt=wb.add_format({**common,'num_format':'dd/mm/yyyy'})
        colors={key:wb.add_format({'bg_color':color,'font_color':'#000000'}) for key,color in [('green','#DDEEDB'),('yellow','#FFF2B3'),('grey','#E7E7E7'),('red','#FADBD8')]}
        for sn,df in sheets:
            df=df.drop(columns=['Banco_Texto_Busqueda'],errors='ignore').copy();ws=wb.add_worksheet(sn);writer.sheets[sn]=ws;ws.hide_gridlines(2);ws.freeze_panes(1,0)
            if not len(df.columns):df=pd.DataFrame(columns=['Estado'])
            widths=[]
            for c,col in enumerate(df.columns):
                width=65 if col=='Motivo' else 42 if 'Detalle' in col else 32 if 'Cliente' in col else 30 if col=='Estado' else 17 if 'Fecha' in col or col=='Fecha en Bancos' else 21 if any(x in col for x in ['Ingreso','Egreso','Credito','Debito']) else 25
                if len(df.columns)==2:width=34 if c==0 else 85
                widths.append(width);ws.set_column(c,c,width,body);ws.write(0,c,col,head)
            ws.set_row(0,34)
            for rr,row in enumerate(df.itertuples(index=False,name=None),1):
                height=20
                for c,value in enumerate(row):
                    col=str(df.columns[c]);fmt=money if any(x in col for x in ['Ingreso','Egreso','Credito','Debito','Neto']) else body
                    if value is None or (not isinstance(value,(list,dict)) and pd.isna(value)):ws.write_blank(rr,c,None,fmt);continue
                    if isinstance(value,(datetime,date,pd.Timestamp)):ws.write_datetime(rr,c,value,datefmt)
                    elif isinstance(value,bool):ws.write_boolean(rr,c,value,body)
                    elif isinstance(value,(int,float)):ws.write_number(rr,c,float(value),fmt)
                    else:
                        text=str(value);ws.write_string(rr,c,text,body)
                        height=max(height,15*sum(max(1,len(textwrap.wrap(line,width=max(8,int(widths[c]*.9)),break_long_words=True))) for line in text.split('\n'))+6)
                ws.set_row(rr,height)
            if len(df.columns):ws.autofilter(0,0,len(df),len(df.columns)-1)
            if 'Estado' in df.columns and len(df):
                c=df.columns.get_loc('Estado')
                for state in df.Estado.dropna().unique():
                    key='grey' if state in ['ARQUEO','ANULADO MAVERIC'] else 'yellow' if state in ['OK, check detalle','SIN REFERENCIA MAVERIC'] else 'green' if str(state).startswith('OK') or state=='TRASPASO OK' else 'red'
                    ws.conditional_format(1,c,len(df),c,{'type':'text','criteria':'containing','value':str(state),'format':colors[key]})
            if sn not in ['Resumen','Notas_Reglas','Control bolsas']:
                rr=len(df)+1;ws.write(rr,0,'TOTAL',totalfmt)
                for c,col in enumerate(df.columns):
                    if col in ['Maveric_Ingreso','Maveric_Egreso','Banco_Credito','Banco_Debito']:
                        from xlsxwriter.utility import xl_col_to_name
                        letter=xl_col_to_name(c);ws.write_formula(rr,c,f'=SUM({letter}2:{letter}{rr})',money,float(pd.to_numeric(df[col],errors='coerce').fillna(0).sum())) if len(df) else ws.write_number(rr,c,0,money)
    out.seek(0);dates=full.Maveric_Fecha
    stats={'filas':len(full),'ok':int(accepted.sum()),'revisar':len(review),'faltan_maveric':len(missing),'periodo':f'{min(dates):%Y%m%d}_a_{max(dates):%Y%m%d}'}
    return out,stats
