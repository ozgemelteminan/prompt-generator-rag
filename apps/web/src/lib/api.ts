const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const apiBaseUrl = configuredBaseUrl.replace(/\/$/, "");

export type AppLanguage = "tr" | "en";

export type ClarificationQuestion = {
  question: string;
};

export type GeneratePromptResponse = {
  state: "ready" | "clarification_required";
  clarificationPlan: {
    questions: ClarificationQuestion[];
    shouldClarify: boolean;
    canGenerate: boolean;
  };
  compiledPrompt: string | null;
  recordId: string | null;
};

export type ExecutePromptResponse = {
  output: string;
  executionId?: string;
};

export type UsageResource = {
  used: number;
  limit: number;
  remaining: number;
  resetAt: string;
};

export type UsageStatusResponse = {
  generation: UsageResource;
  execution: UsageResource;
};

export type DocumentMetadata = {
  id: string;
  filename: string;
  mediaType: string;
  size: number;
  language: string | null;
  status: "uploaded" | "processing" | "parsed" | "chunking" | "chunked" | "embedding" | "embedded" | "ready" | "failed";
  checksum: string;
  createdAt: string;
  updatedAt: string;
  deduplicated: boolean;
};

export type ApiErrorDetails = {
  retryAfterSeconds?: number;
  resetAt?: string;
};

export type PromptHistoryItem = {
  id: string;
  originalInput: string;
  language: AppLanguage;
  isFavorite: boolean;
  compiledPromptPreview: string;
  latestExecutionPreview: string | null;
  createdAt: string;
};

export type PromptHistoryDetail = PromptHistoryItem & {
  compiledPrompt: string;
  executions: { id: string; output: string; createdAt: string }[];
};

export class PromptApiError extends Error {
  constructor(
    public readonly code: string | null,
    message: string,
    public readonly details: ApiErrorDetails | null = null,
  ) {
    super(message);
    this.name = "PromptApiError";
  }
}

export async function generatePrompt(input: {
  input: string;
  language: AppLanguage;
  presetId?: string;
}): Promise<GeneratePromptResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/prompts/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const errorPayload = payload as { error?: { code?: string; message?: string; details?: ApiErrorDetails } } | null;
    throw new PromptApiError(
      errorPayload?.error?.code ?? null,
      errorPayload?.error?.message ?? "Prompt generation failed.",
      errorPayload?.error?.details ?? null,
    );
  }

  return payload as GeneratePromptResponse;
}

export async function executePrompt(input: {
  compiledPrompt: string;
  promptId?: string;
}): Promise<ExecutePromptResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/prompts/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const errorPayload = payload as { error?: { code?: string; message?: string; details?: ApiErrorDetails } } | null;
    throw new PromptApiError(
      errorPayload?.error?.code ?? null,
      errorPayload?.error?.message ?? "Prompt execution failed.",
      errorPayload?.error?.details ?? null,
    );
  }

  return payload as ExecutePromptResponse;
}

async function requestApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init);
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const errorPayload = payload as { error?: { code?: string; message?: string; details?: ApiErrorDetails } } | null;
    throw new PromptApiError(errorPayload?.error?.code ?? null, errorPayload?.error?.message ?? "Request failed.", errorPayload?.error?.details ?? null);
  }
  return payload as T;
}

export function listPromptHistory(favoritesOnly = false): Promise<{ items: PromptHistoryItem[] }> {
  return requestApi(`/api/v1/prompts?limit=30&favoritesOnly=${favoritesOnly}`);
}

export function getPromptHistory(id: string): Promise<PromptHistoryDetail> {
  return requestApi(`/api/v1/prompts/${id}`);
}

export function setPromptFavorite(id: string, isFavorite: boolean): Promise<PromptHistoryItem> {
  return requestApi(`/api/v1/prompts/${id}/favorite`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ isFavorite }),
  });
}

export function submitPromptFeedback(input: {
  promptId: string; rating: "positive" | "negative"; executionId?: string;
}): Promise<void> {
  return requestApi(`/api/v1/prompts/${input.promptId}/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating: input.rating, executionId: input.executionId }),
  });
}

export function getUsageStatus(): Promise<UsageStatusResponse> {
  return requestApi("/api/v1/usage");
}

export function listDocuments(): Promise<{ items: DocumentMetadata[] }> {
  return requestApi("/api/v1/documents");
}

export async function uploadDocument(file: File): Promise<DocumentMetadata> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${apiBaseUrl}/api/v1/documents`, { method: "POST", body: form });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const errorPayload = payload as { error?: { code?: string; message?: string; details?: ApiErrorDetails } } | null;
    throw new PromptApiError(
      errorPayload?.error?.code ?? null,
      errorPayload?.error?.message ?? "Document upload failed.",
      errorPayload?.error?.details ?? null,
    );
  }
  return payload as DocumentMetadata;
}

export function processDocument(id: string): Promise<DocumentMetadata> {
  return requestApi(`/api/v1/documents/${id}/process`, { method: "POST" });
}

export type DocumentChunkingResponse = {
  documentId: string;
  status: "chunked";
  chunkCount: number;
  averageTokenCount: number;
  minTokenCount: number;
  maxTokenCount: number;
};

export function chunkDocument(id: string): Promise<DocumentChunkingResponse> {
  return requestApi(`/api/v1/documents/${id}/chunk`, { method: "POST" });
}

export type RagSource = {
  citationId: number;
  documentId: string;
  chunkId: string;
  filename: string;
  pageStart: number | null;
  pageEnd: number | null;
  section: string | null;
  heading: string | null;
  excerpt: string;
  similarity: number;
};

export type RagAskResponse = {
  state: "answer" | "insufficient_evidence";
  answer: string | null;
  sources: RagSource[];
};

export function askDocuments(input: {
  query: string;
  documentIds?: string[];
  limit?: number;
}): Promise<RagAskResponse> {
  return requestApi("/api/v1/rag/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export type DocumentEmbeddingResponse = {
  documentId: string;
  status: "embedded";
  chunkCount: number;
  embeddedChunkCount: number;
  embeddingModel: string;
};

export function embedDocument(id: string): Promise<DocumentEmbeddingResponse> {
  return requestApi(`/api/v1/documents/${id}/embed`, { method: "POST" });
}
