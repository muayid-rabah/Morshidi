import type { ReactNode } from "react";

import { ProtectedBoundary } from "@/auth/protected-boundary";

export default function ChangeImpactLayout({ children }: { children: ReactNode }) {
  return <ProtectedBoundary>{children}</ProtectedBoundary>;
}
