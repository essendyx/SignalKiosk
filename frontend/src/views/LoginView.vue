<script setup lang="ts">
import { ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import api from "../api"
import { useI18n } from "../i18n"

const username = ref("admin")
const password = ref("admin123!")
const error = ref("")
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const { locale } = useI18n()

const submit = async (): Promise<void> => {
  error.value = ""
  loading.value = true
  try {
    const res = await api.post("/auth/login", { username: username.value, password: password.value })
    localStorage.setItem("token", res.data.access_token as string)
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/"
    router.push(redirect)
  } catch {
    error.value = locale.value === "de" ? "Anmeldung fehlgeschlagen. Bitte Zugangsdaten pruefen." : "Login failed. Please verify your credentials."
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="login-page">
    <div class="ambient"></div>
    <form class="login-card" @submit.prevent="submit">
      <p class="eyebrow">SignalKiosk</p>
      <h1>{{ locale === 'de' ? 'Admin-Anmeldung' : 'Admin Sign In' }}</h1>
      <p class="subtitle">{{ locale === 'de' ? 'Bitte melden Sie sich an, um Inhalte und Zeitplaene zu verwalten.' : 'Sign in to manage content and schedules.' }}</p>
      <label>
        <span>{{ locale === 'de' ? 'Benutzername' : 'Username' }}</span>
        <input v-model="username" autocomplete="username" :placeholder="locale === 'de' ? 'Benutzername' : 'Username'" />
      </label>
      <label>
        <span>{{ locale === 'de' ? 'Passwort' : 'Password' }}</span>
        <input v-model="password" type="password" autocomplete="current-password" :placeholder="locale === 'de' ? 'Passwort' : 'Password'" />
      </label>
      <button :disabled="loading" type="submit">{{ loading ? (locale === 'de' ? 'Anmeldung...' : 'Signing in...') : (locale === 'de' ? 'Einloggen' : 'Sign in') }}</button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>
  </section>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; place-items: center; background: linear-gradient(160deg, #0a2336, #1f5168 45%, #f3f7fa); position: relative; overflow: hidden; padding: 16px; }
.ambient { position: absolute; width: 520px; height: 520px; background: radial-gradient(circle, rgba(255, 255, 255, 0.32), transparent 60%); top: -140px; right: -90px; }
.login-card { width: min(430px, 100%); background: rgba(255, 255, 255, 0.94); border: 1px solid #d2dee8; border-radius: 16px; padding: 28px; box-shadow: 0 24px 60px rgba(9, 25, 38, 0.22); display: grid; gap: 14px; animation: rise .45s ease-out; }
.eyebrow { margin: 0; font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: #2a6078; }
h1 { margin: 0; font-size: 28px; color: #0f2d41; }
.subtitle { margin: 0; color: #3b586a; }
label { display: grid; gap: 6px; }
span { font-size: 14px; color: #27465a; }
input { border: 1px solid #b8cddd; border-radius: 10px; padding: 10px 12px; font-size: 15px; }
input:focus { outline: 2px solid #90bdff; outline-offset: 0; border-color: #6ca6ee; }
button { margin-top: 4px; border: 0; border-radius: 10px; padding: 11px 14px; color: #fff; background: linear-gradient(135deg, #145377, #1e7e93); font-weight: 700; cursor: pointer; }
button:disabled { opacity: 0.7; cursor: default; }
.error { margin: 0; color: #9f1f1f; font-weight: 600; }
@keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
