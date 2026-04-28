<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"

interface Preset { id: string; name: string; is_default: boolean }
const items = ref<Preset[]>([])
const name = ref("")

const load = async (): Promise<void> => {
  const res = await api.get("/presets")
  items.value = res.data as Preset[]
}

const create = async (): Promise<void> => {
  await api.post("/presets", { name: name.value, enabled: true, is_default: false, loop_mode: true, shuffle: false, priority: 0 })
  name.value = ""
  await load()
}

onMounted(load)
</script>

<template>
  <section>
    <h2>Presets</h2>
    <input v-model="name" placeholder="Preset-Name" />
    <button @click="create">Erstellen</button>
    <ul>
      <li v-for="item in items" :key="item.id">{{ item.name }} <strong v-if="item.is_default">(Default)</strong></li>
    </ul>
  </section>
</template>
