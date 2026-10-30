import type { NavItem } from '@/types'

import dashboardIcon from '@/assets/icons/nav/dashboard.svg'
import dashboardActiveIcon from '@/assets/icons/nav/dashboard-active.svg'
import resumeIcon from '@/assets/icons/nav/resume.svg'
import resumeActiveIcon from '@/assets/icons/nav/resume-active.svg'
import profileIcon from '@/assets/icons/nav/profile.svg'
import profileActiveIcon from '@/assets/icons/nav/profile-active.svg'
import jobsIcon from '@/assets/icons/nav/jobs.svg'
import jobsActiveIcon from '@/assets/icons/nav/jobs-active.svg'
import matchingIcon from '@/assets/icons/nav/matching.svg'
import matchingActiveIcon from '@/assets/icons/nav/matching-active.svg'
import historyIcon from '@/assets/icons/nav/history.svg'
import historyActiveIcon from '@/assets/icons/nav/history-active.svg'
import feedbackIcon from '@/assets/icons/nav/feedback.svg'
import feedbackActiveIcon from '@/assets/icons/nav/feedback-active.svg'
import settingsIcon from '@/assets/icons/nav/settings.svg'

/**
 * 侧边导航（图标取自 UI/assets/icons/nav）
 * settings 无 -active 选中态版本，选中态复用默认文件。
 */
export const navItems: NavItem[] = [
  { key: 'dashboard', label: '工作台', icon: dashboardIcon, iconActive: dashboardActiveIcon, to: '/dashboard' },
  { key: 'resume', label: '简历管理', icon: resumeIcon, iconActive: resumeActiveIcon, to: '/resume' },
  { key: 'profile', label: '我的画像', icon: profileIcon, iconActive: profileActiveIcon, to: '/profile' },
  { key: 'jobs', label: '岗位探索', icon: jobsIcon, iconActive: jobsActiveIcon },
  { key: 'matching', label: '智能匹配', icon: matchingIcon, iconActive: matchingActiveIcon },
  { key: 'history', label: '推荐历史', icon: historyIcon, iconActive: historyActiveIcon },
  { key: 'feedback', label: '反馈中心', icon: feedbackIcon, iconActive: feedbackActiveIcon },
  { key: 'settings', label: '个人设置', icon: settingsIcon, iconActive: settingsIcon },
]
