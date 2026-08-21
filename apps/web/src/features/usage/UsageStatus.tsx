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
    <aside className="mb-6 flex flex-wrap items-center justify-end gap-3 text-xs text-slate-400" aria-label="Usage status">
      {usage && <>
        <span>{language === "tr" ? "Oluşturma" : "Generations"}: {usage.generation.used}/{usage.generation.limit}</span>
        <span>{language === "tr" ? "Çalıştırma" : "Executions"}: {usage.execution.used}/{usage.execution.limit}</span>
        <span>{language === "tr" ? "Yenilenme" : "Reset"}: {new Date(usage.generation.resetAt).toLocaleDateString(language === "tr" ? "tr-TR" : "en-US")}</span>
      </>}
      {error && <span role="status">{localizedError(language, error.code, error.details)}</span>}
      <button className="text-cyan-200 hover:text-white" onClick={() => setLanguage((current) => current === "en" ? "tr" : "en")} type="button">{language === "en" ? "TR" : "EN"}</button>
    </aside>
  );
}
