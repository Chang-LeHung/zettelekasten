# 命令行

`zett` 命令用于启动和停止 Zett，也可以从终端、脚本或其他编码 Agent 向你的产物库添加内容。运行 `zett --help` 查看命令列表，运行 `zett <command> --help` 查看某个命令的选项。

## 启动、检查与停止 {#start-check-and-stop}

```bash
zett start      # 在后台启动 Zett 并返回 shell
zett status     # 是否在运行，运行在哪里
zett stop       # 停止它
```

`zett start` 会打印要打开的地址（通常是 `http://127.0.0.1:6280`）和控制台日志的路径：

```text
Zett is running in the background; pid=48213
http://127.0.0.1:6280
Console log: /Users/you/.zettelekasten/logs/background.log
```

| 选项 | 作用 |
| --- | --- |
| `--host ADDRESS` | 监听其他地址。默认值让 Zett 只在这台电脑上可访问。 |
| `-p`, `--port PORT` | 使用其他端口（默认 `6280`）。 |
| `-f`, `--foreground` | 让 Zett 保持在当前终端中运行，并在屏幕上显示日志。用 `Ctrl+C` 停止。 |
| `-b`, `--background` | 脱离终端并返回 shell。这是默认行为。 |

`zett status` 会列出在没有打开浏览器时仍持续工作的各个部分。三项都应显示 `running`：

```text
Zett is running
  url:      http://127.0.0.1:6280
  server:   pid=48213 running
  started:  2026-10-01T09:12:44+08:00
  scheduler: pid=48220 running
  worker:    pid=48221 running
```

如果其中有一项没有运行，先运行 `zett stop`，再运行 `zett start`。如果 Zett 完全没有运行，`zett status` 会如实说明并以非零状态退出，因此可以在脚本中使用。

::: tip 让 Zett 只在这台电脑上运行
你的产物库没有登录界面。除非你清楚还有谁能访问你开放的端口，否则请保持默认地址。
:::

## 添加到产物库 {#add-to-the-library}

`zett artifact` 可以不经过会话，直接在你的产物库中创建卡片、文章和幻灯片。Zett 必须处于运行状态。

```bash
# 用选项创建一张卡片
zett artifact create --type card --title "Local-first beats sync" \
  --body "Your notes should work on a plane." --source cli

# 较长的正文可以来自文件，或用 - 通过管道传入
zett artifact create --type article --title "Reading notes" --body-file notes.md --source cli
cat notes.md | zett artifact create --type article --title "Reading notes" --body - --source cli

# 幻灯片：用只含 --- 的一行分隔每一页
zett artifact create --type slides --title "Ten minutes on local-first" \
  --body-file talk.md --source cli
```

该命令会打印新条目的 id。加上 `--json` 则打印完整的条目。

| 选项 | 作用 |
| --- | --- |
| `--type` | `card`、`article` 或 `slides`。必填。 |
| `--title` | 标题。 |
| `--body`, `--body-file` | Markdown 正文，来自命令行或文件；`-` 表示从标准输入读取。 |
| `--summary` | 简短摘要，用于卡片。 |
| `--subtitle` | 副标题，用于文章和幻灯片。 |
| `--content`, `--content-file` | 当某个选项无法表达时，用 JSON 一次性提供所有字段。 |
| `--raw-content` | 生成该条目所用的原始文本，保留供参考。 |
| `--status` | `saved`（默认）会放入产物库；`draft` 则保持未发布。 |
| `--source` | 创建者，例如 `cli` 或 `cron:nightly`。必填。 |
| `--metadata KEY=VALUE` | 额外的标记；要添加多个时重复使用该选项。 |

`--source` 是必填项，因为在这里创建的条目没有会话可以说明它的来源。请写上创建它的脚本或工具的名称，方便日后分辨。

要指定卡片的类型，请以 JSON 传入字段。卡片类型可以是 `note`、`idea`、`quote`、`todo` 或 `reference`：

```bash
zett artifact create --type card --source cli --content '{
  "title": "Local-first beats sync",
  "content": "Your notes should work on a plane.",
  "card_type": "idea"
}'
```

读取、列出和删除你创建的内容：

```bash
zett artifact list                 # 最新的在前：id、类型、状态、标题
zett artifact list -q sync --limit 50
zett artifact get <id>             # 完整的条目
zett artifact delete <id>
```

