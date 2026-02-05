/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CLERK_PUBLISHABLE_KEY: string;
  readonly VITE_GSD_API_BASE_URL: string;
  readonly VITE_GSD_CLERK_JWT_TEMPLATE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
