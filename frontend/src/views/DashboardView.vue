<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"

interface Status {
  mode: string
  active_preset_id: string | null
  active_content_id: string | null
  ends_at: string | null
  reason: string
}

interface NamedEntity { id: string; name: string }
interface PresetFull extends NamedEntity { is_default: boolean }
interface Schedule { id: string; enabled: boolean }

const status = ref<Status | null>(null)
const presets = ref<PresetFull[]>([])
const contents = ref<NamedEntity[]>([])
const schedules = ref<Schedule[]>([])
const { locale } = useI18n()
const playbackUrl = `${window.location.protocol}//${window.location.hostname}:${import.meta.env.VITE_PLAYBACK_PORT || "8090"}/api/playback/status`

const load = async (): Promise<void> => {
  const [statusRes, presetsRes, contentsRes, schedulesRes] = await Promise.all([
    api.get("/playback/status"),
    api.get("/presets"),
    api.get("/contents"),
    api.get("/schedules")
  ])
  status.value = statusRes.data as Status
  presets.value = presetsRes.data as PresetFull[]
  contents.value = (contentsRes.data.items ?? []) as NamedEntity[]
  schedules.value = schedulesRes.data as Schedule[]
}

const presetName = (id: string | null): string => {
  if (!id) return "-"
  return presets.value.find((p) => p.id === id)?.name || id
}

const contentName = (id: string | null): string => {
  if (!id) return "-"
  return contents.value.find((c) => c.id === id)?.name || id
}

const guidance = (): string => {
  if (locale.value === "de") {
    if (!status.value) return "Lade Status..."
    if (status.value.mode === "fallback") return "Kein aktives Preset verfügbar. Setzen Sie ein Standard-Preset oder aktivieren Sie einen Zeitplan."
    if (status.value.mode === "default") return "Standardbetrieb aktiv. Zeitpläne sind optional und können den Betrieb zeitweise überschreiben."
    if (status.value.mode === "schedule") return "Ein Zeitplan steuert aktuell die Wiedergabe."
    return "Webhook-Override aktiv. Nach Ablauf wird automatisch zur regulären Logik zurückgekehrt."
  }
  if (!status.value) return "Loading status..."
  if (status.value.mode === "fallback") return "No active preset found. Set a default preset or activate a schedule."
  if (status.value.mode === "default") return "Default mode is active. Schedules are optional and can override this temporarily."
  if (status.value.mode === "schedule") return "A schedule currently controls playback."
  return "Webhook override is active. Regular playback resumes automatically after expiration."
}

const checklist = (): Array<{ label: string; ok: boolean; detail: string }> => {
  const hasContent = contents.value.length > 0
  const hasPreset = presets.value.length > 0
  const hasDefaultPreset = presets.value.some((item) => item.is_default)
  const hasSchedule = schedules.value.some((item) => item.enabled)
  if (locale.value === "en") {
    return [
      { label: "Contents", ok: hasContent, detail: hasContent ? "Available" : "Create at least one content item" },
      { label: "Presets", ok: hasPreset, detail: hasPreset ? "Available" : "Create at least one preset" },
      { label: "Default preset", ok: hasDefaultPreset, detail: hasDefaultPreset ? "Defined" : "Mark one preset as default" },
      { label: "Schedule (optional)", ok: true, detail: hasSchedule ? "Active" : "No active schedule - default preset runs continuously" }
    ]
  }
  return [
    { label: "Inhalte", ok: hasContent, detail: hasContent ? "Vorhanden" : "Mindestens einen Inhalt anlegen" },
    { label: "Presets", ok: hasPreset, detail: hasPreset ? "Vorhanden" : "Mindestens ein Preset anlegen" },
    { label: "Standard-Preset", ok: hasDefaultPreset, detail: hasDefaultPreset ? "Definiert" : "Ein Preset als Standard markieren" },
    { label: "Zeitplan (optional)", ok: true, detail: hasSchedule ? "Aktiv" : "Kein aktiver Zeitplan - Standard-Preset läuft dauerhaft" }
  ]
}

onMounted(load)
</script>

<template>
  <section class="page">
    <h2 class="page-title">Dashboard</h2>
    <p class="page-subtitle">{{ locale === 'de' ? 'Übersicht über den aktuellen Wiedergabestatus des Kiosks.' : 'Overview of the current kiosk playback status.' }}</p>
    <div class="toolbar">
      <a :href="playbackUrl" target="_blank" rel="noopener"><button>{{ locale === 'de' ? 'CDP-Runner/Playback-Status' : 'Open CDP runner/playback status' }}</button></a>
    </div>
    <div class="status-grid">
      <div class="card" v-if="status">
        <h3>{{ locale === 'de' ? 'Aktueller Status' : 'Current Status' }}</h3>
        <p><strong>{{ locale === 'de' ? 'Modus' : 'Mode' }}:</strong> {{ status.mode }}</p>
        <p><strong>{{ locale === 'de' ? 'Grund' : 'Reason' }}:</strong> {{ status.reason }}</p>
        <p><strong>{{ locale === 'de' ? 'Aktives Preset' : 'Active Preset' }}:</strong> {{ presetName(status.active_preset_id) }}</p>
        <p><strong>{{ locale === 'de' ? 'Aktiver Inhalt' : 'Active Content' }}:</strong> {{ contentName(status.active_content_id) }}</p>
        <p><strong>{{ locale === 'de' ? 'Gültig bis' : 'Valid Until' }}:</strong> {{ status.ends_at || "-" }}</p>
      </div>
      <div class="card" v-else>{{ locale === 'de' ? 'Lade Statusdaten...' : 'Loading status...' }}</div>
      <div class="card" v-if="status">
        <h3>{{ locale === 'de' ? 'Was ist zu tun?' : 'What should I do?' }}</h3>
        <p>{{ guidance() }}</p>
      </div>
      <div class="card" v-if="status">
        <h3>{{ locale === 'de' ? 'Setup-Checkliste' : 'Setup Checklist' }}</h3>
        <table class="data-table compact-table">
          <thead><tr><th>{{ locale === 'de' ? 'Bereich' : 'Area' }}</th><th>Status</th><th>{{ locale === 'de' ? 'Hinweis' : 'Hint' }}</th></tr></thead>
          <tbody>
            <tr v-for="item in checklist()" :key="item.label">
              <td>{{ item.label }}</td>
              <td><span :class="item.ok ? 'state-ok' : 'state-warn'">{{ item.ok ? (locale === 'de' ? 'Grün' : 'Green') : (locale === 'de' ? 'Gelb' : 'Yellow') }}</span></td>
              <td>{{ item.detail }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

