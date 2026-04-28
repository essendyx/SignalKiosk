<script setup lang="ts">
import { onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"

interface Webhook { id: string; name: string; slug: string; enabled: boolean; allowed_actions: string[] }
const items = ref<Webhook[]>([])
const name = ref("")
const slug = ref("")
const token = ref("")
const editingId = ref<string | null>(null)
const { locale, t } = useI18n()

const load = async (): Promise<void> => {
  const res = await api.get("/webhooks")
  items.value = res.data as Webhook[]
}

const save = async (): Promise<void> => {
  const payload = { name: name.value, slug: slug.value, token: token.value, enabled: true, allowed_actions: ["play_url", "play_existing_content", "play_preset", "stop_override"] }
  if (editingId.value) await api.put(`/webhooks/${editingId.value}`, payload)
  else await api.post("/webhooks", payload)
  name.value = ""
  slug.value = ""
  token.value = ""
  editingId.value = null
  await load()
}

const editItem = (item: Webhook): void => {
  editingId.value = item.id
  name.value = item.name
  slug.value = item.slug
  token.value = ""
}

const remove = async (id: string): Promise<void> => {
  await api.delete(`/webhooks/${id}`)
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page">
    <h2 class="page-title">Webhooks</h2>
    <p class="page-subtitle">{{ locale === 'de' ? 'Externe Systeme koennen Playback-Events sicher ueber diese Endpunkte ausloesen.' : 'External systems can securely trigger playback events through these endpoints.' }}</p>
    <div class="card form-grid wide">
      <label>{{ locale === 'de' ? 'Name' : 'Name' }}<input v-model="name" :placeholder="locale === 'de' ? 'Brandmeldeanlage' : 'Fire alarm'" /></label>
      <label>Slug<input v-model="slug" placeholder="fire-alarm" /></label>
      <label>Token<input v-model="token" type="password" :placeholder="locale === 'de' ? 'Sicherer Zugriffstoken' : 'Secure access token'" /></label>
      <div class="toolbar"><button @click="save">{{ editingId ? t('save') : t('create') }}</button></div>
    </div>
    <table class="data-table">
      <thead><tr><th>{{ locale === 'de' ? 'Name' : 'Name' }}</th><th>Endpoint</th><th>{{ locale === 'de' ? 'Aktionen' : 'Actions' }}</th></tr></thead>
      <tbody>
        <tr v-for="item in items" :key="item.id">
          <td>{{ item.name }}</td>
          <td><code>/webhook/{{ item.slug }}</code></td>
          <td class="actions">
            <button class="ghost" @click="editItem(item)">{{ t('edit') }}</button>
            <button class="danger" @click="remove(item.id)">{{ t('delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
