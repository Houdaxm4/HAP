const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000";

function normalizeBackendBaseUrl(url: string): string {
  return url.replace(/\/+$/, "").replace(/\/api$/, "");
}

export const APP_CONFIG = {
  applicationName: "HAP",
  fullName: "Houda's Analyst Platform",
  primaryUser: "Houda",
  backendBaseUrl: normalizeBackendBaseUrl(
    process.env.NEXT_PUBLIC_BACKEND_URL ?? DEFAULT_BACKEND_BASE_URL,
  ),
} as const;

export function getPageTitle(): string {
  return `${APP_CONFIG.applicationName} — ${APP_CONFIG.fullName}`;
}

export function getAnalystLabel(): string {
  return `${APP_CONFIG.applicationName} Analyst`;
}

export function getAnalystGreeting(): string {
  return `Good morning, ${APP_CONFIG.primaryUser}.\n\nReady for today's first analysis.`;
}

export function getApplicationInitial(): string {
  return APP_CONFIG.applicationName.charAt(0);
}
