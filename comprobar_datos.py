"""Comprueba el catálogo y los perfiles reales después de generar el ejemplo."""
import argparse,copy,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
import metpy.calc as mp
from metpy.units import units
from generar import franjas,validar_cache
from indices import calcular
p=argparse.ArgumentParser();p.add_argument('--sitio',default='ejemplo');p.add_argument('--cache',default='.cache-puntos');args=p.parse_args()
UTC=timezone.utc
run=datetime(2026,11,2,6,tzinfo=UTC)
assert franjas(datetime(2026,11,2,20,59,tzinfo=UTC),run)==[12,15,18,21,24]
assert franjas(datetime(2026,11,2,21,tzinfo=UTC),run)==[15,18,21,24,27]
assert franjas(datetime(2026,11,3,0,tzinfo=UTC),run)==[18,21,24,27,30]
cat=json.loads((Path(args.sitio)/'catalogo.json').read_text());assert cat['spacing_degrees']==.1
valids=[datetime.fromisoformat(x['valid_utc'].replace('Z','+00:00')) for x in cat['profiles']]
assert len(valids)==5 and all((b-a)==timedelta(hours=3) for a,b in zip(valids,valids[1:]))
for record in cat['profiles']:
    dt=datetime.fromisoformat(record['run_utc'].replace('Z','+00:00'));step=record['step_hours'];key=dt.strftime('%Y%m%dT%HZ')+f'_{step:03d}h'
    doc=json.loads((Path(args.cache)/(key+'.json')).read_text());a,meta=validar_cache(doc,dt,step)
    assert abs(meta['lat']-36.2)<1e-5 and abs(meta['lon']+5.3)<1e-5
    assert 5<meta['distance_km']<6
    pp=a[:,0]/100*units.hPa;t=(a[:,2]-273.15)*units.degC;td=(a[:,3]-273.15)*units.degC
    idx=calcular(a)
    assert idx==record['indices']
    for k,func in [('surface',mp.surface_based_cape_cin),('mixed_100hpa',mp.mixed_layer_cape_cin),('unstable_300hpa',mp.most_unstable_cape_cin)]:
        cape,cin=func(pp,t,td)
        assert np.isclose(cape.m,idx[k]['cape_jkg'],atol=.01)
    for name in ['sondeo.png','sondeo.json','interpretacion.txt','perfil.csv']:assert (Path(args.sitio)/record['path']/name).is_file()
    bad=copy.deepcopy(doc);bad['meta']['spacing_degrees']=.25
    try:validar_cache(bad,dt,step)
    except ValueError:pass
    else:raise AssertionError('Se ha aceptado una malla equivocada.')
print('Cinco perfiles reales: resolución, punto, horas válidas, índices de tres parcelas y archivos comprobados.')
