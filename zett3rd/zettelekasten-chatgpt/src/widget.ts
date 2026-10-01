import { App, applyDocumentTheme, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";

type Document = {
  id: string; title: string; summary: string; subtitle: string; content: string;
  artifact_type: string; version: number; tags: string[]; editable: boolean;
};

const app = new App({ name: "zettelekasten-knowledge-card", version: "0.1.0" });
const element = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const status = element<HTMLParagraphElement>("status");
const error = element<HTMLParagraphElement>("error");
const view = element<HTMLElement>("view");
const form = element<HTMLFormElement>("form");
let current: Document | null = null;
let requestedId: string | null = null;
let dirty = false;
let connected = false;
let expanded = false;

async function expand(): Promise<void> {
  if (app.getHostContext()?.availableDisplayModes?.includes("fullscreen")) {
    try {
      await app.requestDisplayMode({ mode: "fullscreen" });
    } catch {
      // The host can refuse a display-mode request; reveal content in place.
    }
  }
  expanded = true;
  document.body.classList.add("expanded");
  element<HTMLButtonElement>("expand").textContent = "Show less";
}

function collapse(): void {
  expanded = false;
  document.body.classList.remove("expanded");
  element<HTMLButtonElement>("expand").textContent = "View full";
  if (app.getHostContext()?.displayMode === "fullscreen") {
    void app.requestDisplayMode({ mode: "inline" }).catch(() => undefined);
  }
}

function message(value: string): void {
  error.textContent = value;
  error.hidden = !value;
}

function show(documentValue: Document): void {
  current = documentValue;
  status.textContent = `Saved in Zettelekasten · version ${documentValue.version}`;
  element("title").textContent = documentValue.title;
  element("kind").textContent = documentValue.artifact_type;
  element("summary").textContent = documentValue.summary;
  element("body").textContent = documentValue.content;
  const tags = element("tags");
  tags.replaceChildren(...documentValue.tags.map((path) => {
    const badge = document.createElement("span");
    badge.textContent = path;
    return badge;
  }));
  element<HTMLButtonElement>("edit").hidden = !documentValue.editable;
  view.hidden = false;
  form.hidden = true;
  dirty = false;
}

function parseDocument(value: unknown): Document | null {
  if (!value || typeof value !== "object" || !("document" in value)) return null;
  const candidate = value.document;
  if (!candidate || typeof candidate !== "object" || !("id" in candidate)) return null;
  if (
    !("title" in candidate)
    || typeof candidate.id !== "string"
    || typeof candidate.title !== "string"
  ) return null;
  return candidate as Document;
}

async function refresh(id: string): Promise<void> {
  status.textContent = "Refreshing…";
  try {
    const answer = await app.callServerTool({ name: "get_knowledge", arguments: { id } });
    if (answer.isError) throw new Error(answer.content.map((part) => part.type === "text" ? part.text : "").join(" "));
    const documentValue = parseDocument(answer.structuredContent);
    if (!documentValue) throw new Error("Zettelekasten returned an invalid document");
    show(documentValue);
    message("");
  } catch (reason) {
    status.textContent = "Could not refresh";
    message(reason instanceof Error ? reason.message : "Unknown error");
  }
}

app.ontoolresult = (params) => {
  const documentValue = parseDocument(params.structuredContent);
  if (documentValue) {
    requestedId = documentValue.id;
    if (!dirty) show(documentValue);
    return;
  }
  const receipt = params.structuredContent;
  if (receipt && typeof receipt === "object" && "id" in receipt && typeof receipt.id === "string") {
    requestedId = receipt.id;
    if (!dirty && connected) void refresh(receipt.id);
  }
};
app.ontoolinput = (params) => {
  const id = params.arguments?.id;
  if (typeof id === "string") requestedId = id;
};
app.onhostcontextchanged = (params) => {
  if (params.theme) applyDocumentTheme(params.theme);
  if (params.styles?.variables) applyHostStyleVariables(params.styles.variables);
};

element<HTMLButtonElement>("refresh").addEventListener("click", () => {
  if (current) void refresh(current.id);
});
element<HTMLButtonElement>("expand").addEventListener("click", () => {
  if (expanded) collapse();
  else void expand();
});
element<HTMLButtonElement>("edit").addEventListener("click", () => {
  if (!current?.editable) return;
  void expand();
  (form.elements.namedItem("title") as HTMLInputElement).value = current.title;
  (form.elements.namedItem("summary") as HTMLInputElement).value = current.summary;
  (form.elements.namedItem("subtitle") as HTMLInputElement).value = current.subtitle;
  (form.elements.namedItem("content") as HTMLTextAreaElement).value = current.content;
  (form.elements.namedItem("tags") as HTMLTextAreaElement).value = current.tags.join("\n");
  element("subtitleLabel").hidden = current.artifact_type === "card";
  view.hidden = true;
  form.hidden = false;
  dirty = true;
});
element<HTMLButtonElement>("cancel").addEventListener("click", () => {
  if (current) show(current);
  message("");
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!current?.editable) return;
  const data = new FormData(form);
  const get = (key: string): string => String(data.get(key) ?? "");
  const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  submit.disabled = true;
  message("");
  try {
    const answer = await app.callServerTool({
      name: "edit_knowledge",
      arguments: {
        id: current.id,
        expected_version: current.version,
        title: get("title").trim(),
        summary: get("summary"),
        subtitle: get("subtitle"),
        content: get("content"),
        tags: get("tags").split("\n").map((tag) => tag.trim()).filter(Boolean),
      },
    });
    if (answer.isError) throw new Error(answer.content.map((part) => part.type === "text" ? part.text : "").join(" "));
    await refresh(current.id);
  } catch (reason) {
    message(reason instanceof Error ? reason.message : "Save failed");
  } finally {
    submit.disabled = false;
  }
});

void app.connect().then(() => {
  connected = true;
  const context = app.getHostContext();
  if (context?.theme) applyDocumentTheme(context.theme);
  if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables);
  if (requestedId && !current) void refresh(requestedId);
}).catch((reason) => {
  status.textContent = "ChatGPT card unavailable";
  message(reason instanceof Error ? reason.message : "Could not connect to host");
});
