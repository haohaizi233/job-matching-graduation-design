<script setup lang="ts">
import { ref } from 'vue'

import IconGlyph from '@/components/common/IconGlyph.vue'
import TrendChart from '@/components/dashboard/TrendChart.vue'
import type { TrendRange } from '@/types'

const ranges: { value: TrendRange; label: string }[] = [
  { value: 7, label: '近7天' },
  { value: 30, label: '近30天' },
  { value: 90, label: '近3个月' },
]

const selected = ref<TrendRange>(30)
</script>

<template>
  <section class="trend-card card">
    <div class="card-header">
      <h2>
        岗位推荐趋势
        <button type="button" class="inline-info" title="显示近期推荐与高匹配岗位数量">
          <IconGlyph name="info" />
        </button>
      </h2>
      <div class="segmented" role="group" aria-label="趋势时间范围">
        <button
          v-for="range in ranges"
          :key="range.value"
          type="button"
          :class="{ selected: selected === range.value }"
          :aria-pressed="selected === range.value"
          @click="selected = range.value"
        >
          {{ range.label }}
        </button>
      </div>
    </div>

    <TrendChart :range="selected" />

    <div class="trend-legend">
      <span><i class="dot blue" />推荐岗位数</span>
      <span><i class="dot violet" />高匹配岗位数</span>
    </div>
  </section>
</template>

<style scoped>
.trend-card {
  height: 245px;
  padding: 13px 17px 5px;
}
.segmented {
  display: flex;
  align-items: center;
  gap: 3px;
  background: #f0f3f8;
  padding: 3px;
  border-radius: 12px;
  margin-top: -2px;
}
.segmented button {
  height: 28px;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 0 15px;
  font-size: 12px;
  color: #6f7d99;
}
.segmented button.selected {
  color: #2475ff;
  border-color: #c9dafe;
  background: #fff;
  box-shadow: 0 1px 3px #dfeaff;
  font-weight: 700;
}
.trend-legend {
  height: 26px;
  display: flex;
  justify-content: center;
  gap: 35px;
  align-items: center;
  color: #8592ad;
  font-size: 11px;
}
.trend-legend span {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 830px) {
  .trend-card {
    height: auto;
    min-height: 238px;
  }
}
@media (max-width: 540px) {
  .trend-card {
    padding: 12px 10px;
  }
  .segmented button {
    padding: 0 7px;
    font-size: 11px;
  }
}
</style>
