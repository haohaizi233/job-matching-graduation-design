<script setup lang="ts">
import IconGlyph from '@/components/common/IconGlyph.vue'

import megaphoneIcon from '@/assets/icons/common/megaphone-orange.png'

defineProps<{ text: string }>()
</script>

<template>
  <section class="notice-card" aria-label="重要提示">
    <img class="notice-megaphone" :src="megaphoneIcon" alt="" aria-hidden="true" />
    <div>
      <strong>重要提示</strong>
      <p>{{ text }}</p>
    </div>
    <span class="notice-document" aria-hidden="true"><IconGlyph name="file" /></span>
  </section>
</template>

<style scoped>
.notice-card {
  height: 102px;
  border: 1px solid #ffd8c0;
  border-radius: 10px;
  background: linear-gradient(115deg, #fff8f4, #fffaf8);
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 14px;
  overflow: hidden;
  position: relative;
}
.notice-megaphone {
  display: block;
  width: 21px;
  height: 21px;
  object-fit: contain;
  transform: rotate(7deg);
  flex-shrink: 0;
}
.notice-card div {
  flex: 1;
  position: relative;
  z-index: 1;
}
.notice-card strong {
  font-size: 12px;
  color: #fb7b38;
}
.notice-card p {
  max-width: 400px;
  margin: 4px 0 0;
  color: #8793aa;
  font-size: 11px;
  line-height: 1.6;
}
.notice-document {
  color: #ffb477;
  position: absolute;
  right: 16px;
  bottom: 15px;
  width: 67px;
  height: 67px;
  background: linear-gradient(140deg, #ffe9d3, #fffaf8);
  clip-path: polygon(0 0, 78% 0, 100% 22%, 100% 100%, 0 100%);
  border-radius: 7px;
  opacity: 0.86;
  display: grid;
  place-items: center;
}
.notice-document .glyph {
  height: 42px;
  width: 42px;
  color: #fff;
  opacity: 0.66;
}

@media (max-width: 830px) {
  .notice-card {
    height: auto;
    min-height: 100px;
  }
}
@media (max-width: 540px) {
  .notice-card p {
    font-size: 10px;
  }
  .notice-document {
    opacity: 0.25;
  }
}
</style>
