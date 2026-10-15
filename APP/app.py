import io, os, re, sys, json, uuid, platform, subprocess
from datetime import datetime, date
from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st
from reconciliation import reconcile

APP_VERSION = "2.1.0"
APP_DATE = "15/10/2026"
APP_NAME = "Conciliador Bancos - Maveric Sevens"
from sevens_ui import apply_design, header, sidebar_brand, sidebar_info, file_heading, footer
from sevens_paths import documents_folder, output_root
from sevens_migrate import migrate
st.set_page_config(page_title=APP_NAME, layout="wide", page_icon="💵", initial_sidebar_state="expanded")
migrate()
apply_design()
APP_DIR=Path(__file__).resolve().parent; ROOT_DIR=APP_DIR.parent; AUTH_FILE=ROOT_DIR/'authorized_machines.json'; ICON_PATH=APP_DIR/'assets'/'icon_sevens_bancos.png'
MONEDA_CFG={"Dólares":{"tokens":["USD","DOLARES","DÓLARES","DOLAR","DÓLAR"],"slug":"dolares"},"Pesos":{"tokens":["PESOS","UYU","URUGUAYOS"],"slug":"pesos"},"Euros":{"tokens":["EUROS","EUR"],"slug":"euros"}}
TOL=0.10

def docs_dir():
    p=Path.home()/"Documents"
    if not p.exists(): p=Path.home()/"Documentos"
    p.mkdir(exist_ok=True); return p

def out_base():
    return output_root()

def open_folder(path):
    try:
        path.mkdir(parents=True, exist_ok=True); s=platform.system().lower()
        if 'darwin' in s: subprocess.Popen(['open',str(path)])
        elif 'windows' in s: os.startfile(str(path))
        else: subprocess.Popen(['xdg-open',str(path)])
        return True
    except Exception: return False

def run_cmd(cmd):
    try: return subprocess.check_output(cmd,shell=True,stderr=subprocess.DEVNULL,text=True).strip()
    except Exception: return ""

def machine_id():
    s=platform.system().lower(); raw=""
    if 'darwin' in s: raw=run_cmd("ioreg -rd1 -c IOPlatformExpertDevice | awk -F'\\\"' '/IOPlatformUUID/{print $(NF-1)}'")
    elif 'windows' in s:
        raw=run_cmd('powershell -NoProfile -Command "(Get-CimInstance Win32_ComputerSystemProduct).UUID"') or run_cmd('wmic csproduct get uuid').replace('UUID','').strip()
    else: raw=run_cmd('cat /etc/machine-id')
    return (raw or str(uuid.getnode())).strip().upper()

def auth_cfg():
    default={"admin_ids":["00000000-0000-0000-0000-309C230BAEF1","86FE5326-6706-53D3-97C4-442452FDC186"],"allowed_ids":["00000000-0000-0000-0000-309C230BAEF1","86FE5326-6706-53D3-97C4-442452FDC186"],"labels":{"00000000-0000-0000-0000-309C230BAEF1":"TUKI PC","86FE5326-6706-53D3-97C4-442452FDC186":"Tuki Mac Admin"},"allow_unregistered":True}
    if not AUTH_FILE.exists(): AUTH_FILE.write_text(json.dumps(default,indent=2),encoding='utf-8')
    try: cfg=json.loads(AUTH_FILE.read_text(encoding='utf-8'))
    except Exception: cfg=default
    cfg.setdefault('labels',{}); cfg.setdefault('allow_unregistered',True); return cfg

def authorized():
    cfg=auth_cfg(); mid=machine_id(); return (mid in cfg.get('allowed_ids',[]) or cfg.get('allow_unregistered',True)), mid, cfg

def ensure_xlrd():
    try: import xlrd; return True
    except Exception:
        try: subprocess.check_call([sys.executable,'-m','pip','install','xlrd']); return True
        except Exception: return False

def norm(x):
    if pd.isna(x): return ""
    s=str(x).strip().upper();
    for a,b in {"ITAÚ":"ITAU","Ó":"O","Á":"A","É":"E","Í":"I","Ú":"U","Ñ":"N"}.items(): s=s.replace(a,b)
    return re.sub(r'\s+',' ',s)

