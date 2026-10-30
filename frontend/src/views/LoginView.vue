<script setup lang="ts">
import { computed, ref } from 'vue'

import AuthCard from '@/components/login/AuthCard.vue'
import BenefitList from '@/components/login/BenefitList.vue'
import { useToast } from '@/composables/useToast'
import type { AuthMode } from '@/types'

import brandCap from '@/assets/art/brand-cap.png'
import loginSky from '@/assets/art/login-sky.png'
import loginArtwork from '@/assets/art/login-artwork.png'

const mode = ref<AuthMode>('login')
const { show } = useToast()

const headerHint = computed(() => (mode.value === 'register' ? '已有账号?' : '还没有账号?'))
const headerActionLabel = computed(() => (mode.value === 'register' ? '立即登录' : '立即注册'))

function toggleHeaderMode() {
  mode.value = mode.value === 'register' ? 'login' : 'register'
}

function handleFooter(name: string) {
  show(`${name}页面待接入实际内容`, 'top')
}
</script>

<template>
  <div class="login-page">
    <header class="site-header">
      <div class="brand">
        <img class="brand-logo" :src="brandCap" alt="毕业帽" />
        <span class="brand-title">大学生就业岗位画像与简历智能匹配系统</span>
      </div>
      <div class="header-actions">
        <span class="header-hint">{{ headerHint }}</span>
        <button type="button" class="register-link" @click="toggleHeaderMode">{{ headerActionLabel }}</button>
      </div>
    </header>

    <main class="page-hero">
      <img class="sky-patch" :src="loginSky" alt="" aria-hidden="true" />
      <img class="artwork" :src="loginArtwork" alt="" aria-hidden="true" />

      <section class="marketing" aria-label="产品介绍">
        <h1>
          让每一位大学生
          <span class="gradient-heading">找到更合适的职业起点</span>
        </h1>
        <p class="marketing-copy">
          基于你的简历画像和求职意向，<br />利用 AI 智能分析，精准匹配优质岗位，助力从校园走向职场。
        </p>
        <BenefitList />
      </section>

      <AuthCard v-model:mode="mode" />
    </main>

    <footer class="site-footer">
      <span>© 2024 大学生就业岗位画像与简历智能匹配系统</span>
      <span class="pipe">|</span>
      <a href="#" @click.prevent="handleFooter('帮助中心')">帮助中心</a>
      <span class="pipe">|</span>
      <a href="#" @click.prevent="handleFooter('隐私政策')">隐私政策</a>
      <span class="pipe">|</span>
      <a href="#" @click.prevent="handleFooter('服务条款')">服务条款</a>
    </footer>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f6f9fe;
  color: #101c44;
}
.site-header {
  height: 70px;
  position: relative;
  z-index: 4;
  background: linear-gradient(90deg, #fafcff, #f7faff);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 50px;
  box-shadow: 0 1px 0 rgba(195, 206, 230, 0.25);
}
.brand {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
}
.brand-logo {
  width: 51px;
  height: 52px;
  object-fit: contain;
  mix-blend-mode: multiply;
  flex-shrink: 0;
}
.brand-title {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: 0.3px;
  color: #112049;
  white-space: nowrap;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 20px;
  white-space: nowrap;
}
.header-hint {
  font-size: 15px;
  font-weight: 600;
  color: #52617d;
}
.register-link {
  height: 44px;
  min-width: 114px;
  border: 1.5px solid #a8c2ff;
  border-radius: 10px;
  color: #2470ff;
  background: linear-gradient(180deg, #fff, #f7faff);
  font-size: 17px;
  font-weight: 800;
  transition: 0.2s;
}
.register-link:hover {
  border-color: #2469ff;
  background: #eff5ff;
}

.page-hero {
  position: relative;
  isolation: isolate;
  flex: 1;
  min-height: 936px;
  overflow: hidden;
  background:
    radial-gradient(ellipse 50% 43% at 91% 17%, #b8d8ff 0%, rgba(186, 218, 255, 0.55) 46%, transparent 100%),
    radial-gradient(ellipse 62% 67% at 48% 22%, #c8e0ff 0%, #dbeaff 46%, transparent 86%),
    linear-gradient(118deg, #f4faff 0%, #e4f0ff 46%, #d6e8ff 75%, #eff6ff 100%);
}
.page-hero::after {
  content: '';
  position: absolute;
  inset: auto 0 0 0;
  height: 10%;
  z-index: -1;
  background: linear-gradient(0deg, rgba(250, 252, 255, 0.5), transparent);
  pointer-events: none;
}
.sky-patch {
  position: absolute;
  top: 0;
  left: 0;
  width: 856px;
  height: 940px;
  z-index: -1;
  pointer-events: none;
  object-fit: contain;
}
.artwork {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 856px;
  height: 940px;
  z-index: -1;
  pointer-events: none;
  object-fit: contain;
  object-position: bottom left;
}

.marketing {
  padding-top: 77px;
  padding-left: max(55px, 7.05vw);
  width: 58%;
  position: relative;
  z-index: 1;
}
.marketing h1 {
  font-size: 47px;
  line-height: 1.3;
  letter-spacing: 1px;
  font-weight: 900;
  margin: 0 0 15px;
  color: #08183e;
}
.marketing h1 .gradient-heading {
  display: block;
  background: linear-gradient(95deg, #2a81ff 4%, #396df7 43%, #8942fa 86%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  white-space: nowrap;
}
.marketing-copy {
  color: #697891;
  line-height: 1.72;
  font-size: 19px;
  letter-spacing: 0.1px;
  font-weight: 500;
  margin: 0;
}

.site-footer {
  height: 52px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 13px;
  font-size: 12.5px;
  color: #8994aa;
  background: #f7faff;
  border-top: 1px solid rgba(207, 220, 241, 0.45);
}
.site-footer a:hover {
  color: #2469ff;
}
.site-footer .pipe {
  color: #a3afc3;
}

@media (max-width: 1150px) {
  .site-header {
    padding: 0 30px;
  }
  .brand-title {
    font-size: 18px;
  }
  .marketing {
    padding-left: 50px;
    width: 52%;
  }
  .marketing h1 {
    font-size: 37px;
  }
  .marketing-copy {
    font-size: 16px;
  }
}
@media (max-width: 900px) {
  .page-hero {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    padding-bottom: 45px;
  }
  .marketing {
    width: 100%;
    padding: 56px 30px 20px;
  }
  .marketing h1 {
    font-size: clamp(28px, 5vw, 43px);
  }
  .marketing-copy {
    font-size: 16px;
  }
  .artwork {
    opacity: 0.32;
    object-fit: cover;
    object-position: bottom left;
  }
  .site-header {
    height: 66px;
    padding: 0 22px;
  }
  .brand-title {
    font-size: clamp(12px, 2.2vw, 18px);
    white-space: normal;
    line-height: 1.3;
  }
  .brand-logo {
    height: 43px;
    width: 43px;
  }
  .header-hint {
    display: none;
  }
}
@media (max-width: 520px) {
  .site-header {
    padding: 0 13px;
    gap: 10px;
  }
  .brand {
    gap: 5px;
  }
  .brand-title {
    font-size: 12px;
  }
  .brand-logo {
    width: 35px;
    height: 38px;
  }
  .register-link {
    min-width: 78px;
    height: 35px;
    font-size: 13px;
  }
  .marketing {
    padding: 44px 20px 10px;
  }
  .marketing h1 {
    letter-spacing: 0;
    font-size: clamp(27px, 7vw, 36px);
  }
  .marketing-copy {
    font-size: 13px;
  }
  .site-footer {
    flex-wrap: wrap;
    height: auto;
    min-height: 54px;
    padding: 10px;
    font-size: 10.5px;
    gap: 6px;
  }
}
</style>
