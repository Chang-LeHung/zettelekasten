import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";

const execFile = promisify(execFileCallback);
const MAX_BODY = 1_000_000;
const MAX_QUERY = 200;
const MAX_TAGS = 100;
const MAX_RESPONSE_BYTES = 4_000_000;

export type Kind = "card" | "article";

export interface Knowledge {
  id: string;
  artifact_type: string;
  title: string;
  summary: string;
  preview: string;
  version: number;
  tags: string[];
  editable: boolean;
}

export interface Category {
  id: string;
  path: string;
  direct_count: number;
  total_count: number;
}

export interface Document extends Knowledge {
  content: string;
  subtitle: string;
}

export interface SaveInput {
  kind: Kind;
  title: string;
  body: string;
  summary?: string;
  tags?: string[];
}

export interface SavedReceipt {
  id: string;
  title: string;
  version: number;
  tags: string[];
}

export interface EditInput {
  id: string;
  expected_version: number;
  title: string;
  content: string;
  summary?: string;
  subtitle?: string;
  tags: string[];
}

interface ArtifactContent {
  artifact_type: string;
  title: string;
  summary: string;
  content: string;
  subtitle?: string;
  card_type?: string;
  keywords: string[];
  suggested_tags: Array<{ path: string; existing: boolean; confidence: number }>;
}

interface ArtifactRow {
  id: string;
  session_id: string;
  artifact_type: string;
  status: string;
  version: number;
  content: ArtifactContent | null;
  draft_content: ArtifactContent | null;
  tags: Array<{ path: string }>;
}

type Fetcher = typeof fetch;

export class ZettClient {
  constructor(private readonly endpoint: () => Promise<string>, private readonly fetcher: Fetcher = fetch) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const base = await this.endpoint();
    const response = await this.fetcher(new URL(path, `${base}/`), {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
      signal: AbortSignal.timeout(15_000),
    });
    const text = await response.text();
    if (text.length > MAX_RESPONSE_BYTES) throw new Error("Zettelekasten response exceeds the allowed size");
    if (!response.ok) {
      let detail = text;
      try {
        const parsed: unknown = JSON.parse(text);
        if (isRecord(parsed) && typeof parsed.detail === "string") detail = parsed.detail;
      } catch { /* Preserve a plain-text error. */ }
      throw new Error(`Zettelekasten ${response.status}: ${detail.slice(0, 500)}`);
    }
    return JSON.parse(text) as T;
  }

  async categories(): Promise<Category[]> {
    const nodes = await this.request<Array<Category & { children: unknown[] }>>("/api/library/tags?target=artifact");
    const categories: Category[] = [];
    const visit = (items: Array<Category & { children: unknown[] }>): void => {
      for (const item of items) {
        categories.push({
          id: item.id, path: item.path, direct_count: item.direct_count, total_count: item.total_count,
        });
        visit(item.children as Array<Category & { children: unknown[] }>);
      }
    };
    visit(nodes);
    return categories;
  }

  async save(input: SaveInput): Promise<SavedReceipt> {
    checkText(input.title, 500, "title");
    checkText(input.body, MAX_BODY, "body");
    if (input.summary && input.summary.length > 20_000) throw new Error("summary is too long");
    checkTags(input.tags ?? []);
    const content = {
      artifact_type: input.kind,
      title: input.title,
      summary: input.summary ?? "",
      content: input.body,
      suggested_tags: (input.tags ?? []).map((path) => ({ path, existing: true, confidence: 1 })),
    };
    const row = await this.request<{
      id: string; version: number; content: { title: string }; tags: Array<{ path: string }>;
    }>("/api/artifacts", {
      method: "POST",
      body: JSON.stringify({ content, status: "saved", metadata: { source: "codex" } }),
    });
    return {
      id: row.id,
      title: row.content.title,
      version: row.version,
      tags: row.tags.map((tag) => tag.path),
    };
  }

  async search(query = "", limit = 20, categoryId?: string): Promise<Knowledge[]> {
    if (query.length > MAX_QUERY) throw new Error("query is too long");
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) throw new Error("limit must be between 1 and 50");
    const params = new URLSearchParams({ limit: String(limit), published_only: "true" });
    params.append("statuses", "saved");
    params.append("artifact_types", "card");
    params.append("artifact_types", "article");
    if (query.trim()) params.set("q", query.trim());
    if (categoryId) {
      checkId(categoryId);
      params.append("tag_ids", categoryId);
    }
    const rows = await this.request<ArtifactRow[]>(`/api/artifacts?${params}`);
    const libraryIds = await this.librarySessionIds();
    return rows
      .filter((row) => isPublishedMarkdown(row))
      .map((row) => project(row, libraryIds).preview);
  }

  async get(id: string): Promise<Document> {
    checkId(id);
    const row = await this.request<ArtifactRow>(`/api/artifacts/${encodeURIComponent(id)}`);
    if (!isPublishedMarkdown(row)) throw new Error("Saved card or article not found");
    return project(row, await this.librarySessionIds()).document;
  }

  async edit(input: EditInput): Promise<Document> {
    const { id, ...edit } = input;
    checkId(id);
    checkText(input.title, 500, "title");
    checkText(input.content, MAX_BODY, "content");
    checkTags(input.tags);
    if (!Number.isInteger(input.expected_version) || input.expected_version < 1) {
      throw new Error("expected_version must be positive");
    }
    const row = await this.request<ArtifactRow>(`/api/artifacts/${encodeURIComponent(id)}`);
    if (!isPublishedMarkdown(row)) throw new Error("Saved card or article not found");
    if (!(await this.librarySessionIds()).has(row.session_id)) {
      throw new Error("Only a global library artifact can be edited from ChatGPT");
    }
    if (row.draft_content && JSON.stringify(row.draft_content) !== JSON.stringify(row.content)) {
      throw new Error("Artifact has an unpublished Zettelekasten draft; review it in Zettelekasten before editing");
    }
    if (row.version !== input.expected_version) throw new Error("Artifact changed; reload it before saving");
    const content = {
      ...row.content,
      title: input.title,
      summary: input.summary ?? "",
      content: input.content,
      ...(row.artifact_type === "article" ? { subtitle: input.subtitle ?? "" } : {}),
      suggested_tags: input.tags.map((path) => ({ path, existing: true, confidence: 1 })),
    };
    await this.request<ArtifactRow>(`/api/agent/${encodeURIComponent(row.session_id)}/artifacts/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ content, expected_version: edit.expected_version }),
    });
    try {
      await this.request<ArtifactRow>(`/api/library/tags/artifacts/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify({ paths: input.tags }),
      });
    } catch (error) {
      throw new Error(`Content was saved, but classification failed; reload before retrying: ${String(error)}`);
    }
    return this.get(id);
  }

  private async librarySessionIds(): Promise<Set<string>> {
    const sessions = await this.request<Array<{ id: string }>>("/api/agent/sessions?types=library&limit=500");
    return new Set(sessions.map((session) => session.id));
  }
}