def bank_aliases(banco):
    b = norm(banco)
    aliases = [b]
    if "SANTANDER" in b or "SANTADER" in b:
        aliases += ["SANTANDER", "SANTADER", "BANCO SANTANDER", "BANCO SANTADER"]
    if "ITAU" in b:
        aliases += ["ITAU", "ITAÚ", "BANCO ITAU", "BANCO ITAÚ"]
    if "BROU" in b or "REPUBLICA" in b:
        aliases += ["BROU", "BANCO REPUBLICA", "BANCO REPÚBLICA", "REPUBLICA", "REPÚBLICA"]
    if "HSBC" in b:
        aliases += ["HSBC", "BANCO HSBC"]
    if "BREX" in b:
        aliases += ["BREX"]
    if "MERCURY" in b:
        aliases += ["MERCURY", "MERCURY BANK"]
    out = []
    for a in aliases:
        na = norm(a)
        if na and na not in out:
            out.append(na)
    return out

def has_bank(text, banco):
    t = norm(text)
    return any(a in t for a in bank_aliases(banco))

def num(x):
    if pd.isna(x): return 0.0
    if isinstance(x,(int,float,np.integer,np.floating)): return 0.0 if pd.isna(x) else float(x)
    s=str(x).strip().replace('$','').replace('USD','').replace('UYU','').replace('EUR','').replace(' ','')
    if not s or s=='-': return 0.0
    if ',' in s and '.' in s: s=s.replace('.','').replace(',','.')
    elif ',' in s: s=s.replace(',','.')
    try: return float(s)
    except Exception: return 0.0

def amount_close(a,b): return abs(float(a or 0)-float(b or 0)) <= TOL

def parse_date(x):
    if pd.isna(x): return pd.NaT
    if isinstance(x,(pd.Timestamp,datetime,date)): dt=pd.to_datetime(x,errors='coerce')
    elif isinstance(x,str):
        s=x.strip()
        if not s or not re.search(r'\d{1,4}[-/]\d{1,2}[-/]\d{1,4}',s): return pd.NaT
        dt=pd.to_datetime(s,errors='coerce',dayfirst=True)
    else: return pd.NaT
    if pd.isna(dt) or dt.year<1900 or dt.year>2035: return pd.NaT
    return dt

def blank(row): return all(pd.isna(v) or str(v).strip()=='' for v in row.values)
def trash(row):
    t=norm(' '.join('' if pd.isna(v) else str(v) for v in row.values)); return 'TOTAL DE LA TRANSACCION' in t or 'BALANCE DEL PERIODO' in t

def read_excel(up, header=None):
    data=up.read(); up.seek(0); name=up.name.lower()
    if name.endswith('.xls'):
        ensure_xlrd(); return pd.read_excel(io.BytesIO(data),sheet_name=None,header=header,engine='xlrd')
    return pd.read_excel(io.BytesIO(data),sheet_name=None,header=header,engine='openpyxl')

def prettify_bank_folder_name(banco):
    b = norm(banco)
    if "SANTANDER" in b or "SANTADER" in b:
        return "Banco Santander"
    if "ITAU" in b:
        return "Banco Itau"
    if "BROU" in b or "REPUBLICA" in b:
        return "BROU"
    if "HSBC" in b:
        return "Banco HSBC"
    if "BREX" in b:
        return "Brex"
    if "MERCURY" in b:
        return "Mercury"
    if "BBVA" in b:
        return "BBVA"
    if "SCOTIABANK" in b:
        return "Scotiabank"
    clean = re.sub(r"[^A-Z0-9]+", " ", b).strip()
    return clean.title() if clean else "Banco"

def bank_slug_for_filename(banco):
    return re.sub(r"[^A-Za-z0-9]+", "_", prettify_bank_folder_name(banco)).strip("_")

