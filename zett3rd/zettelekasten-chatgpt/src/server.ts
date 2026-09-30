import { createServer } from "node:http";
import { pathToFileURL } from "node:url";

import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

import { createMcpServer } from "./mcp.js";
import { localZettEndpoint, ZettClient } from "./zett-client.js";

export function startServer(port = 6281, zett = new ZettClient(localZettEndpoint)) {
  const http = createServer(async (request, response) => {
    if (request.url !== "/mcp" || !["POST", "GET", "DELETE"].includes(request.method ?? "")) {
      response.writeHead(404).end();
      return;
    }
    // Loopback-only and exact Host checking prevent a browser's DNS rebinding
    // from reaching the unauthenticated local MCP endpoint.
    const address = http.address();
    const actualPort = address && typeof address !== "string" ? address.port : port;
    const host = request.headers.host;
    if (host !== `127.0.0.1:${actualPort}` && host !== `localhost:${actualPort}`) {
      response.writeHead(403).end();
      return;
    }
    const origin = request.headers.origin;
    if (origin && origin !== `http://${host}`) {
      response.writeHead(403).end();
      return;
    }
    const server = createMcpServer(zett);
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
      maxRequestBodySize: 2_000_000,
    });
    try {
      await server.connect(transport);
      await transport.handleRequest(request, response);
    } catch (error) {
      console.error("Zettelekasten MCP request failed", error instanceof Error ? error.message : "unknown error");
      if (!response.headersSent) response.writeHead(500).end("MCP request failed");
    } finally {
      if (response.writableFinished) void server.close();
      else response.once("close", () => void server.close());
    }
  });
  http.listen(port, "127.0.0.1", () => {
    const address = http.address();
    console.error(`Zettelekasten MCP listening on http://127.0.0.1:${address && typeof address !== "string" ? address.port : port}/mcp`);
  });
  return http;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  startServer(Number(process.env.ZETT_MCP_PORT ?? "6281"));
}
