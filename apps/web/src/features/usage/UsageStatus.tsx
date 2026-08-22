"use client";

import { useEffect, useState } from "react";

import {
  type AppLanguage,
  getUsageStatus,
  PromptApiError,
  type UsageStatusResponse,
} from "@/lib/api";
import { localizedError } from "@/lib/errors";

export function UsageStatus() {
  const [language, setLanguage] = useState<AppLanguage>("en");
  const [usage, setUsage] = useState<UsageStatusResponse | null>(null);
  const [error, setError] = useState<PromptApiError | null>(null);

  useEffect(() => {
    void getUsageStatus().then(setUsage).catch((reason: unknown) => {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Usage failed."));
    });
  }, []);

  if (!usage && !error) return null;
  return (
    <aside className="space-y-2 border-t border-[#D8D1C1] pt-4 text-xs text-[#747568]" aria-label="Usage status">
      {usage && <>
        <p>{language === "tr" ? "Oluşturma" : "Generations"}: {usage.generation.used}/{usage.generation.limit}</p>
        <p>{language === "tr" ? "Çalıştırma" : "Executions"}: {usage.execution.used}/{usage.execution.limit}</p>
        <p>{language === "tr" ? "Yenilenme" : "Reset"}: {new Date(usage.generation.resetAt).toLocaleDateString(language === "tr" ? "tr-TR" : "en-US")}</p>
      </>}
      {error && <span role="status">{localizedError(language, error.code, error.details)}</span>}
      <button className="pf-button-ghost !px-0 !py-1 text-xs" onClick={() => setLanguage((current) => current === "en" ? "tr" : "en")} type="button">{language === "en" ? "TR" : "EN"}</button>
    </aside>
  );
}