def detect_bank(filename, manual=None):
    if manual and str(manual).strip():
        return norm(manual)
    f = norm(filename)
    known = [
        ("SANTANDER", ["SANTANDER", "SANTADER"]),
        ("ITAU", ["ITAU", "ITAÚ"]),
        ("BROU", ["BROU", "BANCO REPUBLICA", "BANCO REPÚBLICA", "REPUBLICA", "REPÚBLICA"]),
        ("HSBC", ["HSBC"]),
        ("BREX", ["BREX"]),
        ("MERCURY", ["MERCURY"]),
        ("BBVA", ["BBVA"]),
        ("SCOTIABANK", ["SCOTIABANK", "SCOTIA"]),
    ]
    for canonical, aliases in known:
        if any(norm(a) in f for a in aliases):
            return canonical
    base = Path(str(filename)).stem
    base = re.sub(r"\b(20\d{2}|\d{1,2}[-_]\d{1,2}|\d{1,2}[-_]\d{1,2}[-_]\d{2,4}|movimientos?|banco|bank|extracto|estado|cuenta|xls|xlsx)\b", " ", base, flags=re.I)
    base = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ]+", " ", base).strip()
    return norm(base) if base else "BANCO"
def filter_currency(sheets, moneda):
    toks=MONEDA_CFG[moneda]['tokens']; sel={k:v for k,v in sheets.items() if any(t in norm(k) for t in toks)}
    return sel or sheets

def valid_pair(i,e):
    i=num(i); e=num(e); return (abs(i)>0 and abs(e)==0) or (abs(e)>0 and abs(i)==0)

def prepare_mav(sheets):
    raw=sheets[list(sheets.keys())[0]]; raw=raw[~raw.apply(blank,axis=1)].copy(); dates=raw.iloc[:,0].apply(parse_date); mask=dates.notna() & (~raw.apply(trash,axis=1))
    df=raw.loc[mask].copy().reset_index(drop=True); dates=dates.loc[mask].reset_index(drop=True); out=pd.DataFrame(index=df.index)
    out['Maveric_Fecha']=pd.to_datetime(dates).dt.date
    out['Maveric Ref.']=df.iloc[:,1] if df.shape[1]>1 else ''
    out['Maveric_Origen']=df.iloc[:,2] if df.shape[1]>2 else ''
    out['Maveric_Destino']=df.iloc[:,3] if df.shape[1]>3 else ''
    out['Maveric Cliente/Proveedor']=df.iloc[:,4] if df.shape[1]>4 else ''
    out['Maveric Detalle']=df.iloc[:,5] if df.shape[1]>5 else ''
    out['Maveric_Ingreso']=df.iloc[:,6].apply(num) if df.shape[1]>6 else 0.0
    out['Maveric_Egreso']=df.iloc[:,7].apply(num) if df.shape[1]>7 else 0.0
    out['Maveric_Texto_Busqueda']=(out['Maveric Ref.'].astype(str)+' '+out['Maveric Cliente/Proveedor'].astype(str)+' '+out['Maveric Detalle'].astype(str)).map(norm)
    out['Par_Ingreso_Egreso_Valido']=out.apply(lambda r: valid_pair(r['Maveric_Ingreso'],r['Maveric_Egreso']),axis=1)
    return out.reset_index(drop=True)

def prepare_bank(sheets):
    arr=[]
    for sh, raw in sheets.items():
        raw=raw[~raw.apply(blank,axis=1)].copy()
        if raw.empty or raw.shape[1]<7: continue
        dates=raw.iloc[:,0].apply(parse_date); mask=dates.notna() & (~raw.apply(trash,axis=1)); df=raw.loc[mask].copy().reset_index(drop=True); dates=dates.loc[mask].reset_index(drop=True)
        if df.empty: continue
        out=pd.DataFrame(index=df.index); out['Banco_Hoja']=sh; out['Banco_Fecha']=pd.to_datetime(dates).dt.date
        out['Banco_Cheque_Ref']=df.iloc[:,1] if df.shape[1]>1 else ''; out['Banco_Movimiento']=df.iloc[:,2] if df.shape[1]>2 else ''; out['Banco_Detalle']=df.iloc[:,3] if df.shape[1]>3 else ''
        out['Banco_Debito']=df.iloc[:,5].apply(num) if df.shape[1]>5 else 0.0; out['Banco_Credito']=df.iloc[:,6].apply(num) if df.shape[1]>6 else 0.0
        out['Banco_Texto_Busqueda']=(out['Banco_Cheque_Ref'].astype(str)+' '+out['Banco_Movimiento'].astype(str)+' '+out['Banco_Detalle'].astype(str)).map(norm)
        arr.append(out)
    return pd.concat(arr,ignore_index=True) if arr else pd.DataFrame()

def words(s): return [w for w in re.split(r'[^A-Z0-9]+',norm(s)) if w]

