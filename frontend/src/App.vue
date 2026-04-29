<script setup lang="ts">
import { computed, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useI18n } from "./i18n"
import { showToast } from "./state/toast"
import { useToastState } from "./state/toast"

const route = useRoute()
const router = useRouter()
const { locale, applyLocale, setLocale, t } = useI18n()
const toast = useToastState()
const savedLocale = ref(localStorage.getItem("locale") === "en" ? "en" : "de")
const isLoginRoute = computed(() => route.path === "/login")
const playbackUrl = computed(() => {
  const playbackPort = import.meta.env.VITE_PLAYBACK_PORT || "8090"
  return `${window.location.protocol}//${window.location.hostname}:${playbackPort}/api/playback/status`
})

const logout = (): void => {
  localStorage.removeItem("token")
  router.push("/login")
}

const handleLocaleChange = (event: Event): void => {
  const value = (event.target as HTMLSelectElement).value
  if (value === "de" || value === "en") applyLocale(value)
}

const saveLocale = (): void => {
  if (locale.value === savedLocale.value) return
  setLocale(locale.value)
  savedLocale.value = locale.value
  showToast(locale.value === "de" ? "Einstellung gespeichert." : "Setting saved.")
}
</script>

<template>
  <div v-if="!isLoginRoute" class="shell">
    <aside class="sidebar">
      <h1>SignalKiosk</h1>
      <p class="sub">{{ t("navControlCenter") }}</p>
      <router-link to="/">{{ t("navDashboard") }}</router-link>
      <router-link to="/contents">{{ t("navContents") }}</router-link>
      <router-link to="/presets">{{ t("navPresets") }}</router-link>
      <router-link to="/schedules">{{ t("navSchedules") }}</router-link>
      <router-link to="/webhooks">{{ t("navWebhooks") }}</router-link>
      <router-link to="/settings">{{ t("navSettings") }}</router-link>
      <a :href="playbackUrl" target="_blank" rel="noopener">{{ t("navPlayback") }}</a>
      <label class="locale-picker">
        <span>{{ t("language") }}</span>
        <select :value="locale" @change="handleLocaleChange">
          <option value="de">{{ t("german") }}</option>
          <option value="en">{{ t("english") }}</option>
        </select>
        <button type="button" class="locale-save" @click="saveLocale" :disabled="savedLocale === locale">{{ t("save") }}</button>
      </label>
      <button @click="logout">{{ t("logout") }}</button>
    </aside>
    <main class="main-panel">
      <router-view />
    </main>
  </div>
  <router-view v-else />
  <div v-if="toast.visible" class="toast" :class="toast.type" role="status" aria-live="polite">
    <span>{{ toast.message }}</span>
    <button type="button" class="toast-close" @click="toast.hideToast">x</button>
  </div>
</template>

<style scoped>
.shell { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; font-family: "Manrope", sans-serif; }
.sidebar {
  background:
    radial-gradient(circle at 20% -10%, rgba(179, 215, 238, 0.16), transparent 35%),
    linear-gradient(185deg, #0a2538, #0f3b55 52%, #0e3048);
  color: #d8e5f1;
  padding: 26px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-right: 1px solid rgba(197, 226, 247, 0.2);
}
h1 { margin: 0; letter-spacing: -0.01em; font-size: 42px; line-height: 0.94; font-weight: 800; }
.sub { margin: 0 0 10px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.14em; opacity: 0.8; }
a { color: #cfe5f6; text-decoration: none; border: 1px solid transparent; border-radius: 11px; padding: 11px 12px; font-weight: 600; }
a.router-link-active { color: #ffffff; font-weight: 800; background: rgba(255, 255, 255, 0.15); border-color: rgba(255, 255, 255, 0.2); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08); }
a:hover { background: rgba(255, 255, 255, 0.09); }
button { margin-top: auto; border: 1px solid #8db1c9; background: transparent; color: #d8e5f1; border-radius: 10px; min-height: 42px; padding: 10px 12px; cursor: pointer; font-weight: 600; }
button:hover { background: rgba(216, 229, 241, 0.16); }
.main-panel { padding: 28px; background: radial-gradient(circle at top right, #f9fcff, #e6eef5 46%, #e4ebf2); }
.locale-picker { margin-top: auto; display: grid; gap: 6px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em; color: #bdd6e7; }
.locale-picker select { border-radius: 8px; border: 1px solid rgba(173, 204, 224, 0.6); background: rgba(255, 255, 255, 0.1); color: #e5f0f8; min-height: 36px; padding: 6px 8px; }
.locale-picker select option { color: #123247; background: #ffffff; }
.locale-save {
  margin-top: 0 !important;
  min-height: 36px;
  border-radius: 8px;
  border: 1px solid rgba(173, 204, 224, 0.7);
  background: rgba(255, 255, 255, 0.08);
}
.locale-save:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
button { margin-top: 8px; }
.toast {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 200;
  min-width: 260px;
  max-width: 480px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  border-radius: 12px;
  padding: 12px 14px;
  border: 1px solid;
  box-shadow: 0 14px 35px rgba(12, 27, 38, 0.22);
  font-weight: 600;
}
.toast.success { background: #e8f5ee; border-color: #b9dec8; color: #1f5b3a; }
.toast.error { background: #faeceb; border-color: #e2c1bf; color: #7c2623; }
.toast-close {
  margin: 0;
  min-height: 30px;
  border-radius: 8px;
  padding: 4px 8px;
  border: 1px solid rgba(0, 0, 0, 0.16);
  background: rgba(255, 255, 255, 0.5);
  color: inherit;
}
@media (max-width: 1000px) { .shell { grid-template-columns: 1fr; } }
</style>

<style>
html, body, #app {
  margin: 0;
  min-height: 100%;
}
</style>
