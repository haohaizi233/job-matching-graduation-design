<script setup lang="ts">
import IconGlyph from '@/components/common/IconGlyph.vue'
import type { ProgressStep } from '@/types'

defineProps<{
  steps: ProgressStep[]
  status: {
    title: string
    note: string
    percent: number
  }
}>()

defineEmits<{ (e: 'guide'): void }>()
</script>

<template>
  <section class="progress-panel card">
    <div class="card-header progress-head">
      <div>
        <h2>求职进度</h2>
        <span class="minor-heading">5个步骤，完成简历分析即可获得个性化岗位推荐</span>
      </div>
      <button type="button" class="text-link" @click="$emit('guide')">
        查看详细指南
        <IconGlyph name="chevron" />
      </button>
    </div>

    <div class="step-list">
      <div v-for="(step, index) in steps" :key="step.title" class="step" :class="step.state">
        <span class="step-point">
          <IconGlyph v-if="step.state === 'done'" name="check" class="step-check" />
          <template v-else>{{ index + 1 }}</template>
        </span>
        <strong>{{ step.title }}</strong>
        <small>{{ step.note }}</small>
      </div>
    </div>

    <div class="progress-status">
      <span class="loading-spinner" aria-hidden="true" />
      <span class="progress-copy">
        <strong>{{ status.title }}</strong>
        <small>{{ status.note }}</small>
      </span>
      <span class="progress-ring" :style="{ '--progress': status.percent }" :aria-label="`完成进度${status.percent}%`">
        <span>{{ status.percent }}%</span>
      </span>
    </div>
  </section>
</template>

<style scoped>
.progress-panel {
  height: 225px;
  padding: 17px 16px;
}
.progress-head h2 {
  display: inline;
  margin-right: 13px;
}
.minor-heading {
  font-size: 12px;
  color: #8391aa;
  white-space: nowrap;
}
.step-list {
  display: flex;
  justify-content: space-between;
  position: relative;
  margin: 21px 8px 17px 1px;
}
.step-list::before {
  content: '';
  position: absolute;
  z-index: 0;
  left: 9%;
  right: 9%;
  height: 2px;
  top: 16px;
  background: linear-gradient(90deg, #2777fa 0%, #2777fa 51%, #e4eaf1 51%, #e4eaf1 100%);
}
.step {
  z-index: 1;
  min-width: 72px;
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 6px;
}
.step-point {
  height: 32px;
  width: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 800;
  color: #596985;
  background: #e6ebf2;
  border: 2px solid #fff;
}
.step-point .step-check {
  width: 16px;
  height: 16px;
}
.step.done .step-point {
  background: #2879ff;
  color: #fff;
  box-shadow: 0 2px 5px rgba(35, 121, 255, 0.2);
}
.step.current .step-point {
  background: #2e75fa;
  color: #fff;
  border: 3px double #fff;
  outline: 2px solid #6fa4ff;
}
.step strong {
  font-size: 13px;
  color: #23304e;
  white-space: nowrap;
  font-weight: 800;
}
.step small {
  font-size: 11px;
  color: #a3adc2;
}
.step.current small {
  color: #3476ff;
}
.progress-status {
  height: 68px;
  background: #f2f7fd;
  border-radius: 9px;
  display: flex;
  align-items: center;
  gap: 17px;
  padding: 10px 16px;
}
.loading-spinner {
  height: 19px;
  width: 19px;
  border: 2px solid #337dff;
  border-right-color: transparent;
  border-bottom-color: transparent;
  border-radius: 50%;
  animation: spin 2s linear infinite;
  flex-shrink: 0;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.progress-copy {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
  min-width: 0;
}
.progress-copy strong {
  font-size: 12px;
  color: #233352;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.progress-copy small {
  font-size: 11px;
  color: #97a2b6;
}
.progress-ring {
  position: relative;
  width: 57px;
  height: 57px;
  border-radius: 50%;
  background: conic-gradient(#2a75ff calc(var(--progress) * 1%), #dce7fa 0);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.progress-ring::before {
  content: '';
  position: absolute;
  inset: 5px;
  border-radius: 50%;
  background: #f5f9ff;
}
.progress-ring span {
  position: relative;
  color: #2470fb;
  font-weight: 800;
  font-size: 13px;
}

@media (max-width: 1100px) {
  .progress-panel {
    padding: 16px 12px;
  }
  .step {
    min-width: 53px;
  }
  .step strong {
    font-size: 11px;
  }
}
@media (max-width: 830px) {
  .minor-heading {
    display: none;
  }
  .progress-panel {
    height: 215px;
  }
}
@media (max-width: 540px) {
  .progress-panel {
    height: 226px;
  }
  .step-list {
    margin: 20px 0 15px;
  }
  .step {
    min-width: 50px;
    gap: 7px;
  }
  .step strong {
    font-size: 10px;
  }
  .step small {
    font-size: 9px;
  }
  .step-point {
    width: 29px;
    height: 29px;
  }
  .step-list::before {
    top: 14px;
  }
  .progress-status {
    gap: 9px;
    padding: 8px;
  }
  .progress-copy strong {
    font-size: 10px;
  }
  .progress-copy small {
    font-size: 9px;
  }
  .progress-ring {
    width: 47px;
    height: 47px;
  }
}
</style>
