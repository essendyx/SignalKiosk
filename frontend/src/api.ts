import axios from "axios"

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || "/api" })

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem("token")
  if (token) {
    cfg.headers.Authorization = `Bearer ${token}`
  }
  return cfg
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem("token")
      const current = window.location.pathname + window.location.search
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = `/login?redirect=${encodeURIComponent(current)}`
      }
    }
    return Promise.reject(error)
  }
)

export default api
