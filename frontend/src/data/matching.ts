import type {
  MatchCategoryStat,
  MatchDistributionSlice,
  MatchFilterOption,
  MatchJobItem,
  MatchOverview,
} from '@/types/matching'

import logoBytedance from '@/assets/icons/company/bytedance.png'
import logoAlibaba from '@/assets/icons/company/alibaba.png'
import logoHuawei from '@/assets/icons/company/huawei.png'
import logoTencent from '@/assets/icons/company/tencent.png'
import logoMeituan from '@/assets/icons/company/meituan.png'
import logoBaidu from '@/assets/icons/company/baidu.png'

export const heroCopy = {
  title: '智能匹配',
  lines: ['基于你的求职画像与简历技能，为你计算最合适的岗位', '调整匹配参数，开始一次新的匹配（演示数据，非模型真实输出）'],
}

export const profileOptions: MatchFilterOption[] = [
  { label: '画像版本 v2.0（最新）', value: 'v2' },
  { label: '画像版本 v1.5', value: 'v1.5' },
  { label: '画像版本 v1.0', value: 'v1' },
]

export const matchModes = ['综合排序', '高匹配优先', '高潜力优先'] as const

export const topKOptions: MatchFilterOption[] = [
  { label: 'Top 5', value: '5' },
  { label: 'Top 10', value: '10' },
  { label: 'Top 20', value: '20' },
]

export const cityOptions: MatchFilterOption[] = [
  { label: '全国', value: 'all' },
  { label: '北京', value: 'beijing' },
  { label: '杭州', value: 'hangzhou' },
  { label: '深圳', value: 'shenzhen' },
  { label: '上海', value: 'shanghai' },
]

export const categoryOptions: MatchFilterOption[] = [
  { label: '全部类别', value: 'all' },
  { label: '后端开发', value: 'backend' },
  { label: '前端开发', value: 'frontend' },
  { label: '算法工程师', value: 'algorithm' },
  { label: '产品经理', value: 'pm' },
  { label: '数据分析', value: 'data' },
]

export const matchOverview: MatchOverview = {
  avgMatch: 82,
  highMatchCount: 6,
  coveredSkills: 18,
  totalSkills: 24,
}

export const distribution: MatchDistributionSlice[] = [
  { label: '高匹配 85%+', value: 6, color: '#2168ff' },
  { label: '中匹配 70-84%', value: 3, color: '#03b58c' },
  { label: '待观察 <70%', value: 1, color: '#ffb020' },
]

export const categoryStats: MatchCategoryStat[] = [
  { label: '后端开发', value: 3 },
  { label: '算法工程师', value: 2 },
  { label: '产品经理', value: 2 },
  { label: '前端开发', value: 2 },
  { label: '数据分析', value: 1 },
]

export const noticeText =
  '本页匹配度、四维评分与推荐结果均为界面演示数据，不代表模型真实输出，也不构成录用概率。接入后端匹配服务后将展示真实计算结果。'

function reasons(skill: number, education: number, project: number, intent: number) {
  return [
    { key: 'skill' as const, label: '技能覆盖', score: skill },
    { key: 'education' as const, label: '教育匹配', score: education },
    { key: 'project' as const, label: '项目相关性', score: project },
    { key: 'intent' as const, label: '求职意向', score: intent },
  ]
}

