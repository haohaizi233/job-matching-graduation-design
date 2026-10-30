<script setup lang="ts">
import documentTile from '@/assets/icons/common/document-blue-tile.png'
import targetTile from '@/assets/icons/common/target-purple-tile.png'
import chartTile from '@/assets/icons/common/chart-bar-mint.png'
import clockTile from '@/assets/icons/common/clock-orange-tile.png'

const benefits = [
  {
    key: 'parse',
    icon: documentTile,
    title: '简历智能解析',
    desc: 'AI 深度解析简历，提取关键能力与亮点',
  },
  {
    key: 'match',
    icon: targetTile,
    title: '岗位精准匹配',
    desc: '基于画像和求职意向，推荐更合适的岗位',
  },
  {
    key: 'analysis',
    icon: chartTile,
    title: '能力画像分析',
    desc: '多维度能力评估，清晰展示个人优势',
  },
  {
    key: 'history',
    icon: clockTile,
    title: '推荐历史追踪',
    desc: '记录你的求职轨迹，持续优化推荐结果',
  },
]
</script>

<template>
  <div class="benefits">
    <div v-for="item in benefits" :key="item.key" class="benefit">
      <span class="benefit-icon">
        <img :src="item.icon" :alt="item.title" />
      </span>
      <div>
        <h2>{{ item.title }}</h2>
        <p>{{ item.desc }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.benefits {
  display: grid;
  gap: 19px;
  margin-top: 31px;
  max-width: 620px;
}
.benefit {
  display: flex;
  align-items: center;
  gap: 20px;
  min-height: 64px;
}
.benefit-icon {
  width: 62px;
  height: 62px;
  flex: none;
  border-radius: 19px;
  display: grid;
  place-items: center;
  overflow: hidden;
}
.benefit-icon img {
  width: 62px;
  height: 62px;
  object-fit: contain;
}
.benefit h2 {
  font-size: 18px;
  font-weight: 800;
  line-height: 1.4;
  margin: 0 0 4px;
  color: #152342;
}
.benefit p {
  font-size: 15px;
  color: #8690a9;
  line-height: 1.5;
  margin: 0;
  font-weight: 500;
  white-space: nowrap;
}
@media (max-width: 900px) {
  .benefits {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    margin-top: 30px;
  }
  .benefit {
    gap: 12px;
  }
  .benefit-icon,
  .benefit-icon img {
    width: 51px;
    height: 51px;
    border-radius: 15px;
  }
}
@media (max-width: 520px) {
  .benefits {
    grid-template-columns: 1fr;
    gap: 9px;
  }
  .benefit p {
    font-size: 12px;
    white-space: normal;
  }
  .benefit-icon,
  .benefit-icon img {
    width: 45px;
    height: 45px;
    border-radius: 13px;
  }
  .benefit {
    min-height: 48px;
  }
  .benefit h2 {
    margin-bottom: 0;
  }
}
</style>
