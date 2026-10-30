import type {
  FeedbackRecordItem,
  FeedbackStatItem,
  FeedbackStatus,
  FeedbackStatusOption,
  FeedbackTrendRange,
} from '@/types/feedback'

import logoBytedance from '@/assets/icons/company/bytedance.png'
import logoAlibaba from '@/assets/icons/company/alibaba.png'
import logoHuawei from '@/assets/icons/company/huawei.png'
import logoTencent from '@/assets/icons/company/tencent.png'
import logoMeituan from '@/assets/icons/company/meituan.png'
import logoBaidu from '@/assets/icons/company/baidu.png'

export const heroCopy = {
  title: '反馈中心',
  lines: ['记录你对每个推荐岗位的反馈，帮助系统更懂你的求职偏好', '反馈数据为演示示例，尚未同步到服务端'],
}

export const statusText: Record<FeedbackStatus, string> = {
  interested: '感兴趣',
  notInterested: '不感兴趣',
  applied: '已投递',
  interviewed: '已面试',
  irrelevant: '不相关',
}

export const statusOptions: FeedbackStatusOption[] = [
  { label: '全部', value: 'all' },
  { label: '感兴趣', value: 'interested' },
  { label: '不感兴趣', value: 'notInterested' },
  { label: '已投递', value: 'applied' },
  { label: '已面试', value: 'interviewed' },
  { label: '不相关', value: 'irrelevant' },
]

export const feedbackStats: FeedbackStatItem[] = [
  { key: 'total', label: '反馈总数', value: '98', note: '近30天 +12' },
  { key: 'adopt', label: '反馈采纳率', value: '82%', note: '较上月 +4%' },
  { key: 'highMatch', label: '高匹配岗位', value: '36', note: '匹配度 85%+' },
  { key: 'interview', label: '面试转化', value: '12%', note: '已投递 → 面试' },
]

export const trendRanges: FeedbackTrendRange[] = [
  {
    label: '近7天',
    value: '7d',
    points: [
      { label: '10-24', value: 8 },
      { label: '10-25', value: 12 },
      { label: '10-26', value: 9 },
      { label: '10-27', value: 15 },
      { label: '10-28', value: 11 },
      { label: '10-29', value: 18 },
      { label: '10-30', value: 14 },
    ],
  },
  {
    label: '近30天',
    value: '30d',
    points: [
      { label: '第1周', value: 42 },
      { label: '第2周', value: 55 },
      { label: '第3周', value: 48 },
      { label: '第4周', value: 63 },
    ],
  },
  {
    label: '近3个月',
    value: '3m',
    points: [
      { label: '8月', value: 128 },
      { label: '9月', value: 156 },
      { label: '10月', value: 182 },
    ],
  },
]

export const feedbackRecords: FeedbackRecordItem[] = [
  {
    id: 1,
    title: '产品经理（校园）',
    company: '字节跳动',
    industry: '互联网',
    salary: '20-35K',
    location: '北京 · 海淀区',
    time: '2024-10-30 09:20',
    status: 'interested',
    note: '岗位方向与求职意向一致，准备投递。',
    bookmarked: true,
    logo: logoBytedance,
    logoAlt: '字节跳动标识',
    trend: [4, 6, 5, 8, 7, 9, 11],
  },
  {
    id: 2,
    title: '算法工程师（NLP方向）',
    company: '阿里巴巴',
    industry: '互联网',
    salary: '25-40K',
    location: '杭州 · 西湖区',
    time: '2024-10-29 16:45',
    status: 'applied',
    note: '已通过官网投递，等待笔试通知。',
    bookmarked: true,
    logo: logoAlibaba,
    logoAlt: '阿里巴巴标识',
    trend: [3, 5, 7, 6, 8, 10, 12],
  },
  {
    id: 3,
    title: '软件开发工程师',
    company: '华为',
    industry: '通信/网络',
    salary: '18-30K',
    location: '深圳 · 龙岗区',
    time: '2024-10-28 11:32',
    status: 'interviewed',
    note: '一面通过，二面安排在下周。',
    bookmarked: false,
    logo: logoHuawei,
    logoAlt: '华为标识',
    trend: [6, 5, 7, 9, 8, 7, 10],
  },
  {
    id: 4,
    title: '前端开发工程师',
    company: '腾讯',
    industry: '互联网',
    salary: '18-28K',
    location: '深圳 · 南山区',
    time: '2024-10-27 14:08',
    status: 'interested',
    note: '',
    bookmarked: false,
    logo: logoTencent,
    logoAlt: '腾讯标识',
    trend: [2, 4, 3, 6, 5, 7, 8],
  },
  {
    id: 5,
    title: '数据分析师',
    company: '美团',
    industry: '互联网',
    salary: '15-25K',
    location: '北京 · 朝阳区',
    time: '2024-10-26 10:55',
    status: 'notInterested',
    note: '工作内容偏业务分析，与技术方向不符。',
    bookmarked: false,
    logo: logoMeituan,
    logoAlt: '美团标识',
    trend: [5, 4, 6, 3, 4, 5, 4],
  },
  {
    id: 6,
    title: '机器学习工程师',
    company: '百度',
    industry: '互联网',
    salary: '25-38K',
    location: '北京 · 海淀区',
    time: '2024-10-25 19:26',
    status: 'irrelevant',
    note: '要求博士学历，暂不符合条件。',
    bookmarked: false,
    logo: logoBaidu,
    logoAlt: '百度标识',
    trend: [3, 3, 4, 2, 3, 4, 3],
  },
]
