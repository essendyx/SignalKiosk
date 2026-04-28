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

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: DashboardView },
    { path: "/login", component: LoginView },
    { path: "/contents", component: ContentsView },
    { path: "/presets", component: PresetsView },
    { path: "/schedules", component: SchedulesView },
    { path: "/webhooks", component: WebhooksView }
  ]
})

createApp(App).use(createPinia()).use(router).mount("#app")
