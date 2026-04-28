<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"

interface Preset { id: string; name: string }
interface Schedule { id: string; name: string; preset_id: string; start_time: string; end_time: string; weekdays: string }

const schedules = ref<Schedule[]>([])
const presets = ref<Preset[]>([])
const name = ref("")
const presetId = ref("")

const load = async (): Promise<void> => {
  const [s, p] = await Promise.all([api.get("/schedules"), api.get("/presets")])
  schedules.value = s.data as Schedule[]
  presets.value = p.data as Preset[]
  if (!presetId.value && presets.value.length > 0) presetId.value = presets.value[0].id
}

const create = async (): Promise<void> => {
  await api.post("/schedules", { name: name.value, preset_id: presetId.value, weekdays: "0,1,2,3,4,5,6", start_time: "00:00", end_time: "23:59", timezone: "UTC", priority: 0, enabled: true })
  name.value = ""
  await load()
}

onMounted(load)
</script>

<template>
  <section>
    <h2>Zeitplaene</h2>
    <input v-model="name" placeholder="Name" />
    <select v-model="presetId">
      <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.name }}</option>
    </select>
    <button @click="create">Anlegen</button>
    <ul>
      <li v-for="s in schedules" :key="s.id">{{ s.name }} - {{ s.start_time }} bis {{ s.end_time }}</li>
    </ul>
  </section>
</template>
