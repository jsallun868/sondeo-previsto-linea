"""Sondeo previsto ECMWF IFS para el entorno de La Línea; sin claves ni IA."""
import argparse, json, math
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import eccodes as ec
import metpy.calc as mp
from metpy.units import units
from indices import calcular

LAT,LON=36.17,-5.35
LEVELS=[1000,925,850,700,600,500,400,300,250,200,150,100]

def leer(path):
    out={};meta=None
    with open(path,'rb') as f:
        while (h:=ec.codes_grib_new_from_file(f)) is not None:
            try:
                q=ec.codes_grib_find_nearest(h,LAT,LON)[0]
                m={'spacing_degrees':float(ec.codes_get(h,'iDirectionIncrementInDegrees')),'lat':q['lat'],'lon':q['lon'],'distance_km':q['distance'],'date':ec.codes_get(h,'dataDate'),'time':ec.codes_get(h,'dataTime'),'step':ec.codes_get(h,'endStep'),'valid_date':ec.codes_get(h,'validityDate'),'valid_time':ec.codes_get(h,'validityTime')}
                if meta is not None and m!=meta:raise ValueError('Campos con fechas o puntos de malla distintos.')
                meta=m
                out[(ec.codes_get(h,'shortName'),ec.codes_get(h,'level'))]=q['value']
            finally:ec.codes_release(h)
    if not out:raise ValueError('GRIB vacío.')
    if not math.isclose(meta['spacing_degrees'],.1,abs_tol=1e-6):raise ValueError('Se exige malla real de 0,1 grados.')
    return out,meta

def construir(pl,sfc,terrain,meta):
    s={k:v for (k,_),v in sfc.items()}
    p0=s['sp'];z0=terrain['z',0]/9.80665
    rows=[[p0,z0+2,s['2t'],min(s['2d'],s['2t']),float(mp.wind_direction(s['10u']*units('m/s'),s['10v']*units('m/s')).m),math.hypot(s['10u'],s['10v'])]]
    for p in LEVELS:
        if p*100>=p0:continue
        t=pl['t',p];rh=np.clip(pl['r',p],.001,100)
        td=float(mp.dewpoint_from_relative_humidity(t*units.K,rh/100).to('kelvin').m)
        u,v=pl['u',p],pl['v',p]
        if pl['gh',p]<=z0+2:continue
        rows.append([p*100,pl['gh',p],t,min(t,td),float(mp.wind_direction(u*units('m/s'),v*units('m/s')).m),math.hypot(u,v)])
    a=np.array(rows)
    if len(a)<10 or not np.isfinite(a).all() or np.any(np.diff(a[:,1])<=0):raise ValueError('Perfil incompleto o incoherente.')
    meta=dict(meta,terrain_m=z0)
    return a,meta


def f(x,n=0):return '—' if x is None else f'{x:.{n}f}'.replace('.',',')

