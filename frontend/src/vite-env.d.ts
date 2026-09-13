/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MODE?: string;
  readonly VITE_API_BASE?: string;
  readonly VITE_SHOW_DEV_BADGES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
