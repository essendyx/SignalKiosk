<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"
import { useUnsavedChangesGuard } from "../composables/useUnsavedChangesGuard"
import { showToast } from "../state/toast"

interface SettingEntry {
  key: string
  value: Record<string, string | number | boolean | null>
  updated_at: string
}

interface ControlStatus {
  enabled: boolean
  detail?: string
  runner_active?: boolean
}

const items = ref<SettingEntry[]>([])
const newKey = ref("")
const newValue = ref('{"value":""}')
const error = ref("")
const { locale, t } = useI18n()
const isDirty = computed(() => Boolean(newKey.value.trim() || newValue.value !== '{"value":""}'))
const controlStatus = ref<ControlStatus | null>(null)
const controlBusy = ref(false)
const importReplaceExisting = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)
const allConfigSections = ["settings", "contents", "presets", "preset_items", "schedules", "auth_profiles", "users"] as const
const exportSections = ref<string[]>([...allConfigSections])
const importSections = ref<string[]>([...allConfigSections])

const sectionLabel = (value: string): string => {
  const mapDe: Record<string, string> = {
    settings: "Settings",
    contents: "Inhalte",
    presets: "Presets",
    preset_items: "Preset-Items",
    schedules: "Zeitplaene",
    auth_profiles: "Auth-Profile",
    users: "Benutzer"
  }
  const mapEn: Record<string, string> = {
    settings: "Settings",
    contents: "Contents",
    presets: "Presets",
    preset_items: "Preset items",
    schedules: "Schedules",
    auth_profiles: "Auth profiles",
    users: "Users"
  }
  return locale.value === "de" ? (mapDe[value] || value) : (mapEn[value] || value)
}

const load = async (): Promise<void> => {
  const [settingsRes, statusRes] = await Promise.all([
    api.get("/system/settings"),
    api.get("/system/control/status")
  ])
  items.value = settingsRes.data as SettingEntry[]
  controlStatus.value = statusRes.data as ControlStatus
}

const runControl = async (endpoint: string, successDe: string, successEn: string): Promise<void> => {
  controlBusy.value = true
  try {
    await api.post(endpoint)
    showToast(locale.value === "de" ? successDe : successEn)
    await load()
  } catch {
    showToast(locale.value === "de" ? "Aktion fehlgeschlagen." : "Action failed.", "error")
  } finally {
    controlBusy.value = false
  }
}

const restartRunner = async (): Promise<void> => runControl(
  "/system/control/restart-runner",
  "CDP-Runner wird neu gestartet.",
  "CDP runner restart triggered."
)

const restartApp = async (): Promise<void> => runControl(
  "/system/control/restart-app",
  "Backend-Container wird neu gestartet.",
  "Backend container restart triggered."
)

const restartFrontend = async (): Promise<void> => runControl(
  "/system/control/restart-frontend",
  "Frontend-Container wird neu gestartet.",
  "Frontend container restart triggered."
)

const restartAll = async (): Promise<void> => runControl(
  "/system/control/restart-all",
  "App + Frontend werden neu gestartet.",
  "App + frontend restart triggered."
)

