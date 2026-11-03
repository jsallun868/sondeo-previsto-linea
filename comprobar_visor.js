'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const at=Date.parse;
let now=at('2026-11-02T20:59:59Z'),failFetch=false;
const elements=new Map(),images=[];
const el=id=>{if(!elements.has(id))elements.set(id,{id,hidden:true,textContent:'',dataset:{},children:[],addEventListener(){},replaceChildren(){this.children=[];},append(...xs){this.children.push(...xs);}});return elements.get(id);};
const profiles=['18','21'].map(h=>({valid_utc:`2026-11-02T${h}:00:00Z`,run_utc:'2026-11-02T06:00:00Z',step_hours:Number(h)-6,path:`perfiles/20261102T06Z_0${Number(h)-6}h`,sections:[{title:'Prueba',text:'Texto de interpretación'}],note:'Nota'}));
const cat={schema:2,spacing_degrees:.1,generated_at_utc:'2026-11-02T20:00:00Z',profiles};
class Clock extends Date{constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}}
const context=vm.createContext({Date:Clock,Intl,console,AbortController,encodeURIComponent,Image:class{constructor(){images.push(this);}},document:{getElementById:el,createElement:()=>({}),addEventListener(){},hidden:false},setTimeout(){return 1;},clearTimeout(){},setInterval(){},fetch:async()=>{if(failFetch)throw Error('sin red');return{ok:true,json:async()=>cat};}});
for(const file of ['seleccion.js','visor.js'])vm.runInContext(fs.readFileSync(__dirname+'/web/'+file,'utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await flush();assert.equal(images.length,1);images[0].onload();assert.match(el('fechas').textContent,/18:00 UTC/);assert.equal(el('diagrama').hidden,false);
 now=at('2026-11-02T21:00:00Z');vm.runInContext('seleccionar()',context);assert.equal(images.length,2);assert.match(el('fechas').textContent,/18:00 UTC/);
 images[1].onload();assert.match(el('fechas').textContent,/21:00 UTC/);assert.match(el('diagrama').src,/015h/);assert.match(el('csv').href,/015h\/perfil.csv/);
 failFetch=true;await vm.runInContext('consultar()',context);assert.match(el('error').textContent,/conserva/);assert.match(el('fechas').textContent,/21:00 UTC/);assert.equal(el('actualizar').disabled,false);
 now=at('2026-11-03T01:00:00Z');vm.runInContext('seleccionar()',context);assert.equal(el('estado').dataset.warning,'true');
 // Un catálogo con la misma fecha válida pero nueva generación vuelve a cargar la imagen.
 now=at('2026-11-02T21:30:00Z');cat.generated_at_utc='2026-11-02T21:15:00Z';failFetch=false;await vm.runInContext('consultar()',context);images.at(-1).onerror();assert.match(el('error').textContent,/diagrama/);assert.match(el('fechas').textContent,/21:00 UTC/);
 console.log('Visor: carga, cambio automático, coherencia entre imagen y texto, errores de red e imagen y perfil caducado comprobados.');
})().catch(e=>{console.error(e);process.exitCode=1;});
