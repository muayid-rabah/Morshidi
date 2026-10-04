export type CapabilityState = "ENABLED" | "MODELED_ONLY" | "UNAVAILABLE" | "EXTERNAL_DEPENDENCY";

export interface CurrentInstitution {
  institution_id: string;
  display_name: string;
  default_locale: "ar" | "en";
  supported_locales: ("ar" | "en")[];
  theme_key: string;
  capabilities: Record<string, CapabilityState>;
  config_version: string;
  config_fingerprint: string;
}

// No server-provided CSS, HTML, image URL, or arbitrary class name is rendered.
const THEMES: Record<string, string> = {
  default: "bg-[#FFF4C7] text-[#805400]",
  sand: "bg-[#FFF4C7] text-[#805400]",
  indigo: "bg-indigo-50 text-indigo-800",
};

export function institutionThemeClass(themeKey: string): string {
  return THEMES[themeKey] ?? THEMES.default;
}

export function institutionNavVisible(
  context: CurrentInstitution | null,
  capability: string,
): boolean {
  if (!context) return true; // Legacy shell until governed config is installed.
  const state = context.capabilities[capability];
  return state === "ENABLED" || state === "MODELED_ONLY";
}
