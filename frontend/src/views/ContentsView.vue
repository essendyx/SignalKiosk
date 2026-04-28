<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"
import api from "../api"
import { useI18n } from "../i18n"

interface Content {
  id: string
  name: string
  type: string
  description?: string
  config_json: string
  default_duration_seconds: number
}

const items = ref<Content[]>([])
const name = ref("")
const type = ref("webpage")
const sourceUrl = ref("https://example.org")
const webpageMode = ref("direct")
const assetPath = ref("")
const htmlValue = ref("<section><h1>Welcome</h1><p>Your SignalKiosk is ready.</p></section>")
const description = ref("")
const duration = ref(15)
const editingId = ref<string | null>(null)
const uploadState = ref("")
const error = ref("")
const showModal = ref(false)
const showDeleteModal = ref(false)
const selectedContentId = ref("")
const { locale, t } = useI18n()

const load = async (): Promise<void> => {
  const res = await api.get("/contents")
  items.value = (res.data.items ?? []) as Content[]
  if (!selectedContentId.value && items.value.length > 0) selectedContentId.value = items.value[0].id
  if (selectedContentId.value && !items.value.some((item) => item.id === selectedContentId.value)) {
    selectedContentId.value = items.value.length > 0 ? items.value[0].id : ""
  }
}

const resetForm = (): void => {
  name.value = ""
  type.value = "webpage"
  sourceUrl.value = "https://example.org"
  webpageMode.value = "direct"
  assetPath.value = ""
  htmlValue.value = "<section><h1>Welcome</h1><p>Your SignalKiosk is ready.</p></section>"
  description.value = ""
  duration.value = 15
  editingId.value = null
  uploadState.value = ""
  error.value = ""
}

const openCreateModal = (): void => {
  resetForm()
  showModal.value = true
}

const closeModal = (): void => {
  showModal.value = false
}

const buildConfig = (): string => {
  if (type.value === "webpage") return JSON.stringify({ url: sourceUrl.value, webpage_mode: webpageMode.value })
  if (type.value === "html") return JSON.stringify({ html: htmlValue.value })
  if (type.value === "image" || type.value === "video") {
    const cfg: { url?: string; asset_path?: string } = {}
    if (sourceUrl.value.trim()) cfg.url = sourceUrl.value.trim()
    if (assetPath.value.trim()) cfg.asset_path = assetPath.value.trim()
    return JSON.stringify(cfg)
  }
  return "{}"
}

const save = async (): Promise<void> => {
  error.value = ""
  const payload = {
    name: name.value,
    type: type.value,
    description: description.value,
    config_json: buildConfig(),
    default_duration_seconds: duration.value,
    enabled: true
  }
  try {
    if (editingId.value) await api.put(`/contents/${editingId.value}`, payload)
    else await api.post("/contents", payload)
    closeModal()
    resetForm()
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || (locale.value === "de" ? "Speichern fehlgeschlagen" : "Save failed")
  }
}

const editItem = (item: Content): void => {
  editingId.value = item.id
  name.value = item.name
  type.value = item.type
  description.value = item.description || ""
  duration.value = item.default_duration_seconds
  try {
    const cfg = JSON.parse(item.config_json) as { url?: string; html?: string; asset_path?: string; webpage_mode?: string }
    sourceUrl.value = cfg.url || ""
    webpageMode.value = cfg.webpage_mode || "direct"
    htmlValue.value = cfg.html || ""
    assetPath.value = cfg.asset_path || ""
  } catch {
    sourceUrl.value = ""
    webpageMode.value = "direct"
    htmlValue.value = ""
    assetPath.value = ""
  }
  showModal.value = true
}

const onFileSelected = async (event: Event): Promise<void> => {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  uploadState.value = locale.value === "de" ? "Upload laeuft..." : "Upload in progress..."
  const fd = new FormData()
  fd.append("file", input.files[0])
  try {
    const res = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } })
    assetPath.value = res.data.asset_path as string
    uploadState.value = locale.value === "de" ? `Upload erfolgreich: ${res.data.name}` : `Upload successful: ${res.data.name}`
  } catch (err: any) {
    uploadState.value = err?.response?.data?.detail || (locale.value === "de" ? "Upload fehlgeschlagen" : "Upload failed")
  }
}

