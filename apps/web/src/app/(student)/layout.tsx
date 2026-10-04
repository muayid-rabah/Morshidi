import type { ReactNode } from "react";

import { ProtectedBoundary } from "@/auth/protected-boundary";
import { StudentShell } from "@/components/navigation/StudentShell";

export default function StudentLayout({ children }: { children: ReactNode }) {
  return (
    <ProtectedBoundary>
      <StudentShell>
        {children}
      </StudentShell>
    </ProtectedBoundary>
  );
}
