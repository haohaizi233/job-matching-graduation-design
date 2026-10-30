<script setup lang="ts">
import campusArt from '@/assets/art/banner-campus-art.png'

defineProps<{
  greeting: string
  lines: string[]
}>()
</script>

<template>
  <section class="welcome-banner" aria-label="欢迎语">
    <img class="campus-art" :src="campusArt" alt="蓝天校园与纸飞机" />
    <div class="welcome-copy">
      <h1>{{ greeting }} <span class="wave">👋</span></h1>
      <p v-for="(line, index) in lines" :key="index">{{ line }}</p>
    </div>
  </section>
</template>

<style scoped>
.welcome-banner {
  height: 135px;
  position: relative;
  isolation: isolate;
  border-radius: 10px;
  overflow: hidden;
  background: linear-gradient(95deg, #e6f5ff 0%, #cae0ff 35%, #a9c7ff 68%, #c7ddfd 100%);
  margin-bottom: 12px;
}
.welcome-banner::before {
  position: absolute;
  content: '';
  inset: 0;
  z-index: -1;
  background: linear-gradient(
    90deg,
    rgba(235, 246, 255, 0.88) 0%,
    rgba(234, 244, 255, 0.66) 27%,
    rgba(205, 226, 255, 0.05) 63%
  );
}
.campus-art {
  position: absolute;
  right: 0;
  top: 0;
  height: 135px;
  width: 701px;
  object-fit: cover;
  z-index: -2;
}
.welcome-copy {
  padding: 22px 39px;
  position: relative;
}
.welcome-copy h1 {
  font-size: 26px;
  margin: 0 0 9px;
  font-weight: 900;
  letter-spacing: 0.1px;
  color: #071844;
  line-height: 1.2;
}
.wave {
  font-size: 24px;
  margin-left: 6px;
}
.welcome-copy p {
  color: #586888;
  font-size: 14px;
  margin: 0 0 5px;
  line-height: 1.45;
  font-weight: 500;
}

@media (max-width: 830px) {
  .welcome-copy {
    padding: 25px;
  }
}
@media (max-width: 540px) {
  .welcome-banner {
    height: 134px;
  }
  .campus-art {
    opacity: 0.8;
    right: -230px;
  }
  .welcome-copy {
    padding: 22px 14px;
  }
  .welcome-copy h1 {
    font-size: 21px;
  }
  .welcome-copy p {
    font-size: 11px;
    margin-bottom: 7px;
    max-width: 310px;
  }
}
</style>
