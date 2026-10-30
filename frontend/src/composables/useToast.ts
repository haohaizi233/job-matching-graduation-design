import { reactive, readonly } from 'vue'

export type ToastPlacement = 'top' | 'bottom'

interface ToastState {
  message: string
  visible: boolean
  placement: ToastPlacement
}

const state = reactive<ToastState>({
  message: '',
  visible: false,
  placement: 'bottom',
})

let timer: ReturnType<typeof setTimeout> | undefined

/** 全局轻提示（单例，供各组件复用） */
export function useToast() {
  function show(message: string, placement: ToastPlacement = 'bottom', duration = 3100) {
    state.message = message
    state.placement = placement
    state.visible = true
    clearTimeout(timer)
    timer = setTimeout(() => {
      state.visible = false
    }, duration)
  }

  return { toastState: readonly(state), show }
}
