<script setup lang="ts">
import IconGlyph from '@/components/common/IconGlyph.vue'
import type { StatCardItem } from '@/types'

defineProps<{ items: StatCardItem[] }>()

defineEmits<{ (e: 'select', item: StatCardItem): void }>()
</script>

<template>
  <section class="stats-grid" aria-label="工作台摘要">
    <button v-for="item in items" :key="item.key" type="button" class="stat-card" @click="$emit('select', item)">
      <span class="stat-icon" :class="`bg-${item.tone}`">
        <IconGlyph v-if="item.glyph === 'file'" name="fileSolid" class="file-solid" />
        <span v-else-if="item.glyph === 'plus'" class="purple-plus">＋</span>
        <span v-else-if="item.glyph === 'pie'" class="pie-glyph" aria-hidden="true" />
        <IconGlyph v-else name="star" solid class="star-solid" />
      </span>

      <span class="stat-body">
        <span class="stat-name">{{ item.name }}</span>
        <strong :class="{ tabular: item.key === 'jobs' }">{{ item.value }}</strong>
        <small>
          {{ item.note }}
          <em v-if="item.trendText" class="trend" :class="item.trendTone === 'green' ? 'green-text' : 'orange-text'">
            {{ item.trendText }}
          </em>
        </small>
      </span>

      <IconGlyph v-if="item.chevron" name="chevron" class="stat-chevron" />
      <span v-if="item.miniBars" class="mini-bars" aria-hidden="true"><i /><i /><i /></span>
    </button>
  </section>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 15px;
}
.stat-card {
  height: 116px;
  display: flex;
  align-items: flex-start;
  text-align: left;
  position: relative;
  padding: 15px;
  gap: 17px;
  background: #fff;
  border: 1px solid #edf1f7;
  box-shadow: 0 3px 12px rgba(43, 67, 103, 0.045);
  border-radius: 11px;
  transition: transform 0.18s, box-shadow 0.18s;
}
.stat-card:hover {
  box-shadow: 0 6px 22px rgba(44, 90, 155, 0.09);
  transform: translateY(-1px);
}
.stat-icon {
  width: 52px;
  height: 52px;
  flex: 0 0 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.bg-blue {
  background: linear-gradient(135deg, #dbe9ff, #c5d9ff);
  color: #2977ff;
}
.bg-purple {
  background: linear-gradient(135deg, #f1e3ff, #d9c9ff);
  color: #9441f7;
}
.bg-green {
  background: linear-gradient(135deg, #e5fbf3, #d5f7e8);
  color: #00bf87;
}
.bg-orange {
  background: linear-gradient(135deg, #fff4e8, #ffebd5);
  color: #ff9c25;
}
.file-solid {
  width: 31px;
  height: 35px;
  color: #2774fa;
}
.purple-plus {
  font-size: 26px;
  font-weight: 400;
  color: #fff;
  line-height: 1;
  width: 27px;
  height: 29px;
  text-align: center;
  border-radius: 7px;
  background: linear-gradient(145deg, #ad64ff, #8734eb);
  box-shadow: 0 2px 7px rgba(145, 58, 234, 0.19);
}
.pie-glyph {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: conic-gradient(#04b98a 0 75%, #9ae0c5 75% 100%);
  position: relative;
}
.pie-glyph::after {
  content: '';
  position: absolute;
  width: 13px;
  height: 13px;
  background: #d6f8ec;
  left: 15px;
  top: 0;
  border-bottom: 2px solid #fff;
  border-left: 2px solid #fff;
}
.star-solid {
  width: 30px;
  height: 30px;
  color: #ffa329;
}
.stat-body {
  padding-top: 3px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.stat-name {
  font-size: 13px;
  font-weight: 700;
  color: #263452;
}
.stat-body strong {
  font-size: 25px;
  font-weight: 900;
  line-height: 1;
  white-space: nowrap;
  color: #091b45;
  letter-spacing: -0.3px;
}
.stat-body small {
  font-size: 12px;
  color: #8a97b0;
  white-space: nowrap;
  margin-top: 6px;
}
.stat-body small .trend {
  margin-left: 4px;
}
.stat-chevron {
  position: absolute;
  right: 25px;
  top: 44px;
  width: 16px;
  height: 16px;
  stroke-width: 1.8;
  color: #102a51;
}
.mini-bars {
  position: absolute;
  bottom: 47px;
  right: 26px;
  height: 24px;
  display: flex;
  align-items: flex-end;
  gap: 3px;
}
.mini-bars i {
  width: 5px;
  background: #07c68c;
  display: block;
  border-radius: 2px 2px 0 0;
}
.mini-bars i:nth-child(1) {
  height: 12px;
}
.mini-bars i:nth-child(2) {
  height: 20px;
}
.mini-bars i:nth-child(3) {
  height: 26px;
}

@media (max-width: 1100px) {
  .stat-card {
    gap: 9px;
    padding: 13px 9px;
  }
  .stat-icon {
    height: 44px;
    width: 44px;
    flex-basis: 44px;
  }
  .stat-body strong {
    font-size: 22px;
  }
  .stat-body small {
    font-size: 10px;
  }
  .stat-chevron,
  .mini-bars {
    display: none;
  }
}
@media (max-width: 830px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 540px) {
  .stats-grid {
    gap: 8px;
    margin-bottom: 12px;
  }
  .stat-card {
    height: 104px;
    padding: 12px 8px;
    gap: 7px;
  }
  .stat-name {
    font-size: 11px;
  }
  .stat-body {
    gap: 8px;
  }
  .stat-body strong {
    font-size: 21px;
  }
  .stat-body small {
    font-size: 9px;
    margin-top: 0;
    white-space: normal;
  }
  .stat-icon {
    width: 39px;
    height: 39px;
    flex-basis: 39px;
    border-radius: 11px;
  }
}
</style>
