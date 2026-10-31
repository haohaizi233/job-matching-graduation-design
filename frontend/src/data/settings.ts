import type {
  SettingsSelectOption,
  SettingsToggleItem,
} from '@/types/settings'

/**
 * 个人设置页的**展示元数据**（文案/选项/字段定义）。
 *
 * 真实取值一律来自服务端 /students/me/settings（见 api/settings.ts），
 * 本文件不再存放任何演示身份、假设备或假安全日志数据。
 */

export const heroCopy = {
  title: '个人设置',
  lines: [
    '管理你的账号资料、通知偏好与推荐设置',
    '业务设置保存在你的账号下（服务端持久化）；主题等显示偏好仅保存在本机浏览器',
  ],
}

export const schoolYearOptions: SettingsSelectOption[] = [
  { label: '2020', value: '2020' },
  { label: '2021', value: '2021' },
  { label: '2022', value: '2022' },
  { label: '2023', value: '2023' },
  { label: '2024', value: '2024' },
  { label: '2025', value: '2025' },
]

export const graduateYearOptions: SettingsSelectOption[] = [
  { label: '2024', value: '2024' },
  { label: '2025', value: '2025' },
  { label: '2026', value: '2026' },
  { label: '2027', value: '2027' },
]

export const regionOptions: SettingsSelectOption[] = [
  { label: '浙江 · 杭州', value: 'zj-hz' },
  { label: '北京', value: 'bj' },
  { label: '上海', value: 'sh' },
  { label: '广东 · 深圳', value: 'gd-sz' },
  { label: '广东 · 广州', value: 'gd-gz' },
]

/** 主题是纯客户端显示偏好：只存 localStorage，不上传服务端 */
export const themeOptions: SettingsSelectOption[] = [
  { label: '浅色模式', value: 'light' },
  { label: '深色模式', value: 'dark' },
  { label: '跟随系统', value: 'system' },
]

export const notificationToggles: SettingsToggleItem[] = [
  { key: 'siteMessage', label: '站内消息', desc: '接收系统通知与公告', value: true },
  { key: 'emailNotice', label: '邮件通知', desc: '重要动态发送到绑定邮箱', value: false },
  { key: 'matchAlert', label: '匹配提醒', desc: '有高匹配岗位时提醒我', value: true },
  { key: 'weeklyReport', label: '周报推送', desc: '每周推送求职进展周报', value: true },
]

export const resumeParseToggles: SettingsToggleItem[] = [
  { key: 'autoParse', label: '上传后自动解析', desc: '简历上传完成后立即解析', value: true },
  { key: 'ocrImages', label: '识别图片中的文字', desc: '对扫描件启用 OCR（当前解析链路未接入 OCR，此项为预留偏好）', value: false },
]

export const privacyToggles: SettingsToggleItem[] = [
  { key: 'publicResume', label: '公开简历', desc: '允许企业在人才库中搜索到我', value: true },
  { key: 'companyView', label: '允许企业查看', desc: '投递后企业可查看完整简历', value: true },
  { key: 'hideSalary', label: '隐藏期望薪资', desc: '不在公开资料中展示期望薪资', value: false },
]

/**
 * 密码与安全条目。`implemented: false` 表示后端尚未提供安全实现，
 * 页面必须清晰标注"未接入"，不得模拟成功。
 */
export interface SecurityItem {
  key: string
  label: string
  desc: string
  implemented: boolean
}

export const securityItems: SecurityItem[] = [
  { key: 'password', label: '修改密码', desc: '验证原密码后生效，其他登录设备将自动退出', implemented: true },
  { key: 'phone', label: '绑定手机', desc: '未接入短信服务，暂不可用', implemented: false },
  { key: 'email', label: '绑定邮箱', desc: '未接入邮件验证服务，暂不可用', implemented: false },
  { key: 'twoFactor', label: '二次验证', desc: '未接入二次验证服务，暂不可用', implemented: false },
]

/** 纯客户端偏好存储键（只存主题等显示偏好） */
export const STORAGE_KEY = 'job-matching-settings-client'
