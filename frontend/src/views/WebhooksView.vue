<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"

interface Webhook { id: string; name: string; slug: string; enabled: boolean; allowed_actions: string[] }
const items = ref<Webhook[]>([])
const name = ref("")
const slug = ref("")
const token = ref("")

const load = async (): Promise<void> => {
  const res = await api.get("/webhooks")
  items.value = res.data as Webhook[]
}

const create = async (): Promise<void> => {
  await api.post("/webhooks", {
    name: name.value,
    slug: slug.value,
    token: token.value,
    enabled: true,
    allowed_actions: ["play_url", "play_existing_content", "play_preset", "stop_override"]
  })
  await load()
}

onMounted(load)
</script>

<template>
  <section>
    <h2>Webhooks</h2>
    <div>
      <input v-model="name" placeholder="Name" />
      <input v-model="slug" placeholder="Slug" />
      <input v-model="token" type="password" placeholder="Token" />
      <button @click="create">Erstellen</button>
    </div>
    <ul>
      <li v-for="item in items" :key="item.id">{{ item.name }} - /webhook/{{ item.slug }}</li>
    </ul>
  </section>
</template>
