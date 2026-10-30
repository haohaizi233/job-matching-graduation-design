import type {
  DeviceItem,
  SecurityLogItem,
  SettingsSelectOption,
  SettingsToggleItem,
} from '@/types/settings'

export const heroCopy = {
  title: '个人设置',
  lines: ['管理你的账号资料、通知偏好与推荐设置', '设置仅保存在当前浏览器（演示），不会上传服务端'],
}

export const defaultSettings = {
  nickname: '李同学',
  school: '浙江大学',
  major: '软件工程',
  enrollYear: '2021',
  graduateYear: '2025',
  region: '浙江 · 杭州',
  theme: 'light',
  intentTags: ['产品经理', '前端开发', '杭州', '互联网', '校招'],
}

export const schoolYearOptions: SettingsSelectOption[] = [
  { label: '2020', value: '2020' },
  { label: '2021', value: '2021' },
  { label: '2022', value: '2022' },
  { label: '2023', value: '2023' },
  { label: '2024', value: '2024' },
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
  { key: 'ocrImages', label: '识别图片中的文字', desc: '对扫描件启用 OCR（演示）', value: false },
]

export const privacyToggles: SettingsToggleItem[] = [
  { key: 'publicResume', label: '公开简历', desc: '允许企业在人才库中搜索到我', value: true },
  { key: 'companyView', label: '允许企业查看', desc: '投递后企业可查看完整简历', value: true },
  { key: 'hideSalary', label: '隐藏期望薪资', desc: '不在公开资料中展示期望薪资', value: false },
]

export const securityItems = [
  { key: 'password', label: '修改密码', desc: '定期修改密码有助于账号安全' },
  { key: 'phone', label: '绑定手机', desc: '已绑定 138****6789' },
  { key: 'email', label: '绑定邮箱', desc: '已绑定 li***@zju.edu.cn' },
  { key: 'twoFactor', label: '二次验证', desc: '登录时进行短信验证' },
]

export const deviceList: DeviceItem[] = [
  { id: 1, name: 'Chrome · Windows', place: '浙江 杭州', time: '2024-10-30 14:20', current: true },
  { id: 2, name: 'Safari · iPhone', place: '浙江 杭州', time: '2024-10-28 21:05', current: false },
  { id: 3, name: 'Edge · Windows', place: '上海', time: '2024-10-21 09:47', current: false },
]

export const securityLogs: SecurityLogItem[] = [
  { id: 1, time: '2024-10-30 14:20', event: '账号登录成功', location: '浙江 杭州' },
  { id: 2, time: '2024-10-28 21:05', event: '账号登录成功', location: '浙江 杭州' },
  { id: 3, time: '2024-10-26 10:33', event: '修改了通知偏好', location: '浙江 杭州' },
  { id: 4, time: '2024-10-21 09:47', event: '账号登录成功', location: '上海' },
  { id: 5, time: '2024-10-18 16:12', event: '修改了登录密码', location: '浙江 杭州' },
]

export const STORAGE_KEY = 'job-matching-settings'
