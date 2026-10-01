# zett3rd

Integrations that live next to Zett but are not part of its build.

Nothing here is imported by `backend/` or `frontend/`, so a broken integration
can never fail Zett's startup, a route, or a background loop. Each directory is
its own small project with its own README and its own way to run or install it.

| Directory | What it is |
| --- | --- |
| [`chrome-extension/`](chrome-extension/) | The **Zettelekasten** Chrome extension (Vue 3 + TypeScript, built with Vite): embeds a separate conversation in each webpage, talks to the local Agent, and saves artifacts |
| [`zettelekasten-chatgpt/`](zettelekasten-chatgpt/) | The Zettelekasten ChatGPT integration: a loopback MCP Apps bridge to save and classify knowledge in the global Library Session, then search, view, and edit it in ChatGPT |
