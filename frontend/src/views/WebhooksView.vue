<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"
import { useUnsavedChangesGuard } from "../composables/useUnsavedChangesGuard"
import { showToast } from "../state/toast"

interface Webhook { id: string; name: string; slug: string; enabled: boolean; allowed_actions: string[] }
const items = ref<Webhook[]>([])
const name = ref("")
const slug = ref("")
const token = ref("")
const editingId = ref<string | null>(null)
const tokenMessage = ref("")
const { locale, t } = useI18n()
const isDirty = computed(() => Boolean(name.value.trim() || slug.value.trim() || token.value.trim() || editingId.value))

const load = async (): Promise<void> => {
  const res = await api.get("/webhooks")
  items.value = res.data as Webhook[]
}

const save = async (): Promise<void> => {
  const payload = { name: name.value, slug: slug.value, token: token.value, enabled: true, allowed_actions: ["play_url", "play_existing_content", "play_preset", "stop_override"] }
  if (editingId.value) await api.put(`/webhooks/${editingId.value}`, payload)
  else await api.post("/webhooks", payload)
  name.value = ""
  slug.value = ""
  token.value = ""
  editingId.value = null
  await load()
  showToast(locale.value === "de" ? "Webhook gespeichert." : "Webhook saved.")
}

const editItem = (item: Webhook): void => {
  editingId.value = item.id
  name.value = item.name
  slug.value = item.slug
  token.value = ""
}

const remove = async (id: string): Promise<void> => {
  await api.delete(`/webhooks/${id}`)
  await load()
  showToast(locale.value === "de" ? "Webhook geloescht." : "Webhook deleted.")
}

const generateToken = (): void => {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  token.value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")
  tokenMessage.value = locale.value === "de" ? "Token wurde neu generiert." : "Token was regenerated."
}

const copyToken = async (): Promise<void> => {
  if (!token.value) {
    tokenMessage.value = locale.value === "de" ? "Kein Token zum Kopieren vorhanden." : "No token available to copy."
    return
  }
  try {
    await navigator.clipboard.writeText(token.value)
    tokenMessage.value = locale.value === "de" ? "Token wurde in die Zwischenablage kopiert." : "Token copied to clipboard."
  } catch {
    tokenMessage.value = locale.value === "de" ? "Kopieren fehlgeschlagen." : "Copy failed."
  }
}

onMounted(load)
useUnsavedChangesGuard(isDirty, locale)
</script>

<template>
  <section class="page">
    <h2 class="page-title">Webhooks</h2>
    <p class="page-subtitle">{{ locale === 'de' ? 'Externe Systeme koennen Playback-Events sicher ueber diese Endpunkte ausloesen.' : 'External systems can securely trigger playback events through these endpoints.' }}</p>
    <div class="card webhook-help">
      <h3>{{ locale === 'de' ? 'So funktioniert der Aufruf' : 'How webhook calls work' }}</h3>
      <p>
        {{ locale === 'de'
          ? 'Der Slug ist der eindeutige URL-Teil deines Webhooks. Aus Slug "fire-alarm" wird der Endpoint /webhook/fire-alarm.'
          : 'The slug is the unique URL segment of your webhook. Slug "fire-alarm" becomes endpoint /webhook/fire-alarm.' }}
      </p>
      <p>
        {{ locale === 'de'
          ? 'Authentifizierung: Token entweder als Query-Parameter (token=...) oder als Header X-SignalKiosk-Token mitsenden.'
          : 'Authentication: send token either as query parameter (token=...) or as header X-SignalKiosk-Token.' }}
      </p>
      <p>{{ locale === 'de' ? 'Beispiel: play_url' : 'Example: play_url' }}</p>
      <pre><code>curl -X POST "http://localhost:8080/webhook/fire-alarm?token=YOUR_TOKEN" -H "Content-Type: application/json" -d "{\"action\":\"play_url\",\"url\":\"https://status.example.org\",\"duration_seconds\":120,\"priority\":100}"</code></pre>
      <p>{{ locale === 'de' ? 'Beispiel: play_existing_content (mit Header-Token)' : 'Example: play_existing_content (with header token)' }}</p>
      <pre><code>curl -X POST "http://localhost:8080/webhook/fire-alarm" -H "X-SignalKiosk-Token: YOUR_TOKEN" -H "Content-Type: application/json" -d "{\"action\":\"play_existing_content\",\"content_id\":\"CONTENT_ID\",\"duration_seconds\":90}"</code></pre>
      <p>{{ locale === 'de' ? 'Beispiel: play_preset' : 'Example: play_preset' }}</p>
      <pre><code>curl -X POST "http://localhost:8080/webhook/fire-alarm?token=YOUR_TOKEN" -H "Content-Type: application/json" -d "{\"action\":\"play_preset\",\"preset_id\":\"PRESET_ID\",\"duration_seconds\":180}"</code></pre>
      <p>{{ locale === 'de' ? 'Beispiel: stop_override' : 'Example: stop_override' }}</p>
      <pre><code>curl -X POST "http://localhost:8080/webhook/fire-alarm?token=YOUR_TOKEN" -H "Content-Type: application/json" -d "{\"action\":\"stop_override\"}"</code></pre>
    </div>
    <div class="card form-grid wide">
      <label>{{ locale === 'de' ? 'Name' : 'Name' }}<input v-model="name" :placeholder="locale === 'de' ? 'Brandmeldeanlage' : 'Fire alarm'" /></label>
      <label>Slug<input v-model="slug" placeholder="fire-alarm" /></label>
      <label>{{ locale === 'de' ? 'Token' : 'Token' }}
        <div class="token-field">
          <input v-model="token" type="password" :placeholder="locale === 'de' ? 'Sicherer Zugriffstoken' : 'Secure access token'" />
          <button class="ghost" type="button" @click="generateToken">{{ locale === 'de' ? 'Generieren' : 'Generate' }}</button>
          <button class="ghost" type="button" @click="copyToken">{{ locale === 'de' ? 'Kopieren' : 'Copy' }}</button>
        </div>
      </label>
      <p v-if="tokenMessage" class="hint full-width">{{ tokenMessage }}</p>
      <p class="hint full-width">
        {{ locale === 'de'
          ? 'Webhook-Aufrufe koennen den Token als Query-Parameter (token=...) oder als Custom Header X-SignalKiosk-Token mitsenden.'
          : 'Webhook requests can send the token as query parameter (token=...) or as custom header X-SignalKiosk-Token.' }}
      </p>
      <div class="toolbar"><button @click="save">{{ editingId ? t('save') : t('create') }}</button></div>
    </div>
    <table class="data-table">
      <thead><tr><th>{{ locale === 'de' ? 'Name' : 'Name' }}</th><th>Endpoint</th><th>{{ locale === 'de' ? 'Aktionen' : 'Actions' }}</th></tr></thead>
      <tbody>
        <tr v-for="item in items" :key="item.id">
          <td>{{ item.name }}</td>
          <td><code>/webhook/{{ item.slug }}</code></td>
          <td class="actions">
            <button class="ghost" @click="editItem(item)">{{ t('edit') }}</button>
            <button class="danger" @click="remove(item.id)">{{ t('delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.webhook-help {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
}

.webhook-help h3,
.webhook-help p {
  margin: 0;
}

.webhook-help pre {
  margin: 0;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid #d7e1ea;
  background: #f5f8fb;
  overflow-x: auto;
}

.token-field {
  display: flex;
  gap: 8px;
  align-items: center;
}

.token-field input {
  flex: 1;
}

@media (max-width: 980px) {
  .token-field {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
