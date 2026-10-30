<script setup lang="ts">
import { computed } from 'vue'
import type { GlyphName } from '@/types'

/** 内联图标字形（路径取自 UI/html 参考稿的 SVG sprite） */
const glyphPaths: Record<GlyphName, string> = {
  chevron: '<path d="m9 5 7 7-7 7"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  check: '<path d="m4.8 12.6 4.7 4.4 9.7-10"/>',
  star: '<path d="m12 2 3.1 6.4 7 1-5 4.8 1.2 7-6.3-3.3-6.3 3.3 1.2-7-5-4.8 7-1Z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 10.8v5.2m0-8.2v.2"/>',
  file:
    '<path d="M7 2.8h7l4 4v13.4a1.2 1.2 0 0 1-1.2 1.2H7A2 2 0 0 1 5 19.4V4.8a2 2 0 0 1 2-2Z"/>' +
    '<path d="M14 3v4.5h4M8.3 11h6.8M8.3 14.5h6.8M8.3 18h4.5"/>',
  fileSolid:
    '<path d="M6 2h8.5L20 7.5V21a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="currentColor"/>' +
    '<path d="M14.5 2v5.5H20M8 12h8M8 16h8M8 20h5" stroke="#fff" stroke-width="1.6" stroke-linecap="round" fill="none"/>',
  briefcase:
    '<rect x="3" y="7.5" width="18" height="13" rx="2"/>' +
    '<path d="M9 7.5V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2.5M3 13h18"/>',
  eye: '<path d="M2 12c1.5-3.8 5.1-6.5 10-6.5s8.5 2.7 10 6.5c-1.5 3.8-5.1 6.5-10 6.5S3.5 15.8 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff:
    '<path d="M3 3l18 18M10.6 5.5A10.7 10.7 0 0 1 12 5.4c4.8 0 8.6 3.1 10 6.6-.5 1.3-1.3 2.4-2.3 3.4M6 7C4.2 8.2 2.9 10 2 12c1.4 3.5 5.2 6.6 10 6.6 1.5 0 3-.3 4.3-.9M10 10a3 3 0 0 0 4 4"/>',
}

const props = withDefaults(defineProps<{ name: GlyphName; solid?: boolean }>(), { solid: false })

const inner = computed(() => glyphPaths[props.name])
</script>

<template>
  <svg class="glyph" :class="{ solid }" viewBox="0 0 24 24" aria-hidden="true" v-html="inner" />
</template>

<style scoped>
.glyph {
  display: inline-block;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.glyph.solid {
  fill: currentColor;
  stroke: currentColor;
}
</style>
