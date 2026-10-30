const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const svg = (name, css='') => `<svg class="icon ${css}" aria-hidden="true"><use href="#ic-${name}"></use></svg>`;
const src = name => `assets/${name}`;
const jobs = [
 {title:'后端开发工程师',company:'字节跳动',logo:'logo-bytedance.png',city:'北京',type:'后端开发',salary:'15-25K',score:92,tags:['Java','分布式系统','微服务','高并发','数据存储'],skills:90,edu:100,projects:85,intent:90,improve:['云原生技术','高并发架构经验','容器化（Docker/K8s）'],note:'建议在简历中补充相关项目经验或学习相关技术，以进一步提升匹配度。'},
 {title:'算法工程师（NLP方向）',company:'阿里巴巴',logo:'logo-alibaba.png',city:'杭州',type:'算法/机器学习',salary:'20-35K',score:88,tags:['Python','机器学习','自然语言处理','大模型','深度学习'],skills:85,edu:100,projects:90,intent:80,improve:['大模型训练经验','论文或竞赛成果','工程化落地经验'],note:'建议补充大模型相关项目或实践经验，提升在该方向的竞争力。'},
 {title:'前端开发工程师',company:'腾讯',logo:'logo-tencent.png',city:'深圳',type:'前端开发',salary:'18-28K',score:85,tags:['Vue','React','TypeScript','工程化','组件设计'],skills:87,edu:100,projects:78,intent:82,improve:['跨端项目','性能优化','开源贡献'],note:'建议在项目经历中突出前端性能优化和工程实践。'},
 {title:'数据开发工程师',company:'美团',logo:'logo-meituan.png',city:'北京',type:'数据开发',salary:'17-28K',score:83,tags:['SQL','Python','数据仓库','ETL','Spark'],skills:84,edu:100,projects:81,intent:80,improve:['数据平台实战','实时数据处理'],note:'建议补充离线与实时数据处理经验。'},
 {title:'Java开发工程师（校招）',company:'华为',logo:'',city:'深圳',type:'后端开发',salary:'18-30K',score:81,tags:['Java','Spring Boot','MySQL','Redis','Linux'],skills:85,edu:100,projects:72,intent:78,improve:['高可用架构','系统调优'],note:'建议突出服务端项目中的实际技术难点。'},
 {title:'云原生研发工程师',company:'字节跳动',logo:'logo-bytedance.png',city:'北京',type:'后端开发',salary:'20-35K',score:79,tags:['Go','Docker','Kubernetes','Linux'],skills:79,edu:100,projects:75,intent:75,improve:['K8s实践','容器编排'],note:'优先丰富容器化与系统工程项目经验。'},
 {title:'推荐算法工程师',company:'阿里巴巴',logo:'logo-alibaba.png',city:'杭州',type:'算法/机器学习',salary:'23-38K',score:78,tags:['机器学习','Python','推荐系统'],skills:77,edu:100,projects:73,intent:80,improve:['召回排序','特征工程'],note:'增加推荐系统相关工程实践。'},
 {title:'全栈开发工程师',company:'腾讯',logo:'logo-tencent.png',city:'深圳',type:'后端开发',salary:'16-28K',score:77,tags:['Java','Vue','MySQL','Redis'],skills:82,edu:100,projects:72,intent:74,improve:['前后端联调','服务部署'],note:'突出多端项目中的工程协同能力。'},
 {title:'算法平台开发工程师',company:'字节跳动',logo:'logo-bytedance.png',city:'北京',type:'算法/机器学习',salary:'19-32K',score:76,tags:['Python','PyTorch','MLOps'],skills:79,edu:100,projects:70,intent:75,improve:['模型服务化','训练平台'],note:'建议丰富模型部署与平台化经验。'},
 {title:'数据分析师',company:'美团',logo:'logo-meituan.png',city:'北京',type:'数据开发',salary:'15-25K',score:75,tags:['SQL','Python','统计分析'],skills:78,edu:100,projects:76,intent:71,improve:['业务分析案例','数据可视化'],note:'丰富基于业务场景的数据分析成果。'},
];
const restTitles=['后端研发工程师','软件开发工程师','机器学习工程师','数据工程师','云平台研发工程师','前端开发工程师','数据平台开发','产品经理','Java高级研发（校招）','分布式系统研发'];
const restCompanies=['阿里巴巴','腾讯','字节跳动','美团'];
for(let i=0;i<10;i++){
 const company=restCompanies[i%4];
 jobs.push({title:restTitles[i],company,logo:({阿里巴巴:'logo-alibaba.png',腾讯:'logo-tencent.png',字节跳动:'logo-bytedance.png',美团:'logo-meituan.png'})[company],city:['杭州','深圳','北京','上海'][i%4],type:i%3===0?'后端开发':i%3===1?'算法/机器学习':'数据开发',salary:'15-28K',score:[74,73,72,71,70,69,68,67,66,64][i],tags:['Java','Python','项目实践','团队协作'],skills:70+i%7,edu:100,projects:72+i%6,intent:76,improve:['工程经验','技术深度','业务理解'],note:'建议进一步丰富项目实战及业务问题解决能力。'});
}
let currentJobs=jobs.slice(), favorites=new Set(), strategy='comprehensive';
function reasonMarkup(item){
 const reasons=[
  {type:'green',icon:svg('check'),name:'技能覆盖',score:item.skills,text:`掌握${item.tags.slice(0,2).join('、')}等核心技能，与岗位要求高度匹配`},
  {type:'blue',icon:svg('grad'),name:'学历匹配',score:item.edu,text:'本科 · 计算机相关专业符合学历要求'},
  {type:'purple',icon:svg('document'),name:'项目相关性',score:item.projects,text:`有${item.type==='算法/机器学习'?'NLP':'后端开发、分布式'}项目经验，与业务场景匹配`},
  {type:'orange',icon:svg('target'),name:'求职意向一致',score:item.intent,text:`期望城市：${item.city}，岗位方向与意向较为一致`},
 ];
 return reasons.map(r=>`<div class="reason"><span class="reason-icon ${r.type}">${r.icon}</span><div class="reason-metric"><span>${r.name}</span><strong class="${r.type==='green'?'green':r.type==='blue'?'blue':r.type==='purple'?'blue':'green'}">${r.score}%</strong></div><p class="reason-desc">${r.text}</p></div>`).join('');
}
function jobMarkup(job,index){
 const rank=index+1;
 const color=rank===1?'gold':rank===2?'silver':rank===3?'bronze':'gray';
 const logo=job.logo?`<img src="${src(job.logo)}" alt="${job.company}标识">`:`<b style="color:#e82d24">华为</b>`;
 return `<article class="result-card ${rank===1?'top-ranked':''}" data-title="${job.title}" data-company="${job.company}">
  <div class="ranking-ribbon rank-${color}" aria-label="第${rank}名">${rank}</div>
  <div class="result-main"><div class="company-logo">${logo}</div><div class="job-summary"><h3 class="job-title">${job.title}</h3><div class="employer-line"><span>${job.company}</span><span class="company-chip">已上市</span><span class="company-chip">10000人以上</span></div><div class="job-details-row"><span>${svg('pin')}${job.city}</span><span>${svg('grad')}本科及以上</span><span class="salary">${svg('case')}${job.salary}</span></div><div class="skill-tags">${job.tags.map(t=>`<span>${t}</span>`).join('')}</div></div>
  <div class="score-and-actions"><div class="score-circle" style="background:conic-gradient(#246bff 0 160deg,#8e51ef 160deg ${Math.max(160,job.score*3.6)}deg,#e9eef7 ${Math.max(160,job.score*3.6)}deg 360deg)"><div class="score-circle-inner"><strong>${job.score}%</strong><small>匹配度</small></div></div><div class="cta-column"><button class="star-action ${favorites.has(job.company+job.title)?'is-saved':''}" data-save="${job.company+job.title}" title="${favorites.has(job.company+job.title)?'取消收藏':'收藏岗位'}" aria-label="收藏${job.title}">${svg('star')}</button><button class="detail-button" data-detail="${jobs.indexOf(job)}">查看详情</button></div></div></div>
  <div class="reasons-panel"><div class="reasons-title">匹配原因</div><div class="reasons-grid">${reasonMarkup(job)}</div></div>
  <div class="improve"><span class="bulb">💡</span><div class="improve-content"><div class="improve-line"><b>待补充技能</b>${job.improve.map(x=>`<span>${x}</span>`).join('')}</div><p>${job.note}</p></div></div>
 </article>`;
}
function render(){
 const topk=Number($('#topk').value);
 const city=$('#city').value,category=$('#category').value;
 let results=jobs.filter(j=>(!city||j.city===city)&&(!category||j.type===category));
 if(strategy==='accuracy')results.sort((a,b)=>b.skills-a.skills||b.score-a.score);
 else if(strategy==='potential')results.sort((a,b)=>b.projects-a.projects||b.score-a.score);
 else results.sort((a,b)=>b.score-a.score);
 currentJobs=results.slice(0,topk);
 $('#resultsList').innerHTML=currentJobs.length?currentJobs.map(jobMarkup).join(''):'<div style="text-align:center;padding:60px;color:#7887a3">当前筛选条件下暂无匹配岗位，可尝试更换城市或岗位类别。</div>';
 $('#matchedCount').textContent=currentJobs.length;
 $('#countInOverview').textContent=currentJobs.length;
 $('#donutValue').textContent=currentJobs.length;
 $('#currentVersion').textContent=$('#version').selectedOptions[0].textContent;
 $('#overviewFilters').textContent=`${city||'全国'} · ${category||'全部岗位类别'}`;
 $('#extraStrategy').textContent=({comprehensive:'综合排序',accuracy:'高匹配优先',potential:'高潜力优先'})[strategy];
 const counts=[['后端开发',6],['算法 / 机器学习',4],['前端开发',3],['数据开发',3],['产品经理',2]];
 $('#typesWrap').innerHTML=counts.map(([type,num])=>`<div class="type-row"><span>${type}</span><div class="type-progress"><b style="width:${num*16}%"></b></div><small>${num} (${num*5}%)</small></div>`).join('');
}
let toastTimer=null;
function toast(msg){const t=$('#toast');t.textContent=msg;t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{t.hidden=true},2700)}
function modal(title,content){$('#modalTitle').textContent=title;$('#modalBody').innerHTML=content;$('#modal').hidden=false;document.body.style.overflow='hidden'}
function closeModal(){$('#modal').hidden=true;document.body.style.overflow=''}
$$('.strategy').forEach(btn=>btn.addEventListener('click',()=>{strategy=btn.dataset.strategy;$$('.strategy').forEach(x=>x.classList.toggle('active',x===btn));render()}));
['version','topk','city','category'].forEach(id=>$('#'+id).addEventListener('change',render));
$('#startMatching').addEventListener('click',()=>{let b=$('#startMatching');b.disabled=true;b.textContent='匹配中...';setTimeout(()=>{render();b.innerHTML=`${svg('sparkle','solid-sparkle')}开始匹配`;b.disabled=false;$('#generationTime').textContent='2024-10-21 10:24:36';toast(`匹配完成：共生成 ${currentJobs.length} 条演示岗位推荐`)},650)});
$('#resetSettings').addEventListener('click',()=>{ $('#version').value='v2.3';$('#city').value='';$('#category').value='';$('#topk').value='20';$$('.strategy')[0].click();toast('匹配参数已重置')});
$('#detailsToggle').addEventListener('click',()=>{$('#detailsExtra').hidden=!$('#detailsExtra').hidden});
$('#resultsList').addEventListener('click',e=>{
 const save=e.target.closest('[data-save]');if(save){let id=save.dataset.save;favorites.has(id)?favorites.delete(id):favorites.add(id);save.classList.toggle('is-saved',favorites.has(id));save.title=favorites.has(id)?'取消收藏':'收藏岗位';toast(favorites.has(id)?'已收藏岗位':'已取消收藏');return}
 const detail=e.target.closest('[data-detail]');if(detail){const j=jobs[+detail.dataset.detail];modal(j.title,`<p><b>企业：</b>${j.company}</p><p><b>工作城市：</b>${j.city}</p><p><b>参考薪资：</b>${j.salary}</p><p><b>岗位类型：</b>${j.type}</p><p><b>匹配参考分：</b>${j.score}%（仅用于排序，不代表录用概率）</p><p><b>技能要求：</b>${j.tags.join('、')}</p><p style="margin-top:8px"><b>改进建议：</b>${j.note}</p>`)}
});
$('#closeModal').addEventListener('click',closeModal);$('#modalOkay').addEventListener('click',closeModal);$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});window.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
$$('[data-demo]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();toast(`${a.dataset.demo}：当前为智能匹配页面高保真演示`)}));
$('#topSearch').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();const q=e.currentTarget.value.trim();if(q){const j=jobs.find(x=>x.title.includes(q)||x.company.includes(q)||x.tags.some(t=>t.toLowerCase().includes(q.toLowerCase())));if(j)modal('搜索结果',`<p>${j.company}：${j.title}，匹配度 ${j.score}%</p>`);else toast('演示数据中未找到对应岗位')} }});
$('#notificationButton').addEventListener('click',()=>{$('#notificationPopover').hidden=!$('#notificationPopover').hidden;$('#accountPopover').hidden=true});$('#accountButton').addEventListener('click',()=>{$('#accountPopover').hidden=!$('#accountPopover').hidden;$('#notificationPopover').hidden=true});
document.addEventListener('click',e=>{if(!e.target.closest('.pop-host')){$('#notificationPopover').hidden=true;$('#accountPopover').hidden=true}});
render();
