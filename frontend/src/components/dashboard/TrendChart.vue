<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { trendDatasets } from '@/data/trend'
import type { TrendRange } from '@/types'

const props = defineProps<{ range: TrendRange }>()

/** 图表几何参数（与参考稿保持一致） */
const VIEW_W = 584
const X0 = 34
const X1 = 567
const TOP = 12
const BOTTOM = 129
const Y_MAX = 120
const TOOLTIP_W = 133

const svgRef = ref<SVGSVGElement | null>(null)
const hoverIndex = ref<number | null>(null)
const tooltipLeft = ref<number | null>(null)

const dataset = computed(() => trendDatasets[props.range])
const pointCount = computed(() => dataset.value.recommended.length)

watch(
  () => props.range,
  () => {
    hoverIndex.value = null
    tooltipLeft.value = null
  },
)

function xAt(i: number): number {
  return X0 + ((X1 - X0) * i) / (pointCount.value - 1)
}

function yAt(v: number): number {
  return BOTTOM - (v / Y_MAX) * (BOTTOM - TOP)
}

function linePath(values: number[]): string {
  return values.map((v, i) => `${i ? 'L' : 'M'}${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)}`).join(' ')
}

function areaPath(values: number[]): string {
  return `${linePath(values)} L${X1} ${BOTTOM} L${X0} ${BOTTOM} Z`
}

const gridY = [0, 30, 60, 90, 120]
const gridX = Array.from({ length: 9 }, (_, i) => X0 + ((X1 - X0) * i) / 8)

function axisLabelX(index: number): number {
  const labels = dataset.value.axisLabels
  return X0 + ((X1 - X0) * index) / (labels.length - 1)
}

const activeIndex = computed(() => hoverIndex.value ?? pointCount.value - 1)

const tooltipDate = computed(() => dataset.value.dates[activeIndex.value])
const tooltipRecommended = computed(() => dataset.value.recommended[activeIndex.value])
const tooltipHighMatch = computed(() => dataset.value.highMatch[activeIndex.value])

function handlePointerMove(event: PointerEvent) {
  const svg = svgRef.value
  if (!svg) return
  const bounds = svg.getBoundingClientRect()
  const px = ((event.clientX - bounds.left) / bounds.width) * VIEW_W
  const ratio = (px - X0) / (X1 - X0)
  const index = Math.max(0, Math.min(pointCount.value - 1, Math.round(ratio * (pointCount.value - 1))))
  hoverIndex.value = index
  tooltipLeft.value = Math.min(
    Math.max((xAt(index) / VIEW_W) * bounds.width - TOOLTIP_W / 2, 0),
    Math.max(0, bounds.width - TOOLTIP_W),
  )
}

function handlePointerLeave() {
  hoverIndex.value = null
  tooltipLeft.value = null
}

const tooltipStyle = computed(() =>
  tooltipLeft.value === null ? { left: 'auto', right: '36px' } : { left: `${tooltipLeft.value}px`, right: 'auto' },
)
</script>

<template>
  <div class="trend-chart-wrap">
    <svg
      ref="svgRef"
      class="trend-chart"
      viewBox="0 0 584 165"
      preserveAspectRatio="none"
      aria-label="推荐趋势折线图"
      role="img"
    >
      <defs>
        <linearGradient id="blueFade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#5aa0ff" stop-opacity=".23" />
          <stop offset="100%" stop-color="#9fc7ff" stop-opacity=".02" />
        </linearGradient>
        <linearGradient id="purpleFade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ad79f6" stop-opacity=".16" />
          <stop offset="100%" stop-color="#b783ff" stop-opacity=".02" />
        </linearGradient>
      </defs>

      <g>
        <template v-for="v in gridY" :key="`gy-${v}`">
          <line class="grid-line" :x1="X0" :y1="yAt(v)" :x2="X1" :y2="yAt(v)" />
          <text x="18" :y="yAt(v) + 4" text-anchor="end">{{ v }}</text>
        </template>
        <line v-for="(x, i) in gridX" :key="`gx-${i}`" class="grid-line" :x1="x" :y1="TOP" :x2="x" :y2="BOTTOM" />
        <text
          v-for="(label, index) in dataset.axisLabels"
          :key="`ax-${label}`"
          :x="axisLabelX(index)"
          y="150"
          text-anchor="middle"
        >
          {{ label }}
        </text>
      </g>

      <path :d="areaPath(dataset.recommended)" fill="url(#blueFade)" />
      <path :d="linePath(dataset.recommended)" class="line-blue" />
      <path :d="areaPath(dataset.highMatch)" fill="url(#purpleFade)" />
      <path :d="linePath(dataset.highMatch)" class="line-purple" />

      <line :x1="X1" :y1="TOP" :x2="X1" :y2="BOTTOM" stroke="#528cff" stroke-width="1.5" stroke-dasharray="2 2" />
      <circle :cx="xAt(pointCount - 1)" :cy="yAt(dataset.recommended[pointCount - 1])" r="6.3" fill="#fff" />
      <circle :cx="xAt(pointCount - 1)" :cy="yAt(dataset.recommended[pointCount - 1])" r="4.8" fill="#317bff" />
      <circle :cx="xAt(pointCount - 1)" :cy="yAt(dataset.highMatch[pointCount - 1])" r="6.3" fill="#fff" />
      <circle :cx="xAt(pointCount - 1)" :cy="yAt(dataset.highMatch[pointCount - 1])" r="4.8" fill="#9855ff" />

      <rect
        :x="X0"
        :y="TOP"
        :width="X1 - X0"
        :height="BOTTOM - TOP"
        fill="transparent"
        style="cursor: crosshair"
        @pointermove="handlePointerMove"
        @pointerleave="handlePointerLeave"
      />
    </svg>

    <div class="chart-tooltip" :style="tooltipStyle">
      <span class="tooltip-date">{{ tooltipDate }}</span>
      <div><i class="dot blue" />推荐岗位数 <b class="tabular">{{ tooltipRecommended }}</b></div>
      <div><i class="dot violet" />高匹配岗位数 <b class="tabular">{{ tooltipHighMatch }}</b></div>
    </div>
  </div>
</template>

<style scoped>
.trend-chart-wrap {
  margin-top: 12px;
  position: relative;
  height: 160px;
}
.trend-chart {
  display: block;
  width: 100%;
  height: 155px;
  overflow: visible;
}
.trend-chart text {
  font-family: Arial, 'Noto Sans CJK SC', sans-serif;
  font-size: 11px;
  fill: #8a99b3;
}
.trend-chart .grid-line {
  stroke: #e6ebf6;
  stroke-dasharray: 2.1 2.1;
  stroke-width: 1;
}
.trend-chart .line-blue,
.trend-chart .line-purple {
  fill: none;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.trend-chart .line-blue {
  stroke: #327fff;
}
.trend-chart .line-purple {
  stroke: #9550ff;
}
.chart-tooltip {
  position: absolute;
  top: 0;
  width: 133px;
  height: 70px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #dfe7f3;
  box-shadow: 0 2px 14px rgba(48, 87, 145, 0.12);
  z-index: 1;
  padding: 9px 10px;
  color: #5d6b86;
  font-size: 11px;
}
.chart-tooltip .tooltip-date {
  font-size: 11px;
  display: block;
  margin-bottom: 5px;
}
.chart-tooltip div {
  display: flex;
  align-items: center;
  margin-top: 3px;
  gap: 5px;
}
.chart-tooltip b {
  margin-left: auto;
  color: #152543;
}
</style>