def compact_alnum(x):
    return re.sub(r'[^A-Z0-9]', '', norm(x))

def reference_candidates(x):
    """Referencias/cheques comparables, ignorando espacios, guiones y puntuación."""
    raw = norm(x)
    vals = set()
    compact = compact_alnum(raw)
    if len(compact) >= 4 and any(ch.isdigit() for ch in compact):
        vals.add(compact)
    for token in re.findall(r'[A-Z0-9][A-Z0-9 ._/-]*[A-Z0-9]', raw):
        c = compact_alnum(token)
        if len(c) >= 4 and any(ch.isdigit() for ch in c):
            vals.add(c)
    for token in re.findall(r'[A-Z0-9]+', raw):
        if len(token) >= 4 and any(ch.isdigit() for ch in token):
            vals.add(token)
    return sorted(vals, key=len, reverse=True)

def reference_match(a, b):
    aa = reference_candidates(a)
    bb = reference_candidates(b)
    for x in aa:
        for y in bb:
            if x == y or (len(x) >= 4 and x in y) or (len(y) >= 4 and y in x):
                return True
    return False

def is_profit_distribution_text(x):
    c = compact_alnum(x)
    return ('DISTRIBUCIONDEUTILIDADES' in c or
            'DISTRICUCIONDEUTILIDADES' in c or
            ('DISTRIBUCION' in c and 'UTILIDADES' in c) or
            ('DISTRICUCION' in c and 'UTILIDADES' in c))

def row_contains_annulled(row):
    """
    Detecta anulaciones en cualquier campo.
    Acepta, entre otras variantes:
    ANULADO, ANULADA, ANULACION, ANULACIÓN, ANULA, ANULACION DE MOV.
    """
    try:
        values = row.to_dict().values()
    except Exception:
        values = row.values() if hasattr(row, 'values') else [row]

    for value in values:
        text = norm(value)
        compact = re.sub(r'[^A-Z0-9]+', '', text)
        if (
            'ANULADO' in compact
            or 'ANULADA' in compact
            or 'ANULACION' in compact
            or 'ANULAMIENTO' in compact
            or compact.startswith('ANULA')
            or ' ANULA' in f' {text}'
        ):
            return True
    return False
def text_match(mt,bt):
    mt=norm(mt); bt=norm(bt)
    if 'SEVENS TRAVEL' in mt and 'IATA' in bt: return True
    # Regla especial: Distribución de Utilidades puede estar en Detalle o Referencia,
    # y se acepta coincidencia o contenido en cualquiera de los dos sentidos.
    if is_profit_distribution_text(mt) and is_profit_distribution_text(bt): return True
    if reference_match(mt, bt): return True
    stop={'EFECTIVO','BANCO','ITAU','PAGO','TRANSFERENCIA','GASTOS','GASTO','CH','SA','SAS','SRL','LTDA','CLIENTES','PROVEEDORES'}
    ww=[w for w in re.split(r'[^A-Z0-9]+',mt) if len(w)>=4 and w not in stop]
    return any(w in bt for w in ww) or mt in bt or bt in mt

def same_date(a,b):
    da=pd.to_datetime(a,errors='coerce'); db=pd.to_datetime(b,errors='coerce'); return not pd.isna(da) and not pd.isna(db) and da.date()==db.date()
def mov_tokens(x): return reference_candidates(x)
def is_tarjeta_mav(r):
    tc_words=words(r.get('Maveric Cliente/Proveedor',''))
    txt = norm(r.get('Maveric Detalle','')) + ' ' + norm(r.get('Maveric Cliente/Proveedor','')) + ' ' + norm(r.get('Maveric_Origen',''))
    return (
        'TRJ' in txt
        or 'TARJETAS' in txt
        or ' AMEX ' in f' {txt} '
        or 'CRED DIRECTOOCA' in txt
        or 'CRED.DIRECTOOCA' in txt
        or 'OCA S.A' in txt
        or 'OCA SA' in txt
        or 'TC' in tc_words
    )
def is_bank_tarj(r):
    t=norm(r.get('Banco_Texto_Busqueda',''))
    if 'TARJETA CELESTE' in t:
        return False
    return (
        'TRJ' in t
        or 'TARJETA' in t
        or 'TARJETAS' in t
        or ' AMEX ' in f' {t} '
        or 'CRED DIRECTOOCA' in t
        or 'CRED.DIRECTOOCA' in t
        or 'OCA S.A' in t
        or 'OCA SA' in t
        or ' TC ' in f' {t} '
    )