def producto(a,meta,out):
    idx=calcular(a)
    p=a[:,0]/100*units.hPa;t=(a[:,2]-273.15)*units.degC;td=(a[:,3]-273.15)*units.degC
    parcel=mp.parcel_profile(p,t[0],td[0]);rh=mp.relative_humidity_from_dewpoint(t,td).m*100
    keys=['surface','mixed_100hpa','unstable_300hpa'];names=['cerca de superficie','capa mezclada de 100 hPa','parcela más inestable de los 300 hPa inferiores']
    caps=[idx[k]['cape_jkg'] for k in keys if idx[k]]
    text='CAPE: '+ '; '.join(n+': '+f(idx[k]['cape_jkg'])+' J/kg' for k,n in zip(keys,names) if idx[k])+'. '
    text+=('No aparece energía positiva para estas parcelas en el perfil previsto. Esto no descarta lluvia ni cambios posteriores.' if max(caps)<1 else 'Hay energía disponible para algunas ascendencias. Por sí sola no indica que vaya a haber tormentas: también importan el disparo y la inhibición.')
    sections=[('Estabilidad y convección',text)]
    humidity=[]
    for h in [850,700,500]:
        i=np.where(np.isclose(p.m,h))[0]
        if len(i):humidity.append(f'{h} hPa (unos {f(a[i[0],1]/1000,1)} km): {f(rh[i[0]])} %')
    sections.append(('Humedad en altura','Humedad relativa prevista a '+ '; '.join(humidity)+'. Valores altos son compatibles con nubosidad, pero no la confirman por sí solos.'))
    inv=[(a[i,1],a[i+1,1],a[i+1,2]-a[i,2]) for i in range(len(a)-1) if a[i,1]<5000 and a[i+1,1]<=5000 and a[i+1,2]-a[i,2]>=.5]
    sections.append(('Capas que pueden frenar las ascendencias',('La temperatura aumenta entre '+ '; '.join(f'{f(lo)} y {f(hi)} m (+{f(dt,1)} °C)' for lo,hi,dt in inv)+'. Esa estabilidad puede dificultar la mezcla vertical.' if inv else 'No se aprecia un aumento térmico de al menos 0,5 °C entre los niveles disponibles por debajo de 5 km. La separación entre niveles impide descartar inversiones más finas.')))
    wind=[];dirs=['norte','noreste','este','sureste','sur','suroeste','oeste','noroeste']
    for h in [850,500,300]:
        i=np.where(np.isclose(p.m,h))[0]
        if len(i):
            r=a[i[0]];wind.append(f'{h} hPa: del {dirs[int((r[4]+22.5)//45)%8]} a unos {f(r[5]*3.6)} km/h')
    sections.append(('Viento en altura','; '.join(wind)+'. Las barbas del diagrama muestran el viento en nudos.'))
    run=datetime.strptime(str(meta['date'])+f"{meta['time']:04d}",'%Y%m%d%H%M');valid=datetime.strptime(str(meta['valid_date'])+f"{meta['valid_time']:04d}",'%Y%m%d%H%M')
    note=f"Perfil previsto IFS en el punto de malla {meta['lat']:.2f}°, {meta['lon']:.2f}°, a {meta['distance_km']:.1f} km del punto solicitado de La Línea (36,17°, −5,35°). Malla 0,1°. {len(a)-1} niveles de presión y condiciones próximas a superficie. Los índices se recalculan con este perfil reducido y pueden diferir de los del modelo completo. Alturas sobre el nivel del mar; terreno del modelo: {f(meta['terrain_m'])} m. Temperatura y rocío iniciales a 2 m; viento inicial a 10 m."
    res={'source':'ECMWF Open Data · IFS · CC BY 4.0','run_utc':run.isoformat()+'Z','valid_utc':valid.isoformat()+'Z','step_hours':meta['step'],'grid':meta,'indices':idx,'sections':[{'title':x,'text':y} for x,y in sections],'note':note,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'method':'Reglas meteorológicas deterministas; sin IA.'}
    out.mkdir(exist_ok=True,parents=True)
    (out/'sondeo.json').write_text(json.dumps(res,ensure_ascii=False,indent=2,allow_nan=False))
    (out/'interpretacion.txt').write_text('SONDEO PREVISTO · LA LÍNEA\nPasada: '+str(run)+' UTC\nVálido: '+str(valid)+' UTC\n\n'+'\n\n'.join(x+': '+y for x,y in sections)+'\n\n'+note+'\nFuente: '+res['source']+'\n'+res['method'])
    np.savetxt(out/'perfil.csv',np.column_stack([a[:,0]/100,a[:,1],a[:,2]-273.15,a[:,3]-273.15,a[:,4],a[:,5],rh]),delimiter=',',header='pressure_hpa,height_m_asl,temperature_c,dewpoint_c,wind_direction_deg,wind_speed_ms,rh_percent',comments='')
    dibujar(a,parcel,res,out/'sondeo.png')
    return res

