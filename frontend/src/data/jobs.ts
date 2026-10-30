import type { JobCardItem, JobDetailData, JobFilterOption, SelectedFilter } from '@/types'

import logoBytedance from '@/assets/icons/company/bytedance.png'
import logoAlibaba from '@/assets/icons/company/alibaba.png'
import logoHuawei from '@/assets/icons/company/huawei.png'
import logoTencent from '@/assets/icons/company/tencent-qq.png'
import logoMeituan from '@/assets/icons/company/meituan.png'

export const heroCopy = {
  title: '探索更多适合你的岗位',
  lines: ['海量优质校招岗位，发现更广阔的职业可能', '多维度筛选，精准匹配，助你找到心仪的 offer'],
}

export const cityOptions: JobFilterOption[] = [
  { label: '全国', value: 'all' },
  { label: '北京', value: 'beijing' },
  { label: '杭州', value: 'hangzhou' },
  { label: '深圳', value: 'shenzhen' },
  { label: '上海', value: 'shanghai' },
  { label: '广州', value: 'guangzhou' },
]

export const categoryOptions: JobFilterOption[] = [
  { label: '全部类别', value: 'all' },
  { label: '后端开发', value: 'backend' },
  { label: '前端开发', value: 'frontend' },
  { label: '算法工程师', value: 'algorithm' },
  { label: '产品经理', value: 'pm' },
  { label: '数据分析', value: 'data' },
]

export const educationOptions: JobFilterOption[] = [
  { label: '全部学历', value: 'all' },
  { label: '本科及以上', value: 'bachelor' },
  { label: '硕士及以上', value: 'master' },
  { label: '博士', value: 'phd' },
]

export const hotTags = [
  'Java',
  'Python',
  '前端开发',
  '产品经理',
  '数据分析',
  '人工智能',
  '算法',
  '大数据',
  '软件测试',
  '运营',
  'UI设计',
]

export const sortOptions = ['综合排序', '最新发布', '薪资从高到低', '薪资从低到高', '匹配度从高到低']

export const selectedFilters: SelectedFilter[] = [
  { key: 'city', label: '北京' },
  { key: 'edu', label: '本科' },
  { key: 'category', label: '产品经理' },
]

export const jobList: JobCardItem[] = [
  {
    id: 1,
    title: '产品经理（校园）',
    company: '字节跳动',
    industry: '互联网',
    scale: '10000人以上',
    location: '北京 · 海淀区',
    publishTime: '2024-10-20 发布',
    salary: '20-35K',
    months: 14,
    match: 92,
    education: '本科及以上',
    experience: '应届生',
    tags: ['本科及以上', '产品经理', '数据分析', '用户研究', 'Axure', '需求分析'],
    desc: '负责字节产品的用户增长与商业化方向，参与产品规划、需求分析、版本迭代，推动产品从0到1落地。我们希望你具备良好的逻辑思维和问题洞察能力，热爱互联网产品...',
    logo: logoBytedance,
    logoAlt: '字节跳动标识',
    category: 'pm',
  },
  {
    id: 2,
    title: '算法工程师（NLP方向）',
    company: '阿里巴巴',
    industry: '互联网',
    scale: '10000人以上',
    location: '杭州 · 西湖区',
    publishTime: '2024-10-18 发布',
    salary: '25-40K',
    months: 16,
    match: 88,
    education: '硕士及以上',
    experience: '应届生',
    tags: ['硕士及以上', '自然语言处理', '深度学习', 'Python', '大模型', '算法优化'],
    desc: '从事大模型相关的算法研发工作，探索AIGC在电商、搜索等场景的应用。要求扎实的机器学习和深度学习基础，有相关论文或项目经历者优先。',
    logo: logoAlibaba,
    logoAlt: '阿里巴巴标识',
    category: 'algorithm',
  },
  {
    id: 3,
    title: '软件开发工程师',
    company: '华为',
    industry: '通信/网络',
    scale: '10000人以上',
    location: '深圳 · 龙岗区',
    publishTime: '2024-10-17 发布',
    salary: '18-30K',
    months: 15,
    match: 85,
    education: '本科及以上',
    experience: '应届生',
    tags: ['本科及以上', 'Java', '分布式系统', '微服务', '数据库', 'Linux'],
    desc: '参与公司核心产品的软件研发工作，负责模块设计、编码实现与测试。要求计算机相关专业，熟悉Java或C/C++，具备良好的编码能力和团队协作精神。',
    logo: logoHuawei,
    logoAlt: '华为标识',
    category: 'backend',
  },
  {
    id: 4,
    title: '前端开发工程师',
    company: '腾讯',
    industry: '互联网',
    scale: '10000人以上',
    location: '深圳 · 南山区',
    publishTime: '2024-10-16 发布',
    salary: '18-28K',
    months: 16,
    match: 83,
    education: '本科及以上',
    experience: '应届生',
    tags: ['本科及以上', '前端开发', 'React', 'TypeScript', '工程化', '性能优化'],
    desc: '负责腾讯云产品前端研发，参与大型中后台系统的建设。要求熟悉前端基础知识，掌握React/Vue等主流框架，具备良好的代码质量意识和问题解决能力。',
    logo: logoTencent,
    logoAlt: '腾讯标识',
    category: 'frontend',
  },
  {
    id: 5,
    title: '数据分析师',
    company: '美团',
    industry: '互联网',
    scale: '10000人以上',
    location: '北京 · 朝阳区',
    publishTime: '2024-10-15 发布',
    salary: '15-25K',
    months: 14,
    match: 80,
    education: '本科及以上',
    experience: '应届生',
    tags: ['本科及以上', '数据分析', 'SQL', 'Python', '数据可视化'],
    desc: '负责业务数据的分析与洞察，支持产品和运营决策。要求熟练使用SQL和Python，具备良好的数据敏感度和逻辑分析能力。',
    logo: logoMeituan,
    logoAlt: '美团标识',
    category: 'data',
  },
]