def is_bank_prov(r):
    t=norm(r.get('Banco_Texto_Busqueda','')); return 'PROVEEDOR' in t or 'PROVEEDORES' in t or 'PAGO' in t

def is_bank_gasto(r):
    t=norm(r.get('Banco_Texto_Busqueda',''))
    return 'GASTO BANCARIO' in t or 'GASTOS BANCARIOS' in t
def is_gasto(r):
    t=norm(r.get('Maveric_Destino',''))+' '+norm(r.get('Maveric Cliente/Proveedor',''))+' '+norm(r.get('Maveric Detalle',''))
    return 'GASTO BANCARIO' in t or 'GASTOS BANCARIOS' in t

def classify(mav, bank, banco):
    return reconcile(mav, bank, banco)

def order_cols(df):
    cols=['Maveric_Fecha','Maveric Ref.','Maveric_Origen','Maveric_Destino','Maveric Cliente/Proveedor','Maveric Detalle','Banco_Detalle','Maveric_Ingreso','Banco_Credito','Maveric_Egreso','Banco_Debito','Estado','Fecha en Bancos','Motivo','Tipo','Es_Tarjeta','Es_Pago_Proveedor','Es_Gasto_Bancario','Banco_Hoja','Banco_Fecha','Banco_Cheque_Ref','Banco_Movimiento','Par_Ingreso_Egreso_Valido']
    return df[[c for c in cols if c in df.columns]].copy()
def total(df):
    df=df.copy()
    if df.empty: return df
    row={c:'' for c in df.columns}; row[df.columns[0]]='TOTAL'
    for c in ['Maveric_Ingreso','Maveric_Egreso','Banco_Debito','Banco_Credito']:
        if c in df.columns: row[c]=pd.to_numeric(df[c],errors='coerce').fillna(0).sum()
    return pd.concat([df,pd.DataFrame([row])],ignore_index=True)
def periodo_lindo(stats):
    meses={1:'ene',2:'feb',3:'mar',4:'abr',5:'may',6:'jun',7:'jul',8:'ago',9:'sep',10:'oct',11:'nov',12:'dic'}; raw=str(stats.get('periodo') or stats.get('rango') or ''); nums=re.findall(r'(20\d{2})[-]?(\d{2})[-]?(\d{2})',raw)
    if len(nums)>=2:
        y1,m1,d1=map(int,nums[0]); y2,m2,d2=map(int,nums[1]); return f'{d1}-{d2}_{meses.get(m1,m1)}_{y1}' if y1==y2 and m1==m2 else f'{d1}_{meses.get(m1,m1)}_{y1}_a_{d2}_{meses.get(m2,m2)}_{y2}'
    return raw.replace(' ','_').replace(':','').replace('/','-')
def bank_side(bank, cat, used=None):
    if bank.empty: return pd.DataFrame()
    used = used or set()
    out=[]
    for idx,r in bank.iterrows():
        if idx in used:
            continue
        if cat=='tarjetas' and is_bank_tarj(r):
            rr=r.to_dict(); rr['Origen']='Banco'; rr['Estado']='Banco no usado en Maveric'; out.append(rr)
        if cat=='proveedores' and is_bank_prov(r) and not is_bank_gasto(r) and not is_bank_tarj(r):
            rr=r.to_dict(); rr['Origen']='Banco'; rr['Estado']='Banco no usado en Maveric'; out.append(rr)
        if cat=='gastos' and is_bank_gasto(r):
            rr=r.to_dict(); rr['Origen']='Banco'; rr['Estado']='Banco no usado en Maveric'; out.append(rr)
    return pd.DataFrame(out)

def bank_matches_any_maveric(br, full):
    btxt = br.get('Banco_Texto_Busqueda','')
    bdeb = num(br.get('Banco_Debito',0))
    bcre = num(br.get('Banco_Credito',0))
    for _, mr in full.iterrows():
        mtxt = mr.get('Maveric_Texto_Busqueda','')
        ming = num(mr.get('Maveric_Ingreso',0))
        megr = num(mr.get('Maveric_Egreso',0))
        amount_ok = (abs(bcre)>0 and amount_close(bcre, ming)) or (abs(bdeb)>0 and amount_close(bdeb, megr))
        if amount_ok and text_match(mtxt, btxt):
            return True
    return False

