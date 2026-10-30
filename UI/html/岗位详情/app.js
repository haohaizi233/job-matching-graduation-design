(()=>{
'use strict';
const q=(s)=>document.querySelector(s),qa=(s)=>[...document.querySelectorAll(s)];
const toast=q('#toast');let toastTimer;
function note(message){toast.textContent=message;toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),2300)}
function modal(title,desc){q('#modalTitle').textContent=title;q('#modalDescription').textContent=desc;q('#modalBackdrop').hidden=false;q('#closeModal').focus()}
function closeModal(){q('#modalBackdrop').hidden=true}
q('#closeModal').addEventListener('click',closeModal);q('#modalConfirm').addEventListener('click',closeModal);q('#modalBackdrop').addEventListener('click',e=>{if(e.target===e.currentTarget)closeModal()});document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();q('#notificationMenu').hidden=true;q('#profileMenu').hidden=true}});
const tabNames={duties:'岗位详情',company:'公司介绍',jd:'原始JD',structure:'结构化画像'};
qa('.detail-tabs .tab').forEach(button=>button.addEventListener('click',()=>{
qa('.detail-tabs .tab').forEach(el=>{const active=el===button;el.classList.toggle('active',active);el.setAttribute('aria-selected',String(active))});
Object.keys(tabNames).forEach(name=>q('#tab'+name[0].toUpperCase()+name.slice(1)).hidden=(name!==button.dataset.tab));
note('正在查看：'+tabNames[button.dataset.tab]);
}));
let saved=false;q('#saveJob').addEventListener('click',()=>{saved=!saved;q('#saveJob').classList.toggle('saved',saved);q('#saveJob span').textContent=saved?'已收藏':'收藏岗位';note(saved?'已收藏岗位：后端开发工程师':'已取消收藏')});
for(const id of ['heroMatch','startMatch'])q('#'+id).addEventListener('click',()=>modal('开始智能匹配','该页面展示的是截图中的演示匹配结果（82%），并非真实就业录用概率。接入 FastAPI 匹配服务后，可根据实际简历、岗位与模型版本发起评估。'));
q('#matchExplanation').addEventListener('click',()=>modal('匹配度说明','82% 及技能匹配结果来自界面演示数据。真实系统应显示模型版本、评分依据、置信度及可解释结果，且不能视为录用概率。'));
qa('.help-icon').forEach(b=>b.addEventListener('click',()=>modal('关于匹配度',b.dataset.tip)));
for(const id of ['breadcrumbBack','backToList'])q('#'+id).addEventListener('click',()=>{note('演示入口：在主项目中通过岗位探索路由返回列表')});
for(const id of ['moreCompany','companyMore2'])q('#'+id).addEventListener('click',()=>{q('.detail-tabs [data-tab="company"]').click();window.scrollTo({top:0,behavior:'smooth'})});
function toggle(id,other){const cur=q('#'+id),otherMenu=q('#'+other);cur.hidden=!cur.hidden;otherMenu.hidden=true;const button=q(id==='notificationMenu'?'#notificationToggle':'#profileToggle');button.setAttribute('aria-expanded',String(!cur.hidden))}
q('#notificationToggle').addEventListener('click',()=>toggle('notificationMenu','profileMenu'));
q('#profileToggle').addEventListener('click',()=>toggle('profileMenu','notificationMenu'));
q('#globalSearchForm').addEventListener('submit',e=>{e.preventDefault();note(q('#globalSearch').value?'搜索：'+q('#globalSearch').value:'请输入关键词')});
qa('.side-link').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();if(b.classList.contains('active'))return;note(b.textContent.trim()+'页面可通过主项目路由接入')}));
qa('[data-action]').forEach(b=>b.addEventListener('click',()=>note(b.textContent.trim()+'：演示入口')));
})();
