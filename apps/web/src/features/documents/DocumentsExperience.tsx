"use client";

import { FormEvent, useEffect, useState } from "react";

import { chunkDocument, embedDocument, listDocuments, processDocument, type DocumentMetadata, PromptApiError, uploadDocument } from "@/lib/api";
import { localizedError } from "@/lib/errors";

const content = {
  tr: { title: "Belgeler", description: "Belgelerinizi yükleyin; hazırlanınca onlara güvenilir yanıtlar için soru sorun.", choose: "Belge seçin", upload: "Yükle", uploading: "Yükleniyor…", success: "Belge yüklendi.", empty: "Henüz belge yüklenmedi.", process: "Hazırla", processing: "Hazırlanıyor…", chunk: "Parçala", chunking: "Parçalanıyor…", embed: "Hazır duruma getir", embedding: "Hazırlanıyor…", ready: "Hazır", failed: "Başarısız", preparing: "Hazırlanıyor" },
  en: { title: "Documents", description: "Upload your documents, then ask grounded questions once they are ready.", choose: "Choose a document", upload: "Upload", uploading: "Uploading…", success: "Document uploaded.", empty: "No documents yet. Upload one to get started.", process: "Prepare", processing: "Preparing…", chunk: "Prepare", chunking: "Preparing…", embed: "Make ready", embedding: "Preparing…", ready: "Ready", failed: "Failed", preparing: "Preparing" },
} as const;

export function DocumentsExperience() {
  const [language, setLanguage] = useState<"en" | "tr">("en");
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [error, setError] = useState<PromptApiError | null>(null);
  const text = content[language];

  useEffect(() => { void listDocuments().then((result) => setDocuments(result.items)).catch((reason: unknown) => setError(asApiError(reason, "Document list failed."))); }, []);
  async function handleUpload(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!file) return; setIsUploading(true); setError(null); try { const uploaded = await uploadDocument(file); setDocuments((current) => [uploaded, ...current.filter((document) => document.id !== uploaded.id)]); setSuccessMessage(text.success); setFile(null); } catch (reason) { setError(asApiError(reason, "Document upload failed.")); } finally { setIsUploading(false); } }
  async function advance(document: DocumentMetadata) { setBusyId(document.id); setError(null); try { const next = document.status === "uploaded" || document.status === "failed" ? await processDocument(document.id) : document.status === "parsed" ? await chunkDocument(document.id) : await embedDocument(document.id); setDocuments((current) => current.map((item) => item.id === document.id ? { ...item, status: next.status } : item)); } catch (reason) { setError(asApiError(reason, "Document preparation failed.")); } finally { setBusyId(null); } }

  return <section className="mx-auto max-w-5xl space-y-8">
    <header className="space-y-3"><p className="pf-eyebrow">Prompt Generator</p><h1 className="pf-page-title">{text.title}</h1><p className="max-w-2xl leading-7 pf-muted">{text.description}</p><LanguageToggle language={language} onChange={setLanguage} /></header>
    <form className="pf-card flex flex-col gap-4 p-5 sm:flex-row sm:items-end sm:justify-between" onSubmit={handleUpload}>
      <label className="block min-w-0 text-sm font-semibold">{text.choose}<input accept=".pdf,.docx,.txt,.md,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="mt-2 block w-full text-sm font-normal text-[#747568] file:mr-3 file:rounded-md file:border-0 file:bg-[#ECE6D8] file:px-3 file:py-2 file:font-semibold file:text-[#454A35]" disabled={isUploading} onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" /></label>
      <button className="pf-button-primary shrink-0" disabled={!file || isUploading} type="submit">{isUploading ? text.uploading : text.upload}</button>
    </form>
    {successMessage && <p className="pf-alert pf-alert-success" role="status">{successMessage}</p>}
    {error && <p className="pf-alert pf-alert-error" role="alert">{localizedError(language, error.code, error.details)}</p>}
    <div className="space-y-3">{documents.length === 0 ? <div className="pf-card-muted p-8 text-center"><p className="font-medium">{text.empty}</p></div> : documents.map((document) => <DocumentCard busy={busyId === document.id} document={document} key={document.id} language={language} onAdvance={() => void advance(document)} text={text} />)}</div>
  </section>;
}

function DocumentCard({ busy, document, language, onAdvance, text }: { busy: boolean; document: DocumentMetadata; language: "en" | "tr"; onAdvance: () => void; text: typeof content.en | typeof content.tr }) {
  const ready = document.status === "embedded" || document.status === "ready";
  const failed = document.status === "failed";
  const action = document.status === "uploaded" || failed ? text.process : document.status === "parsed" ? text.chunk : document.status === "chunked" ? text.embed : null;
  const status = ready ? text.ready : failed ? text.failed : text.preparing;
  const badge = ready ? "pf-badge-ready" : failed ? "pf-badge-error" : "pf-badge-warning";
  return <article className="pf-card p-5"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div className="min-w-0"><h2 className="truncate font-semibold">{document.filename}</h2><p className="mt-1 text-sm pf-muted">{document.mediaType} · {new Date(document.createdAt).toLocaleDateString(language === "tr" ? "tr-TR" : "en-US")}</p></div><div className="flex flex-wrap items-center gap-2"><span className={`pf-badge ${badge}`}><span aria-hidden="true">●</span>{status}</span>{action && <button className="pf-button-secondary" disabled={busy} onClick={onAdvance} type="button">{busy ? (document.status === "chunked" ? text.embedding : text.processing) : action}</button>}</div></div></article>;
}

function LanguageToggle({ language, onChange }: { language: "en" | "tr"; onChange: (language: "en" | "tr") => void }) { return <div className="inline-flex rounded-lg border border-[#D8D1C1] bg-[#FBF9F3] p-1" aria-label="Language"><button aria-pressed={language === "en"} className={`rounded-md px-3 py-1.5 text-sm font-semibold ${language === "en" ? "bg-[#ECE6D8] text-[#454A35]" : "pf-muted"}`} onClick={() => onChange("en")} type="button">English</button><button aria-pressed={language === "tr"} className={`rounded-md px-3 py-1.5 text-sm font-semibold ${language === "tr" ? "bg-[#ECE6D8] text-[#454A35]" : "pf-muted"}`} onClick={() => onChange("tr")} type="button">Türkçe</button></div>; }
function asApiError(reason: unknown, fallback: string) { return reason instanceof PromptApiError ? reason : new PromptApiError(null, fallback); }
