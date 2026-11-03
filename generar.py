"""Actualiza perfiles ECMWF IFS 0,1° cada tres horas y publica un catálogo horario."""
import argparse, contextlib, hashlib, json, logging, shutil, tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from perfil import leer,construir,producto,LEVELS,LAT,LON
UTC=timezone.utc
SCHEMA=2

def iso(d):return d.astimezone(UTC).isoformat().replace('+00:00','Z')
def floor3(d):return d.astimezone(UTC).replace(hour=d.astimezone(UTC).hour//3*3,minute=0,second=0,microsecond=0)
def franjas(now,run,horizonte=12):
    start=floor3(now)
    if run>start:raise ValueError('Pasada posterior a la franja actual.')
    steps=[int((start+timedelta(hours=h)-run).total_seconds()/3600) for h in range(0,horizonte+1,3)]
    if any(s<0 or s>144 or s%3 for s in steps):raise ValueError('Plazos incompatibles con la salida trihoraria.')
    return steps

def compactar(pl,sfc,terreno,destino,source):
    x,m=leer(pl);s,sm=leer(sfc);z,zm=leer(terreno)
    if m!=sm:raise ValueError('Fechas o puntos distintos entre superficie y altura.')
    if any(m[k]!=zm[k] for k in ['lat','lon','date','time','spacing_degrees']):raise ValueError('Terreno de otra pasada o malla.')
    valid=datetime.strptime(str(m['valid_date'])+f"{m['valid_time']:04d}",'%Y%m%d%H%M').replace(tzinfo=UTC)
    run=datetime.strptime(str(m['date'])+f"{m['time']:04d}",'%Y%m%d%H%M').replace(tzinfo=UTC)
    if run+timedelta(hours=m['step'])!=valid:raise ValueError('Hora válida incoherente.')
    a,meta=construir(x,s,z,m)
    doc={'schema':SCHEMA,'source':source,'requested_lat':LAT,'requested_lon':LON,'meta':meta,'run_utc':iso(run),'valid_utc':iso(valid),'array':a.tolist(),'downloaded_at_utc':iso(datetime.now(UTC)),
         'raw_sha256':{key:hashlib.sha256(Path(path).read_bytes()).hexdigest() for key,path in [('pl',pl),('sfc',sfc),('terrain',terreno)]}}
    destino.parent.mkdir(parents=True,exist_ok=True)
    destino.write_text(json.dumps(doc,ensure_ascii=False,allow_nan=False))
    return doc

def validar_cache(doc,run,step):
    import numpy as np
    if doc['schema']!=SCHEMA or doc['requested_lat']!=LAT or doc['requested_lon']!=LON:raise ValueError('Caché de otra configuración.')
    if doc['run_utc']!=iso(run) or doc['valid_utc']!=iso(run+timedelta(hours=step)):raise ValueError('Caché de otro plazo.')
    a=np.asarray(doc['array'],dtype=float);m=doc['meta']
    if a.ndim!=2 or a.shape[1]!=6 or a.shape[0]<10 or not np.isfinite(a).all():raise ValueError('Datos de caché incompletos.')
    if not np.all(np.diff(a[:,0])<0) or not np.all(np.diff(a[:,1])>0):raise ValueError('Perfil de caché desordenado.')
    if abs(m['spacing_degrees']-.1)>1e-6 or m['step']!=step:raise ValueError('Resolución o plazo incorrectos.')
    if np.any(a[:,3]>a[:,2]):raise ValueError('Rocío incompatible con temperatura.')
    return a,m

def generar(out,cache,source='ecmwf',now=None,run=None,offline=False,horizonte=12):
    from ecmwf.opendata import Client
    now=now or datetime.now(UTC);out=out.resolve();cache=cache.resolve();cache.mkdir(parents=True,exist_ok=True)
    client=None
    if not offline:
        client=Client(source=source,resol='0p1',maximum_retries=3,retry_after=5,use_server_retry_after=False)
        if run is None:run=client.latest(type='fc',step=24,param='t',levtype='pl').replace(tzinfo=UTC)
    if run is None:raise ValueError('En modo sin descarga debes indicar --pasada.')
    run=run.astimezone(UTC)
    if now-run>timedelta(hours=30) or run>now:raise ValueError('La pasada no es reciente o es futura.')
    steps=franjas(now,run,horizonte)
    print('Pasada:',iso(run),'plazos:',steps,flush=True)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.sondeo-',dir=out.parent) as tmp:
        tmp=Path(tmp);staging=tmp/'site';staging.mkdir();work=tmp/'grib';work.mkdir()
        # El terreno es estático dentro de la pasada; se descarga una sola vez si hace falta.
        terrain=work/'terreno.grib2';records=[]
        for step in steps:
            key=run.strftime('%Y%m%dT%HZ')+f'_{step:03d}h';point=cache/(key+'.json');doc=None
            if point.exists():
                try:doc=json.loads(point.read_text());validar_cache(doc,run,step)
                except (ValueError,KeyError,TypeError):doc=None
            if doc is None:
                if offline:raise ValueError('No hay datos reales guardados para '+key)
                if not terrain.exists():client.retrieve(date=run.strftime('%Y%m%d'),time=run.hour,type='fc',step=0,levtype='sfc',param='z',target=str(terrain))
                common=dict(date=run.strftime('%Y%m%d'),time=run.hour,type='fc',step=step)
                pl=work/'perfil.grib2';sfc=work/'superficie.grib2'
                client.retrieve(**common,levtype='pl',param=['t','r','u','v','gh'],levelist=LEVELS,target=str(pl))
                client.retrieve(**common,levtype='sfc',param=['sp','2t','2d','10u','10v'],target=str(sfc))
                doc=compactar(pl,sfc,terrain,point,source)
                pl.unlink();sfc.unlink()
            a,meta=validar_cache(doc,run,step)
            relative=Path('perfiles')/key
            res=producto(a,meta,staging/relative)
            records.append(dict(res,path=relative.as_posix()))
            print('Generado',doc['valid_utc'],'punto:',meta['lat'],meta['lon'],flush=True)
        manifest={'schema':SCHEMA,'generated_at_utc':iso(datetime.now(UTC)),'spacing_degrees':.1,'interval_hours':3,'profiles':records}
        if not any(datetime.fromisoformat(r['valid_utc'].replace('Z','+00:00'))<=now for r in records):raise ValueError('No hay ningún perfil para la franja actual.')
        (staging/'catalogo.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False))
        web=Path(__file__).parent/'web'
        for p in web.iterdir():
            if p.is_file():shutil.copy2(p,staging/p.name)
        # La publicación solo se hace después de completar todos los perfiles.
        if out.exists():shutil.rmtree(out)
        shutil.move(str(staging),out)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--salida',default='_site');p.add_argument('--cache',default='.cache-puntos')
    p.add_argument('--source',default='ecmwf',choices=['ecmwf','aws','google'])
    p.add_argument('--sin-descarga',action='store_true');p.add_argument('--ahora',help='Solo para reproducir ejemplos: ISO UTC')
    p.add_argument('--pasada',help='ISO UTC; en producción se consulta la última disponible')
    p.add_argument('--horizonte',type=int,default=12,choices=[6,12,24])
    a=p.parse_args()
    dt=lambda s:datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(UTC) if s else None
    if a.ahora and not a.sin_descarga:p.error('--ahora solo está permitido con --sin-descarga')
    generar(Path(a.salida),Path(a.cache),a.source,dt(a.ahora),dt(a.pasada),a.sin_descarga,a.horizonte)
