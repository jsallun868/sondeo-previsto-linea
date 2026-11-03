(function(root){
  'use strict';
  const INTERVAL=3*60*60*1000;
  function elegir(profiles, now){
    return profiles.filter(p=>Number.isFinite(Date.parse(p.valid_utc))&&Number.isFinite(Date.parse(p.run_utc))&&Date.parse(p.valid_utc)<=now&&Date.parse(p.run_utc)<=now)
      .sort((a,b)=>Date.parse(b.valid_utc)-Date.parse(a.valid_utc)||Date.parse(b.run_utc)-Date.parse(a.run_utc))[0]||null;
  }
  function estado(p,now){
    if(!p)return {outdated:true,text:'Todavía no hay un perfil con hora válida anterior a este momento.'};
    const age=now-Date.parse(p.valid_utc),runAge=now-Date.parse(p.run_utc);
    if(age>=INTERVAL)return {outdated:true,text:'El perfil disponible es anterior a la franja actual. Comprueba su fecha y hora válida.'};
    if(runAge>18*60*60*1000)return {outdated:true,text:'Perfil de la franja actual, calculado con una pasada del modelo de hace más de 18 horas.'};
    return {outdated:false,text:'Perfil previsto para la franja actual de tres horas.'};
  }
  function pathSeguro(path){return typeof path==='string'&&/^perfiles\/[0-9]{8}T[0-9]{2}Z_[0-9]{3}h$/.test(path);}
  root.Sondeo={elegir,estado,pathSeguro,INTERVAL};
  if(typeof module==='object')module.exports=root.Sondeo;
})(typeof globalThis!=='undefined'?globalThis:window);
