import assert from "node:assert/strict";
import { once } from "node:events";
import { test } from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

import { startServer } from "../src/server.js";
import { ZettClient } from "../src/zett-client.js";

test("loopback HTTP MCP accepts a client and rejects foreign origins", async () => {
  const zett = new ZettClient(async () => "http://127.0.0.1:6280", async () => Response.json([]));
  const server = startServer(0, zett);
  await once(server, "listening");
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  const url = new URL(`http://127.0.0.1:${address.port}/mcp`);
  const client = new Client({ name: "http-test", version: "1.0.0" });
  try {
    await client.connect(new StreamableHTTPClientTransport(url));
    assert.ok((await client.listTools()).tools.some((tool) => tool.name === "save_knowledge"));
    const blocked = await fetch(url, { method: "POST", headers: {
      origin: "https://untrusted.example",
      "content-type": "application/json",
    }, body: "{}" });
    assert.equal(blocked.status, 403);
  } finally {
    await client.close();
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});
