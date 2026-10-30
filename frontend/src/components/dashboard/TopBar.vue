<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import IconGlyph from '@/components/common/IconGlyph.vue'
import { useAuth } from '@/composables/useAuth'
import { notifications, student } from '@/data/dashboard'

import brandCap from '@/assets/art/brand-cap.png'
import notificationIcon from '@/assets/icons/topbar/notification.svg'
import searchIcon from '@/assets/icons/topbar/search.svg'

const emit = defineEmits<{
  (e: 'search', query: string): void
  (e: 'submit', query: string): void
  (e: 'logout'): void
}>()
const router = useRouter()
const { state: authState, logout } = useAuth()

/** 联调：顶栏展示真实登录用户名，未登录时回退演示名 */
const displayName = computed(() => authState.user?.username || student.name)

const query = ref('')
const openMenu = ref<'notification' | 'profile' | null>(null)

function toggleMenu(menu: 'notification' | 'profile') {
  openMenu.value = openMenu.value === menu ? null : menu
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  if (target && !target.closest('.popover-host')) openMenu.value = null
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))

function handleSearch() {
  emit('submit', query.value)
}

function handleSearchInput() {
  emit('search', query.value)
}

function goSettings() {
  openMenu.value = null
  router.push('/settings')
}

async function handleLogout() {
  openMenu.value = null
  await logout()
  emit('logout')
  router.push('/login')
}
</script>

