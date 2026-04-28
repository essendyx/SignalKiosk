<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"

interface Preset { id: string; name: string }
interface Schedule { id: string; name: string; preset_id: string; start_time: string; end_time: string; weekdays: string; timezone: string; priority: number; enabled: boolean }

const schedules = ref<Schedule[]>([])
const presets = ref<Preset[]>([])
const name = ref("")
const presetId = ref("")
const startTime = ref("08:00")
const endTime = ref("18:00")
const timezone = ref("UTC")
const priority = ref(0)
const editingId = ref<string | null>(null)
const { locale, t } = useI18n()

const load = async (): Promise<void> => {
  const [s, p] = await Promise.all([api.get("/schedules"), api.get("/presets")])
  schedules.value = s.data as Schedule[]
  presets.value = p.data as Preset[]
  if (!presetId.value && presets.value.length > 0) presetId.value = presets.value[0].id
}

const save = async (): Promise<void> => {
  const payload = { name: name.value, preset_id: presetId.value, weekdays: "0,1,2,3,4,5,6", start_time: startTime.value, end_time: endTime.value, timezone: timezone.value, priority: priority.value, enabled: true }
  if (editingId.value) await api.put(`/schedules/${editingId.value}`, payload)
  else await api.post("/schedules", payload)
  name.value = ""
  startTime.value = "08:00"
  endTime.value = "18:00"
  timezone.value = "UTC"
  priority.value = 0
  editingId.value = null
  await load()
}

const editItem = (item: Schedule): void => {
  editingId.value = item.id
  name.value = item.name
  presetId.value = item.preset_id
  startTime.value = item.start_time
  endTime.value = item.end_time
  timezone.value = item.timezone
  priority.value = item.priority
}

const remove = async (id: string): Promise<void> => {
  await api.delete(`/schedules/${id}`)
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page">
    <h2 class="page-title">{{ locale === 'de' ? 'Zeitplaene' : 'Schedules' }}</h2>
    <p class="page-subtitle">{{ locale === 'de' ? 'Zeitplaene sind optional. Ausserhalb aller Zeitfenster laeuft das Standard-Preset.' : 'Schedules are optional. Outside schedule windows, the default preset runs.' }}</p>
    <div class="card form-grid wide">
      <label>{{ locale === 'de' ? 'Planname' : 'Schedule name' }}<input v-model="name" :placeholder="locale === 'de' ? 'Morgenrotation' : 'Morning rotation'" /></label>
      <label>Preset<select v-model="presetId">
        <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select></label>
      <label>{{ locale === 'de' ? 'Startzeit' : 'Start time' }}<input v-model="startTime" type="time" /></label>
      <label>{{ locale === 'de' ? 'Endzeit' : 'End time' }}<input v-model="endTime" type="time" /></label>
      <label>{{ locale === 'de' ? 'Zeitzone' : 'Timezone' }}<input v-model="timezone" placeholder="Europe/Berlin" /></label>
      <label>{{ locale === 'de' ? 'Prioritaet' : 'Priority' }}<input v-model.number="priority" type="number" /></label>
      <div class="toolbar"><button @click="save">{{ editingId ? t('save') : (locale === 'de' ? 'Anlegen' : 'Create') }}</button></div>
    </div>
    <table class="data-table">
      <thead><tr><th>{{ locale === 'de' ? 'Name' : 'Name' }}</th><th>Preset</th><th>{{ locale === 'de' ? 'Zeitfenster' : 'Window' }}</th><th>{{ locale === 'de' ? 'Aktionen' : 'Actions' }}</th></tr></thead>
      <tbody>
        <tr v-for="s in schedules" :key="s.id">
          <td>{{ s.name }}</td>
          <td>{{ presets.find((p) => p.id === s.preset_id)?.name || s.preset_id }}</td>
          <td>{{ s.start_time }} - {{ s.end_time }} ({{ s.timezone }})</td>
          <td class="actions">
            <button class="ghost" @click="editItem(s)">{{ t('edit') }}</button>
            <button class="danger" @click="remove(s.id)">{{ t('delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
