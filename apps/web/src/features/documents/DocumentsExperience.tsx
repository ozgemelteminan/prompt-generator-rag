"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  chunkDocument,
  listDocuments,
  processDocument,
  type DocumentMetadata,
  PromptApiError,
  uploadDocument,
} from "@/lib/api";
import { localizedError } from "@/lib/errors";

const content = {
  tr: {
    title: "Belgeler",
    description: "PDF, DOCX, TXT veya Markdown belgesi yükleyin ve yapısal metni çıkarın.",
    choose: "Belge seçin",
    upload: "Yükle",
    uploading: "Yükleniyor…",
    success: "Belge yüklendi.",
    empty: "Henüz belge yüklenmedi.",
    status: "Durum",
    process: "İşle",
    processing: "İşleniyor…",
    parsed: "Belge işlendi.",
    chunk: "Parçala",
    chunking: "Parçalanıyor…",
    chunked: "Belge parçalandı",
  },
  en: {
    title: "Documents",
    description: "Upload a PDF, DOCX, TXT, or Markdown document and extract structured text.",
    choose: "Choose a document",
    upload: "Upload",
    uploading: "Uploading…",
    success: "Document uploaded.",
    empty: "No documents have been uploaded yet.",
    status: "Status",
    process: "Process",
    processing: "Processing…",
    parsed: "Document processed.",
    chunk: "Chunk",
    chunking: "Chunking…",
    chunked: "Document chunked",
  },
} as const;

export function DocumentsExperience() {
  const [language, setLanguage] = useState<"en" | "tr">("en");
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [chunkingId, setChunkingId] = useState<string | null>(null);
  const [chunkCounts, setChunkCounts] = useState<Record<string, number>>({});
  const [error, setError] = useState<PromptApiError | null>(null);
  const text = content[language];

  useEffect(() => {
    void listDocuments().then((result) => setDocuments(result.items)).catch((reason: unknown) => {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Document list failed."));
    });
  }, []);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setIsUploading(true);
    setSuccessMessage(null);
    setError(null);
    try {
      const uploaded = await uploadDocument(file);
      setDocuments((current) => [uploaded, ...current.filter((document) => document.id !== uploaded.id)]);
      setSuccessMessage(text.success);
      setFile(null);
    } catch (reason) {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Document upload failed."));
    } finally {
      setIsUploading(false);
    }
  }

  async function handleChunk(document: DocumentMetadata) {
    setChunkingId(document.id);
    setSuccessMessage(null);
    setError(null);
    try {
      const result = await chunkDocument(document.id);
      setDocuments((current) => current.map((item) => item.id === document.id ? { ...item, status: result.status } : item));
      setChunkCounts((current) => ({ ...current, [document.id]: result.chunkCount }));
      setSuccessMessage(`${text.chunked}: ${result.chunkCount}`);
    } catch (reason) {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Document chunking failed."));
    } finally {
      setChunkingId(null);
    }
  }

  async function handleProcess(document: DocumentMetadata) {
    setProcessingId(document.id);
    setSuccessMessage(null);
    setError(null);
    try {
      const processed = await processDocument(document.id);
      setDocuments((current) => current.map((item) => item.id === processed.id ? processed : item));
      setSuccessMessage(text.parsed);
    } catch (reason) {
      setError(reason instanceof PromptApiError ? reason : new PromptApiError(null, "Document processing failed."));
    } finally {
      setProcessingId(null);
    }
  }

  return <section className="mx-auto max-w-4xl space-y-8 py-8">
    <header className="space-y-3"><p className="text-sm font-semibold uppercase tracking-[0.18em] text-cyan-300">PromptForge</p><h1 className="text-4xl font-semibold text-white">{text.title}</h1><p className="text-slate-300">{text.description}</p><button className="text-sm text-cyan-200" onClick={() => setLanguage((current) => current === "en" ? "tr" : "en")} type="button">{language === "en" ? "Türkçe" : "English"}</button></header>
    <form className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-700 bg-slate-900/70 p-5" onSubmit={handleUpload}>
      <label className="text-sm text-slate-200">{text.choose}<input accept=".pdf,.docx,.txt,.md,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="mt-2 block" disabled={isUploading} onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" /></label>
      <button className="rounded-lg bg-cyan-300 px-4 py-2 font-semibold text-slate-950 disabled:opacity-60" disabled={!file || isUploading} type="submit">{isUploading ? text.uploading : text.upload}</button>
    </form>
    {successMessage && <p className="rounded-xl bg-emerald-300/10 p-4 text-emerald-100" role="status">{successMessage}</p>}
    {error && <p className="rounded-xl bg-rose-400/10 p-4 text-rose-100" role="alert">{localizedError(language, error.code, error.details)}</p>}
    <div className="space-y-3">{documents.length === 0 ? <p className="text-slate-400">{text.empty}</p> : documents.map((document) => <article className="rounded-xl border border-slate-700 bg-slate-900/70 p-4" key={document.id}><div className="flex flex-wrap justify-between gap-3"><div><h2 className="font-medium text-white">{document.filename}</h2><p className="mt-1 text-sm text-slate-400">{document.mediaType} · {document.size.toLocaleString()} bytes · {new Date(document.createdAt).toLocaleString()}{document.language ? ` · ${document.language.toUpperCase()}` : ""}{chunkCounts[document.id] !== undefined ? ` · ${chunkCounts[document.id]} chunks` : ""}</p></div><div className="flex items-center gap-2"><span className="rounded-full bg-cyan-300/10 px-3 py-1 text-sm text-cyan-100">{text.status}: {document.status}</span>{(document.status === "uploaded" || document.status === "failed") && <button className="rounded-lg border border-cyan-300/50 px-3 py-1 text-sm text-cyan-100 disabled:opacity-60" disabled={processingId === document.id} onClick={() => void handleProcess(document)} type="button">{processingId === document.id ? text.processing : text.process}</button>}{document.status === "parsed" && <button className="rounded-lg border border-cyan-300/50 px-3 py-1 text-sm text-cyan-100 disabled:opacity-60" disabled={chunkingId === document.id} onClick={() => void handleChunk(document)} type="button">{chunkingId === document.id ? text.chunking : text.chunk}</button>}</div></div></article>)}</div>
  </section>;
}
