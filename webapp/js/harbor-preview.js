import { HarborScene } from './harbor-scene.js';
import { COUNTRIES, STAGES, demoState, projectHarborState } from './harbor-state.js';
const $=s=>document.querySelector(s);
const params=new URLSearchParams(location.search);
let country=Object.hasOwn(COUNTRIES,params.get('country'))?params.get('country'):'Tropia';
const status=(text,error=false)=>{$('#map-status').textContent=text;$('#map-status').dataset.error=String(error);};
let viewer;
try {viewer=new HarborScene($('#map'),{onStatus:status,onSelect:detail=>{$('#selection-title').textContent=detail.title;$('#selection-copy').textContent=detail.description;}});}
catch(error){status('이 기기에서 3D 화면을 열 수 없어요. WebGL을 지원하는 브라우저에서 다시 열어 주세요.',true);console.error(error);}
function update(){
  const state=demoState(country,$('#stage').value,$('#machine').value,$('#electronics').value);
  const v=projectHarborState(state);$('#country-title').textContent=v.label;$('#stage-title').textContent=STAGES[v.stage-1];$('#stage-value').textContent=v.stage;
  for(const button of $('#countries').children)button.setAttribute('aria-pressed',String(button.dataset.country===country));
  $('#selection-title').textContent='항구를 둘러보세요';$('#selection-copy').textContent='물체를 누르면 자세히 볼 수 있어요. 드래그로 회전 · 휠로 확대';
  viewer?.update(state);
}
for(const [key,c]of Object.entries(COUNTRIES)){
  const b=document.createElement('button');b.dataset.country=key;b.style.setProperty('--country-color',c.color);
  const dot=document.createElement('i');dot.setAttribute('aria-hidden','true');b.append(dot,document.createTextNode(c.label));
  b.onclick=()=>{country=key;const url=new URL(location.href);url.searchParams.set('country',key);history.replaceState(null,'',url);update();};$('#countries').append(b);
}
for(const id of ['stage','machine','electronics'])$('#'+id).addEventListener('input',update);
$('#evolve').onclick=()=>{const next=Number($('#stage').value)%4+1;$('#stage').value=next;$('#machine').value=Math.min(3,next);$('#electronics').value=Math.min(3,next);update();};
for(const b of document.querySelectorAll('[data-focus]'))b.onclick=()=>viewer?.focus(b.dataset.focus);
const models={'harbor-crane':'항구 하역 크레인','gantry-crane':'컨테이너 크레인','early-truck':'초기 화물차','diesel-truck':'디젤 트럭','electric-truck':'전기 물류차','diesel-freighter':'디젤 화물선','container-ship':'컨테이너선','biplane':'복엽기','turboprop':'쌍발 프로펠러기','cargo-jet':'제트 화물기','modern-warehouse':'현대 창고','smart-warehouse':'스마트 창고','concrete-quay':'콘크리트 부두','smart-quay':'스마트 부두','factory':'공장'};
for(const [key,name]of Object.entries(models)){const a=document.createElement('a');a.href=`assets/harbor/${key}.glb`;a.download=`${key}.glb`;a.textContent=name+' · GLB';$('#asset-links').append(a);}
window.addEventListener('pagehide',()=>viewer?.dispose(),{once:true});update();
