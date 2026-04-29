<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import api from "../api"
import { useI18n } from "../i18n"
import { confirmDiscardChanges, useUnsavedChangesGuard } from "../composables/useUnsavedChangesGuard"
import { showToast } from "../state/toast"

interface Preset {
  id: string
  name: string
  description?: string
  enabled: boolean
  is_default: boolean
  loop_mode: boolean
  shuffle: boolean
  priority: number
}

interface Content { id: string; name: string }

interface PresetItem {
  id: string
  preset_id: string
  content_id: string
  position: number
  duration_seconds: number | null
  enabled: boolean
}

const presets = ref<Preset[]>([])
const contents = ref<Content[]>([])
const presetItems = ref<PresetItem[]>([])

const selectedPresetId = ref("")
const contentId = ref("")
const newDuration = ref<number | null>(null)
const error = ref("")
const draggingItemId = ref("")

const showCreateModal = ref(false)
const showDeleteModal = ref(false)
const createName = ref("")
const createDescription = ref("")
const createIsDefault = ref(false)
const dirtyItemIds = ref<string[]>([])
const suppressPresetSwitchGuard = ref(false)
const { locale, t } = useI18n()

const text = computed(() => locale.value === "de" ? {
  title: "Presets",
  subtitle: "Wählen Sie ein Preset zur Bearbeitung oder erstellen Sie ein neues Preset über den Hauptbutton.",
  newPreset: "+ Neues Preset",
  currentPreset: "Aktuelles Preset",
  setDefault: "Als Standard setzen",
  deletePreset: "Preset löschen",
  defaultHint: "Dieses Preset ist aktuell als Standard markiert und läuft außerhalb von Zeitplänen.",
  noneTitle: "Noch kein Preset vorhanden",
  noneText: "Erstellen Sie zuerst ein Preset über + Neues Preset, bevor Sie Inhalte zuordnen können.",
  presetContent: "Inhalte im Preset",
  content: "Inhalt",
  duration: "Dauer (Sekunden)",
  durationReq: "Pflicht ab 2 Inhalten",
  durationOpt: "Bei einem Inhalt optional",
  addContent: "Inhalt hinzufügen",
  rule: "Regel: Bei genau einem Inhalt kann die Dauer leer bleiben (endlos). Ab zwei Inhalten ist die Dauer pro Inhalt verpflichtend.",
  drag: "Sortierung per Drag-and-Drop. Dauer und Inhalt pro Zeile sind direkt editierbar.",
  colContent: "Inhalt",
  colPos: "Position",
  colDuration: "Dauer (s)",
  colActions: "Aktionen",
  optional: "Optional",
  required: "Pflicht",
  createTitle: "Neues Preset",
  presetName: "Preset-Name",
  description: "Beschreibung",
  markDefault: "Als Standard markieren",
  no: "Nein",
  yes: "Ja",
  createPreset: "Preset erstellen",
  deleteTitle: "Preset löschen?",
  deleteText: "Dieses Preset und alle zugeordneten Einträge werden entfernt. Dieser Vorgang kann nicht rückgängig gemacht werden.",
  deleteFinal: "Endgültig löschen"
} : {
  title: "Presets",
  subtitle: "Select a preset to edit or create a new one using the primary action.",
  newPreset: "+ New Preset",
  currentPreset: "Current preset",
  setDefault: "Set as default",
  deletePreset: "Delete preset",
  defaultHint: "This preset is marked as default and runs outside schedule windows.",
  noneTitle: "No presets yet",
  noneText: "Create your first preset via + New Preset before assigning content.",
  presetContent: "Preset content",
  content: "Content",
  duration: "Duration (seconds)",
  durationReq: "Required from 2 items",
  durationOpt: "Optional for a single item",
  addContent: "Add content",
  rule: "Rule: with exactly one item, duration can stay empty (infinite). From two items onward, each item needs a duration.",
  drag: "Reorder via drag and drop. Duration and content can be edited inline.",
  colContent: "Content",
  colPos: "Position",
  colDuration: "Duration (s)",
  colActions: "Actions",
  optional: "Optional",
  required: "Required",
  createTitle: "New preset",
  presetName: "Preset name",
  description: "Description",
  markDefault: "Mark as default",
  no: "No",
  yes: "Yes",
  createPreset: "Create preset",
  deleteTitle: "Delete preset?",
  deleteText: "This deletes the preset and all linked entries. This action cannot be undone.",
  deleteFinal: "Delete permanently"
})

