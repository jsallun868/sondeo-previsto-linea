'use strict';
const $=id=>document.getElementById(id);
let catalogo=null,actual=null,cargando=false,version=0,objetivo=null,timer;
const fecha=s=>new Intl.DateTimeFormat('es-ES',{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(s))+' UTC';
function aviso(){
  const s=Sondeo.estado(actual,Date.now());$('estado').textContent=s.text;$('estado').dataset.warning=String(s.outdated);
}
function programar(){
  clearTimeout(timer);const now=Date.now();
  timer=setTimeout(()=>{seleccionar();consultar();},Math.min(60000,Sondeo.INTERVAL-now%Sondeo.INTERVAL+100));
}
function seleccionar(){
  programar();
  const p=Sondeo.elegir(catalogo?.profiles||[],Date.now());
  if(!p){
    if(actual&&Date.parse(actual.valid_utc)>Date.now()){actual=null;++version;objetivo=null;$('diagrama').hidden=true;$('detalle').hidden=true;$('descargas').hidden=true;$('fechas').textContent='No hay un perfil para la hora actual.';}
    aviso();return;
  }
  const key=p.path+'?v='+encodeURIComponent(catalogo.generated_at_utc);
  if(actual?._key===key||objetivo===key){aviso();return;}
  const request=++version;objetivo=key;
  const img=new Image();
  img.onload=()=>{
    if(request!==version)return;
    // Si cambió la franja durante la descarga, se elige de nuevo.
    const latest=Sondeo.elegir(catalogo?.profiles||[],Date.now());
    if(!latest||latest.path!==p.path){objetivo=null;seleccionar();return;}
    $('diagrama').src=img.src;$('diagrama').hidden=false;
    $('fechas').textContent='Válido: '+fecha(p.valid_utc)+' · Pasada: '+fecha(p.run_utc)+' · Plazo: +'+p.step_hours+' h';
    const body=$('interpretacion');body.replaceChildren();
    for(const sec of p.sections||[]){const h=document.createElement('h2'),t=document.createElement('p');h.textContent=sec.title;t.textContent=sec.text;body.append(h,t);}
    $('nota').textContent=p.note;$('detalle').hidden=false;$('descargas').hidden=false;
    const suffix='?v='+encodeURIComponent(catalogo.generated_at_utc);
    for(const [id,name] of [['png','sondeo.png'],['csv','perfil.csv'],['txt','interpretacion.txt']])$(id).href=p.path+'/'+name+suffix;
    actual={...p,_key:key};objetivo=null;$('error').textContent='';aviso();
  };
  img.onerror=()=>{if(request!==version)return;objetivo=null;$('error').textContent='No se ha podido cargar el nuevo diagrama. Se volverá a intentar automáticamente.';aviso();};
  img.src=p.path+'/sondeo.png?v='+encodeURIComponent(catalogo.generated_at_utc);
}
async function consultar(){
  if(cargando)return;cargando=true;$('actualizar').disabled=true;
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),20000);
  try{
    const response=await fetch('catalogo.json?t='+Date.now(),{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error('HTTP '+response.status);
    const c=await response.json();
    if(c.schema!==2||c.spacing_degrees!==.1||!Number.isFinite(Date.parse(c.generated_at_utc))||!Array.isArray(c.profiles)||!c.profiles.length||c.profiles.some(p=>!Sondeo.pathSeguro(p.path)||!Number.isFinite(Date.parse(p.valid_utc))||!Number.isFinite(Date.parse(p.run_utc))))throw Error('Catálogo inválido');
    catalogo=c;$('error').textContent='';seleccionar();
  }catch(_){$('error').textContent=actual?'No se ha podido comprobar la actualización. Se conserva el perfil mostrado con su fecha.':'No se ha podido cargar la predicción. Se volverá a intentar automáticamente.';aviso();}
  finally{clearTimeout(timeout);cargando=false;$('actualizar').disabled=false;}
}
$('actualizar').addEventListener('click',consultar);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){seleccionar();consultar();}});
setInterval(()=>{if(!document.hidden)consultar();},60000);
programar();consultar();
