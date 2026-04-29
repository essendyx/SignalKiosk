import { ref } from "vue"

type ToastType = "success" | "error"

const visible = ref(false)
const message = ref("")
const type = ref<ToastType>("success")
let timer: number | null = null

const clearTimer = (): void => {
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
}

export const showToast = (text: string, toastType: ToastType = "success", timeout = 2800): void => {
  clearTimer()
  message.value = text
  type.value = toastType
  visible.value = true
  timer = window.setTimeout(() => {
    visible.value = false
    timer = null
  }, timeout)
}

export const hideToast = (): void => {
  clearTimer()
  visible.value = false
}

export const useToastState = () => ({
  visible,
  message,
  type,
  hideToast,
})
