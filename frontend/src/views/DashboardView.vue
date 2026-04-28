<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"

interface Status {
  mode: string
  active_preset_id: string | null
  active_content_id: string | null
  ends_at: string | null
}

const status = ref<Status | null>(null)
const load = async (): Promise<void> => {
  const res = await api.get("/playback/status")
  status.value = res.data as Status
}
onMounted(load)
</script>

<template>
  <div>
    <h2>Dashboard</h2>
    <pre v-if="status">{{ status }}</pre>
    <p v-else>Lade...</p>
  </div>
</template>
