<script setup lang="ts">
import IconGlyph from '@/components/common/IconGlyph.vue'
import type { JobItem } from '@/types'

defineProps<{
  jobs: JobItem[]
}>()

defineEmits<{
  (e: 'select', job: JobItem): void
  (e: 'more'): void
}>()
</script>

<template>
  <section class="recommendations card">
    <div class="card-header">
      <h2>
        近期推荐岗位
        <button type="button" class="inline-info" title="排名分数仅用于推荐参考">
          <IconGlyph name="info" />
        </button>
      </h2>
      <button type="button" class="more-muted" @click="$emit('more')">
        查看更多
        <IconGlyph name="chevron" class="more-chevron" />
      </button>
    </div>

    <div class="jobs-list">
      <button
        v-for="job in jobs"
        :key="job.id"
        type="button"
        class="job-row"
        @click="$emit('select', job)"
      >
        <img :src="job.logo" :alt="job.logoAlt" />
        <span class="job-details">
          <strong>{{ job.title }}</strong>
          <span class="job-tags">
            <em v-for="tag in job.tags" :key="tag">{{ tag }}</em>
          </span>
          <small>{{ job.company }}</small>
        </span>
        <span class="job-salary">{{ job.salary }}</span>
        <span class="job-match" :style="{ '--degree': job.match }">
          <span>{{ job.match }}%</span>
          <small>匹配度</small>
        </span>
        <IconGlyph name="chevron" class="row-chevron" />
      </button>
    </div>

    <p v-if="jobs.length === 0" class="no-results">未找到与关键词匹配的推荐岗位。</p>
  </section>
</template>

<style scoped>
.recommendations {
  height: 341px;
  padding: 13px 16px 10px;
}
.more-muted {
  font-size: 11px;
  color: #9aa5bb;
  display: flex;
  align-items: center;
  gap: 2px;
}
.more-chevron {
  height: 14px;
  width: 14px;
}
.jobs-list {
  margin-top: 20px;
}
.job-row {
  height: 75px;
  width: 100%;
  display: flex;
  align-items: center;
  text-align: left;
  border-bottom: 1px solid #e8edf5;
  gap: 13px;
  padding: 0 2px;
  position: relative;
}
.job-row:last-child {
  border-bottom: 0;
}
.job-row:hover {
  background: #f7faff;
}
.job-row > img {
  width: 58px;
  height: 60px;
  object-fit: contain;
  flex: 0 0 58px;
}
.job-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  white-space: nowrap;
}
.job-details strong {
  font-size: 13px;
  font-weight: 800;
  color: #1b2947;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.job-details small {
  font-size: 11px;
  color: #939eb2;
}
.job-tags {
  display: flex;
  gap: 6px;
}
.job-tags em {
  font-size: 11px;
  font-style: normal;
  color: #7887a4;
  background: #f1f4fa;
  border-radius: 3px;
  padding: 2px 7px;
  line-height: 14px;
}
.job-tags em:first-child {
  color: #2474ff;
  background: #edf4ff;
}
.job-salary {
  font-weight: 800;
  color: #ff5e2a;
  font-size: 14px;
  min-width: 72px;
  white-space: nowrap;
}
.job-match {
  width: 54px;
  align-self: center;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-weight: 800;
  color: #172449;
  position: relative;
  font-size: 13px;
  line-height: 22px;
}
.job-match::before {
  content: '';
  position: absolute;
  left: 0;
  top: -4px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: conic-gradient(
    #9252f6 0%,
    #bb65f5 calc(var(--degree) * 1%),
    #e6e8f3 calc(var(--degree) * 1%) 100%
  );
  mask: radial-gradient(farthest-side, transparent calc(100% - 4px), #000 calc(100% - 3.5px));
  transform: translateX(5px);
}
.job-match span {
  padding-top: 4px;
}
.job-match small {
  font-size: 10px;
  color: #8a95af;
  font-weight: 500;
}
.row-chevron {
  width: 14px;
  height: 14px;
  color: #3c4f76;
  margin-left: 4px;
}
.no-results {
  font-size: 13px;
  padding: 70px 20px;
  text-align: center;
  color: #8d9ab4;
}

@media (max-width: 1380px) {
  .job-row {
    gap: 8px;
  }
  .job-salary {
    font-size: 12px;
    min-width: 60px;
  }
}
@media (max-width: 1100px) {
  .recommendations {
    padding: 13px 9px;
  }
  .job-row > img {
    width: 43px;
    height: 53px;
    flex-basis: 43px;
  }
  .job-match {
    width: 48px;
  }
  .job-details strong {
    font-size: 11px;
  }
  .job-tags {
    gap: 2px;
  }
  .job-tags em {
    padding: 1px 4px;
  }
  .row-chevron {
    margin: 0;
  }
}
@media (max-width: 830px) {
  .recommendations {
    height: auto;
  }
}
@media (max-width: 540px) {
  .recommendations {
    padding: 12px 9px;
  }
  .job-row {
    height: 73px;
    gap: 7px;
  }
  .job-row > img {
    width: 39px;
    height: 46px;
    flex: 0 0 39px;
  }
  .job-details strong {
    font-size: 11px;
  }
  .job-tags em {
    font-size: 9px;
    padding: 1px 4px;
  }
  .job-details small {
    font-size: 10px;
  }
  .job-salary {
    font-size: 11px;
    min-width: 52px;
  }
  .job-match {
    font-size: 11px;
    width: 43px;
  }
  .job-match::before {
    width: 38px;
    height: 38px;
    left: 0;
    top: -2px;
    transform: translateX(3px);
  }
  .job-match span {
    padding-top: 2px;
  }
  .row-chevron {
    display: none;
  }
}
</style>
