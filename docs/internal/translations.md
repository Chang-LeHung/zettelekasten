# Translations

The site is published in English and Simplified Chinese.

- **Documentation.** `docs/zh/` mirrors `docs/` file for file, and VitePress serves it under `/docs/zh/`
  with its own sidebar, search, and language switch (`docs/.vitepress/config.mts`, `locales`).
- **Landing page.** `web/index.html` is English and `web/zh/index.html` is Chinese, two complete documents
  rather than a runtime swap, so there is no flash of the wrong language and each page is indexable.
  `web/tools/compose_site.mjs` writes both and builds one search index per language. The Chinese page uses
  screenshots from the product in its Chinese interface (`web/assets/product/zh/`).

## Adding or changing a page

1. Change the English page.
2. Make the same change in `docs/zh/<same path>`. Keep the links, code blocks, tables, and admonitions
   identical; translate prose and `#` comments only. Do not translate tool docstrings or string literals in
   code, because those are what the code returns or matches on.
3. Give every `##` and `###` heading in the Chinese page an explicit anchor equal to the slug of the
   **English** heading, for example `## 安装扩展 {#install-the-extension}`. Links such as
   `settings.md#ai-providers` then keep working in both trees.
4. Run `make docs-build`. `web/tools/check-translations.mjs` fails when a page is missing or its structure,
   anchors, code, or links drifted. It checks structure only; wording is yours to review.

## Wording

Use the product's own Chinese interface text (the `zh` block of `frontend/src/i18n/index.ts`) for every
button, tab, and menu you name, for example 产物, 全局资源, 定时任务, 通信渠道, 设置 → 模型服务. Keep command
names, flags, identifiers, file names, and provider names in English.

`docs/zh/agim.md` and `docs/zh/weixin.md` are translations of the package READMEs, not snippet includes; update
them when `backend/agim/README.md` or `backend/zett-weixin/README.md` changes.
