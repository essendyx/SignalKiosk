<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"
import { useUnsavedChangesGuard } from "../composables/useUnsavedChangesGuard"
import { showToast } from "../state/toast"

interface WebhookToken {
  id: string
  name: string
  token_preview: string
}

interface WebhookConfigResponse {
  endpoint: string
  enabled: boolean
  token_configured: boolean
  legacy_token_configured: boolean
  tokens: WebhookToken[]
}

const endpoint = ref("/webhook")
const enabled = ref(true)
const tokenConfigured = ref(false)
const legacyTokenConfigured = ref(false)
const tokens = ref<WebhookToken[]>([])
const newTokenName = ref("")
const tokenMessage = ref("")
const visibleToken = ref("")
const visibleTokenName = ref("")
const { locale, t } = useI18n()
const initialFormSnapshot = ref("")

const formSnapshot = (): string => JSON.stringify({ enabled: enabled.value })
const markClean = (): void => {
  initialFormSnapshot.value = formSnapshot()
}
const isDirty = computed(() => formSnapshot() !== initialFormSnapshot.value)

const load = async (): Promise<void> => {
  const res = await api.get("/webhook-config")
  const data = res.data as WebhookConfigResponse
  endpoint.value = data.endpoint || "/webhook"
  enabled.value = Boolean(data.enabled)
  tokenConfigured.value = Boolean(data.token_configured)
  legacyTokenConfigured.value = Boolean(data.legacy_token_configured)
  tokens.value = Array.isArray(data.tokens) ? data.tokens : []
  if (!initialFormSnapshot.value) markClean()
}

const save = async (): Promise<void> => {
  await api.put("/webhook-config", { enabled: enabled.value })
  markClean()
  showToast(locale.value === "de" ? "Webhook-Konfiguration gespeichert." : "Webhook configuration saved.")
}

const generateToken = (): void => {
  tokenMessage.value = locale.value === "de" ? "Token wird beim Hinzufuegen automatisch erzeugt." : "Token is generated automatically when added."
}

const fallbackCopyText = (value: string): boolean => {
  const ta = document.createElement("textarea")
  ta.value = value
  ta.setAttribute("readonly", "")
  ta.style.position = "fixed"
  ta.style.top = "-1000px"
  ta.style.left = "-1000px"
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  let ok = false
  try {
    ok = document.execCommand("copy")
  } catch {
    ok = false
  }
  document.body.removeChild(ta)
  return ok
}

const copyToken = async (id: string): Promise<void> => {
  try {
    const res = await api.get(`/webhook-config/tokens/${id}/secret`)
    const token = String((res.data as { token?: string }).token || "")
    if (!token) {
      tokenMessage.value = locale.value === "de" ? "Token konnte nicht gelesen werden." : "Token could not be read."
      return
    }
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(token)
    } else if (!fallbackCopyText(token)) {
      throw new Error("clipboard copy failed")
    }
    tokenMessage.value = locale.value === "de" ? "Token wurde in die Zwischenablage kopiert." : "Token copied to clipboard."
  } catch {
    tokenMessage.value = locale.value === "de" ? "Kopieren fehlgeschlagen. Nutze HTTPS oder localhost, oder kopiere das Token manuell ueber die API." : "Copy failed. Use HTTPS or localhost, or copy the token manually via API."
  }
}

const showTokenSecret = async (id: string): Promise<void> => {
  try {
    const res = await api.get(`/webhook-config/tokens/${id}/secret`)
    const payload = res.data as { token?: string; name?: string }
    const token = String(payload.token || "")
    if (!token) {
      tokenMessage.value = locale.value === "de" ? "Token konnte nicht gelesen werden." : "Token could not be read."
      return
    }
    visibleToken.value = token
    visibleTokenName.value = String(payload.name || "Token")
    tokenMessage.value = ""
  } catch {
    tokenMessage.value = locale.value === "de" ? "Token konnte nicht gelesen werden." : "Token could not be read."
  }
}

const hideTokenSecret = (): void => {
  visibleToken.value = ""
  visibleTokenName.value = ""
}

const createToken = async (): Promise<void> => {
  const name = newTokenName.value.trim()
  if (!name) {
    tokenMessage.value = locale.value === "de" ? "Name ist erforderlich." : "Name is required."
    return
  }
  await api.post("/webhook-config/tokens", { name })
  newTokenName.value = ""
  await load()
  tokenConfigured.value = true
  showToast(locale.value === "de" ? "Token hinzugefuegt." : "Token added.")
}

const removeToken = async (id: string): Promise<void> => {
  await api.delete(`/webhook-config/tokens/${id}`)
  await load()
  showToast(locale.value === "de" ? "Token geloescht." : "Token deleted.")
}

onMounted(load)
useUnsavedChangesGuard(isDirty, locale)
</script>

