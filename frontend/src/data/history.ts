import type { HistoryRecordItem, HistoryStatusOption } from '@/types/history'

import logoBytedance from '@/assets/icons/company/bytedance.png'
import logoAlibaba from '@/assets/icons/company/alibaba.png'
import logoHuawei from '@/assets/icons/company/huawei.png'
import logoTencent from '@/assets/icons/company/tencent.png'
import logoMeituan from '@/assets/icons/company/meituan.png'
import logoBaidu from '@/assets/icons/company/baidu.png'

export const heroCopy = {
  title: '推荐历史',
  lines: ['每一次匹配的结果都会保存在这里，方便你回顾与对比', '选择历史记录查看当时的推荐结果（演示数据）'],
}

export const statusOptions: HistoryStatusOption[] = [
  { label: '全部状态', value: 'all' },
  { label: '已完成', value: 'done' },
  { label: '进行中', value: 'pending' },
  { label: '已过期', value: 'expired' },
]

export const statusText: Record<HistoryRecordItem['status'], string> = {
  done: '已完成',
  pending: '进行中',
  expired: '已过期',
}

export const historyRecords: HistoryRecordItem[] = [
  {
    id: 101,
    time: '2024-10-28 14:32',
    profileVersion: 'v2.0',
    mode: '综合排序',
    jobCount: 10,
    highMatchCount: 6,
    status: 'done',
    avgMatch: 82,
    jobs: [
      { id: 1, title: '产品经理（校园）', company: '字节跳动', salary: '20-35K', match: 92, logo: logoBytedance, logoAlt: '字节跳动标识' },
      { id: 2, title: '算法工程师（NLP方向）', company: '阿里巴巴', salary: '25-40K', match: 88, logo: logoAlibaba, logoAlt: '阿里巴巴标识' },
      { id: 3, title: '软件开发工程师', company: '华为', salary: '18-30K', match: 85, logo: logoHuawei, logoAlt: '华为标识' },
      { id: 4, title: '前端开发工程师', company: '腾讯', salary: '18-28K', match: 83, logo: logoTencent, logoAlt: '腾讯标识' },
    ],
  },
  {
    id: 102,
    time: '2024-10-25 09:18',
    profileVersion: 'v2.0',
    mode: '高匹配优先',
    jobCount: 10,
    highMatchCount: 4,
    status: 'done',
    avgMatch: 79,
    jobs: [
      { id: 2, title: '算法工程师（NLP方向）', company: '阿里巴巴', salary: '25-40K', match: 88, logo: logoAlibaba, logoAlt: '阿里巴巴标识' },
      { id: 5, title: '数据分析师', company: '美团', salary: '15-25K', match: 80, logo: logoMeituan, logoAlt: '美团标识' },
      { id: 7, title: '机器学习工程师', company: '百度', salary: '25-38K', match: 76, logo: logoBaidu, logoAlt: '百度标识' },
    ],
  },
  {
    id: 103,
    time: '2024-10-22 16:45',
    profileVersion: 'v1.5',
    mode: '高潜力优先',
    jobCount: 8,
    highMatchCount: 3,
    status: 'done',
    avgMatch: 75,
    jobs: [
      { id: 7, title: '机器学习工程师', company: '百度', salary: '25-38K', match: 76, logo: logoBaidu, logoAlt: '百度标识' },
      { id: 6, title: '后端开发工程师（Go）', company: '字节跳动', salary: '22-35K', match: 78, logo: logoBytedance, logoAlt: '字节跳动标识' },
      { id: 9, title: 'Web 前端工程师', company: '阿里巴巴', salary: '16-26K', match: 70, logo: logoAlibaba, logoAlt: '阿里巴巴标识' },
    ],
  },
  {
    id: 104,
    time: '2024-10-20 11:02',
    profileVersion: 'v1.5',
    mode: '综合排序',
    jobCount: 10,
    highMatchCount: 2,
    status: 'expired',
    avgMatch: 71,
    jobs: [
      { id: 3, title: '软件开发工程师', company: '华为', salary: '18-30K', match: 85, logo: logoHuawei, logoAlt: '华为标识' },
      { id: 10, title: '数据开发工程师', company: '华为', salary: '17-27K', match: 65, logo: logoHuawei, logoAlt: '华为标识' },
    ],
  },
  {
    id: 105,
    time: '2024-10-18 20:37',
    profileVersion: 'v1.0',
    mode: '综合排序',
    jobCount: 6,
    highMatchCount: 1,
    status: 'expired',
    avgMatch: 68,
    jobs: [
      { id: 4, title: '前端开发工程师', company: '腾讯', salary: '18-28K', match: 83, logo: logoTencent, logoAlt: '腾讯标识' },
      { id: 9, title: 'Web 前端工程师', company: '阿里巴巴', salary: '16-26K', match: 70, logo: logoAlibaba, logoAlt: '阿里巴巴标识' },
    ],
  },
  {
    id: 106,
    time: '2024-10-30 10:15',
    profileVersion: 'v2.0',
    mode: '高匹配优先',
    jobCount: 5,
    highMatchCount: 3,
    status: 'pending',
    avgMatch: 84,
    jobs: [
      { id: 1, title: '产品经理（校园）', company: '字节跳动', salary: '20-35K', match: 92, logo: logoBytedance, logoAlt: '字节跳动标识' },
      { id: 2, title: '算法工程师（NLP方向）', company: '阿里巴巴', salary: '25-40K', match: 88, logo: logoAlibaba, logoAlt: '阿里巴巴标识' },
      { id: 3, title: '软件开发工程师', company: '华为', salary: '18-30K', match: 85, logo: logoHuawei, logoAlt: '华为标识' },
    ],
  },
]
