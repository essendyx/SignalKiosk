<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"

interface SettingEntry {
  key: string
  value: Record<string, string | number | boolean | null>
  updated_at: string
}

const items = ref<SettingEntry[]>([])
const newKey = ref("")
const newValue = ref('{"value":""}')
const error = ref("")
const { locale, t } = useI18n()

const load = async (): Promise<void> => {
  const res = await api.get("/system/settings")
  items.value = res.data as SettingEntry[]
}

const save = async (item: SettingEntry): Promise<void> => {
  await api.put(`/system/settings/${item.key}`, { key: item.key, value: item.value })
  await load()
}

const create = async (): Promise<void> => {
  error.value = ""
  try {
    const value = JSON.parse(newValue.value) as Record<string, string | number | boolean | null>
    await api.put(`/system/settings/${newKey.value}`, { key: newKey.value, value })
    newKey.value = ""
    newValue.value = '{"value":""}'
    await load()
  } catch {
    error.value = "JSON-Format ungueltig. Beispiel: {\"value\":\"text\"}"
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <h2 class="page-title">{{ locale === 'de' ? 'Einstellungen' : 'Settings' }}</h2>
    <p class="page-subtitle">{{ locale === 'de' ? 'Zentrale Systemwerte fuer Integrationen und Laufzeitverhalten.' : 'Central system values for integrations and runtime behavior.' }}</p>
    <div class="card">
      <h3>{{ locale === 'de' ? 'Neue Einstellung' : 'New setting' }}</h3>
      <label>{{ locale === 'de' ? 'Schluessel (z. B. kiosk.refresh_interval)' : 'Key (e.g. kiosk.refresh_interval)' }}<input v-model="newKey" placeholder="kiosk.refresh_interval" /></label>
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