const selectedPreset = computed(() => presets.value.find((item) => item.id === selectedPresetId.value) || null)
const hasPresets = computed(() => presets.value.length > 0)
const durationRequiredForNew = computed(() => presetItems.value.filter((item) => item.enabled).length >= 1)
const hasDirtyItems = computed(() => dirtyItemIds.value.length > 0)
const isDirty = computed(() => {
  const createDirty = showCreateModal.value && (Boolean(createName.value.trim()) || Boolean(createDescription.value.trim()) || createIsDefault.value)
  return createDirty || dirtyItemIds.value.length > 0
})

const load = async (): Promise<void> => {
  error.value = ""
  const [presetsRes, contentsRes] = await Promise.all([api.get("/presets"), api.get("/contents")])
  presets.value = presetsRes.data as Preset[]
  contents.value = (contentsRes.data.items ?? []) as Content[]
  if (!selectedPresetId.value && presets.value.length > 0) {
    selectedPresetId.value = presets.value[0].id
  }
  if (selectedPresetId.value && !presets.value.some((item) => item.id === selectedPresetId.value)) {
    selectedPresetId.value = presets.value.length > 0 ? presets.value[0].id : ""
  }
  if (!contentId.value && contents.value.length > 0) {
    contentId.value = contents.value[0].id
  }
  await loadPresetItems()
}

const loadPresetItems = async (): Promise<void> => {
  presetItems.value = []
  if (!selectedPresetId.value) return
  const res = await api.get(`/presets/${selectedPresetId.value}/items`)
  presetItems.value = (res.data as PresetItem[]).sort((a, b) => a.position - b.position)
}

const openCreateModal = (): void => {
  createName.value = ""
  createDescription.value = ""
  createIsDefault.value = false
  error.value = ""
  showCreateModal.value = true
}

const closeCreateModal = (): void => {
  if (showCreateModal.value && (createName.value.trim() || createDescription.value.trim() || createIsDefault.value) && !confirmDiscardChanges(locale)) return
  showCreateModal.value = false
}

const closeDeleteModal = (): void => {
  showDeleteModal.value = false
}

const createPreset = async (): Promise<void> => {
  error.value = ""
  try {
    await api.post("/presets", {
      name: createName.value,
      description: createDescription.value,
      enabled: true,
      is_default: createIsDefault.value,
      loop_mode: true,
      shuffle: false,
      priority: 0
    })
    closeCreateModal()
    await load()
    const created = presets.value.find((item) => item.name === createName.value)
    if (created) selectedPresetId.value = created.id
    showToast(locale.value === "de" ? "Preset gespeichert." : "Preset saved.")
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "Preset konnte nicht erstellt werden"
    showToast(locale.value === "de" ? "Speichern fehlgeschlagen." : "Save failed.", "error")
  }
}

const deleteSelectedPreset = async (): Promise<void> => {
  if (!selectedPresetId.value) return
  error.value = ""
  try {
    await api.delete(`/presets/${selectedPresetId.value}`)
    closeDeleteModal()
    selectedPresetId.value = ""
    await load()
    showToast(locale.value === "de" ? "Preset gelöscht." : "Preset deleted.")
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "Preset konnte nicht gelöscht werden"
  }
}

const setAsDefault = async (): Promise<void> => {
  if (!selectedPreset.value) return
  error.value = ""
  try {
    await api.put(`/presets/${selectedPreset.value.id}`, {
      name: selectedPreset.value.name,
      description: selectedPreset.value.description || "",
      enabled: selectedPreset.value.enabled,
      is_default: true,
      loop_mode: selectedPreset.value.loop_mode,
      shuffle: selectedPreset.value.shuffle,
      priority: selectedPreset.value.priority
    })
    const keepId = selectedPreset.value.id
    await load()
    selectedPresetId.value = keepId
    showToast(locale.value === "de" ? "Standard-Preset gesetzt." : "Default preset updated.")
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "Standard-Preset konnte nicht gesetzt werden"
  }
}

const addItem = async (): Promise<void> => {
  if (!selectedPresetId.value || !contentId.value) return
  error.value = ""
  try {
    await api.post(`/presets/${selectedPresetId.value}/items`, {
      content_id: contentId.value,
      position: presetItems.value.length,
      duration_seconds: newDuration.value,
      play_until_end: false,
      enabled: true,
      transition: null
    })
    newDuration.value = null
    await loadPresetItems()
    showToast(locale.value === "de" ? "Inhalt hinzugefügt." : "Content added.")
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "Inhalt konnte nicht hinzugefügt werden"
  }
}

const saveItem = async (item: PresetItem): Promise<void> => {
  error.value = ""
  try {
    await api.put(`/preset-items/${item.id}`, {
      content_id: item.content_id,
      position: item.position,
      duration_seconds: item.duration_seconds,
      play_until_end: false,
      enabled: item.enabled,
      transition: null
    })
    dirtyItemIds.value = dirtyItemIds.value.filter((id) => id !== item.id)
    showToast(locale.value === "de" ? "Eintrag gespeichert." : "Item saved.")
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "Inhalt konnte nicht gespeichert werden"
    await loadPresetItems()
  }
}

