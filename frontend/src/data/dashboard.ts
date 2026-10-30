import type { ActivityItem, JobItem, NotificationItem, ProgressStep, StatCardItem } from '@/types'

import logoBytedance from '@/assets/icons/company/bytedance.png'
import logoAlibaba from '@/assets/icons/company/alibaba.png'
// 参考设计稿中「腾讯科技」一行使用的是通用企业标（蓝色环绕地球），如需真实腾讯标识可换为 tencent-qq.png
import logoTencent from '@/assets/icons/company/generic-globe.png'
import logoMeituan from '@/assets/icons/company/meituan.png'
import avatarStudent from '@/assets/art/avatar-student.png'

export const student = {
  name: '李同学',
  meta: '计算机科学与技术 · 大四',
  avatar: avatarStudent,
}

export const welcomeCopy = {
  greeting: '上午好，李同学',
  lines: ['新的一天，从探索更适合你的职业机会开始！', '基于你的简历画像，系统已为你准备了最新的岗位推荐。'],
}

export const statCards: StatCardItem[] = [
  {
    key: 'resume',
    name: '简历状态',
    value: '已完成',
    note: '最后更新：2024-10-20',
    tone: 'blue',
    glyph: 'file',
    chevron: true,
    target: '简历管理',
  },
  {
    key: 'profile',
    name: '当前画像版本',
    value: 'v2.3',
    note: '更新于：2024-10-21',
    tone: 'purple',
    glyph: 'plus',
    chevron: true,
    target: '我的画像',
  },
  {
    key: 'jobs',
    name: '可投递岗位',
    value: '1,286',
    note: '较上周',
    trendText: '+12% ↑',
    trendTone: 'green',
    tone: 'green',
    glyph: 'pie',
    chevron: false,
    miniBars: true,
    target: '岗位探索',
  },
  {
    key: 'matching',
    name: '最近推荐',
    value: '20',
    note: '今日新增',
    trendText: '5 ↑',
    trendTone: 'orange',
    tone: 'orange',
    glyph: 'star',
    chevron: true,
    target: '智能匹配',
  },
]

export const progressSteps: ProgressStep[] = [
  { title: '上传简历', note: '10-18', state: 'done' },
  { title: '解析画像', note: '10-18', state: 'done' },
  { title: '确认画像', note: '进行中', state: 'current' },
  { title: '智能推荐', note: '待完成', state: 'future' },
  { title: '反馈岗位', note: '待完成', state: 'future' },
]

export const progressStatus = {
  title: '正在基于你的简历内容生成多维度能力画像...',
  note: '预计还需 1-2 分钟，请耐心等待',
  percent: 68,
}

export const jobItems: JobItem[] = [
  {
    id: 1,
    title: '后端开发工程师',
    company: '字节跳动',
    tags: ['校招', '北京', '本科'],
    salary: '18-28K',
    match: 92,
    logo: logoBytedance,
    logoAlt: '字节跳动标识',
  },
  {
    id: 2,
    title: '算法工程师（NLP方向）',
    company: '阿里巴巴',
    tags: ['校招', '北京', '本科'],
    salary: '20-35K',
    match: 88,
    logo: logoAlibaba,
    logoAlt: '阿里巴巴标识',
  },
  {
    id: 3,
    title: 'Java开发工程师',
    company: '腾讯科技',
    tags: ['校招', '上海', '本科'],
    salary: '15-25K',
    match: 85,
    logo: logoTencent,
    logoAlt: '腾讯科技标识',
  },
  {
    id: 4,
    title: '产品经理（校招）',
    company: '美团',
    tags: ['校招', '深圳', '本科'],
    salary: '14-25K',
    match: 82,
    logo: logoMeituan,
    logoAlt: '美团标识',
  },
]

export const activityItems: ActivityItem[] = [
  {
    id: 1,
    title: '你上传了新的简历',
    desc: '系统正在解析你的简历内容...',
    time: '今天 10:24',
    dotTone: 'blue',
    iconTone: 'blue',
    glyph: 'file',
    line: true,
  },
  {
    id: 2,
    title: '完成了能力画像分析',
    desc: '生成了你的职业能力雷达图和标签',
    time: '昨天 16:20',
    dotTone: 'violet',
    iconTone: 'purple',
    glyph: 'briefcase',
    line: true,
  },
  {
    id: 3,
    title: '浏览了岗位：后端开发工程师（字节跳动）',
    desc: '你查看了该岗位的详细信息',
    time: '10-19  20:17',
    dotTone: 'green',
    iconTone: 'green',
    glyph: 'file',
    line: true,
  },
  {
    id: 4,
    title: '收藏了岗位：算法工程师（阿里巴巴）',
    desc: '已加入我的收藏',
    time: '10-18  14:36',
    dotTone: 'gray',
    iconTone: 'orange',
    glyph: 'star',
    line: false,
  },
]

export const notifications: NotificationItem[] = [
  { id: 1, text: '画像分析正在进行中' },
  { id: 2, text: '今日为你新增5个推荐岗位' },
  { id: 3, text: '你收藏的岗位发布了新动态' },
]

export const noticeText =
  '系统提供的岗位匹配评分仅基于你的简历画像与岗位要求的相似度计算，用于排序和推荐参考，不代表企业的实际录用概率。请结合自身情况综合判断，并主动了解企业的招聘要求。'
