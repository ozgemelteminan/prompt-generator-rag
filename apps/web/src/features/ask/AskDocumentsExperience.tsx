"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  askDocuments,
  listDocuments,
  type DocumentMetadata,
  PromptApiError,
  type RagAskResponse,
  type RagSource,
} from "@/lib/api";
import { localizedError } from "@/lib/errors";

const content = {
  en: {
    title: "Ask your documents",
    description: "Select ready documents and ask a question grounded in their content.",
    documents: "Ready documents",
    selected: "Selected documents",
    noneSelected: "All ready documents will be searched.",
    question: "Your question",
    placeholder: "For example: What is the planned launch timeline?",
    ask: "Ask",
    asking: "Searching and preparing…",
    answer: "Grounded answer",
    sources: "Sources",
    insufficient: "We couldn’t find enough information in the selected documents to answer reliably.",
    noDocuments: "No ready documents are available yet. Prepare a document first.",
    page: "Page",
  },
  tr: {
    title: "Belgelerinize sorun",
    description: "Hazır belgeleri seçin ve içeriklerine dayalı bir soru sorun.",
    documents: "Hazır belgeler",
    selected: "Seçilen belgeler",
    noneSelected: "Tüm hazır belgelerde arama yapılacak.",
    question: "Sorunuz",
    placeholder: "Örneğin: Planlanan lansman takvimi nedir?",
    ask: "Sor",
    asking: "Aranıyor ve hazırlanıyor…",
    answer: "Belgelere dayalı yanıt",
    sources: "Kaynaklar",
    insufficient: "Seçilen belgelerde güvenilir bir yanıt için yeterli bilgi bulamadık.",
    noDocuments: "Henüz hazır belge yok. Önce bir belge hazırlayın.",
    page: "Sayfa",
  },
} as const;

export function AskDocumentsExperience() {
  const [language, setLanguage] = useState<"en" | "tr">("en");
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<RagAskResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<PromptApiError | null>(null);
  const [highlightedCitation, setHighlightedCitation] = useState<number | null>(null);
  const text = content[language];
  const readyDocuments = documents.filter((document) => document.status === "embedded" || document.status === "ready");
  const selectedDocuments = readyDocuments.filter((document) => selectedIds.includes(document.id));

  useEffect(() => {
    void listDocuments().then((response) => setDocuments(response.items)).catch((reason: unknown) => {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Document list failed."));
    });
  }, []);

  function toggleDocument(id: string) {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) {
      setError(new PromptApiError("retrieval_invalid_query", "Question is required."));
      return;
    }
    setIsLoading(true);
    setError(null);
    setResult(null);
    setHighlightedCitation(null);
    try {
      setResult(await askDocuments({ query: question, documentIds: selectedIds.length ? selectedIds : undefined }));
    } catch (reason) {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Document question failed."));
    } finally {
      setIsLoading(false);
    }
  }

  function focusCitation(citationId: number) {
    setHighlightedCitation(citationId);
    window.requestAnimationFrame(() => document.getElementById(`source-${citationId}`)?.focus());
  }

  return <section className="mx-auto max-w-5xl space-y-8 text-[#272A22]">
    <header className="space-y-3"><p className="pf-eyebrow">PromptForge</p><h1 className="pf-page-title">{text.title}</h1><p className="max-w-2xl text-base leading-7 pf-muted">{text.description}</p><button className="pf-button-secondary" onClick={() => setLanguage((current) => current === "en" ? "tr" : "en")} type="button">{language === "en" ? "Türkçe" : "English"}</button></header>
    <form className="pf-card space-y-6 p-5 sm:p-7" onSubmit={handleAsk}>
      <fieldset className="space-y-3"><legend className="text-sm font-semibold">{text.documents}</legend>{readyDocuments.length === 0 ? <p className="text-sm text-[#747568]">{text.noDocuments}</p> : <div className="flex flex-wrap gap-2">{readyDocuments.map((document) => <label className={`cursor-pointer rounded-lg border px-3 py-2 text-sm transition ${selectedIds.includes(document.id) ? "border-[#6F7454] bg-[#ECE6D8]" : "border-[#D8D1C1] bg-[#FBF9F3]"}`} key={document.id}><input checked={selectedIds.includes(document.id)} className="mr-2 accent-[#6F7454]" onChange={() => toggleDocument(document.id)} type="checkbox" />{document.filename}</label>)}</div>}</fieldset>
      <div className="flex flex-wrap items-center gap-2 text-sm text-[#747568]"><span className="font-medium text-[#454A35]">{text.selected}:</span>{selectedDocuments.length ? selectedDocuments.map((document) => <span className="pf-badge bg-[#ECE6D8] text-[#454A35]" key={document.id}>{document.filename}</span>) : <span>{text.noneSelected}</span>}</div>
      <div className="space-y-2"><label className="text-sm font-semibold" htmlFor="document-question">{text.question}</label><textarea className="pf-input min-h-36 resize-y leading-7" disabled={isLoading} id="document-question" onChange={(event) => setQuestion(event.target.value)} placeholder={text.placeholder} value={question} /></div>
      <button className="pf-button-primary px-5 py-3" disabled={isLoading || readyDocuments.length === 0} type="submit">{isLoading ? text.asking : text.ask}</button>
    </form>
    {error && <p className="pf-alert pf-alert-error" role="alert">{localizedError(language, error.code, error.details)}</p>}
    {result?.state === "insufficient_evidence" && <p className="pf-alert pf-alert-warning" role="status">{text.insufficient}</p>}
    {result?.state === "answer" && result.answer && <section className="space-y-7"><article className="pf-card p-5 sm:p-7"><h2 className="text-xl font-semibold">{text.answer}</h2><p className="mt-4 whitespace-pre-wrap leading-7">{renderAnswer(result.answer, focusCitation)}</p></article><section className="space-y-3"><h2 className="text-xl font-semibold">{text.sources}</h2>{result.sources.map((source) => <SourceCard highlighted={highlightedCitation === source.citationId} key={source.citationId} source={source} text={text} />)}</section></section>}
  </section>;
}

function renderAnswer(answer: string, onCitationClick: (citationId: number) => void) {
  return answer.split(/(\[\d+\])/g).map((part, index) => {
    const match = /^\[(\d+)\]$/.exec(part);
    return match ? <button aria-label={`View source ${match[1]}`} className="mx-0.5 font-semibold text-[#6F7454] underline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-[#6F7454]" key={`${part}-${index}`} onClick={() => onCitationClick(Number(match[1]))} type="button">{part}</button> : part;
  });
}

function SourceCard(
  { highlighted, source, text }: { highlighted: boolean; source: RagSource; text: { page: string } },
) {
  const page = source.pageStart === null ? null : source.pageStart === source.pageEnd ? source.pageStart : `${source.pageStart}-${source.pageEnd}`;
  return <article className={`rounded-xl border bg-[#FBF9F3] p-5 outline-none transition ${highlighted ? "border-[#6F7454] ring-2 ring-[#6F7454]/30" : "border-[#D8D1C1]"}`} id={`source-${source.citationId}`} tabIndex={-1}><p className="text-sm font-semibold text-[#6F7454]">[{source.citationId}] {source.filename}</p><p className="mt-1 text-sm text-[#747568]">{page !== null ? `${text.page} ${page}` : ""}{source.section ? ` · ${source.section}` : ""}{source.heading ? ` · ${source.heading}` : ""}</p><p className="mt-3 text-sm leading-6 text-[#272A22]">{source.excerpt}</p></article>;
}
