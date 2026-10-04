export class PublicConfigurationError extends Error {
  constructor(public readonly field: string) {
    super(`Missing public application configuration: ${field}`);
    this.name = "PublicConfigurationError";
  }
}

export interface PublicSupabaseConfig {
  url: string;
  publishableKey: string;
}

function requireValue(value: string | undefined, field: string): string {
  const normalized = value?.trim();
  if (!normalized) throw new PublicConfigurationError(field);
  return normalized;
}

function validatedUrl(value: string | undefined, field: string): string {
  const normalized = requireValue(value, field);
  try {
    return new URL(normalized).toString().replace(/\/$/, "");
  } catch {
    throw new PublicConfigurationError(field);
  }
}

export function getPublicSupabaseConfig(): PublicSupabaseConfig {
  return {
    url: validatedUrl(
      process.env.NEXT_PUBLIC_SUPABASE_URL,
      "NEXT_PUBLIC_SUPABASE_URL",
    ),
    publishableKey: requireValue(
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    ),
  };
}

export function getPublicApiBaseUrl(): string {
  return validatedUrl(
    process.env.NEXT_PUBLIC_API_BASE_URL,
    "NEXT_PUBLIC_API_BASE_URL",
  );
}
