"use client";

import { useEffect, useState } from "react";

import {
  getPromptHistory,
  listPromptHistory,
  type PromptHistoryDetail,
  type PromptHistoryItem,
  PromptApiError,
  setPromptFavorite,
} from "@/lib/api";
import { localizedError } from "@/lib/errors";

export function HistoryExperience() {
  const [items, setItems] = useState<PromptHistoryItem[]>([]);
  const [detail, setDetail] = useState<PromptHistoryDetail | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [language, setLanguage] = useState<"en" | "tr">("en");
  const [error, setError] = useState<PromptApiError | null>(null);

  useEffect(() => {
    void listPromptHistory(favoritesOnly).then((result) => setItems(result.items)).catch((reason: unknown) => setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "History failed.")));
  }, [favoritesOnly]);

  async function openItem(id: string) {
    try { setDetail(await getPromptHistory(id)); } catch (reason) { setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "History failed.")); }
  }

  async function toggleFavorite(item: PromptHistoryItem) {
    try {
      const updated = await setPromptFavorite(item.id, !item.isFavorite);
      setItems((current) => current.map((entry) => entry.id === item.id ? updated : entry));
      if (detail?.id === item.id) setDetail({ ...detail, isFavorite: updated.isFavorite });
    } catch (reason) {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Favorite failed."));
    }
  }

  const copyPrompt = language === "tr" ? "Promptu kopyala" : "Copy prompt";
  const copyResult = language === "tr" ? "Yanıtı kopyala" : "Copy result";
  return <section className="space-y-6">
    <header><p className="text-sm font-semibold uppercase tracking-[0.18em] text-cyan-300">PromptForge</p><h1 className="mt-3 text-4xl font-semibold text-white">{language === "tr" ? "Geçmiş" : "History"}</h1></header>
    <div className="flex flex-wrap gap-4"><label className="flex items-center gap-2 text-sm text-slate-200"><input checked={favoritesOnly} onChange={(event) => setFavoritesOnly(event.target.checked)} type="checkbox" /> {language === "tr" ? "Yalnızca favoriler" : "Favorites only"}</label><button className="text-sm text-cyan-200" onClick={() => setLanguage((current) => current === "en" ? "tr" : "en")} type="button">{language === "en" ? "Türkçe" : "English"}</button></div>
    {error && <p className="rounded-xl bg-rose-400/10 p-4 text-rose-100" role="alert">{localizedError(language, error.code, error.details)}</p>}
    <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
      <div className="space-y-3">{items.map((item) => <article className="rounded-xl border border-slate-700 bg-slate-900/70 p-4" key={item.id}><div className="flex justify-between gap-2"><button className="text-left font-medium text-white" onClick={() => void openItem(item.id)} type="button">{item.originalInput}</button><button aria-pressed={item.isFavorite} className="text-cyan-200" onClick={() => void toggleFavorite(item)} type="button">{item.isFavorite ? "★" : "☆"}</button></div><p className="mt-2 text-xs text-slate-400">{new Date(item.createdAt).toLocaleString()} · {item.language.toUpperCase()}</p><p className="mt-3 line-clamp-3 whitespace-pre-wrap text-sm text-slate-300">{item.compiledPromptPreview}</p>{item.latestExecutionPreview && <p className="mt-2 line-clamp-2 text-sm text-emerald-200">{item.latestExecutionPreview}</p>}</article>)}</div>
      {detail && <article className="space-y-4 rounded-xl border border-cyan-300/40 bg-slate-900/70 p-5"><h2 className="text-xl font-semibold text-white">{language === "tr" ? "Kaydedilen prompt" : "Saved prompt"}</h2><p className="text-slate-300">{detail.originalInput}</p><pre className="whitespace-pre-wrap rounded-lg bg-slate-950 p-3 text-sm text-slate-100">{detail.compiledPrompt}</pre><button className="rounded-lg border border-cyan-200 px-3 py-2 text-cyan-100" onClick={() => void navigator.clipboard.writeText(detail.compiledPrompt)} type="button">{copyPrompt}</button>{detail.executions.map((execution) => <section className="space-y-2" key={execution.id}><p className="font-medium text-emerald-100">{language === "tr" ? "Yanıt" : "Result"}</p><p className="whitespace-pre-wrap text-slate-200">{execution.output}</p><button className="rounded-lg border border-emerald-200/50 px-3 py-2 text-emerald-100" onClick={() => void navigator.clipboard.writeText(execution.output)} type="button">{copyResult}</button></section>)}</article>}
    </div>
  </section>;
}