<template>
  <section class="page">
    <h2 class="page-title">Webhooks</h2>
    <p class="page-subtitle">{{ locale === 'de' ? 'Ein zentraler Webhook mit beliebig vielen Tokens fuer externe Systeme.' : 'One central webhook with unlimited tokens for external systems.' }}</p>

    <div class="card form-grid wide">
      <label>{{ locale === 'de' ? 'Endpoint' : 'Endpoint' }}<input :value="endpoint" disabled /></label>
      <label>{{ locale === 'de' ? 'Aktiv' : 'Enabled' }}
        <select v-model="enabled">
          <option :value="true">{{ locale === 'de' ? 'Ja' : 'Yes' }}</option>
          <option :value="false">{{ locale === 'de' ? 'Nein' : 'No' }}</option>
        </select>
      </label>
      <p class="hint full-width">
        {{ locale === 'de'
          ? (tokenConfigured ? 'Mindestens ein Token ist hinterlegt.' : 'Es ist noch kein Token hinterlegt.')
          : (tokenConfigured ? 'At least one token is configured.' : 'No token is configured yet.') }}
      </p>
      <p v-if="legacyTokenConfigured" class="hint full-width">{{ locale === 'de' ? 'Hinweis: Ein altes Legacy-Token ist aktiv, kann aber nicht angezeigt werden.' : 'Note: A legacy token is active but cannot be displayed.' }}</p>
      <div class="toolbar"><button @click="save">{{ t('save') }}</button></div>
    </div>

    <div class="card form-grid wide">
      <label>{{ locale === 'de' ? 'Token-Name' : 'Token name' }}<input v-model="newTokenName" :placeholder="locale === 'de' ? 'z. B. Leitwarte' : 'e.g. Control room'" /></label>
      <label class="full-width">{{ locale === 'de' ? 'Token erzeugen' : 'Generate token' }}
        <div class="token-field">
          <button class="ghost" type="button" @click="generateToken">{{ locale === 'de' ? 'Hinweis' : 'Info' }}</button>
          <button type="button" @click="createToken">{{ locale === 'de' ? 'Token hinzufuegen' : 'Add token' }}</button>
        </div>
      </label>
      <p v-if="tokenMessage" class="hint full-width">{{ tokenMessage }}</p>
    </div>

    <table class="data-table compact-table">
      <thead><tr><th>{{ locale === 'de' ? 'Name' : 'Name' }}</th><th>{{ locale === 'de' ? 'Token (Maskiert)' : 'Token (masked)' }}</th><th>{{ locale === 'de' ? 'Aktionen' : 'Actions' }}</th></tr></thead>
      <tbody>
        <tr v-for="item in tokens" :key="item.id">
          <td>{{ item.name }}</td>
          <td><code>{{ item.token_preview }}</code></td>
          <td class="actions">
            <button class="ghost" @click="showTokenSecret(item.id)">{{ locale === 'de' ? 'Anzeigen' : 'Show' }}</button>
            <button class="ghost" @click="copyToken(item.id)">{{ locale === 'de' ? 'Kopieren' : 'Copy' }}</button>
            <button class="danger" @click="removeToken(item.id)">{{ t('delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="visibleToken" class="card form-grid wide">
      <p class="hint full-width">{{ locale === 'de' ? 'Token (nur jetzt sichtbar):' : 'Token (visible now only):' }} <strong>{{ visibleTokenName }}</strong></p>
      <label class="full-width">
        <input :value="visibleToken" readonly />
      </label>
      <div class="toolbar">
        <button class="ghost" type="button" @click="hideTokenSecret">{{ locale === 'de' ? 'Schliessen' : 'Close' }}</button>
      </div>
    </div>

    <div class="card webhook-help">
      <h3>{{ locale === 'de' ? 'Aufruf und Authentifizierung' : 'Call and authentication' }}</h3>
      <p>{{ locale === 'de' ? 'Sende POST-Requests an /webhook. Authentifiziere mit token als Query-Parameter oder als Header X-SignalKiosk-Token.' : 'Send POST requests to /webhook. Authenticate using token query parameter or X-SignalKiosk-Token header.' }}</p>
      <pre><code>curl -X POST "http://localhost:8080/webhook?token=YOUR_TOKEN" -H "Content-Type: application/json" -d "{\"content_type\":\"webpage\",\"url\":\"https://status.example.org\",\"duration_seconds\":120,\"apply_mode\":\"replace_now\"}"</code></pre>

      <h3>{{ locale === 'de' ? 'Felder im Request' : 'Request fields' }}</h3>
      <ul>
        <li><code>content_type</code>: <code>webpage</code>, <code>html</code>, <code>image</code>, <code>video</code></li>
        <li><code>duration_seconds</code>: Pflichtfeld (1-86400)</li>
        <li><code>apply_mode</code>: <code>replace_now</code> oder <code>queue_next_once</code></li>
        <li><code>webpage</code>: braucht <code>url</code></li>
        <li><code>html</code>: braucht <code>html</code></li>
        <li><code>image</code>/<code>video</code>: braucht <code>url</code> oder <code>asset_path</code></li>
      </ul>

      <h3>{{ locale === 'de' ? 'Modi im Playback' : 'Playback modes' }}</h3>
      <p><code>replace_now</code>: {{ locale === 'de' ? 'ersetzt die aktuell laufende Seite sofort fuer die angegebene Dauer.' : 'replaces the currently running page immediately for the provided duration.' }}</p>
      <p><code>queue_next_once</code>: {{ locale === 'de' ? 'reiht den Inhalt einmalig als naechsten Inhalt ein. Danach laeuft der normale Plan weiter.' : 'queues the content once as the next item. After that, normal rotation resumes.' }}</p>
    </div>
  </section>
</template>

<style scoped>
.webhook-help {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.webhook-help h3,
.webhook-help p {
  margin: 0;
}

.webhook-help ul {
  margin: 0;
  padding-left: 18px;
}

.webhook-help pre {
  margin: 0;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid #d7e1ea;
  background: #f5f8fb;
  overflow-x: auto;
}

.webhook-help code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.95em;
}

.webhook-help pre code {
  font-size: 14px;
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