export const jobDetail: JobDetailData = {
  id: 999,
  title: '后端开发工程师（校招）',
  company: '阿里巴巴集团',
  industry: '互联网',
  scale: '10000人以上',
  status: '已上市',
  location: '北京 · 海淀区',
  education: '本科及以上',
  publishTime: '2024-10-18 发布',
  salary: '18-28K',
  months: 16,
  tags: ['校招', '后端开发', 'Java', '分布式', '高并发', '技术成长', '大厂平台'],
  logo: logoAlibaba,
  logoAlt: '阿里巴巴标识',
  matchPreview: {
    percent: 82,
    level: '非常匹配',
    desc: '你的技能背景与该岗位高度匹配，建议立即投递！',
  },
  skillMatch: {
    matched: ['Java', 'MySQL', '计算机网络', '数据结构', '操作系统', 'Linux'],
    improve: ['分布式系统', 'Kubernetes'],
  },
  conditionMatch: [
    { label: '学历要求', value: '本科及以上' },
    { label: '专业要求', value: '计算机相关专业' },
    { label: '工作地点', value: '北京 · 海淀区' },
    { label: '岗位类型', value: '校招' },
  ],
  advice: [
    '建议在简历中突出你在 Java、分布式方面的项目经验',
    '补充 Kubernetes 相关的学习或实践经历',
    '展示你的开源项目或技术竞赛经历（如有）',
  ],
  duties: [
    '参与公司核心业务系统的后端架构设计与开发，支撑高并发、高可用的业务场景；',
    '负责后端服务的需求分析、技术方案设计、编码实现与单元测试；',
    '持续优化系统性能、稳定性和可扩展性，解决线上问题；',
    '与产品、前端、测试等团队紧密协作，推动产品迭代和技术落地；',
    '关注业界技术发展，探索并引入合适的新技术，提升研发效率和工程质量。',
  ],
  requirements: [
    '2025届及以后毕业的本科及以上学历，计算机相关专业；',
    '扎实的计算机基础知识，熟悉数据结构、操作系统、计算机网络等；',
    '具备良好的编程能力和工程素养，有较强的学习能力和问题解决能力；',
    '具备良好的沟通能力、团队协作精神和责任心；',
    '对技术有热情，乐于挑战，有开源项目或技术竞赛经历者优先。',
  ],
  skillGroups: [
    { group: '必备技能', skills: ['Java', '计算机网络', '数据结构', '操作系统', 'MySQL'] },
    { group: '加分技能', skills: ['分布式系统', '高并发设计', '微服务', 'Linux', 'Kubernetes', '中间件'] },
    { group: '其他要求', skills: ['良好的代码风格', '技术文档能力', '团队协作', '快速学习能力'] },
  ],
  companyIntro:
    '阿里巴巴集团控股有限公司（NYSE: BABA, HKEX: 9988）创立于1999年，是一家以技术驱动的数字商业基础设施提供商，业务涵盖电商、云计算、数字媒体、本地生活等多个领域。我们致力于通过技术让天下没有难做的生意，持续为客户创造价值。',
}
