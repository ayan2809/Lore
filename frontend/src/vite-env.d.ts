/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string // backend URL, default http://localhost:8000
  readonly VITE_MOCK?: string // "1" = run against the fake in-browser backend
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
