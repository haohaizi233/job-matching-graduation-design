<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { toastState } = useToast()
</script>

<template>
  <div class="toast-host" :class="[toastState.placement, { 'is-visible': toastState.visible }]" role="status" aria-live="polite">
    {{ toastState.message }}
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  z-index: 60;
  left: 50%;
  background: #14264d;
  color: #fff;
  border-radius: 10px;
  font-size: 13px;
  padding: 11px 19px;
  box-shadow: 0 14px 36px #1c2b5070;
  opacity: 0;
  pointer-events: none;
  max-width: 90vw;
  white-space: normal;
  transition: opacity 0.22s, transform 0.22s;
}
.toast-host.bottom {
  bottom: 24px;
  transform: translate(-50%, 16px);
}
.toast-host.top {
  top: 90px;
  transform: translate(-50%, -20px);
}
.toast-host.is-visible {
  opacity: 1;
  transform: translate(-50%, 0);
}
</style>
