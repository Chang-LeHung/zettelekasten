import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { RESOURCE_MIME_TYPE, registerAppResource, registerAppTool } from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { ZettClient } from "./zett-client.js";

const URI = "ui://zettelekasten/knowledge-card-v3.html";
const viewFile = fileURLToPath(new URL("./widget.html", import.meta.url));
const widgetScript = fileURLToPath(new URL("../dist/widget.js", import.meta.url));
const annotations = (readOnly: boolean, destructive = false) => ({
  readOnlyHint: readOnly, destructiveHint: destructive, openWorldHint: false,
});
const result = (value: Record<string, unknown>, text: string) => ({
  structuredContent: value,
  content: [{ type: "text" as const, text }],
});

export function createMcpServer(zett: ZettClient): McpServer {
  const server = new McpServer(
    { name: "zettelekasten-knowledge", version: "0.1.0" },
    { instructions: "Only save knowledge when the user asks. Prefer existing artifact categories. Read search previews, then fetch a specific document when needed. Never save an entire conversation transcript." },
  );

  server.registerTool(
    "list_categories",
    {
      title: "List Zettelekasten categories",
      description: "Read existing knowledge categories before classifying a note.",
      inputSchema: {},
      outputSchema: { categories: z.array(z.object({
        id: z.string(), path: z.string(), direct_count: z.number(), total_count: z.number(),
      })) },
      annotations: annotations(true),
    },
    async () => {
      const categories = await zett.categories();
      return result({ categories }, `${categories.length} categories available.`);
    },
  );

  registerAppTool(
    server,
    "save_knowledge",
    {
      title: "Save knowledge in Zettelekasten",
      description: "When the user asks to retain a useful conclusion, save a concise card or article to the Zettelekasten library and classify it. This is a durable write; repeating the call creates a second item.",
      inputSchema: {
        kind: z.enum(["card", "article"]),
        title: z.string().min(1).max(500),
        body: z.string().min(1).max(1_000_000),
        summary: z.string().max(20_000).optional(),
        tags: z.array(z.string().min(1).max(500)).max(100).optional(),
      },
      outputSchema: { id: z.string(), title: z.string(), version: z.number(), tags: z.array(z.string()) },
      annotations: annotations(false),
      _meta: { ui: { resourceUri: URI }, "openai/outputTemplate": URI },
    },
    async (input) => {
      const saved = await zett.save(input);
      return result(
        { id: saved.id, title: saved.title, version: saved.version, tags: saved.tags },
        `Saved "${saved.title}" in Zettelekasten (${saved.id}).`,
      );
    },
  );

  server.registerTool(
    "search_knowledge",
    {
      title: "Search saved Zettelekasten knowledge",
      description: "Find published Zettelekasten cards and articles by text or category. Returns small previews; fetch a specific ID to read its complete body.",
      inputSchema: {
        query: z.string().max(200).optional(),
        category_id: z.string().max(64).optional(),
        limit: z.number().int().min(1).max(50).optional(),
      },
      outputSchema: { items: z.array(z.object({
        id: z.string(), title: z.string(), summary: z.string(), preview: z.string(),
        artifact_type: z.string(), tags: z.array(z.string()), version: z.number(), editable: z.boolean(),
      })) },
      annotations: annotations(true),
    },
    async ({ query, category_id, limit }) => {
      const items = await zett.search(query, limit, category_id);
      return result({ items }, `Found ${items.length} saved items.`);
    },
  );

  server.registerTool(
    "get_knowledge",
    {
      title: "Read saved Zettelekasten knowledge",
      description: "Read the published body of one knowledge item by ID for use in this conversation.",
      inputSchema: { id: z.string().min(1).max(64) },
      outputSchema: { document: z.object({
        id: z.string(), title: z.string(), content: z.string(), summary: z.string(),
        subtitle: z.string(), artifact_type: z.string(), tags: z.array(z.string()),
        version: z.number(), preview: z.string(), editable: z.boolean(),
      }) },
      annotations: annotations(true),
      _meta: { ui: { visibility: ["model", "app"] }, "openai/widgetAccessible": true },
    },
    async ({ id }) => {
      const document = await zett.get(id);
      return result({ document }, `Read "${document.title}".`);
    },
  );

  registerAppTool(
    server,
    "show_knowledge_card",
    {
      title: "Show an editable Zettelekasten card",
      description: "After saving or reading an item, show its interactive Zettelekasten card in this chat. Provide an existing ID; this tool does not save or change data.",
      inputSchema: { id: z.string().min(1).max(64) },
      outputSchema: { id: z.string(), title: z.string(), version: z.number(), tags: z.array(z.string()) },
      annotations: annotations(true),
      _meta: { ui: { resourceUri: URI }, "openai/outputTemplate": URI },
    },
    async ({ id }) => {
      const document = await zett.get(id);
      return result(
        { id: document.id, title: document.title, version: document.version, tags: document.tags },
        `Showing Zettelekasten card "${document.title}" (${id}).`,
      );
    },
  );

  server.registerTool(
    "edit_knowledge",
    {
      title: "Save edits to a Zettelekasten card",
      description: "Update an existing library-owned card or article with explicit user intent. Requires the version just read; refuses stale writes and replaces the complete tag list.",
      inputSchema: {
        id: z.string().min(1).max(64),
        expected_version: z.number().int().min(1),
        title: z.string().min(1).max(500),
        content: z.string().min(1).max(1_000_000),
        summary: z.string().max(20_000).optional(),
        subtitle: z.string().max(500).optional(),
        tags: z.array(z.string().min(1).max(500)).max(100),
      },
      outputSchema: { id: z.string(), title: z.string(), version: z.number(), tags: z.array(z.string()) },
      annotations: annotations(false, true),
      _meta: { ui: { visibility: ["model", "app"] }, "openai/widgetAccessible": true },
    },
    async (input) => {
      const document = await zett.edit(input);
      return result(
        { id: document.id, title: document.title, version: document.version, tags: document.tags },
        `Updated "${document.title}".`,
      );
    },
  );

  registerAppResource(server, "Zettelekasten knowledge card", URI, {}, async () => {
    const template = await readFile(viewFile, "utf8");
    const script = (await readFile(widgetScript, "utf8")).replaceAll("</script", "<\\/script");
    // A replacement string interprets `$&` in the bundled JavaScript as the
    // matched placeholder, corrupting the script before the iframe parses it.
    const html = template.replace(
      "<!-- ZETT_WIDGET_SCRIPT -->",
      () => `<script type="module">${script}</script>`,
    );
    return {
      contents: [{
        uri: URI,
        mimeType: RESOURCE_MIME_TYPE,
        text: html,
        _meta: { ui: { prefersBorder: true } },
      }],
    };
  });
  return server;
}
