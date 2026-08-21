"use client";

import { FormEvent, useState } from "react";

import {
  type AppLanguage,
  type ApiErrorDetails,
  executePrompt,
  generatePrompt,
  type GeneratePromptResponse,
  PromptApiError,
  setPromptFavorite,
  submitPromptFeedback,
} from "@/lib/api";
import { localizedError } from "@/lib/errors";

import { taskPresets } from "./presets";

const content = {
  tr: {
    eyebrow: "PromptForge",
    title: "Ne yapmak istediğinizi anlatın.",
    description: "İhtiyacınızı kendi kelimelerinizle yazın. Birkaç ayrıntı gerekirse birlikte tamamlarız.",
    language: "Yanıt dili",
    turkish: "Türkçe",
    english: "English",
    presets: "Hızlı başlangıç",
    optional: "İsteğe bağlı",
    requestLabel: "Ne yapmak istiyorsunuz?",
    requestPlaceholder: "Örneğin: Yeni müşterilere göndermek için kısa bir proje güncellemesi e-postası yazmama yardım et.",
    generate: "Prompt oluştur",
    generating: "Hazırlanıyor…",
    detailsTitle: "Kısa bir ayrıntıya daha ihtiyacımız var",
    detailsDescription: "Daha iyi bir sonuç hazırlamak için aşağıdaki soruları yanıtlayın.",
    continue: "Devam et",
    resultTitle: "Promptunuz hazır",
    copy: "Kopyala",
    copied: "Kopyalandı",
    run: "Çalıştır",
    running: "Çalıştırılıyor…",
    answerTitle: "Yanıt",
    copyAnswer: "Yanıtı kopyala",
    answerCopied: "Yanıt kopyalandı",
    runAgain: "Tekrar çalıştır",
    favorite: "Favori",
    unfavorite: "Favoriden çıkar",
    feedback: "Bu sonuç faydalı mıydı?",
    feedbackSaved: "Geri bildiriminiz kaydedildi.",
    tryAgain: "İsteğinizi düzenleyip yeniden deneyin.",
    clarificationLimit: "Daha fazla ayrıntı gerekirse isteğinizi güncelleyip yeniden oluşturun.",
  },
  en: {
    eyebrow: "PromptForge",
    title: "Tell us what you want to do.",
    description: "Describe your need in your own words. We’ll ask for a small detail only when it helps.",
    language: "Response language",
    turkish: "Türkçe",
    english: "English",
    presets: "Quick start",
    optional: "Optional",
    requestLabel: "What would you like to do?",
    requestPlaceholder: "For example: Help me write a short project update email for new customers.",
    generate: "Create prompt",
    generating: "Creating…",
    detailsTitle: "We need one small detail",
    detailsDescription: "Answer these questions so we can prepare a better result.",
    continue: "Continue",
    resultTitle: "Your prompt is ready",
    copy: "Copy",
    copied: "Copied",
    run: "Run",
    running: "Running…",
    answerTitle: "Answer",
    copyAnswer: "Copy answer",
    answerCopied: "Answer copied",
    runAgain: "Run again",
    favorite: "Favorite",
    unfavorite: "Remove favorite",
    feedback: "Was this result helpful?",
    feedbackSaved: "Thanks for your feedback.",
    tryAgain: "Edit your request and try again.",
    clarificationLimit: "If more detail is needed, update your request and create it again.",
  },
} as const;

