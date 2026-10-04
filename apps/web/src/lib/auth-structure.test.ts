import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const read = (path: string) => readFileSync(resolve(root, path), "utf8");

test("frontend configuration exposes only public Supabase inputs", () => {
  const example = read(".env.example");
  expect(example).toContain("NEXT_PUBLIC_SUPABASE_URL=");
  expect(example).toContain("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=");
  for (const forbidden of [
    "SUPABASE_SERVICE_ROLE",
    "SUPABASE_SECRET",
    "ADVISOR_LLM_API_KEY",
    "OPENAI_API_KEY",
  ]) {
    expect(example).not.toContain(forbidden);
  }
});

test("uses official Supabase session APIs without custom JWT decoding", () => {
  const provider = read("src/auth/auth-provider.tsx");
  const proxy = read("src/lib/supabase/proxy.ts");
  expect(provider).toContain("signInWithPassword");
  expect(provider).toContain("getSession");
  expect(provider).toContain("refreshSession");
  expect(provider).toContain("onAuthStateChange");
  expect(proxy).toContain("getClaims");
  for (const forbidden of ["jwtDecode", "atob(", "JSON.parse(token", "localStorage."]){
    expect(`${provider}\n${proxy}`).not.toContain(forbidden);
  }
});

test("contains no advisor UI or direct provider integration", () => {
  const packageJson = read("package.json");
  const source = [
    read("src/auth/auth-provider.tsx"),
    read("src/lib/api/authenticated-client.ts"),
    read("src/app/(student)/student/page.tsx"),
  ].join("\n");
  expect(source).not.toContain("AdvisorChat");
  expect(source).not.toContain("/v1/responses");
  expect(source).not.toContain("openai");
  expect(packageJson).not.toContain("openai");
});
