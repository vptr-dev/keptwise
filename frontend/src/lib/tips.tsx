// Tips and suggestions with a close button. Once closed they stay closed
// (saved with the look settings), and Settings -> Appearance can bring
// them all back.
import { createContext, useContext, type ReactNode } from "react";

import { Notice } from "../components/ui";

type Tips = { dismissed: string[]; dismiss: (id: string) => void };

const TipsContext = createContext<Tips>({ dismissed: [], dismiss: () => undefined });

export const TipsProvider = TipsContext.Provider;

export function useTips(): Tips {
  return useContext(TipsContext);
}

/** A tip that can be closed for good. */
export function Tip({ id, children, tone = "info" }: { id: string; children: ReactNode; tone?: "info" | "warning" }) {
  const { dismissed, dismiss } = useTips();
  if (dismissed.includes(id)) return null;
  return (
    <div className="kw-tip">
      <Notice tone={tone} onClose={() => dismiss(id)}>
        {children}
      </Notice>
    </div>
  );
}