`zett artifact list` 和 `zett artifact delete` 适用于从命令行和其他集成创建的条目。在会话中生成的产物，需要在该会话中删除，或在产物库的阅读器中删除。

目前还不能在这里创建图片和 LaTeX PDF；请让 Agent 来做。

## 用标签整理 {#organize-with-tags}

`zett tag` 操作的是你在侧边栏中看到的同一套分类。标签是一个路径，例如 `Engineering/Python`；使用尚不存在的路径会创建它，同时创建缺失的上级。

```bash
zett tag list                                  # 分类树
zett tag create Engineering/Python --description "Python notes"
zett tag update <tag-id> --path Engineering/Python/Async
zett tag delete <tag-id> --recursive --force

zett tag add <artifact-id> Engineering/Python Ideas     # 保留已有标签
zett tag remove <artifact-id> Ideas
zett tag set <artifact-id> Projects/Zett                # 替换所有标签
zett tag set <artifact-id> --clear                      # 移除所有标签
```

`zett tag list` 的每一行格式为 `path  direct/total  id`。**direct** 统计恰好打在该标签上的条目数，**total** 再加上树中更下层的所有条目，所以如果某个上级标签唯一的条目位于子标签中，它会显示为 `0/1`。

- `update` 可以重命名、移动标签或修改其样式。有子标签的标签不能重命名或移动。
- `delete` 会拒绝删除有子标签或仍在使用的标签；`--recursive` 会同时删除其子标签，`--force` 会把它从带有该标签的条目上移除。
- `remove` 只接受已经存在的路径。
- 只有已保存的条目才能带标签，因此 `--status draft` 的条目不能打标签。

全局资源有自己的分类树。给 `list`、`create`、`add`、`remove` 或 `set` 加上 `--asset`，即可操作那棵树和资源 id：

```bash
zett tag list --asset
zett tag add --asset <asset-id> Papers/CRDT
```

两棵树中相同的路径是两个不同的分类。

## 让编码 Agent 使用 Zett {#let-a-coding-agent-use-zett}

`zett install` 会教 Claude Code 或 Codex 这类编码 Agent 把结果保存到你的产物库。它会在该 Agent 查找技能的位置写入一个技能文件；之后你只要说“把这份总结作为文章保存到 Zett”，Agent 就会自行运行上面的命令。

```bash
zett install --list      # 它支持的 Agent
zett install claude      # 写入 ~/.claude/skills/zett-cli/SKILL.md
zett install codex       # 写入 ~/.codex/skills/zett-cli/SKILL.md
zett install --dir ~/.my-agent/skills   # 其他任意 Agent，通过它的技能文件夹指定
```

无论 Zett 是否在运行，都可以安装；Agent 使用该技能时需要 Zett 正在运行。再次运行该命令会更新文件。如果你编辑过已安装的文件，Zett 会保留你的版本并告知你；加上 `--force` 即可替换。

## 从 ChatGPT 保存 {#save-from-chatgpt}

`zett3rd/zettelekasten-chatgpt` 中的 ChatGPT 集成可以让 ChatGPT 把卡片或文章保存到你的产物库，归入你的分类，之后还能查找、阅读或编辑它。它运行在你的电脑上，与 Zett 并排。

1. 用 `zett start` 启动 Zett。
2. 在 `zett3rd/zettelekasten-chatgpt` 中运行：

   ```bash
   npm ci
   npm run build
   ZETT_BASE_URL=http://127.0.0.1:6280 npm run dev
   ```

   它监听端口 `6281`；设置 `ZETT_MCP_PORT` 可以更改。
3. 在 ChatGPT 或 Codex 的开发者模式中，通过 [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) 连接 `http://127.0.0.1:6281/mcp`。

ChatGPT 只能看到已发布的卡片和文章，看不到你的草稿。让它把同一内容保存两次会创建两个条目。如果条目在 ChatGPT 读取之后发生了变化，或者带有未保存的草稿，编辑会被拒绝，请重新打开后再试。ChatGPT 对话本身的任何内容都不会存储在 Zett 中。

::: warning 请保持私密
该集成没有密码。切勿把它的地址或 Zett 的地址暴露在公共隧道或代理上。
:::
