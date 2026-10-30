import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      redirect: '/login',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录', public: true },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { title: '工作台' },
    },
    {
      path: '/resume',
      name: 'resume',
      component: () => import('@/views/ResumeView.vue'),
      meta: { title: '简历管理' },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('@/views/ProfileView.vue'),
      meta: { title: '我的画像' },
    },
    {
      path: '/jobs',
      name: 'jobs',
      component: () => import('@/views/JobsView.vue'),
      meta: { title: '岗位探索' },
    },
    {
      path: '/job/:id',
      name: 'job-detail',
      component: () => import('@/views/JobDetailView.vue'),
      meta: { title: '岗位详情' },
    },
    {
      path: '/matching',
      name: 'matching',
      component: () => import('@/views/MatchingView.vue'),
      meta: { title: '智能匹配' },
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('@/views/HistoryView.vue'),
      meta: { title: '推荐历史' },
    },
    {
      path: '/feedback',
      name: 'feedback',
      component: () => import('@/views/FeedbackView.vue'),
      meta: { title: '反馈中心' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: '个人设置' },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/login',
    },
  ],
})

router.afterEach((to) => {
  const page = typeof to.meta.title === 'string' ? to.meta.title : ''
  document.title = page
    ? `${page} · 大学生就业岗位画像与简历智能匹配系统`
    : '大学生就业岗位画像与简历智能匹配系统'
})

/** 联调：除公开页（登录）外均需会话；无 token 一律回登录页 */
router.beforeEach((to) => {
  const token = localStorage.getItem('jm_token')
  if (to.meta.public) return true
  if (!token) return { path: '/login' }
  return true
})

export default router
