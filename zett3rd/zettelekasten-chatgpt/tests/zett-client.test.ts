import assert from "node:assert/strict";
import { test } from "node:test";

import { checkedLocalEndpoint, ZettClient } from "../src/zett-client.js";

test("saving uses one library request and returns a bounded receipt", async () => {
  const requests: Array<{ url: string; body: unknown }> = [];
  const fetcher: typeof fetch = async (input, init) => {
    const url = String(input);
    requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    return Response.json({
      id: "artifact-1",
      content: { title: "Idea" },
      version: 1,
      tags: [{ path: "Python" }],
    });
  };
  const client = new ZettClient(async () => "http://127.0.0.1:6280", fetcher);
  const saved = await client.save({ kind: "card", title: "Idea", body: "Body", tags: ["Python"] });
  assert.deepEqual(saved, { id: "artifact-1", title: "Idea", version: 1, tags: ["Python"] });
  assert.deepEqual(requests[0].body, {
    content: {
      artifact_type: "card", title: "Idea", summary: "", content: "Body",
      suggested_tags: [{ path: "Python", existing: true, confidence: 1 }],
    },
    status: "saved",
    metadata: { source: "codex" },
  });
  assert.equal(requests.length, 1);
});

const artifact = (overrides: Record<string, unknown> = {}) => ({
  id: "artifact-1",
  session_id: "library-1",
  artifact_type: "card",
  status: "saved",
  version: 1,
  content: {
    artifact_type: "card", title: "Idea", summary: "", content: "Published body",
    card_type: "note", keywords: ["keyword"], suggested_tags: [],
  },
  draft_content: null,
  raw_content: "Private source text",
  tags: [{ path: "Python" }],
  ...overrides,
});

test("search sends published-only criteria and projects away drafts, raw text and metadata", async () => {
  const paths: string[] = [];
  const fetcher: typeof fetch = async (input) => {
    const path = String(input);
    paths.push(path);
    return Response.json(path.includes("/api/artifacts?")
      ? [artifact({
        draft_content: { artifact_type: "card", title: "Unpublished", content: "Draft body" },
      })]
      : [{ id: "library-1", type: "library" }]);
  };
  const client = new ZettClient(async () => "http://127.0.0.1:6280", fetcher);
  const items = await client.search("Published", 5, "tag-1");
  assert.deepEqual(items, [{
    id: "artifact-1", artifact_type: "card", title: "Idea", summary: "",
    preview: "Published body", version: 1, tags: ["Python"], editable: false,
  }]);
  const url = new URL(paths[0]);
  assert.equal(url.pathname, "/api/artifacts");
  assert.equal(url.searchParams.get("published_only"), "true");
  assert.deepEqual(url.searchParams.getAll("statuses"), ["saved"]);
  assert.deepEqual(url.searchParams.getAll("artifact_types"), ["card", "article"]);
  assert.deepEqual(url.searchParams.getAll("tag_ids"), ["tag-1"]);
  assert.equal(paths[1], "http://127.0.0.1:6280/api/agent/sessions?types=library&limit=500");
});

test("editing uses the existing session-scoped PUT and tag replacement routes", async () => {
  const calls: Array<{ url: string; body: unknown }> = [];
  const fetcher: typeof fetch = async (input, init) => {
    const url = String(input);
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith("/api/agent/sessions?types=library&limit=500")) return Response.json([{ id: "library-1" }]);
    if (url.endsWith("/api/library/tags/artifacts/artifact-1")) return Response.json(artifact({
      version: 2, tags: [{ path: "Python" }, { path: "Concurrency" }],
    }));
    if (url.endsWith("/api/agent/library-1/artifacts/artifact-1")) return Response.json(artifact({ version: 2 }));
    return Response.json(artifact({
      version: calls.length > 4 ? 2 : 1,
      content: calls.length > 4 ? {
        ...artifact().content, title: "New", content: "Body",
        suggested_tags: [{ path: "Python", existing: true, confidence: 1 },
          { path: "Concurrency", existing: true, confidence: 1 }],
      } : artifact().content,
      tags: calls.length > 4 ? [{ path: "Python" }, { path: "Concurrency" }] : [{ path: "Python" }],
    }));
  };
  const client = new ZettClient(async () => "http://127.0.0.1:6280", fetcher);
  const edited = await client.edit({
    id: "artifact-1", expected_version: 1, title: "New", content: "Body",
    tags: ["Python", "Concurrency"],
  });
  assert.equal(edited.version, 2);
  assert.equal(calls[2].url, "http://127.0.0.1:6280/api/agent/library-1/artifacts/artifact-1");
  assert.deepEqual(calls[2].body, {
    content: {
      ...artifact().content,
      title: "New",
      summary: "",
      content: "Body",
      suggested_tags: [
        { path: "Python", existing: true, confidence: 1 },
        { path: "Concurrency", existing: true, confidence: 1 },
      ],
    },
    expected_version: 1,
  });
  assert.equal(calls[3].url, "http://127.0.0.1:6280/api/library/tags/artifacts/artifact-1");
  assert.deepEqual(calls[3].body, { paths: ["Python", "Concurrency"] });
});

test("editing refuses a session-owned artifact before sending a PUT", async () => {
  const methods: string[] = [];
  const fetcher: typeof fetch = async (input, init) => {
    methods.push(init?.method ?? "GET");
    return Response.json(String(input).includes("/api/agent/sessions?")
      ? [{ id: "library-1" }]
      : artifact({ session_id: "other-session" }));
  };
  const client = new ZettClient(async () => "http://127.0.0.1:6280", fetcher);
  await assert.rejects(
    client.edit({ id: "artifact-1", expected_version: 1, title: "New", content: "Body", tags: [] }),
    /Only a global library artifact/,
  );
  assert.deepEqual(methods, ["GET", "GET"]);
});

test("classification failure reports a partial edit instead of retrying content", async () => {
  const calls: string[] = [];
  const fetcher: typeof fetch = async (input) => {
    const url = String(input);
    calls.push(url);
    if (url.includes("/api/agent/sessions?")) return Response.json([{ id: "library-1" }]);
    if (url.includes("/api/library/tags/artifacts/")) {
      return Response.json({ detail: "Invalid tag" }, { status: 422 });
    }
    return Response.json(artifact());
  };
  const client = new ZettClient(async () => "http://127.0.0.1:6280", fetcher);
  await assert.rejects(
    client.edit({ id: "artifact-1", expected_version: 1, title: "New", content: "Body", tags: ["Python"] }),
    /Content was saved, but classification failed/,
  );
  assert.equal(calls.filter((path) => path.includes("/api/agent/library-1/artifacts/")).length, 1);
});

test("Zettelekasten failures are bounded and malformed ids are refused", async () => {
  const client = new ZettClient(async () => "http://127.0.0.1:6280", async () =>
    Response.json({ detail: "Artifact changed; reload it" }, { status: 409 }));
  await assert.rejects(client.get("a/b"), /Invalid artifact id/);
  await assert.rejects(client.get("artifact-1"), /Zettelekasten 409: Artifact changed/);
});

test("explicit backend address can only name a loopback origin", () => {
  assert.equal(checkedLocalEndpoint("http://127.0.0.1:6280"), "http://127.0.0.1:6280");
  assert.throws(() => checkedLocalEndpoint("https://zett.example.com"), /loopback HTTP/);
  assert.throws(() => checkedLocalEndpoint("http://127.0.0.1:6280/api"), /loopback HTTP/);
});
