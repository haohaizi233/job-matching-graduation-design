import type { MatchFilterOption, MatchModeOption } from '@/types/matching'

/** 智能匹配页静态文案与筛选选项（对齐设计稿 07-matching） */

export const heroCopy = {
  title: '智能匹配',
  lead: '基于你的简历画像和求职意向，智能推荐最合适的岗位',
  sub: '通过多维度语义理解与画像匹配算法，为你筛选高匹配度的优质岗位，助力职业发展',
}

/** 画像版本选项（演示下拉；真实画像版本以推荐运行记录为准） */
export const profileOptions: MatchFilterOption[] = [
  { label: 'v2.3（最新）', value: 'v2.3' },
  { label: 'v2.2', value: 'v2.2' },
  { label: 'v2.1', value: 'v2.1' },
]

export const profileUpdateNote = '更新于 2024-10-21'

export const matchModes: MatchModeOption[] = [
  { key: '综合推荐', label: '综合推荐', desc: '平衡匹配度与发展前景' },
  { key: '高匹配优先', label: '高匹配优先', desc: '更关注匹配度得分' },
  { key: '高潜力优先', label: '高潜力优先', desc: '挖掘潜在发展机会' },
]

export const topKOptions: MatchFilterOption[] = [
  { label: '20', value: '20' },
  { label: '10', value: '10' },
  { label: '5', value: '5' },
]

export const cityOptions: MatchFilterOption[] = [
  { label: '全部城市', value: '' },
  { label: '北京', value: '北京' },
  { label: '杭州', value: '杭州' },
  { label: '上海', value: '上海' },
  { label: '深圳', value: '深圳' },
  { label: '广州', value: '广州' },
]

export const categoryOptions: MatchFilterOption[] = [
  { label: '全部类别', value: '' },
  { label: '后端开发', value: 'backend' },
  { label: '算法/机器学习', value: 'algorithm' },
  { label: '前端开发', value: 'frontend' },
  { label: '数据开发', value: 'data' },
  { label: '产品经理', value: 'pm' },
]

/** 「重要提示」卡片文案（固定免责说明，非业务数据） */
export const noticeLines: string[] = [
  '匹配分仅用于排序参考，不代表录用概率。',
  '系统基于你的简历画像与岗位要求的相似度进行算法推荐，实际录用结果还会受到企业招聘需求、面试表现等多种因素影响。',
  '建议你结合自身情况，理性参考，积极投递。',
]

/** 结果卡「待补充技能」建议语 */
export const missingTipText = '建议在简历中补充相关项目经验或学习相关技术，以进一步提升匹配度。'

/** 匹配结果分布分段（分数段与设计稿一致） */
export const distributionBands: Array<{ label: string; min: number; max: number; color: string }> = [
  { label: '90-100分', min: 90, max: 101, color: '#2168ff' },
  { label: '80-89分', min: 80, max: 90, color: '#22b8e6' },
  { label: '70-79分', min: 70, max: 80, color: '#9754ff' },
  { label: '60-69分', min: 60, max: 70, color: '#ff9a2e' },
  { label: '60分以下', min: -1, max: 60, color: '#b9c4d8' },
]
