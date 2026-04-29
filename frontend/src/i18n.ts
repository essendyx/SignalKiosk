import { ref } from "vue"

export type Locale = "de" | "en"

const messages = {
  de: {
    navControlCenter: "Control Center",
    navDashboard: "Dashboard",
    navContents: "Inhalte",
    navPresets: "Presets",
    navSchedules: "Zeitplaene",
    navWebhooks: "Webhooks",
    navSettings: "Einstellungen",
    navPlayback: "CDP-Runner Status",
    logout: "Abmelden",
    language: "Sprache",
    german: "Deutsch",
    english: "Englisch",
    save: "Speichern",
    create: "Erstellen",
    delete: "Loeschen",
    edit: "Bearbeiten",
    remove: "Entfernen",
    cancel: "Abbrechen",
    loading: "Lade...",
  },
  en: {
    navControlCenter: "Control Center",
    navDashboard: "Dashboard",
    navContents: "Contents",
    navPresets: "Presets",
    navSchedules: "Schedules",
    navWebhooks: "Webhooks",
    navSettings: "Settings",
    navPlayback: "CDP Runner Status",
    logout: "Log out",
    language: "Language",
    german: "German",
    english: "English",
    save: "Save",
    create: "Create",
    delete: "Delete",
    edit: "Edit",
    remove: "Remove",
    cancel: "Cancel",
    loading: "Loading...",
  }
} as const

const stored = localStorage.getItem("locale")
const initial: Locale = stored === "en" || stored === "de" ? stored : "de"
export const locale = ref<Locale>(initial)

export const applyLocale = (value: Locale): void => {
  locale.value = value
}

export const setLocale = (value: Locale): void => {
  applyLocale(value)
  localStorage.setItem("locale", value)
}

export const useI18n = () => {
  const t = (key: keyof typeof messages.de): string => messages[locale.value][key]
  return { locale, applyLocale, setLocale, t }
}