const remove = async (id: string): Promise<void> => {
  await api.delete(`/contents/${id}`)
  await load()
}

const editSelected = (): void => {
  const found = items.value.find((item) => item.id === selectedContentId.value)
  if (found) editItem(found)
}

const removeSelected = async (): Promise<void> => {
  if (!selectedContentId.value) return
  await remove(selectedContentId.value)
  showDeleteModal.value = false
}

const typeLabel = (value: string): string => {
  if (locale.value === "de") {
    if (value === "webpage") return "Webseite"
    if (value === "image") return "Bild"
    return value
  }
  if (value === "webpage") return "Web page"
  if (value === "image") return "Image"
  return value
}

const sourceSummary = (item: Content): string => {
  try {
    const cfg = JSON.parse(item.config_json) as { url?: string; asset_path?: string; html?: string }
    if (item.type === "html") return locale.value === "de" ? "Inline HTML" : "Inline HTML"
    if (cfg.asset_path) return cfg.asset_path
    if (cfg.url) return cfg.url
  } catch {
    return "-"
  }
  return "-"
}

const onEsc = (event: KeyboardEvent): void => {
  if (event.key !== "Escape") return
  if (showDeleteModal.value) showDeleteModal.value = false
  if (showModal.value) closeModal()
}

onMounted(async () => {
  window.addEventListener("keydown", onEsc)
  await load()
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onEsc)
})
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ locale === 'de' ? 'Inhalte' : 'Contents' }}</h2>
        <p class="page-subtitle">{{ locale === 'de' ? 'Inhalte werden ueber einen professionellen Erstellungsdialog angelegt.' : 'Create and manage content using a professional modal workflow.' }}</p>
      </div>
      <button @click="openCreateModal">{{ locale === 'de' ? '+ Neuer Inhalt' : '+ New Content' }}</button>
    </div>

    <div class="card" v-if="items.length > 0">
      <div class="current-toolbar">
        <label class="current-select">{{ locale === 'de' ? 'Aktueller Inhalt' : 'Current content' }}
          <select v-model="selectedContentId">
            <option v-for="item in items" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
        </label>
        <div class="actions">
          <button class="ghost" @click="editSelected">{{ t('edit') }}</button>
          <button class="danger" @click="showDeleteModal = true">{{ t('delete') }}</button>
        </div>
      </div>
    </div>

    <table class="data-table contents-table">
      <thead><tr><th>{{ locale === 'de' ? 'Name' : 'Name' }}</th><th>{{ locale === 'de' ? 'Typ' : 'Type' }}</th><th>{{ locale === 'de' ? 'Quelle' : 'Source' }}</th><th>{{ locale === 'de' ? 'Dauer (s)' : 'Duration (s)' }}</th><th>{{ locale === 'de' ? 'Aktionen' : 'Actions' }}</th></tr></thead>
      <tbody>
        <tr v-for="item in items" :key="item.id">
          <td>{{ item.name }}</td>
          <td>{{ typeLabel(item.type) }}</td>
          <td>{{ sourceSummary(item) }}</td>
          <td>{{ item.default_duration_seconds }}</td>
          <td class="actions row-actions">
            <button class="ghost" @click="editItem(item)">{{ t('edit') }}</button>
            <button class="danger" @click="remove(item.id)">{{ t('delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showDeleteModal" class="modal-backdrop" @click.self="showDeleteModal = false">
      <div class="modal-card" role="dialog" aria-modal="true" aria-label="Delete content">
        <h3>{{ locale === 'de' ? 'Inhalt loeschen?' : 'Delete content?' }}</h3>
        <p>{{ locale === 'de' ? 'Dieser Inhalt wird dauerhaft entfernt.' : 'This content will be removed permanently.' }}</p>
        <div class="modal-actions">
          <button class="ghost" @click="showDeleteModal = false">{{ t('cancel') }}</button>
          <button class="danger" @click="removeSelected">{{ t('delete') }}</button>
        </div>
      </div>
    </div>

    <div v-if="showModal" class="modal-backdrop" @click.self="closeModal">
      <div class="modal-card" role="dialog" aria-modal="true" aria-label="Content dialog">
        <h3>{{ editingId ? (locale === 'de' ? 'Inhalt bearbeiten' : 'Edit content') : (locale === 'de' ? 'Neuer Inhalt' : 'New content') }}</h3>
        <div class="form-grid wide">
          <label>{{ locale === 'de' ? 'Anzeigename' : 'Display name' }}<input v-model="name" /></label>
          <label>{{ locale === 'de' ? 'Inhaltstyp' : 'Content type' }}<select v-model="type"><option value="webpage">{{ locale === 'de' ? 'Webseite' : 'Web page' }}</option><option value="image">{{ locale === 'de' ? 'Bild' : 'Image' }}</option><option value="video">Video</option><option value="html">HTML</option></select></label>
          <label v-if="type === 'webpage'">URL<input v-model="sourceUrl" placeholder="https://..." /></label>
          <label v-if="type === 'webpage'">{{ locale === 'de' ? 'Webseiten-Modus' : 'Webpage mode' }}
            <select v-model="webpageMode">
              <option value="direct">{{ locale === 'de' ? 'Direkt (Proxy, mit Rotation)' : 'Direct (proxy, rotation-safe)' }}</option>
              <option value="embedded">{{ locale === 'de' ? 'Eingebettet (iframe)' : 'Embedded (iframe)' }}</option>
            </select>
          </label>
          <label v-if="type === 'image' || type === 'video'">{{ locale === 'de' ? 'Externe URL (optional)' : 'External URL (optional)' }}<input v-model="sourceUrl" placeholder="https://..." /></label>
          <label v-if="type === 'image' || type === 'video'">{{ locale === 'de' ? 'Datei hochladen' : 'Upload file' }}<input type="file" :accept="type === 'image' ? 'image/*' : 'video/*'" @change="onFileSelected" /></label>
          <label v-if="type === 'image' || type === 'video'">{{ locale === 'de' ? 'Upload-Pfad' : 'Upload path' }}<input v-model="assetPath" placeholder="/media/..." /></label>
          <label v-if="type === 'html'" class="full-width">HTML<textarea v-model="htmlValue" rows="10"></textarea></label>
          <label>{{ locale === 'de' ? 'Beschreibung' : 'Description' }}<input v-model="description" /></label>
          <label>{{ locale === 'de' ? 'Dauer (Sekunden)' : 'Duration (seconds)' }}<input v-model.number="duration" type="number" min="1" max="86400" /></label>
          <p v-if="uploadState" class="hint full-width">{{ uploadState }}</p>
          <p v-if="error" class="error full-width">{{ error }}</p>
        </div>
        <div class="modal-actions">
          <button class="ghost" @click="closeModal">{{ t('cancel') }}</button>
          <button @click="save">{{ editingId ? t('save') : t('create') }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: start; gap: 12px; }
.current-toolbar { display: flex; gap: 12px; align-items: end; }
.current-select { width: 100%; max-width: 520px; }
.contents-table td { vertical-align: middle; }
.contents-table .row-actions { align-items: center; }
.contents-table .row-actions button { min-height: 36px; padding: 8px 11px; font-size: 13px; }
.contents-table tbody tr { height: 62px; }
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(8, 24, 36, 0.45);
  backdrop-filter: blur(4px);
  display: grid;
  place-items: center;
  z-index: 60;
  padding: 16px;
}
.modal-card {
  width: min(920px, 100%);
  background: #fff;
  border: 1px solid #cfdae4;
  border-radius: 14px;
  box-shadow: 0 30px 70px rgba(7, 24, 38, 0.25);
  padding: 20px;
  display: grid;
  gap: 12px;
}
.modal-card h3 { margin: 0; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
@media (max-width: 980px) {
  .page-head { flex-direction: column; }
  .current-toolbar { flex-direction: column; align-items: stretch; }
}
</style>