function isPublishedMarkdown(row: ArtifactRow): row is ArtifactRow & { content: ArtifactContent } {
  return row.status === "saved"
    && (row.artifact_type === "card" || row.artifact_type === "article")
    && row.content !== null;
}

function project(
  row: ArtifactRow & { content: ArtifactContent },
  libraryIds: Set<string>,
): { preview: Knowledge; document: Document } {
  const content = row.content;
  const preview: Knowledge = {
    id: row.id,
    artifact_type: row.artifact_type,
    title: content.title,
    summary: content.summary ?? "",
    preview: content.content.slice(0, 500),
    version: row.version,
    tags: row.tags.map((tag) => tag.path),
    editable: libraryIds.has(row.session_id)
      && (!row.draft_content || JSON.stringify(row.draft_content) === JSON.stringify(content)),
  };
  return {
    preview,
    document: {
      ...preview,
      content: content.content,
      subtitle: content.subtitle ?? "",
    },
  };
}

export async function localZettEndpoint(): Promise<string> {
  const configured = process.env.ZETT_BASE_URL;
  if (configured) return checkedLocalEndpoint(configured);
  // The CLI owns runtime.json and the port-detection rules; no second parser here.
  const { stdout } = await execFile("zett", ["status"], { timeout: 5_000, maxBuffer: 16_384 });
  const match = stdout.match(/^\s*url:\s+(http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):\d+)\/?\s*$/m);
  if (!match) throw new Error("Start Zettelekasten on loopback with `zett start` before connecting ChatGPT");
  return checkedLocalEndpoint(match[1]);
}

export function checkedLocalEndpoint(value: string): string {
  const url = new URL(value);
  if (
    url.protocol !== "http:"
    || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
    || !url.port
    || url.pathname !== "/"
    || url.search
    || url.hash
    || url.username
    || url.password
  ) {
    throw new Error("ZETT_BASE_URL must be a loopback HTTP origin with an explicit port");
  }
  return url.origin;
}

export function checkId(id: string): void {
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) throw new Error("Invalid artifact id");
}

function checkText(value: string, length: number, label: string): void {
  if (!value.trim() || value.length > length) throw new Error(`${label} must be nonblank and at most ${length} characters`);
}

function checkTags(tags: string[]): void {
  if (tags.length > MAX_TAGS) throw new Error(`At most ${MAX_TAGS} tags are allowed`);
  for (const tag of tags) {
    if (!tag || tag.length > 500 || tag.split("/").some((part) => !part.trim() || part.length > 100)) {
      throw new Error("Invalid tag path");
    }
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