export const matchJobs: MatchJobItem[] = [
  {
    id: 1,
    title: '产品经理（校园）',
    company: '字节跳动',
    industry: '互联网',
    location: '北京 · 海淀区',
    salary: '20-35K',
    months: 14,
    match: 92,
    potential: 88,
    tags: ['产品经理', '需求分析', '用户研究', 'Axure'],
    reasons: reasons(90, 95, 88, 94),
    missingSkills: ['商业化经验', 'A/B 实验'],
    logo: logoBytedance,
    logoAlt: '字节跳动标识',
    category: 'pm',
  },
  {
    id: 2,
    title: '算法工程师（NLP方向）',
    company: '阿里巴巴',
    industry: '互联网',
    location: '杭州 · 西湖区',
    salary: '25-40K',
    months: 16,
    match: 88,
    potential: 93,
    tags: ['自然语言处理', '深度学习', 'Python', '大模型'],
    reasons: reasons(86, 92, 90, 84),
    missingSkills: ['分布式训练', '论文发表'],
    logo: logoAlibaba,
    logoAlt: '阿里巴巴标识',
    category: 'algorithm',
  },
  {
    id: 3,
    title: '软件开发工程师',
    company: '华为',
    industry: '通信/网络',
    location: '深圳 · 龙岗区',
    salary: '18-30K',
    months: 15,
    match: 85,
    potential: 82,
    tags: ['Java', '分布式系统', '微服务', 'Linux'],
    reasons: reasons(88, 90, 80, 82),
    missingSkills: ['Kubernetes', '高并发实战'],
    logo: logoHuawei,
    logoAlt: '华为标识',
    category: 'backend',
  },
  {
    id: 4,
    title: '前端开发工程师',
    company: '腾讯',
    industry: '互联网',
    location: '深圳 · 南山区',
    salary: '18-28K',
    months: 16,
    match: 83,
    potential: 86,
    tags: ['React', 'TypeScript', '工程化', '性能优化'],
    reasons: reasons(84, 88, 82, 78),
    missingSkills: ['可视化', '跨端开发'],
    logo: logoTencent,
    logoAlt: '腾讯标识',
    category: 'frontend',
  },
  {
    id: 5,
    title: '数据分析师',
    company: '美团',
    industry: '互联网',
    location: '北京 · 朝阳区',
    salary: '15-25K',
    months: 14,
    match: 80,
    potential: 79,
    tags: ['SQL', 'Python', '数据可视化'],
    reasons: reasons(78, 86, 76, 80),
    missingSkills: ['统计建模', 'Tableau'],
    logo: logoMeituan,
    logoAlt: '美团标识',
    category: 'data',
  },
  {
    id: 6,
    title: '后端开发工程师（Go）',
    company: '字节跳动',
    industry: '互联网',
    location: '北京 · 海淀区',
    salary: '22-35K',
    months: 14,
    match: 78,
    potential: 85,
    tags: ['Go', '微服务', 'MySQL', 'Redis'],
    reasons: reasons(76, 84, 78, 74),
    missingSkills: ['Go 工程实践', '消息队列'],
    logo: logoBytedance,
    logoAlt: '字节跳动标识',
    category: 'backend',
  },
  {
    id: 7,
    title: '机器学习工程师',
    company: '百度',
    industry: '互联网',
    location: '北京 · 海淀区',
    salary: '25-38K',
    months: 16,
    match: 76,
    potential: 90,
    tags: ['机器学习', 'PyTorch', '推荐系统'],
    reasons: reasons(72, 82, 80, 70),
    missingSkills: ['推荐系统实战', '特征工程'],
    logo: logoBaidu,
    logoAlt: '百度标识',
    category: 'algorithm',
  },
  {
    id: 8,
    title: '产品经理（增长方向）',
    company: '美团',
    industry: '互联网',
    location: '北京 · 朝阳区',
    salary: '18-30K',
    months: 14,
    match: 73,
    potential: 77,
    tags: ['增长', '数据分析', '需求分析'],
    reasons: reasons(70, 80, 72, 70),
    missingSkills: ['增长模型', '渠道运营'],
    logo: logoMeituan,
    logoAlt: '美团标识',
    category: 'pm',
  },
  {
    id: 9,
    title: 'Web 前端工程师',
    company: '阿里巴巴',
    industry: '互联网',
    location: '杭州 · 余杭区',
    salary: '16-26K',
    months: 16,
    match: 70,
    potential: 74,
    tags: ['Vue', 'JavaScript', 'CSS', '小程序'],
    reasons: reasons(72, 76, 68, 64),
    missingSkills: ['Node 服务端', '微前端'],
    logo: logoAlibaba,
    logoAlt: '阿里巴巴标识',
    category: 'frontend',
  },
  {
    id: 10,
    title: '数据开发工程师',
    company: '华为',
    industry: '通信/网络',
    location: '深圳 · 龙岗区',
    salary: '17-27K',
    months: 15,
    match: 65,
    potential: 72,
    tags: ['大数据', 'Flink', '数仓', 'SQL'],
    reasons: reasons(62, 74, 64, 60),
    missingSkills: ['Flink 实时计算', '数仓建模'],
    logo: logoHuawei,
    logoAlt: '华为标识',
    category: 'data',
  },
]
