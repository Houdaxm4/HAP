export const APP_CONFIG = {
  applicationName: "HAP",
  fullName: "Houda's Analyst Platform",
  primaryUser: "Houda",
  backendBaseUrl: "http://localhost:8000",
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
