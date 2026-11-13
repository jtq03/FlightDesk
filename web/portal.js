import {api, render, command, getSnapshot, portalHooks} from '/app.js';
const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
let catalog={}, types={}, editing=false;
function pane(name){
 for(const p of document.querySelectorAll('[data-settings-pane]'))p.hidden=p.dataset.settingsPane!==name;
 for(const b of document.querySelectorAll('[data-tab]'))b.setAttribute('aria-pressed',String(b.dataset.tab===name));
 if(name==='artwork')loadLibrary().catch(e=>$('art-status').textContent=e.message);
 if(name==='devices')loadDevices().catch(e=>$('device-list').textContent=e.message);
}
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>pane(b.dataset.tab);
const markDirty=()=>$('settings-form').dispatchEvent(new Event('input',{bubbles:true}));
function presetRow(place={name:'',latitude:'',longitude:'',zoom:11}){
 const row=el('div',null,'preset-row');
 for(const [key,label] of [['name','Name'],['latitude','Latitude'],['longitude','Longitude'],['zoom','Zoom']]){
  const l=el('label',label),i=el('input');i.dataset.field=key;i.value=place[key];i.required=true;
  if(key==='name')i.maxLength=24;else {i.type='number';i.step=key==='zoom'?'.25':'any';i.min=key==='latitude'?-85:key==='longitude'?-180:3;i.max=key==='latitude'?85:key==='longitude'?180:15;}
  l.append(i);row.append(l);
 }
 const remove=el('button','Remove','quiet');remove.type='button';remove.onclick=()=>{row.remove();markDirty();};row.append(remove);
 $('preset-editor').append(row);
}
$('add-preset').onclick=()=>{
 if($('preset-editor').children.length>=8){$('settings-error').textContent='Use up to eight quick locations.';return;}
 presetRow();markDirty();
};
portalHooks.load=s=>{
 editing=true;pane('general');$('preset-editor').replaceChildren();for(const p of s.settings.presets)presetRow(p);
 const home=s.settings.observer;
 $('observer-label').value=home?.label||'Home';$('observer-lat').value=home?.latitude??'';$('observer-lon').value=home?.longitude??'';$('idle-minutes').value=home?.idle_minutes||5;
 $('location-results').replaceChildren();
};
portalHooks.save=()=>{
 const presets=[...$('preset-editor').children].map(row=>Object.fromEntries([...row.querySelectorAll('[data-field]')].map(i=>[i.dataset.field,i.dataset.field==='name'?i.value.trim():Number(i.value)])));
 const lat=$('observer-lat').value,lon=$('observer-lon').value;
 if((lat==='')!==(lon===''))throw Error('Add both coordinates for your home position.');
 return {presets,observer:lat===''?null:{label:$('observer-label').value.trim()||'Home',latitude:Number(lat),longitude:Number(lon),idle_minutes:Number($('idle-minutes').value)}};
};
portalHooks.notify=s=>{
 if(!s)return;
 const a=s.aircraft.find(a=>a.id===s.desk.aircraft_id);
 $('remote-status').textContent=s.desk.mode==='map'?'Your desk is exploring the sky':(s.desk.mode==='follow'?'Following ':'Selected ')+(a?.callsign||a?.registration||s.desk.aircraft_id)+(s.desk.panel_open===false?' · full map':'');
};
$('airline-picker').onchange=e=>{if(e.target.value){$('new-airline').value=e.target.value;$('new-colour').focus();}};
api('airlines').then(({airlines})=>{for(const [code,name] of Object.entries(airlines).sort((a,b)=>a[1].localeCompare(b[1]))){const option=el('option',`${name} · ${code}`);option.value=code;$('airline-picker').append(option);}}).catch(()=>{});
// Never follow a search result silently. The phone gives an explicit Follow action.
$('search-form').onsubmit=async e=>{
 e.preventDefault();const button=e.currentTarget.querySelector('button');button.disabled=true;
 const results=$('search-results');results.hidden=false;results.replaceChildren(el('p','Looking for that flight…'));
 try{
  const found=await api('search?q='+encodeURIComponent($('query').value.trim()));results.replaceChildren();
  if(!found.aircraft.length)results.append(el('p',found.message));
  for(const a of found.aircraft){
   const row=el('article',null,'search-result'),info=el('div');info.append(el('strong',a.callsign||a.registration||a.id),el('small',[a.aircraft_type,a.registration].filter(Boolean).join(' · ')));
   const view=el('button','View','quiet');view.onclick=()=>command('detail',a.id);
   const follow=el('button','Follow ↗');follow.onclick=async()=>{await command('follow',a.id);results.hidden=true;$('flight-view').scrollIntoView({behavior:'smooth',block:'start'});};
   row.append(info,view,follow);results.append(row);
  }
 }catch(err){results.replaceChildren(el('p',err.message));}finally{button.disabled=false;}
};
$('find-location').onclick=async()=>{
 const button=$('find-location');button.disabled=true;const holder=$('location-results');holder.replaceChildren(el('p','Searching places…'));
 try{
  const {results,credit}=await api('locations/search?q='+encodeURIComponent($('location-query').value));holder.replaceChildren();
  if(!results.length)holder.append(el('p','No matches. Try the city and province, or enter coordinates.'));
  for(const p of results){
   const card=el('article',null,'location-result');card.append(el('p',p.label));
   const home=el('button','Use as home');home.type='button';home.onclick=()=>{$('observer-lat').value=p.latitude;$('observer-lon').value=p.longitude;$('observer-label').value=p.label.slice(0,180);markDirty();holder.replaceChildren(el('p','Home selected. Save settings to apply.'));};
   const shortcut=el('button','Add shortcut','quiet');shortcut.type='button';shortcut.onclick=()=>{if($('preset-editor').children.length>=8){holder.append(el('p','Eight shortcuts is the maximum.'));return;}presetRow({name:p.label.split(',')[0].slice(0,24),latitude:p.latitude,longitude:p.longitude,zoom:11});markDirty();holder.replaceChildren(el('p','Shortcut added. Edit its name above, then save.'));};
   card.append(home,shortcut);holder.append(card);
  }
  if(credit)holder.append(el('small',credit));
 }catch(e){holder.replaceChildren(el('p',e.message));}finally{button.disabled=false;}
};
async function loadDevices(){
 const {devices}=await api('devices'),holder=$('device-list');holder.replaceChildren();
 for(const d of devices){
  const row=el('article',null,'device-row');row.append(el('span',d.name+(d.this_device?' · this phone':'')));
  const remove=el('button','Unpair','quiet');remove.type='button';remove.onclick=async()=>{
   remove.disabled=true;try{await api('devices/'+d.id,{},'DELETE');if(d.this_device)location.reload();else await loadDevices();}catch(e){$('settings-error').textContent=e.message;remove.disabled=false;}
  };row.append(remove);holder.append(row);
 }
 if(!devices.length)holder.append(el('p','No phones paired yet.'));
}
$('show-pairing').onclick=async()=>{try{await api('pairing/show',{});$('show-pairing').textContent='Code is on the desk · 2 minutes';}catch(e){$('settings-error').textContent=e.message;}};
async function loadLibrary(){
 const result=await api('artwork');catalog=result.catalog;types=result.types;renderLibrary();
}
function renderLibrary(){
 const query=$('art-filter').value.trim().toLowerCase(),holder=$('art-library');holder.replaceChildren();
 const all=[...new Set([...Object.keys(catalog),...Object.keys(types)])].sort();
 let count=0;
 for(const key of all){
  const entry=catalog[key]||catalog.DEFAULT;
  const name=key.startsWith('POE_')?'Porter edition · '+key.slice(4):types[key]||entry.label||key.replace('class_','Class · ');
  if(query&&!`${key} ${name}`.toLowerCase().includes(query))continue;
  count++;
  const row=el('article',null,'art-row'),image=el('img');image.src=entry.asset;image.alt=entry.alt||name;image.loading='lazy';
  const body=el('div');body.append(el('strong',name),el('small',key+(catalog[key]?.custom?' · your image':catalog[key]?' · original':' · uses class/default art')));
  const label=el('label','Replace image','upload-button');const input=el('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.setAttribute('aria-label','Replace '+key+' image');
  input.onchange=async()=>{
   const file=input.files[0];if(!file)return;
   if(file.size>6*1024*1024){$('art-status').textContent='Please choose an image smaller than 6 MB.';input.value='';return;}
   input.disabled=true;$('art-status').textContent='Uploading '+key+'…';
   try{
    const response=await fetch('/api/artwork/'+encodeURIComponent(key),{method:'PUT',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});
    const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'The image could not be uploaded');
    await loadLibrary();$('art-status').textContent=key+' image saved. The desk updates automatically.';
   }catch(e){$('art-status').textContent=e.message;input.disabled=false;}
  };
  label.append(input);body.append(label);
  if(catalog[key]?.custom){const restore=el('button','Restore original','quiet');restore.type='button';restore.onclick=async()=>{restore.disabled=true;try{await api('artwork/'+key,{},'DELETE');await loadLibrary();$('art-status').textContent='Original restored.';}catch(e){$('art-status').textContent=e.message;restore.disabled=false;}};body.append(restore);}
  row.append(image,body);holder.append(row);
 }
 if(!count)holder.append(el('p','No matching models. Add its ICAO type code above.'));
}
$('art-filter').oninput=renderLibrary;
$('art-add').onclick=()=>{
 const type=$('art-new-type').value.trim().toUpperCase();if(!/^[A-Z0-9]{2,8}$/.test(type)){$('art-status').textContent='Use the 2–8 character ICAO aircraft type code.';return;}
 types[type]=types[type]||type;$('art-filter').value=type;renderLibrary();$('art-new-type').value='';
};
// Set up the airline list after pairing too (the first load is intentionally unauthorized).
const oldNotify=portalHooks.notify;let airlinesLoaded=false;
portalHooks.notify=s=>{oldNotify(s);if(!airlinesLoaded){airlinesLoaded=true;api('airlines').then(({airlines})=>{if($('airline-picker').options.length>1)return;for(const [code,name] of Object.entries(airlines).sort((a,b)=>a[1].localeCompare(b[1]))){const o=el('option',`${name} · ${code}`);o.value=code;$('airline-picker').append(o);}}).catch(()=>{airlinesLoaded=false;});}};
