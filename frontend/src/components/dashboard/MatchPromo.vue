<script setup lang="ts">
import IconGlyph from '@/components/common/IconGlyph.vue'

import matchingArt from '@/assets/art/matching-art.png'

defineEmits<{ (e: 'start'): void }>()
</script>

<template>
  <button type="button" class="match-promo" @click="$emit('start')">
    <img :src="matchingArt" class="matching-art" alt="AI简历分析装饰图" />
    <span class="promo-tag">AI 智能匹配</span>
    <span class="promo-heading">
      开始智能匹配
      <span class="promo-arrow"><IconGlyph name="arrow" /></span>
    </span>
    <span class="promo-desc">基于你的简历画像和求职意向<br />为你推荐更合适的岗位</span>
  </button>
</template>

<style scoped>
.match-promo {
  position: relative;
  height: 225px;
  overflow: hidden;
  border-radius: 10px;
  background: linear-gradient(115deg, #5697ff 0%, #4379f8 43%, #a6baff 77%, #dcd4ff 100%);
  text-align: left;
  color: #fff;
  padding: 25px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  isolation: isolate;
  border: 1px solid rgba(255, 255, 255, 0.45);
  box-shadow: 0 2px 6px rgba(49, 90, 151, 0.05);
}
.match-promo::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -2;
  background: linear-gradient(30deg, transparent 0 46%, rgba(181, 162, 255, 0.16) 46% 51%, transparent 70%);
}
.matching-art {
  position: absolute;
  right: 0;
  top: 0;
  height: 225px;
  width: 241px;
  object-fit: contain;
  z-index: -1;
}
.promo-tag {
  padding: 7px 13px;
  background: rgba(255, 255, 255, 0.25);
  border-radius: 26px;
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  margin-bottom: 16px;
}
.promo-heading {
  display: flex;
  align-items: center;
  gap: 18px;
  font-size: 23px;
  font-weight: 900;
  line-height: 1.25;
  white-space: nowrap;
  letter-spacing: 0.2px;
}
.promo-arrow {
  display: inline-flex;
  background: #fff;
  color: #246fff;
  width: 33px;
  height: 33px;
  border-radius: 50%;
  align-items: center;
  justify-content: center;
}
.promo-arrow .glyph {
  width: 20px;
  height: 20px;
}
.promo-desc {
  font-size: 14px;
  line-height: 1.8;
  color: #fff;
  margin-top: 12px;
}
.match-promo:hover .promo-arrow {
  transform: translateX(3px);
  transition: transform 0.2s;
}

@media (max-width: 1100px) {
  .promo-heading {
    font-size: 19px;
  }
}
@media (max-width: 830px) {
  .match-promo {
    height: 215px;
  }
}
@media (max-width: 540px) {
  .promo-heading {
    font-size: 21px;
  }
}
</style>
