// Keep the canvas outside the frequently re-rendered student action forms.
import { projectHarborState, STAGES } from './harbor-state.js';
let latest=null,viewer=null,opening=false,revision=0;
export function updateHarborState(state){latest=state;viewer?.update(state);const button=document.querySelector('#harbor-open');if(button&&!viewer&&!opening)button.hidden=false;const label=document.querySelector('#harbor-live-title');if(label)label.textContent=`${state.label}의 항구 · ${state.round}라운드`;const note=document.querySelector('#harbor-live-note');const v=projectHarborState(state);if(note)note.textContent=`${STAGES[v.stage-1]} · 대표 산업 Lv.${v.stage} · 기계 ${v.machine}세대 · 전자제품 ${v.electronics}세대${state.room?.paused?' · 일시정지':''}`;}
export async function openHarbor(){
  if(opening||viewer||!latest)return;opening=true;const rev=++revision;
  const host=document.querySelector('#harbor-live');host.hidden=false;document.querySelector('#harbor-open').hidden=true;
  const note=document.querySelector('#harbor-live-status');note.textContent='지도를 준비하는 중…';
  try{
    const {HarborScene}=await import('./harbor-scene.js');if(rev!==revision)return;
    viewer=new HarborScene(document.querySelector('#harbor-live-canvas'),{onStatus:(text,error)=>{note.textContent=text;note.dataset.error=String(error);},onSelect:d=>{document.querySelector('#harbor-live-selection').textContent=`${d.title} · ${d.description}`;}});
    updateHarborState(latest);
  }catch(error){note.textContent='이 기기에서는 3D 지도를 열 수 없어요. 아래 게임 화면에서 계속할 수 있어요.';console.error(error);}finally{opening=false;}
}
export function closeHarbor(){++revision;viewer?.dispose();viewer=null;opening=false;document.querySelector('#harbor-live').hidden=true;document.querySelector('#harbor-open').hidden=false;}
document.querySelector('#harbor-open')?.addEventListener('click',openHarbor);
document.querySelector('#harbor-close')?.addEventListener('click',closeHarbor);
document.querySelector('#harbor-reset')?.addEventListener('click',()=>viewer?.focus('overview'));
window.addEventListener('pagehide',()=>viewer?.dispose(),{once:true});