def dibujar(a,parcel,res,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from metpy.plots import SkewT,Hodograph
    import textwrap
    fig=plt.figure(figsize=(15,15),facecolor='#fff8df');col='#473b2a'
    fig.text(.06,.96,'SONDEO PREVISTO · LA LÍNEA',fontsize=23,weight='bold',color=col)
    valid=datetime.fromisoformat(res['valid_utc'].replace('Z','+00:00'));run=datetime.fromisoformat(res['run_utc'].replace('Z','+00:00'))
    fig.text(.06,.932,'Válido: '+valid.strftime('%d/%m/%Y · %H:%M UTC')+ '   |   ECMWF IFS · +'+str(res['step_hours'])+' h',fontsize=14,color=col)
    fig.text(.06,.911,'Pasada: '+run.strftime('%d/%m/%Y · %H:%M UTC')+'   |   Perfil del punto de malla próximo a la ciudad',fontsize=11,color=col)
    sk=SkewT(fig,rotation=45,rect=[.075,.39,.58,.48]);sk.ax.set_facecolor('#fffdf6');p=a[:,0]/100*units.hPa
    sk.plot(p,(a[:,2]-273.15)*units.degC,color='#d23837',lw=2,marker='.',label='Temperatura')
    sk.plot(p,(a[:,3]-273.15)*units.degC,color='#188258',lw=2,marker='.',label='Punto de rocío')
    sk.plot(p,parcel.to('degC'),color='#6b4c9a',ls='--',label='Parcela próxima a superficie')
    sk.ax.set_ylim(1050,100);sk.ax.set_xlim(-40,40);sk.ax.set_xlabel('Temperatura (°C)');sk.ax.set_ylabel('Presión (hPa)');sk.ax.grid(alpha=.35)
    sk.plot_dry_adiabats(alpha=.2,colors='#b58466');sk.plot_moist_adiabats(alpha=.2,colors='#598d7c');sk.plot_mixing_lines(alpha=.2,colors='#7d9972')
    u,v=mp.wind_components(a[:,5]*units('m/s'),a[:,4]*units.deg);sk.plot_barbs(p,u.to('knots'),v.to('knots'),length=5);sk.ax.legend(fontsize=9,loc='upper left')
    ax=fig.add_axes([.73,.69,.23,.18]);hod=Hodograph(ax,component_range=max(15,math.ceil(np.max(abs(np.r_[u.m,v.m]))/5)*5));hod.add_grid(increment=5,alpha=.2);hod.plot_colormapped(u,v,a[:,1]/1000,cmap='viridis');ax.set_title('Hodógrafa · m/s',fontsize=12)
    idx=res['indices'];rows=[]
    for title,key in [('CAPE (J/kg)','cape_jkg'),('CIN (J/kg)','cin_jkg'),('LCL (hPa)','lcl_hpa'),('LFC (hPa)','lfc_hpa'),('EL (hPa)','el_hpa')]:rows.append([title]+[f(idx[k][key],1) if idx[k] else '—' for k in ['surface','mixed_100hpa','unstable_300hpa']])
    ax=fig.add_axes([.71,.47,.27,.14]);ax.axis('off');tab=ax.table(cellText=rows,colLabels=['Índice','Sup.*','ML 100','MU 300'],loc='center',cellLoc='center',colWidths=[.37,.21,.21,.21]);tab.auto_set_font_size(False);tab.set_fontsize(9);tab.scale(1,1.7)
    for (r,c),cell in tab.get_celld().items():cell.set_facecolor('#f2e5bd' if r==0 else '#fffdf6');cell.set_edgecolor('#d8cda9')
    fig.text(.72,.44,'LI cerca de superficie: '+f(idx['surface']['li_c'],1)+' °C',fontsize=11)
    fig.text(.72,.42,'K: '+f(idx['k_c'],1)+' °C   |   TT: '+f(idx['total_totals_c'],1)+' °C',fontsize=11)
    fig.text(.72,.398,'* Parcela con T y rocío a 2 m.',fontsize=9)
    fig.text(.72,.38,'—: no existe / no aplicable / sin datos',fontsize=8.5)
    fig.text(.06,.335,'INTERPRETACIÓN DEL PERFIL PREVISTO',fontsize=17,weight='bold',color=col)
    y=.306
    for sec in res['sections']:
        wrapped=textwrap.fill(sec['text'],145);fig.text(.06,y,sec['title'],fontsize=11.5,weight='bold',color=col);fig.text(.06,y-.016,wrapped,fontsize=10.3,color=col,va='top',linespacing=1.35);y-=.027+.013*len(wrapped.splitlines())
    fig.text(.06,.073,textwrap.fill(res['note'],165),fontsize=8.5,color=col,va='top',linespacing=1.3)
    fig.text(.06,.024,'Fuente: ECMWF Open Data · CC BY 4.0. Elaboración propia. Interpretación por reglas; sin IA.',fontsize=9,color=col)
    fig.text(.06,.011,'CAPE/CIN con temperatura virtual; LCL/LFC/EL tabulados con temperatura ordinaria. Resolución vertical reducida.',fontsize=8,color=col)
    fig.savefig(path,dpi=180,facecolor=fig.get_facecolor());plt.close(fig)

