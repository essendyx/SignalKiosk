<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"

interface Content {
  id: string
  name: string
  type: string
  config_json: string
  default_duration_seconds: number
}

const items = ref<Content[]>([])
const name = ref("")
const type = ref("webpage")
const url = ref("https://example.org")

const load = async (): Promise<void> => {
  const res = await api.get("/contents")
  items.value = (res.data.items ?? []) as Content[]
}

const create = async (): Promise<void> => {
  await api.post("/contents", {
    name: name.value,
    type: type.value,
    config_json: JSON.stringify({ url: url.value }),
    default_duration_seconds: 15,
    enabled: true
  })
  await load()
}

onMounted(load)
</script>

<template>
  <section>
    <h2>Inhalte</h2>
    <div>
      <input v-model="name" placeholder="Name" />
      <select v-model="type">
        <option value="webpage">Webseite</option>
        <option value="image">Bild</option>
        <option value="video">Video</option>
        <option value="html">HTML</option>
      </select>
      <input v-model="url" placeholder="URL/Datei" />
      <button @click="create">Hinzufuegen</button>
    </div>
    <ul>
      <li v-for="item in items" :key="item.id">{{ item.name }} - {{ item.type }}</li>
    </ul>
  </section>
</template>