def build_excel(full, bank, bank_rango, used, banco, moneda):
    from excel_output import export_excel
    return export_excel(full, bank, bank_rango, used, banco, moneda, APP_VERSION, order_cols, is_bank_tarj, is_bank_prov, is_bank_gasto)

def run(banco_file,mav_file,banco_manual,moneda):
    bs=filter_currency(read_excel(banco_file,header=None),moneda); ms=read_excel(mav_file,header=None); banco=detect_bank(banco_file.name,banco_manual); mav=prepare_mav(ms); bank=prepare_bank(bs)
    if mav.empty: raise ValueError('No encontré movimientos válidos en Maveric.')
    d=pd.to_datetime(mav['Maveric_Fecha'],errors='coerce'); mind=d.min().date(); maxd=d.max().date(); bank_rango=bank[(bank['Banco_Fecha']>=mind)&(bank['Banco_Fecha']<=maxd)].copy() if not bank.empty else pd.DataFrame()
    full,used=classify(mav,bank,banco); excel,stats=build_excel(full,bank,bank_rango,used,banco,moneda); return excel,stats,banco

def save_copy(excel, filename, periodo, banco=None):
    folder = prettify_bank_folder_name(banco or "Banco")
    p = out_base()/folder/str(periodo)
    p.mkdir(parents=True,exist_ok=True)
    f = p/filename
    f.write_bytes(excel.getvalue())
    return f

ok, mid, cfg=authorized()
if not ok: st.error('Este equipo no está autorizado.'); st.stop()
with st.sidebar:
    sidebar_brand('Bancos')
    if st.button('Abrir carpeta de conciliaciones', icon=':material/folder_open:',use_container_width=True,key='abrir_carpeta'):
        open_folder(out_base())
    sidebar_info(cfg.get('labels',{}).get(mid,'Equipo no identificado'),APP_VERSION,APP_DATE)
    if st.button('Cerrar aplicación',icon=':material/power_settings_new:',use_container_width=True,key='cerrar_aplicacion'):
        os._exit(0)
header('Bancos','Compará los movimientos del banco con registros de  Maveric.')
st.markdown('<h2 class="sevens-section-title">Cargar archivos</h2>',unsafe_allow_html=True)
c1,c2=st.columns(2,gap='medium')
with c1:
    with st.container(border=True,key='upload_banco'):
        file_heading('Subir Excel del banco')
        banco_file=st.file_uploader('Subir Excel del banco',type=['xlsx','xls'],key='banco',label_visibility='collapsed')
with c2:
    with st.container(border=True,key='upload_maveric'):
        file_heading('Subir Excel de Bancos Maveric')
        mav_file=st.file_uploader('Subir Excel de Bancos Maveric',type=['xlsx','xls'],key='mav',label_visibility='collapsed')
banco_manual=''
with st.container(border=True):
    moneda=st.selectbox('Moneda',['Dólares','Pesos','Euros'],index=0)
if st.button('GENERAR CONCILIACIÓN',type='primary',icon=':material/fact_check:',use_container_width=True,key='generar_conciliacion',disabled=not(banco_file and mav_file)):
    try:
        with st.spinner('Conciliando archivos...'):
            excel,stats,banco=run(banco_file,mav_file,banco_manual,moneda)
            now=datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')
            moneda_slug=MONEDA_CFG[moneda]['slug']
            fname=f"Conciliacion_Bancos_{bank_slug_for_filename(banco)}_{moneda_slug}_{stats['periodo']}_{now}.xlsx"
            saved=save_copy(excel,fname,stats['periodo'],banco)
        a,b,c,d=st.columns(4)
        a.metric('Movimientos',stats['filas']);b.metric('OK en BANCOS',stats['ok']);c.metric('Revisar',stats['revisar']);d.metric('Faltan en Maveric',stats['faltan_maveric'])
        st.success(f'Archivo guardado en: {saved}')
        st.download_button('Descargar Excel conciliado',data=excel,file_name=fname,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e: st.error(f'No pude generar la conciliación: {e}')
footer()