const saveDirtyItems = async (): Promise<void> => {
  const dirtyItems = presetItems.value.filter((item) => dirtyItemIds.value.includes(item.id))
  if (dirtyItems.length === 0) return
  error.value = ""
  try {
    await Promise.all(
      dirtyItems.map((item) => api.put(`/preset-items/${item.id}`, {
        content_id: item.content_id,
        position: item.position,
        duration_seconds: item.duration_seconds,
        play_until_end: false,
        enabled: item.enabled,
        transition: null
      }))
    )
    dirtyItemIds.value = []
    showToast(locale.value === "de" ? "Änderungen gespeichert." : "Changes saved.")
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "Änderungen konnten nicht gespeichert werden"
    showToast(locale.value === "de" ? "Speichern fehlgeschlagen." : "Save failed.", "error")
    await loadPresetItems()
  }
}

const removeItem = async (id: string): Promise<void> => {
  error.value = ""
  try {
    await api.delete(`/preset-items/${id}`)
    await loadPresetItems()
    dirtyItemIds.value = dirtyItemIds.value.filter((itemId) => itemId !== id)
    showToast(locale.value === "de" ? "Eintrag entfernt." : "Item removed.")
  } catch (err: any) {
    error.value = err?.response?.data?.detail || "Inhalt konnte nicht entfernt werden"
  }
}

const onDragStart = (id: string): void => {
  draggingItemId.value = id
}

const onDrop = async (targetId: string): Promise<void> => {
  if (!draggingItemId.value || draggingItemId.value === targetId) return
  const sourceIndex = presetItems.value.findIndex((item) => item.id === draggingItemId.value)
  const targetIndex = presetItems.value.findIndex((item) => item.id === targetId)
  if (sourceIndex < 0 || targetIndex < 0) return

  const reordered = [...presetItems.value]
  const [moved] = reordered.splice(sourceIndex, 1)
  reordered.splice(targetIndex, 0, moved)
  presetItems.value = reordered.map((item, index) => ({ ...item, position: index }))
  for (const item of presetItems.value) markItemDirty(item.id)
  draggingItemId.value = ""
}

const markItemDirty = (id: string): void => {
  if (!dirtyItemIds.value.includes(id)) dirtyItemIds.value.push(id)
}

const onEsc = (event: KeyboardEvent): void => {
  if (event.key !== "Escape") return
  if (showDeleteModal.value) closeDeleteModal()
  if (showCreateModal.value) closeCreateModal()
}

watch(selectedPresetId, async (nextId, prevId) => {
  if (suppressPresetSwitchGuard.value) {
    suppressPresetSwitchGuard.value = false
    return
  }
  if (nextId !== prevId && dirtyItemIds.value.length > 0 && !confirmDiscardChanges(locale)) {
    suppressPresetSwitchGuard.value = true
    selectedPresetId.value = prevId
    return
  }
  dirtyItemIds.value = []
  await loadPresetItems()
})

onMounted(async () => {
  window.addEventListener("keydown", onEsc)
  await load()
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onEsc)
})

useUnsavedChangesGuard(isDirty, locale)
</script>