const exportConfig = async (): Promise<void> => {
  try {
    const sections = exportSections.value.join(",")
    const res = await api.get("/system/config/export", { params: { sections } })
    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const stamp = new Date().toISOString().replace(/[:.]/g, "-")
    const link = document.createElement("a")
    link.href = url
    link.download = `signalkiosk-config-${stamp}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    showToast(locale.value === "de" ? "Konfiguration exportiert." : "Configuration exported.")
  } catch {
    showToast(locale.value === "de" ? "Export fehlgeschlagen." : "Export failed.", "error")
  }
}

const importConfig = async (event: Event): Promise<void> => {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  const file = input.files[0]
  try {
    const overwrite = importReplaceExisting.value
    const warning = locale.value === "de"
      ? (overwrite
        ? "Achtung: Bestehende Keys werden beim Import ueberschrieben. Fortfahren?"
        : "Import startet. Nur neue Keys werden angelegt, bestehende bleiben unveraendert. Fortfahren?")
      : (overwrite
        ? "Warning: Existing keys will be overwritten during import. Continue?"
        : "Import will add only new keys and keep existing keys unchanged. Continue?")
    if (!window.confirm(warning)) {
      input.value = ""
      return
    }

    const text = await file.text()
    const payload = JSON.parse(text) as { sections?: Record<string, unknown> }
    if (!payload.sections || typeof payload.sections !== "object") throw new Error("invalid")
    const res = await api.post("/system/config/import", {
      sections: payload.sections,
      selected_sections: importSections.value,
      replace_existing: importReplaceExisting.value
    })
    const data = res.data as { imported?: number; skipped?: number }
    await load()
    showToast(
      locale.value === "de"
        ? `Import abgeschlossen (importiert: ${data.imported ?? 0}, uebersprungen: ${data.skipped ?? 0}).`
        : `Import completed (imported: ${data.imported ?? 0}, skipped: ${data.skipped ?? 0}).`
    )
  } catch {
    showToast(locale.value === "de" ? "Import fehlgeschlagen." : "Import failed.", "error")
  } finally {
    input.value = ""
  }
}

const openImportPicker = (): void => {
  importFileInput.value?.click()
}

const save = async (item: SettingEntry): Promise<void> => {
  await api.put(`/system/settings/${item.key}`, { key: item.key, value: item.value })
  await load()
  showToast(locale.value === "de" ? "Einstellung gespeichert." : "Setting saved.")
}

const create = async (): Promise<void> => {
  error.value = ""
  try {
    const value = JSON.parse(newValue.value) as Record<string, string | number | boolean | null>
    await api.put(`/system/settings/${newKey.value}`, { key: newKey.value, value })
    newKey.value = ""
    newValue.value = '{"value":""}'
    await load()
    showToast(locale.value === "de" ? "Einstellung gespeichert." : "Setting saved.")
  } catch {
    error.value = "JSON-Format ungültig. Beispiel: {\"value\":\"text\"}"
    showToast(locale.value === "de" ? "Speichern fehlgeschlagen." : "Save failed.", "error")
  }
}

onMounted(load)
useUnsavedChangesGuard(isDirty, locale)
</script>

<template>
  <section class="page">
    <h2 class="page-title">{{ locale === 'de' ? 'Einstellungen' : 'Settings' }}</h2>
    <p class="page-subtitle">{{ locale === 'de' ? 'Zentrale Systemwerte für Integrationen und Laufzeitverhalten.' : 'Central system values for integrations and runtime behavior.' }}</p>

    <div class="card">
      <h3>{{ locale === 'de' ? 'Kiosk-Steuerung' : 'Kiosk control' }}</h3>
      <p v-if="controlStatus && !controlStatus.enabled" class="error">{{ locale === 'de' ? 'Host-Control ist nicht aktiv:' : 'Host control is not active:' }} {{ controlStatus.detail || '-' }}</p>
      <p v-else-if="controlStatus" class="hint">{{ locale === 'de' ? 'Runner aktiv:' : 'Runner active:' }} <strong>{{ controlStatus.runner_active ? (locale === 'de' ? 'Ja' : 'Yes') : (locale === 'de' ? 'Nein' : 'No') }}</strong></p>
      <div class="toolbar">
        <button :disabled="controlBusy || !controlStatus?.enabled" @click="restartRunner">{{ locale === 'de' ? 'CDP-Runner neu starten' : 'Restart CDP runner' }}</button>
        <button :disabled="controlBusy || !controlStatus?.enabled" @click="restartApp">{{ locale === 'de' ? 'Backend neu starten' : 'Restart backend' }}</button>
        <button :disabled="controlBusy || !controlStatus?.enabled" @click="restartFrontend">{{ locale === 'de' ? 'Frontend neu starten' : 'Restart frontend' }}</button>
        <button :disabled="controlBusy || !controlStatus?.enabled" @click="restartAll">{{ locale === 'de' ? 'App + Frontend neu starten' : 'Restart app + frontend' }}</button>
      </div>
    </div>

    <div class="card">
      <h3>{{ locale === 'de' ? 'Konfiguration Export/Import' : 'Configuration export/import' }}</h3>
      <p class="hint">{{ locale === 'de' ? 'Exportiert und importiert System-Settings als JSON-Datei.' : 'Exports and imports system settings as a JSON file.' }}</p>
      <div class="section-grid">
        <label v-for="entry in allConfigSections" :key="`export-${entry}`" class="checkbox-row">
          <input type="checkbox" :value="entry" v-model="exportSections" />
          <span>{{ sectionLabel(entry) }} ({{ locale === 'de' ? 'Export' : 'export' }})</span>
        </label>
      </div>
      <div class="section-grid">
        <label v-for="entry in allConfigSections" :key="`import-${entry}`" class="checkbox-row">
          <input type="checkbox" :value="entry" v-model="importSections" />
          <span>{{ sectionLabel(entry) }} ({{ locale === 'de' ? 'Import' : 'import' }})</span>
        </label>
      </div>
      <div class="import-grid">
        <label class="checkbox-row">
          <input type="checkbox" v-model="importReplaceExisting" />
          <span>{{ locale === 'de' ? 'Bestehende Keys beim Import ueberschreiben' : 'Replace existing keys during import' }}</span>
        </label>
      </div>
      <div class="toolbar">
        <button @click="exportConfig">{{ locale === 'de' ? 'Exportieren' : 'Export' }}</button>
        <button type="button" @click="openImportPicker">{{ locale === 'de' ? 'JSON importieren' : 'Import JSON' }}</button>
        <input ref="importFileInput" class="hidden-file-input" type="file" accept="application/json" @change="importConfig" />
      </div>
    </div>

    <div class="card">
      <h3>{{ locale === 'de' ? 'Neue Einstellung' : 'New setting' }}</h3>
      <label>{{ locale === 'de' ? 'Schlüssel (z. B. kiosk.refresh_interval)' : 'Key (e.g. kiosk.refresh_interval)' }}<input v-model="newKey" placeholder="kiosk.refresh_interval" /></label>
      <label>{{ locale === 'de' ? 'Wert als JSON' : 'Value as JSON' }}<textarea v-model="newValue" rows="3"></textarea></label>
      <button @click="create">{{ t('save') }}</button>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <div class="card">
      <table class="data-table">
        <thead>
          <tr><th>Key</th><th>{{ locale === 'de' ? 'Wert (JSON)' : 'Value (JSON)' }}</th><th>{{ locale === 'de' ? 'Aktion' : 'Action' }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.key">
            <td>{{ item.key }}</td>
            <td><code>{{ JSON.stringify(item.value) }}</code></td>
            <td><button @click="save(item)">{{ locale === 'de' ? 'Neu speichern' : 'Save again' }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.hidden-file-input {
  display: none;
}

.checkbox-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  text-transform: none;
  letter-spacing: 0;
  font-size: 14px;
  color: #163548;
}

.checkbox-row span {
  line-height: 1.35;
  white-space: nowrap;
}

.import-grid {
  display: flex;
  justify-content: flex-start;
}

.section-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 8px 0;
}
</style>