export function CreateExperience() {
  const [language, setLanguage] = useState<AppLanguage>("en");
  const [request, setRequest] = useState("");
  const [presetId, setPresetId] = useState<string | undefined>();
  const [result, setResult] = useState<GeneratePromptResponse | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [clarificationAttempted, setClarificationAttempted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<ApiErrorDetails | null>(null);
  const [executionErrorCode, setExecutionErrorCode] = useState<string | null>(null);
  const [executionErrorDetails, setExecutionErrorDetails] = useState<ApiErrorDetails | null>(null);
  const [copied, setCopied] = useState(false);
  const [answerCopied, setAnswerCopied] = useState(false);
  const [executionOutput, setExecutionOutput] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [isFavorite, setIsFavorite] = useState(false);
  const [feedbackSaved, setFeedbackSaved] = useState(false);
  const text = content[language];

  async function requestGeneration(input: string) {
    setIsLoading(true);
    setErrorCode(null);
    setErrorDetails(null);
    setExecutionErrorCode(null);
    setExecutionErrorDetails(null);
    setExecutionOutput(null);
    setExecutionId(null);
    setCopied(false);
    setAnswerCopied(false);
    setIsFavorite(false);
    setFeedbackSaved(false);
    try {
      const nextResult = await generatePrompt({ input, language, presetId });
      setResult(nextResult);
      setAnswers(nextResult.clarificationPlan.questions.map(() => ""));
    } catch (error) {
      setResult(null);
      setErrorCode(error instanceof PromptApiError ? error.code : null);
      setErrorDetails(error instanceof PromptApiError ? error.details : null);
    } finally {
      setIsLoading(false);
    }
  }

  function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!request.trim()) {
      setErrorCode("invalid_request");
      setErrorDetails(null);
      return;
    }
    setClarificationAttempted(false);
    void requestGeneration(request);
  }

  function handleClarification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!result || answers.some((answer) => !answer.trim())) {
      setErrorCode("invalid_request");
      setErrorDetails(null);
      return;
    }
    const additionalDetails = result.clarificationPlan.questions
      .map((question, index) => `${question.question}\n${answers[index]}`)
      .join("\n\n");
    setClarificationAttempted(true);
    void requestGeneration(`${request}\n\nAdditional details from the user:\n${additionalDetails}`);
  }

  async function copyPrompt() {
    if (!result?.compiledPrompt) return;
    await navigator.clipboard.writeText(result.compiledPrompt);
    setCopied(true);
  }

  async function runPrompt() {
    if (!result?.compiledPrompt) return;
    setIsExecuting(true);
    setExecutionErrorCode(null);
    setExecutionErrorDetails(null);
    setAnswerCopied(false);
    try {
      const execution = await executePrompt({ compiledPrompt: result.compiledPrompt, promptId: result.recordId ?? undefined });
      setExecutionOutput(execution.output);
      setExecutionId(execution.executionId ?? null);
    } catch (error) {
      setExecutionErrorCode(error instanceof PromptApiError ? error.code : null);
      setExecutionErrorDetails(error instanceof PromptApiError ? error.details : null);
    } finally {
      setIsExecuting(false);
    }
  }

  async function copyAnswer() {
    if (!executionOutput) return;
    await navigator.clipboard.writeText(executionOutput);
    setAnswerCopied(true);
  }

  async function toggleFavorite() {
    if (!result?.recordId) return;
    try {
      const updated = await setPromptFavorite(result.recordId, !isFavorite);
      setIsFavorite(updated.isFavorite);
    } catch (error) {
      setErrorCode(error instanceof PromptApiError ? error.code : null);
      setErrorDetails(error instanceof PromptApiError ? error.details : null);
    }
  }

  async function sendFeedback(rating: "positive" | "negative") {
    if (!result?.recordId) return;
    try {
      await submitPromptFeedback({ promptId: result.recordId, rating, executionId: executionId ?? undefined });
      setFeedbackSaved(true);
    } catch (error) {
      setErrorCode(error instanceof PromptApiError ? error.code : null);
      setErrorDetails(error instanceof PromptApiError ? error.details : null);
    }
  }

  return (
    <section className="mx-auto flex min-h-[78vh] max-w-4xl flex-col justify-center gap-10 py-8">
      <header className="max-w-2xl space-y-4">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-cyan-300">{text.eyebrow}</p>
        <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">{text.title}</h1>
        <p className="text-lg leading-8 text-slate-300">{text.description}</p>
      </header>

      <form className="space-y-8 rounded-2xl border border-slate-700 bg-slate-900/70 p-5 shadow-2xl shadow-slate-950/30 sm:p-8" onSubmit={handleGenerate}>
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium text-slate-200">{text.language}</legend>
          <div className="flex gap-3">
            {(["tr", "en"] as const).map((option) => (
              <button
                className={`rounded-lg px-4 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-cyan-300 ${language === option ? "bg-cyan-300 text-slate-950" : "bg-slate-800 text-slate-200 hover:bg-slate-700"}`}
                key={option}
                onClick={() => setLanguage(option)}
                type="button"
              >
                {option === "tr" ? text.turkish : text.english}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-sm font-medium text-slate-200">{text.presets} <span className="font-normal text-slate-400">{text.optional}</span></legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {taskPresets.map((preset) => (
              <button
                aria-pressed={presetId === preset.id}
                className={`rounded-xl border p-3 text-left transition focus:outline-none focus:ring-2 focus:ring-cyan-300 ${presetId === preset.id ? "border-cyan-300 bg-cyan-300/10" : "border-slate-700 bg-slate-800/60 hover:border-slate-500"}`}
                key={preset.id}
                onClick={() => setPresetId((current) => current === preset.id ? undefined : preset.id)}
                type="button"
              >
                <span className="block text-sm font-medium text-white">{preset.title[language]}</span>
                <span className="mt-1 block text-sm text-slate-400">{preset.description[language]}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <div className="space-y-3">
          <label className="block text-sm font-medium text-slate-200" htmlFor="prompt-request">{text.requestLabel}</label>
          <textarea
            className="min-h-40 w-full rounded-xl border border-slate-700 bg-slate-950/70 p-4 text-base leading-7 text-white placeholder:text-slate-500 focus:border-cyan-300 focus:outline-none focus:ring-2 focus:ring-cyan-300"
            disabled={isLoading}
            id="prompt-request"
            onChange={(event) => setRequest(event.target.value)}
            placeholder={text.requestPlaceholder}
            value={request}
          />
        </div>

        <button className="w-full rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-slate-950 transition hover:bg-cyan-200 focus:outline-none focus:ring-2 focus:ring-cyan-100 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:opacity-60" disabled={isLoading} type="submit">
          {isLoading ? text.generating : text.generate}
        </button>
      </form>

      {errorCode && <p className="rounded-xl border border-rose-400/40 bg-rose-400/10 p-4 text-sm leading-6 text-rose-100" role="alert">{localizedError(language, errorCode, errorDetails)} {text.tryAgain}</p>}

      {result?.state === "clarification_required" && (
        <section className="space-y-5 rounded-2xl border border-amber-300/40 bg-amber-300/10 p-5 sm:p-8">
          <div>
            <h2 className="text-xl font-semibold text-amber-50">{text.detailsTitle}</h2>
            <p className="mt-2 text-sm leading-6 text-amber-100/80">{text.detailsDescription}</p>
          </div>
          {clarificationAttempted ? <p className="text-sm text-amber-100">{text.clarificationLimit}</p> : (
            <form className="space-y-5" onSubmit={handleClarification}>
              {result.clarificationPlan.questions.map((item, index) => (
                <label className="block space-y-2 text-sm font-medium text-amber-50" key={`${item.question}-${index}`}>
                  <span>{item.question}</span>
                  <input className="w-full rounded-lg border border-amber-200/30 bg-slate-950/60 px-3 py-2 text-white focus:border-amber-200 focus:outline-none focus:ring-2 focus:ring-amber-200" disabled={isLoading} onChange={(event) => setAnswers((current) => current.map((answer, answerIndex) => answerIndex === index ? event.target.value : answer))} value={answers[index] ?? ""} />
                </label>
              ))}
              <button className="rounded-xl bg-amber-200 px-5 py-3 font-semibold text-slate-950 focus:outline-none focus:ring-2 focus:ring-amber-50 disabled:cursor-not-allowed disabled:opacity-60" disabled={isLoading} type="submit">{isLoading ? text.generating : text.continue}</button>
            </form>
          )}
        </section>
      )}

      {result?.state === "ready" && result.compiledPrompt && (
        <section className="space-y-4 rounded-2xl border border-emerald-300/40 bg-emerald-300/10 p-5 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold text-emerald-50">{text.resultTitle}</h2>
            <div className="flex flex-wrap gap-2">
              <button className="rounded-lg border border-emerald-100/50 px-3 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-100/10 focus:outline-none focus:ring-2 focus:ring-emerald-100" onClick={() => void copyPrompt()} type="button">{copied ? text.copied : text.copy}</button>
              {result.recordId && <button aria-pressed={isFavorite} className="rounded-lg border border-emerald-100/50 px-3 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-100/10 focus:outline-none focus:ring-2 focus:ring-emerald-100" onClick={() => void toggleFavorite()} type="button">{isFavorite ? text.unfavorite : text.favorite}</button>}
              <button className="rounded-lg bg-emerald-200 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-100 focus:outline-none focus:ring-2 focus:ring-emerald-50 disabled:cursor-not-allowed disabled:opacity-60" disabled={isExecuting} onClick={() => void runPrompt()} type="button">{isExecuting ? text.running : executionOutput ? text.runAgain : text.run}</button>
            </div>
          </div>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-950/70 p-4 text-sm leading-6 text-slate-100">{result.compiledPrompt}</pre>
          {executionErrorCode && <p className="rounded-xl border border-rose-400/40 bg-rose-400/10 p-4 text-sm leading-6 text-rose-100" role="alert">{localizedError(language, executionErrorCode, executionErrorDetails)} {text.tryAgain}</p>}
          {executionOutput && (
            <section className="space-y-3 rounded-xl border border-emerald-100/20 bg-slate-950/50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-semibold text-emerald-50">{text.answerTitle}</h3>
                <button className="rounded-lg border border-emerald-100/50 px-3 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-100/10 focus:outline-none focus:ring-2 focus:ring-emerald-100" onClick={() => void copyAnswer()} type="button">{answerCopied ? text.answerCopied : text.copyAnswer}</button>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6 text-slate-100">{executionOutput}</p>
            </section>
          )}
          {result.recordId && <div className="flex flex-wrap items-center gap-3 text-sm text-emerald-50"><span>{text.feedback}</span><button aria-label="Positive feedback" className="rounded-lg border border-emerald-100/50 px-3 py-1 hover:bg-emerald-100/10" onClick={() => void sendFeedback("positive")} type="button">👍</button><button aria-label="Negative feedback" className="rounded-lg border border-emerald-100/50 px-3 py-1 hover:bg-emerald-100/10" onClick={() => void sendFeedback("negative")} type="button">👎</button>{feedbackSaved && <span>{text.feedbackSaved}</span>}</div>}
        </section>
      )}
    </section>
  );
}
