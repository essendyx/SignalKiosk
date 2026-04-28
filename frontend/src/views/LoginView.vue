<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import api from "../api"

const username = ref("admin")
const password = ref("admin123!")
const error = ref("")
const router = useRouter()

const submit = async (): Promise<void> => {
  try {
    const res = await api.post("/auth/login", { username: username.value, password: password.value })
    localStorage.setItem("token", res.data.access_token as string)
    router.push("/")
  } catch {
    error.value = "Login fehlgeschlagen"
  }
}
</script>

<template>
  <section>
    <h2>Admin Login</h2>
    <input v-model="username" placeholder="Benutzername" />
    <input v-model="password" type="password" placeholder="Passwort" />
    <button @click="submit">Einloggen</button>
    <p>{{ error }}</p>
  </section>
</template>
