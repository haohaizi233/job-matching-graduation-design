<script setup lang="ts">
import { useRouter } from 'vue-router'

import { navItems } from '@/data/nav'
import { useToast } from '@/composables/useToast'

import sidebarStudent from '@/assets/art/sidebar-student.png'

defineProps<{ activeKey: string }>()

const router = useRouter()
const { show } = useToast()

function handleClick(item: (typeof navItems)[number]) {
  if (item.to) {
    router.push(item.to)
    return
  }
  show(`「${item.label}」属于页面导航演示，尚未连接实际业务后端。`)
}
</script>

<template>
  <aside class="sidebar">
    <nav class="side-nav" aria-label="主导航">
      <button
        v-for="item in navItems"
        :key="item.key"
        type="button"
        class="side-link"
        :class="{ active: item.key === activeKey }"
        :aria-current="item.key === activeKey ? 'page' : undefined"
        :aria-label="item.label"
        @click="handleClick(item)"
      >
        <img class="side-icon" :src="item.key === activeKey ? item.iconActive : item.icon" alt="" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </button>
    </nav>
    <div class="sidebar-motto" aria-label="让每一位大学生找到更合适的职业起点">
      <span>让每一位大学生<br />找到更合适的职业起点</span>
      <img :src="sidebarStudent" alt="飞向未来的大学生插画" />
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  position: fixed;
  top: 62px;
  left: 0;
  bottom: 0;
  width: 198px;
  border-right: 1px solid #edf2fb;
  background: linear-gradient(100deg, #fcfeff 0%, #f8fbff 94%);
  z-index: 10;
  display: flex;
  flex-direction: column;
  padding: 20px 9px 0 11px;
}
.side-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.side-link {
  height: 46px;
  width: 178px;
  display: flex;
  align-items: center;
  gap: 18px;
  border-radius: 9px;
  padding: 0 19px;
  position: relative;
  color: #222c45;
  font-size: 15px;
  font-weight: 600;
}
.side-link:hover {
  background: #edf4ff;
}
.side-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  object-fit: contain;
}
.side-link.active {
  color: #1264ff;
  background: #e9f1ff;
  font-weight: 800;
}
.side-link.active::before {
  content: '';
  background: #2673ff;
  border-radius: 1px;
  position: absolute;
  left: -11px;
  top: 0;
  width: 4px;
  height: 46px;
}
.sidebar-motto {
  margin-top: auto;
  position: relative;
  text-align: center;
  padding-bottom: 40px;
}
.sidebar-motto span {
  display: block;
  font-size: 13px;
  font-weight: 700;
  text-align: left;
  color: #6a7ca6;
  line-height: 1.65;
  margin-left: 23px;
  margin-bottom: 0;
}
.sidebar-motto img {
  width: 162px;
  height: 172px;
  object-fit: cover;
  display: block;
  margin: 6px auto 0;
  mix-blend-mode: multiply;
}

@media (max-width: 1100px) {
  .sidebar {
    width: 76px;
    align-items: center;
    padding: 20px 8px;
  }
  .side-link {
    width: 54px;
    justify-content: center;
    padding: 0;
  }
  .side-link span {
    display: none;
  }
  .side-link.active::before {
    left: -12px;
  }
  .sidebar-motto {
    display: none;
  }
}
@media (max-width: 540px) {
  .sidebar {
    top: auto;
    bottom: 0;
    width: 100%;
    height: 64px;
    flex-direction: row;
    padding: 4px 7px 0;
    border-right: 0;
    border-top: 1px solid #e8eef6;
    box-shadow: 0 -3px 12px #1d3e6f0d;
    z-index: 21;
  }
  .side-nav {
    flex-direction: row;
    overflow-x: auto;
    width: 100%;
    gap: 0;
    justify-content: space-around;
    scrollbar-width: none;
  }
  .side-nav::-webkit-scrollbar {
    display: none;
  }
  .side-link {
    flex: 0 0 48px;
    height: 49px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    justify-content: center;
    border-radius: 6px;
  }
  .side-link span {
    display: block;
    font-size: 9px;
    white-space: nowrap;
  }
  .side-icon {
    width: 18px;
    height: 18px;
  }
  .side-link.active::before {
    left: 8px;
    top: -4px;
    width: 32px;
    height: 3px;
  }
}
</style>
