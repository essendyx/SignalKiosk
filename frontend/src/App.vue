<template>
  <div class="shell">
    <aside>
      <h1>signalKiosk</h1>
      <router-link to="/">Dashboard</router-link>
      <router-link to="/contents">Inhalte</router-link>
      <router-link to="/presets">Presets</router-link>
      <router-link to="/schedules">Zeitplaene</router-link>
      <router-link to="/webhooks">Webhooks</router-link>
      <router-link to="/login">Login</router-link>
    </aside>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.shell { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; font-family: "IBM Plex Sans", sans-serif; }
aside { background: linear-gradient(180deg, #0c1b2a, #122f46); color: #d8e5f1; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
a { color: #c0dfff; text-decoration: none; }
main { padding: 24px; background: radial-gradient(circle at top right, #f5f8fc, #e7edf5); }
@media (max-width: 900px) { .shell { grid-template-columns: 1fr; } }
</style>
