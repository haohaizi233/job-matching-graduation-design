<script setup lang="ts">
import IconGlyph from '@/components/common/IconGlyph.vue'
import type { ActivityItem, GlyphName } from '@/types'

defineProps<{ items: ActivityItem[] }>()

defineEmits<{ (e: 'more'): void }>()

const glyphOf = (item: ActivityItem): GlyphName => item.glyph
</script>

<template>
  <section class="activity-card card">
    <div class="card-header">
      <h2>最近动态</h2>
      <button type="button" class="text-link" @click="$emit('more')">
        查看更多
        <IconGlyph name="chevron" />
      </button>
    </div>

    <div class="activity-list">
      <div v-for="item in items" :key="item.id" class="activity-row">
        <span v-if="item.line" class="activity-line" />
        <span class="activity-dot" :class="item.dotTone" />
        <span class="activity-icon" :class="`activity-${item.iconTone}`">
          <IconGlyph :name="glyphOf(item)" :solid="item.glyph === 'star'" />
        </span>
        <div>
          <strong>{{ item.title }}</strong>
          <small>{{ item.desc }}</small>
        </div>
        <time>{{ item.time }}</time>
      </div>
    </div>
  </section>
</template>

<style scoped>
.activity-card {
  height: 199px;
  padding: 12px 17px 8px;
  overflow: hidden;
}
.activity-list {
  margin-top: 9px;
}
.activity-row {
  display: flex;
  align-items: center;
  height: 40px;
  gap: 10px;
  position: relative;
  padding-left: 27px;
}
.activity-row .activity-line {
  position: absolute;
  left: 7px;
  top: 20px;
  height: 40px;
  width: 1px;
  background: #e7ebf4;
}
.activity-dot {
  position: absolute;
  left: 4px;
  top: 15px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.activity-dot.blue {
  background: #367aff;
}
.activity-dot.violet {
  background: #a355ff;
}
.activity-dot.green {
  background: #09c7a1;
}
.activity-dot.gray {
  background: #9aa8bb;
}
.activity-icon {
  height: 31px;
  width: 31px;
  flex: 0 0 31px;
  border: 4px solid #e6effe;
  background: #7aafff;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #fff;
}
.activity-icon .glyph {
  width: 15px;
  height: 15px;
}
.activity-blue {
  background: #7cafff;
  border-color: #d9e8ff;
}
.activity-purple {
  background: #a96bf5;
  border-color: #ead9ff;
}
.activity-green {
  background: #07bf96;
  border-color: #d7f8ef;
}
.activity-orange {
  background: #ffa52f;
  border-color: #fff0d4;
}
.activity-row div {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.activity-row strong {
  font-size: 11px;
  color: #253450;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.activity-row small {
  font-size: 10px;
  color: #9aa7be;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.activity-row time {
  font-size: 11px;
  color: #8894ad;
  white-space: nowrap;
  align-self: flex-start;
  margin-top: 7px;
}

@media (max-width: 830px) {
  .activity-card {
    height: auto;
    min-height: 218px;
  }
}
</style>
