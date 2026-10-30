(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const escapeHTML = (text) => String(text ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const jobs = [
    {id:1,title:'产品经理（校招）', company:'字节跳动', companyType:'互联网',size:'10000人以上',logo:'logo-bytedance.png',city:'北京',district:'海淀区',date:'2024-10-20',salary:20,maxSalary:35,months:14,score:92,education:'本科',type:'产品经理',tags:['本科及以上','产品经理','数据分析','用户研究','Axure','需求分析'],desc:'负责字节系产品的用户增长与商业化方向，参与产品规划、需求分析、版本迭代，推动产品从0到1的落地。我们希望你具备良好的逻辑思维和用户洞察能力，热爱互联网产品...'},
    {id:2,title:'算法工程师（NLP方向）',company:'阿里巴巴集团',companyType:'互联网',size:'10000人以上',logo:'logo-alibaba.png',city:'杭州',district:'西湖区',date:'2024-10-18',salary:25,maxSalary:40,months:16,score:88,education:'硕士',type:'算法工程师',tags:['硕士及以上','自然语言处理','深度学习','Python','大模型','算法优化'],desc:'从事大模型相关的算法研发工作，探索AIGC在电商、搜索等场景的应用。要求扎实的机器学习和深度学习基础，有相关论文或项目经历者优先。'},
    {id:3,title:'软件开发工程师',company:'华为技术有限公司',companyType:'通信/硬件',size:'10000人以上',logo:'logo-huawei.png',city:'深圳',district:'龙岗区',date:'2024-10-17',salary:18,maxSalary:30,months:15,score:85,education:'本科',type:'软件开发',tags:['本科及以上','Java','分布式系统','微服务','数据库','Linux'],desc:'参与公司核心产品的研发工作，负责模块设计、编码实现与测试。要求计算机相关专业基础扎实，熟悉Java或C++，具备良好的工程能力和团队协作精神。'},
    {id:4,title:'前端开发工程师',company:'腾讯科技',companyType:'互联网',size:'10000人以上',logo:'logo-tencent.png',city:'深圳',district:'南山区',date:'2024-10-16',salary:18,maxSalary:28,months:16,score:83,education:'本科',type:'前端开发',tags:['本科及以上','前端开发','React','TypeScript','工程化','性能优化'],desc:'负责腾讯云产品前端研发，参与大型中台系统的建设。要求熟悉前端基础知识，掌握React/Vue等主流框架，具备良好的代码质量意识和问题解决能力。'},
    {id:5,title:'数据分析师',company:'美团',companyType:'互联网',size:'10000人以上',logo:'logo-meituan.png',city:'北京',district:'朝阳区',date:'2024-10-15',salary:15,maxSalary:25,months:14,score:80,education:'本科',type:'数据分析',tags:['本科及以上','Python','SQL','数据分析','商业分析'],desc:'负责业务数据分析、指标体系搭建和数据可视化，使用SQL及Python完成数据处理，协助业务团队进行产品优化和增长决策。'},
    {id:6,title:'Java后端开发工程师',company:'字节跳动',companyType:'互联网',size:'10000人以上',logo:'logo-bytedance.png',city:'北京',district:'海淀区',date:'2024-10-13',salary:20,maxSalary:32,months:15,score:79,education:'本科',type:'后端开发',tags:['本科及以上','Java','MySQL','分布式系统','Redis'],desc:'参与业务服务端模块开发，完成接口设计、数据库建模及性能优化，支持高可用、高并发系统。'},
    {id:7,title:'Python数据开发工程师',company:'阿里巴巴集团',companyType:'互联网',size:'10000人以上',logo:'logo-alibaba.png',city:'杭州',district:'西湖区',date:'2024-10-12',salary:18,maxSalary:31,months:16,score:78,education:'本科',type:'后端开发',tags:['本科及以上','Python','数据分析','大数据','Linux'],desc:'参与数据平台建设和数据服务接口开发，支持业务智能化分析和数据治理。'},
    {id:8,title:'软件测试开发工程师',company:'华为技术有限公司',companyType:'通信/硬件',size:'10000人以上',logo:'logo-huawei.png',city:'深圳',district:'龙岗区',date:'2024-10-11',salary:16,maxSalary:25,months:14,score:75,education:'本科',type:'软件开发',tags:['本科及以上','软件测试','Python','自动化测试','Linux'],desc:'负责测试平台及自动化工具开发，参与持续集成和质量保障体系建设。'}
  ];
  const state={sort:'综合排序',view:'list',query:{},chips:['北京','本科','产品经理'], expanded:false,selected:new Set(), current:null};
  const logoURI = (filename) => (window.__embeddedAssets && window.__embeddedAssets[filename]) || `assets/${filename}`;
  const icon=(id,extra='') => `<svg class="icon" ${extra}><use href="#i-${id}"></use></svg>`;
  function toast(message){const node=$('#toast');node.textContent=message;node.classList.add('show');clearTimeout(toast.timeout);toast.timeout=setTimeout(()=>node.classList.remove('show'),2600)}
  function scoreIcon(){return icon('circle-check')}
  function card(j){
    const safe=escapeHTML;
    const companyLogo=`<img class="company-logo" loading="lazy" src="${safe(logoURI(j.logo))}" alt="${safe(j.company)}标识">`;
    const dateParts=j.date.split('-');
    return `<article class="job-card" data-job="${j.id}">
      ${companyLogo}
      <div class="job-main"><div class="job-head"><strong>${safe(j.title)}</strong><span class="job-campus">校招</span></div>
      <div class="job-company">${safe(j.company)}<span>|</span>${safe(j.companyType)}<span>|</span>${safe(j.size)}</div>
      <div class="job-tags">${j.tags.map(t=>`<span>${safe(t)}</span>`).join('')}</div></div>
      <div class="job-location"><div>${icon('location')}${safe(j.city)} · ${safe(j.district)}</div><div>${icon('clock')}${safe(j.date)} 发布</div></div>
      <div class="job-salary">${j.salary}-${j.maxSalary}K · <small>${j.months}薪</small></div>
      <div class="job-score"><div class="score-line">${scoreIcon()}<strong>${j.score}%</strong><span>匹配度</span></div><div class="score-meter"><i style="width:${j.score}%"></i></div></div>
      <div class="job-actions"><button type="button" data-detail="${j.id}">查看详情</button><button type="button" class="primary ${state.selected.has(j.id)?'added':''}" data-match="${j.id}">${icon(state.selected.has(j.id)?'check':'paper')}${state.selected.has(j.id)?'已加入':'加入匹配'}</button></div>
      <div class="job-description">${safe(j.desc)}</div></article>`;
  }
  function filteredJobs(){
    const f=state.query; let v=jobs.slice();
    if(f.keyword){const k=f.keyword.toLowerCase();v=v.filter(j=>(j.title+j.company+j.type+j.city+j.tags.join(' ')+j.desc).toLowerCase().includes(k));}
    if(f.city)v=v.filter(j=>j.city===f.city);
    if(f.category)v=v.filter(j=>j.type===f.category||j.title.includes(f.category));
    if(f.education)v=v.filter(j=>j.education===f.education||(f.education==='本科'&&j.tags.includes('本科及以上')));
    if(f.skill)v=v.filter(j=>j.tags.some(t=>t.toLowerCase().includes(f.skill.toLowerCase())));
    if(Number.isFinite(f.min))v=v.filter(j=>j.maxSalary>=f.min);
    if(Number.isFinite(f.max))v=v.filter(j=>j.salary<=f.max);
    if(state.sort==='最新发布')v.sort((a,b)=>b.date.localeCompare(a.date));
    if(state.sort==='薪资从高到低')v.sort((a,b)=>b.salary-a.salary);
    if(state.sort==='薪资从低到高')v.sort((a,b)=>a.salary-b.salary);
    if(state.sort==='匹配度从高到低')v.sort((a,b)=>b.score-a.score);
    return v;
  }
  function renderChips(){
    $('#activeChips').innerHTML=state.chips.map(c=>`<button class="chip" data-chip="${escapeHTML(c)}" type="button">${escapeHTML(c)} ×</button>`).join('');
    $('#activeChips').querySelectorAll('[data-chip]').forEach(b=>b.addEventListener('click',()=>{state.chips=state.chips.filter(x=>x!==b.dataset.chip);if($('#city').value===b.dataset.chip)$('#city').value='';if($('#education').value===b.dataset.chip)$('#education').value='';if($('#category').value===b.dataset.chip)$('#category').value='';state.query=readForm();render();}));
  }
  function render(){
    let v=filteredJobs();if(!state.expanded)v=v.slice(0,5);
    $('#jobResults').classList.toggle('grid-view',state.view==='grid');
    $('#jobResults').innerHTML=v.length?v.map(card).join(''):'<div class="empty-jobs">没有符合当前条件的演示岗位，请调整筛选条件。</div>';
    const isDefault=Object.keys(state.query).length===0 || !Object.values(state.query).some(x=>x!==''&&x!==undefined&&x!==null&&x!==false);
    $('#resultCount').textContent=isDefault?'1,286':filteredJobs().length.toLocaleString('zh-CN');
    $('#showMoreJobs').textContent=state.expanded?'收起岗位':'加载更多岗位';
    $('#showMoreJobs').style.visibility=(filteredJobs().length>5)?'visible':'hidden';
    renderChips();
    $('#jobResults').querySelectorAll('[data-detail]').forEach(b=>b.addEventListener('click',()=>openDetail(+b.dataset.detail)));
    $('#jobResults').querySelectorAll('[data-match]').forEach(b=>b.addEventListener('click',()=>toggleMatch(+b.dataset.match)));
  }
  function readForm(){
    const raw={keyword:$('#keyword').value.trim(),city:$('#city').value,category:$('#category').value,education:$('#education').value,skill:$('#skill').value};
    if($('#salaryMin').value!=='')raw.min=Number($('#salaryMin').value);
    if($('#salaryMax').value!=='')raw.max=Number($('#salaryMax').value);
    return raw;
  }
  function applySearch(){
    const f=readForm();
    if(f.min!==undefined&&f.max!==undefined&&f.min>f.max){toast('最低薪资不能高于最高薪资');return;}
    state.query=f;state.expanded=false;state.chips=[f.city,f.education,f.category,f.skill,f.keyword].filter(Boolean);
    if(f.min!==undefined||f.max!==undefined)state.chips.push(`${f.min??0}–${f.max??'不限'}K`);
    render();toast(`筛选完成：找到 ${filteredJobs().length} 条演示岗位`);
  }
  function clearFilters(){
    $('#jobFilterForm').reset();state.query={};state.chips=[];state.expanded=false;
    $('#popularTags').querySelectorAll('button').forEach(b=>b.classList.remove('selected'));
    render();toast('筛选条件已重置');
  }
  function toggleMatch(id){
    if(state.selected.has(id)){state.selected.delete(id);toast('已从匹配清单移除');}
    else{state.selected.add(id);toast('已加入匹配清单（演示模式）');}
    render();if(!$('#jobModal').hidden)$('#modalMatch').textContent=state.selected.has(id)?'移出匹配':'加入匹配';
  }
  function openDetail(id){
    const j=jobs.find(x=>x.id===id);if(!j)return;state.current=j.id;
    $('#modalLogo').src=logoURI(j.logo);$('#modalLogo').alt=j.company;
    $('#jobModalTitle').textContent=j.title;$('#modalCompany').textContent=`${j.company} · ${j.city} · ${j.district} · ${j.education}及以上`;
    $('#modalSalary').textContent=`${j.salary}-${j.maxSalary}K · ${j.months}薪 · 匹配度 ${j.score}%`;
    $('#modalTags').innerHTML=j.tags.map(t=>`<span>${escapeHTML(t)}</span>`).join('');$('#modalDescription').textContent=j.desc;
    $('#modalMatch').textContent=state.selected.has(id)?'移出匹配':'加入匹配';
    $('#mask').hidden=false;$('#jobModal').hidden=false;$('#closeModal').focus();document.body.style.overflow='hidden';
  }
  function closeDetail(){ $('#mask').hidden=true;$('#jobModal').hidden=true;document.body.style.overflow='';}
  $('#jobFilterForm').addEventListener('submit',e=>{e.preventDefault();applySearch();});
  $('#resetFilters').addEventListener('click',clearFilters);
  $('#clearChips').addEventListener('click',clearFilters);
  $('#sortTabs').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{state.sort=b.dataset.sort;$('#sortTabs').querySelectorAll('button').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-selected',x===b?'true':'false')});render();}));
  $('.view-modes').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{state.view=b.dataset.view;$('.view-modes').querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));render();}));
  $('#popularTags').querySelectorAll('[data-tag]').forEach(b=>b.addEventListener('click',()=>{const tag=b.dataset.tag;$('#keyword').value=tag;b.classList.add('selected');applySearch()}));
  $('#moreTags').addEventListener('click',()=>toast('可通过关键词直接搜索更多热门标签'));
  $('#showMoreJobs').addEventListener('click',()=>{state.expanded=!state.expanded;render();});
  $('#closeModal').addEventListener('click',closeDetail);$('#mask').addEventListener('click',closeDetail);
  $('#modalMatch').addEventListener('click',()=>state.current&&toggleMatch(state.current));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail();});
  $('#globalSearchForm').addEventListener('submit',e=>{e.preventDefault();$('#keyword').value=$('#globalSearch').value;applySearch();$('#jobs').scrollIntoView({behavior:'smooth'});});
  const menus=[['#notificationToggle','#notificationMenu'],['#profileToggle','#profileMenu']];
  for(const [btnSel,menuSel] of menus){const btn=$(btnSel),menu=$(menuSel);btn.addEventListener('click',e=>{e.stopPropagation();const wasOpen=!menu.hidden;menus.forEach(([b,m])=>{$(m).hidden=true;$(b).setAttribute('aria-expanded','false')});menu.hidden=wasOpen;btn.setAttribute('aria-expanded',String(!wasOpen));});}
  document.addEventListener('click',e=>{if(!e.target.closest('.popover-host')){menus.forEach(([b,m])=>{$(m).hidden=true;$(b).setAttribute('aria-expanded','false')});}});
  document.querySelectorAll('[data-demo]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();toast(`“${b.dataset.demo}”可在系统完整版本中跳转；当前展示岗位探索复刻页面`)}));
  render();
})();