<template>
  <header class="topbar">
    <a href="#/dashboard" class="brand" aria-label="大学生就业岗位画像与简历智能匹配系统">
      <img :src="brandCap" class="brand-logo" alt="学士帽标识" />
      <span>大学生就业岗位画像与简历智能匹配系统</span>
    </a>

    <div class="topbar-right">
      <form class="global-search" role="search" @submit.prevent="handleSearch">
        <img class="search-icon" :src="searchIcon" alt="" aria-hidden="true" />
        <input
          v-model="query"
          aria-label="搜索岗位、公司或关键词"
          placeholder="搜索岗位、公司或关键词..."
          autocomplete="off"
          @input="handleSearchInput"
        />
      </form>

      <div class="popover-host">
        <button
          class="notification-button"
          title="消息通知"
          aria-label="消息通知"
          :aria-expanded="openMenu === 'notification'"
          @click.stop="toggleMenu('notification')"
        >
          <img class="bell-icon" :src="notificationIcon" alt="" aria-hidden="true" />
          <span class="notification-count">{{ notifications.length }}</span>
        </button>
        <div v-show="openMenu === 'notification'" class="popover notifications">
          <div class="popover-title">消息通知 <span class="muted">{{ notifications.length }}条未读</span></div>
          <p v-for="item in notifications" :key="item.id">{{ item.text }}</p>
        </div>
      </div>

      <div class="topbar-separator" />

      <div class="popover-host">
        <button
          class="user-menu-button"
          aria-label="个人账户菜单"
          :aria-expanded="openMenu === 'profile'"
          @click.stop="toggleMenu('profile')"
        >
          <img class="avatar" :src="student.avatar" :alt="`${displayName}头像`" />
          <span class="user-meta">
            <strong>{{ displayName }}</strong>
            <small>{{ student.meta }}</small>
          </span>
          <IconGlyph name="chevron" class="chevron-down" />
        </button>
        <div v-show="openMenu === 'profile'" class="popover user-popover">
          <div class="popover-title">{{ displayName }} <span class="muted">学生账号</span></div>
          <button type="button" @click="goSettings">个人设置</button>
          <button type="button" @click="handleLogout">退出登录</button>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  height: 62px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: fixed;
  z-index: 20;
  left: 0;
  right: 0;
  top: 0;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 1px 3px rgba(35, 84, 138, 0.035);
  padding: 0 26px;
  white-space: nowrap;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 900;
  font-size: 19px;
  letter-spacing: 0.1px;
  color: #09173d;
}
.brand-logo {
  width: 43px;
  height: 41px;
  object-fit: contain;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 23px;
  height: 100%;
}
.global-search {
  width: 389px;
  height: 36px;
  border-radius: 30px;
  background: #f2f5fa;
  display: flex;
  gap: 9px;
  align-items: center;
  padding: 0 16px;
  color: #a6b0c6;
  box-shadow: inset 0 1px 2px rgba(12, 53, 120, 0.01);
}
.search-icon {
  width: 17px;
  height: 17px;
  flex-shrink: 0;
}
.global-search input {
  color: #243457;
  width: 100%;
  background: transparent;
  border: 0;
  outline: 0;
  font-size: 12px;
}
.global-search input::placeholder {
  color: #9da8bf;
}
.notification-button {
  width: 36px;
  height: 39px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.bell-icon {
  width: 23px;
  height: 23px;
}
.notification-count {
  position: absolute;
  top: -1px;
  right: 1px;
  border-radius: 30px;
  background: #ff4454;
  color: #fff;
  line-height: 17px;
  min-width: 17px;
  height: 17px;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
}
.topbar-separator {
  height: 28px;
  width: 1px;
  background: #e5e9f2;
  margin-left: -9px;
  margin-right: -9px;
}
.user-menu-button {
  display: flex;
  align-items: center;
  gap: 11px;
  text-align: left;
  padding: 0;
}
.user-menu-button .avatar {
  width: 43px;
  height: 43px;
  border-radius: 50%;
  object-fit: cover;
}
.user-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.user-meta strong {
  font-weight: 800;
  font-size: 13px;
}
.user-meta small {
  font-size: 12px;
  color: #74819e;
}
.chevron-down {
  width: 15px;
  height: 15px;
  transform: rotate(90deg);
  color: #142247;
  margin-left: 12px;
}
.popover-host {
  position: relative;
}
.popover {
  position: absolute;
  top: calc(100% + 13px);
  right: 0;
  background: #fff;
  border: 1px solid #e6ecf6;
  box-shadow: 0 9px 36px rgba(30, 52, 95, 0.13);
  border-radius: 12px;
  min-width: 245px;
  padding: 13px;
  white-space: normal;
}
.popover-title {
  font-size: 14px;
  font-weight: 800;
  padding: 5px 7px 12px;
  border-bottom: 1px solid #eef2fa;
  display: flex;
  justify-content: space-between;
  gap: 18px;
}
.popover-title .muted {
  font-size: 11px;
  font-weight: 400;
}
.notifications p {
  padding: 7px 5px;
  color: #5b6a8e;
  margin: 0;
  border-bottom: 1px solid #f5f7fc;
}
.notifications p:last-child {
  border: 0;
}
.user-popover button {
  display: block;
  width: 100%;
  padding: 10px;
  text-align: left;
  border-radius: 5px;
}
.user-popover button:hover {
  background: #f4f7ff;
}

@media (max-width: 1380px) {
  .brand {
    font-size: 17px;
  }
  .topbar-right {
    gap: 15px;
  }
  .global-search {
    width: 315px;
  }
}
@media (max-width: 1100px) {
  .topbar {
    padding: 0 18px;
  }
  .brand {
    font-size: 15px;
  }
  .brand-logo {
    width: 36px;
    height: 36px;
  }
  .global-search {
    width: 240px;
  }
}
@media (max-width: 830px) {
  .topbar {
    height: 58px;
    padding: 0 12px;
  }
  .brand span {
    font-size: 13px;
    max-width: 290px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .topbar-right {
    gap: 6px;
  }
  .global-search {
    display: none;
  }
  .topbar-separator {
    display: none;
  }
  .user-meta {
    display: none;
  }
  .user-menu-button .chevron-down {
    margin-left: 1px;
  }
}
@media (max-width: 540px) {
  .topbar {
    padding: 0 8px;
  }
  .brand {
    gap: 6px;
  }
  .brand span {
    max-width: 195px;
    font-size: 11px;
  }
  .brand-logo {
    width: 31px;
    height: 31px;
  }
  .notification-button {
    width: 28px;
  }
  .user-menu-button .avatar {
    height: 34px;
    width: 34px;
  }
  .topbar-right {
    gap: 7px;
  }
}
</style>
