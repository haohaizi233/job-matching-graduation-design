<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import type { JobItem } from '@/types'

const props = defineProps<{ job: JobItem | null }>()
const emit = defineEmits<{ (e: 'close'): void }>()

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.job) emit('close')
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div v-if="job" class="dialog-backdrop" @click.self="emit('close')">
    <div class="job-dialog" role="dialog" aria-modal="true" aria-labelledby="dialogTitle">
      <button type="button" class="dialog-close" aria-label="关闭详情" @click="emit('close')">×</button>
      <span class="dialog-kicker">岗位详情 · 演示数据</span>
      <h2 id="dialogTitle">{{ job.title }}</h2>
      <p class="dialog-company">{{ job.company }}</p>
      <div class="dialog-score">匹配参考分 <strong>{{ job.match }}%</strong></div>
      <p class="dialog-desc">
        此页面为基于参考截图制作的交互演示，暂无真实招聘数据接入。岗位匹配分仅用于视觉展示，不代表录用概率。
      </p>
      <button type="button" class="dialog-primary" @click="emit('close')">知道了</button>
    </div>
  </div>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: #17284970;
  display: grid;
  place-items: center;
  z-index: 35;
  padding: 20px;
}
.job-dialog {
  position: relative;
  background: #fff;
  border-radius: 18px;
  width: min(460px, 100%);
  padding: 32px;
  box-shadow: 0 30px 90px #09183444;
}
.dialog-close {
  position: absolute;
  right: 18px;
  top: 12px;
  font-size: 27px;
  color: #8994a9;
}
.dialog-kicker {
  font-size: 11px;
  color: #367aff;
  font-weight: 800;
}
.job-dialog h2 {
  font-size: 22px;
  margin: 9px 0 4px;
}
.dialog-company {
  font-size: 13px;
  line-height: 1.7;
  color: #70809f;
  margin: 0;
}
.dialog-score {
  border-radius: 9px;
  background: #eff5ff;
  padding: 12px;
  margin: 19px 0;
  color: #586b8e;
}
.dialog-score strong {
  float: right;
  color: #266aff;
  font-size: 19px;
}
.dialog-desc {
  font-size: 13px;
  line-height: 1.7;
  color: #70809f;
}
.dialog-primary {
  color: white;
  background: #2b71f5;
  padding: 11px 30px;
  border-radius: 7px;
  display: block;
  margin-left: auto;
  font-weight: 800;
}
</style>
