import { createApp } from "vue"
import { createPinia } from "pinia"
import { createRouter, createWebHistory } from "vue-router"
import App from "./App.vue"
import LoginView from "./views/LoginView.vue"
import DashboardView from "./views/DashboardView.vue"
import ContentsView from "./views/ContentsView.vue"
import PresetsView from "./views/PresetsView.vue"
import SchedulesView from "./views/SchedulesView.vue"
import WebhooksView from "./views/WebhooksView.vue"
import SettingsView from "./views/SettingsView.vue"
import "./styles/admin.css"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: DashboardView, meta: { requiresAuth: true } },
    { path: "/login", component: LoginView, meta: { guestOnly: true } },
    { path: "/contents", component: ContentsView, meta: { requiresAuth: true } },
    { path: "/presets", component: PresetsView, meta: { requiresAuth: true } },
    { path: "/schedules", component: SchedulesView, meta: { requiresAuth: true } },
    { path: "/webhooks", component: WebhooksView, meta: { requiresAuth: true } },
    { path: "/settings", component: SettingsView, meta: { requiresAuth: true } }
  ]
})

router.beforeEach((to) => {
  const isAuthenticated = Boolean(localStorage.getItem("token"))
  if (to.meta.requiresAuth && !isAuthenticated) {
    return { path: "/login", query: { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && isAuthenticated) {
    return { path: "/" }
  }
  return true
})

createApp(App).use(createPinia()).use(router).mount("#app")
