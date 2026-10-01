import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import { createMcpServer } from "../src/mcp.js";
import { ZettClient } from "../src/zett-client.js";

test("MCP tools expose saved knowledge and one UI resource", async () => {
  const zett = new ZettClient(async () => "http://127.0.0.1:6280", async (request) => {
    const url = String(request);
    if (url.endsWith("/api/artifacts")) return Response.json({
      id: "artifact-1", content: { title: "Idea" }, version: 1, tags: [],
    });
    if (url.endsWith("/api/artifacts/artifact-1")) {
      return Response.json({
        id: "artifact-1", session_id: "library-1", artifact_type: "card", status: "saved",
        version: 1, raw_content: null, draft_content: null,
        content: {
          artifact_type: "card", title: "Idea", summary: "",
          content: "Body", card_type: "note", keywords: [], suggested_tags: [],
        },
        tags: [],
      });
    }
    if (url.includes("/api/agent/sessions?")) return Response.json([{ id: "library-1" }]);
    if (url.includes("/api/library/tags")) return Response.json([]);
    return Response.json([]);
  });
  const [serverTransport, clientTransport] = InMemoryTransport.createLinkedPair();
  const server = createMcpServer(zett);
  const client = new Client({ name: "zett-test", version: "1.0.0" });
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  try {
    const tools = (await client.listTools()).tools;
    assert.deepEqual(tools.map((tool) => tool.name), [
      "list_categories", "save_knowledge", "search_knowledge", "get_knowledge",
      "show_knowledge_card", "edit_knowledge",
    ]);
    assert.equal(tools.find((tool) => tool.name === "show_knowledge_card")?._meta?.ui &&
      (tools.find((tool) => tool.name === "show_knowledge_card")?._meta?.ui as { resourceUri: string }).resourceUri,
    "ui://zettelekasten/knowledge-card-v3.html");
    assert.equal((tools.find((tool) => tool.name === "save_knowledge")?._meta?.ui as { resourceUri: string }).resourceUri,
      "ui://zettelekasten/knowledge-card-v3.html");
    assert.equal(tools.find((tool) => tool.name === "show_knowledge_card")?._meta?.["openai/outputTemplate"],
      "ui://zettelekasten/knowledge-card-v3.html");
    assert.equal(tools.find((tool) => tool.name === "get_knowledge")?._meta?.["openai/widgetAccessible"], true);
    assert.equal(tools.find((tool) => tool.name === "edit_knowledge")?._meta?.["openai/widgetAccessible"], true);
    const saved = await client.callTool({
      name: "save_knowledge", arguments: { kind: "card", title: "Idea", body: "Body" },
    });
    assert.equal(saved.isError, undefined);
    assert.equal((saved.structuredContent as { id: string }).id, "artifact-1");
    const card = await client.callTool({ name: "show_knowledge_card", arguments: { id: "artifact-1" } });
    assert.deepEqual(card.structuredContent, { id: "artifact-1", title: "Idea", version: 1, tags: [] });
    const resource = await client.readResource({ uri: "ui://zettelekasten/knowledge-card-v3.html" });
    assert.match(resource.contents[0].mimeType ?? "", /mcp-app/);
    assert.ok("text" in resource.contents[0]);
    assert.match(resource.contents[0].text, /<script type="module">/);
    assert.ok(Buffer.byteLength(resource.contents[0].text, "utf8") < 1024 * 1024);
    const script = resource.contents[0].text.match(/<script type="module">([\s\S]*?)<\/script>/)?.[1];
    const builtScript = await readFile(fileURLToPath(new URL("../dist/widget.js", import.meta.url)), "utf8");
    assert.equal(script, builtScript, "HTML must embed the compiled script byte-for-byte");
    assert.doesNotThrow(() => new vm.Script(script));
  } finally {
    await client.close();
    await server.close();
  }
});
