import { onBeforeUnmount, type Ref } from "vue"
import { onBeforeRouteLeave } from "vue-router"

export const confirmDiscardChanges = (locale: Ref<string>): boolean => {
  const message = locale.value === "de"
    ? "Sie haben ungespeicherte Aenderungen. Wirklich verwerfen und Seite verlassen?"
    : "You have unsaved changes. Discard and leave this page?"
  return window.confirm(message)
}

export const useUnsavedChangesGuard = (isDirty: Ref<boolean>, locale: Ref<string>): void => {
  const handleBeforeUnload = (event: BeforeUnloadEvent): void => {
    if (!isDirty.value) return
    event.preventDefault()
    event.returnValue = ""
  }

  window.addEventListener("beforeunload", handleBeforeUnload)

  onBeforeRouteLeave(() => {
    if (!isDirty.value) return true
    return confirmDiscardChanges(locale)
  })

  onBeforeUnmount(() => {
    window.removeEventListener("beforeunload", handleBeforeUnload)
  })
}