<template>
  <section class="page presets-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">Presets</h2>
        <p class="page-subtitle">{{ text.subtitle }}</p>
      </div>
      <button class="add-preset-btn" @click="openCreateModal">{{ text.newPreset }}</button>
    </div>

    <div class="card" v-if="hasPresets">
      <div class="preset-toolbar">
        <label class="preset-select">
          {{ text.currentPreset }}
          <select v-model="selectedPresetId">
            <option v-for="item in presets" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
        </label>
        <div class="preset-actions">
          <button class="ghost" @click="setAsDefault" :disabled="Boolean(selectedPreset?.is_default)">{{ text.setDefault }}</button>
          <button class="danger" @click="showDeleteModal = true">{{ text.deletePreset }}</button>
        </div>
      </div>
      <p class="hint" v-if="selectedPreset?.is_default">{{ text.defaultHint }}</p>
    </div>

    <div class="card empty-state" v-else>
      <h3>{{ text.noneTitle }}</h3>
      <p>{{ text.noneText }}</p>
    </div>

    <div class="card" v-if="hasPresets">
      <h3>{{ text.presetContent }}</h3>
      <div class="form-grid wide">
        <label>
          {{ text.content }}
          <select v-model="contentId" :disabled="contents.length === 0">
            <option v-for="c in contents" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </label>
        <label>
          {{ text.duration }}
          <input v-model.number="newDuration" type="number" min="1" :required="durationRequiredForNew" :placeholder="durationRequiredForNew ? text.durationReq : text.durationOpt" />
        </label>
        <div class="toolbar">
          <button @click="addItem" :disabled="contents.length === 0">{{ text.addContent }}</button>
        </div>
      </div>
      <p class="hint">{{ text.rule }}</p>
      <p class="hint">{{ text.drag }}</p>
      <div class="toolbar">
        <button @click="saveDirtyItems" :disabled="!hasDirtyItems">{{ t("save") }}</button>
      </div>
    </div>

    <table class="data-table preset-items-table" v-if="hasPresets">
      <thead><tr><th>{{ text.colContent }}</th><th>{{ text.colPos }}</th><th>{{ text.colDuration }}</th><th>{{ text.colActions }}</th></tr></thead>
      <tbody>
        <tr
          v-for="row in presetItems"
          :key="row.id"
          draggable="true"
          @dragstart="onDragStart(row.id)"
          @dragover.prevent
          @drop="onDrop(row.id)"
        >
          <td>
            <select v-model="row.content_id" @change="markItemDirty(row.id)">
              <option v-for="c in contents" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </td>
          <td>{{ row.position }}</td>
          <td>
            <input v-model.number="row.duration_seconds" type="number" min="1" :placeholder="presetItems.length <= 1 ? `${text.optional} (s)` : `${text.required} (s)`" @change="markItemDirty(row.id)" />
          </td>
          <td class="actions">
            <button class="ghost" @click="saveItem(row)">{{ t("save") }}</button>
            <button class="danger" @click="removeItem(row.id)">{{ t("remove") }}</button>
          </td>
        </tr>
      </tbody>
    </table>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="showCreateModal" class="modal-backdrop" @click.self="closeCreateModal">
      <div class="modal-card" role="dialog" aria-modal="true" :aria-label="locale === 'de' ? 'Neues Preset erstellen' : 'Create new preset'">
        <h3>{{ text.createTitle }}</h3>
        <label>{{ text.presetName }}<input v-model="createName" placeholder="z. B. Tagesbetrieb" /></label>
        <label>{{ text.description }}<input v-model="createDescription" :placeholder="text.optional" /></label>
        <label>{{ text.markDefault }}
          <select v-model="createIsDefault">
            <option :value="false">{{ text.no }}</option>
            <option :value="true">{{ text.yes }}</option>
          </select>
        </label>
        <div class="modal-actions">
          <button class="ghost" @click="closeCreateModal">{{ t("cancel") }}</button>
          <button @click="createPreset">{{ text.createPreset }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDeleteModal" class="modal-backdrop" @click.self="closeDeleteModal">
      <div class="modal-card" role="dialog" aria-modal="true" :aria-label="locale === 'de' ? 'Preset löschen bestätigen' : 'Confirm preset deletion'">
        <h3>{{ text.deleteTitle }}</h3>
        <p>{{ text.deleteText }}</p>
        <div class="modal-actions">
          <button class="ghost" @click="closeDeleteModal">{{ t("cancel") }}</button>
          <button class="danger" @click="deleteSelectedPreset">{{ text.deleteFinal }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.presets-page { gap: 16px; }
.page-head { display: flex; justify-content: space-between; align-items: start; gap: 12px; }
.add-preset-btn { min-width: 170px; }
.preset-toolbar { display: flex; gap: 12px; align-items: end; }
.preset-select { max-width: 500px; width: 100%; }
.preset-actions { display: flex; gap: 8px; }
.preset-items-table td { vertical-align: middle; }
.preset-items-table td select,
.preset-items-table td input { width: 100%; box-sizing: border-box; }
.preset-items-table .actions { align-items: center; }
.preset-items-table tbody tr { height: 64px; }
.preset-items-table td { padding-top: 10px; padding-bottom: 10px; }
.preset-items-table td:first-child { min-width: 360px; }
.preset-items-table .actions button { min-height: 36px; padding: 8px 11px; font-size: 13px; }
.preset-items-table thead th { border-bottom: 1px solid #dce6ee; }
.preset-items-table tbody tr + tr td { border-top: 1px solid #eef3f7; }
.empty-state { text-align: left; }
.empty-state h3 { margin-top: 0; }
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
  width: min(560px, 100%);
  background: #fff;
  border: 1px solid #cfdae4;
  border-radius: 14px;
  box-shadow: 0 30px 70px rgba(7, 24, 38, 0.25);
  padding: 20px;
  display: grid;
  gap: 12px;
}
.modal-card h3 { margin: 0; }
.modal-card p { margin: 0; color: #536d7f; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
@media (max-width: 980px) {
  .page-head { flex-direction: column; }
  .preset-toolbar { flex-direction: column; align-items: stretch; }
  .add-preset-btn { width: 100%; }
}
</style>

