import type { Citation, ConversationState, Lecture, TutorAnswer } from "../types";

function apiBaseUrl() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (typeof window !== "undefined") return `${window.location.protocol}//${window.location.hostname}:8000`;
  return "http://localhost:8000";
}

type ApiDocument = Omit<Lecture, "uploadedAt" | "file" | "fileUrl" | "previewUrl"> & { uploadedAt: string; fileUrl: string; previewUrl?: string };
type ApiAnswer = { text: string; citations: Array<Citation & { chunkId?: string; excerpt?: string }>; confidence: number; confidenceLabel: string };

function apiUrl(path: string) { return `${apiBaseUrl()}${path}`; }

export async function parseApiResponse<T>(response: Response): Promise<T | undefined> {
  if (response.status === 204 || response.status === 205) return undefined;
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  const text = await response.text();
  if (!text.trim()) return undefined;
  if (!contentType.includes("application/json")) {
    throw new Error(`Backend trả về nội dung không hợp lệ (${contentType || "không có Content-Type"}).`);
  }
  try { return JSON.parse(text) as T; }
  catch { throw new Error("Backend trả về JSON không hợp lệ."); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(apiUrl(path), init); }
  catch { throw new Error("Không thể kết nối backend. Hãy kiểm tra backend đang chạy tại " + apiBaseUrl() + "."); }
  const body = await parseApiResponse<T | { detail?: string }>(response);
  if (!response.ok) {
    throw new Error(body?.detail ?? `Backend trả về lỗi ${response.status}.`);
  }
  return body as T;
}

function toLecture(document: ApiDocument): Lecture {
  return { ...document, uploadedAt: new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(document.uploadedAt)), fileUrl: apiUrl(document.fileUrl), previewUrl: document.previewUrl ? apiUrl(document.previewUrl) : undefined };
}

export async function checkBackend(): Promise<void> { await request<{ status: string }>("/api/health"); }
export async function listLectures(): Promise<Lecture[]> { return (await request<ApiDocument[]>("/api/documents")).map(toLecture); }
export async function uploadLecture(file: File): Promise<Lecture> {
  const form = new FormData(); form.append("file", file);
  return toLecture(await request<ApiDocument>("/api/documents/upload", { method: "POST", body: form }));
}
export async function deleteLecture(id: string): Promise<void> { await request(`/api/documents/${id}`, { method: "DELETE" }); }
export async function retryLecturePreview(id: string): Promise<Lecture> {
  return toLecture(await request<ApiDocument>(`/api/documents/${id}/retry-preview`, { method: "POST" }));
}
export async function askTutor(question: string, documentId: string, page: number, history: Array<{ role: "user" | "assistant"; content: string }> = [], conversationState?: ConversationState): Promise<TutorAnswer> {
  return request<ApiAnswer>("/api/tutor/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, documentId, page, history, conversationState }) });
}
export async function getDocumentPageText(documentId: string, page: number): Promise<string> {
  return (await request<{ original_text: string }>(`/api/documents/${documentId}/pages/${page}`)).original_text;
}
export async function saveFeedback(messageId: string, value: "up" | "down", note?: string, documentId?: string): Promise<void> {
  await request("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messageId, value, note, documentId }) });
}
