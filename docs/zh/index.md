---
layout: home

hero:
  name: Zett
  text: 做出值得留下的东西。
  tagline: "在你自己的电脑上与 AI 一起思考。从一个想法、一份文件或正在阅读的网页出发，把你选定的版本留在属于你的文件夹里。"
  actions:
    - theme: brand
      text: 快速开始
      link: '#quick-start'
    - theme: alt
      text: 阅读指南
      link: /zh/guide/conversations
    - theme: alt
      text: GitHub
      link: https://github.com/Chang-LeHung/zettelekasten

features:
  - title: 会话
    details: "可在回答期间排队追加消息、中途引导方向、审核 Shell 命令，并为每个会话选择八档推理强度。"
    link: /zh/guide/conversations
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>'
  - title: 在 Chrome 中使用
    details: "在任意页面旁打开 Zett。它能读取页面；填写或点击前，每一步都需要你批准。"
    link: /zh/guide/chrome-extension
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M14 13h4M14 16h4"/></svg>'
  - title: 产物与产物库
    details: "卡片、文章、图片、幻灯片和 LaTeX 论文：先出草稿，保存后才正式发布。"
    link: /zh/guide/artifacts
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>'
  - title: 资源
    details: "为单个会话准备参考文件，也可以把常用文件放进全局资源库，在所有会话中复用。"
    link: /zh/guide/assets
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>'
  - title: 定时任务
    details: "让 Zett 每天早上、每周或每月自动完成同一件事，无需打开浏览器。"
    link: /zh/guide/scheduled-tasks
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
  - title: 通信渠道
    details: "在手机上通过微信给 Zett 发消息，支持照片、语音和文件。"
    link: /zh/guide/channels
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="20" rx="2.5"/><path d="M11 18h2"/></svg>'
  - title: 设置与本地数据
    details: "接入任意模型、设置限制、查看用量，并备份一个文件夹即可。"
    link: /zh/guide/settings
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/></svg>'
  - title: 命令行
    details: "启动和停止 Zett，用脚本写入产物库，让 Claude Code 或 Codex 替你归档。"
    link: /zh/guide/command-line
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m5 8 4 4-4 4M12 17h7"/></svg>'
---
## 快速开始 {#quick-start}

你需要 Python 3.10 到 3.14，系统可以是 macOS、Linux 或 Windows。无需注册 Zett 账号。

```bash
uv tool install zettelekasten   # 或：pipx install zettelekasten
zett start       # 在后台启动 Zett
zett status      # 检查是否正在运行
```

发行包名是 `zettelekasten`，安装的命令是 `zett`。如果想从源码目录运行同一个应用：

```bash
git clone https://github.com/Chang-LeHung/zettelekasten
cd zettelekasten
make install     # 构建界面并安装 `zett` 命令
zett start
```

1. 打开 `http://127.0.0.1:6280`。
2. 在 **设置 → 模型服务** 中添加你想让 Zett 使用的模型。Zett 自身不带模型，详见 [AI 模型服务](guide/settings.md#ai-providers)。
3. 选择 **新建会话**，试试这句话：“做一张简洁的卡片：对个人笔记来说，本地优先胜过同步。”
4. 在聊天旁边查看这张卡片，然后选择 **保存**，把它放进你的产物库。

用完后运行 `zett stop` 即可停止 Zett。想一边试用一边查看日志，可以改用 `zett start --foreground`。

## 一次不错的上手体验 {#a-good-first-session}

1. 在[会话](guide/conversations.md)中粘贴一段文字，或附上一份文件。
2. 让它做一张简洁的卡片。在聊天旁边阅读，提出修改意见，措辞满意后再保存。
3. 把它归入某个[分类](guide/artifacts.md#tags)方便以后查找，并把会反复用到的文件放进[全局资源](guide/assets.md#static-assets)。
4. 阅读时也一样：[在 Chrome 中打开 Zett](guide/chrome-extension.md)。

## 在 Zett 之上构建 {#build-on-zett}

<ul class="home-links">
  <li><a href="plugins/"><strong>插件</strong><span>插件如何打包、安装和加载。</span></a></li>
  <li><a href="plugins/agent-plugins"><strong>Agent 插件</strong><span>为 Zett 增加新的工具、钩子、Slash 命令和 <code>@</code> 引用。</span></a></li>
  <li><a href="plugins/channel-plugins"><strong>渠道插件</strong><span>通过登录、接收和发送，接入另一个聊天应用。</span></a></li>
  <li><a href="agim"><strong>agim SDK</strong><span>微信插件所基于的小型聊天平台 SDK。</span></a></li>
  <li><a href="weixin"><strong>微信渠道插件</strong><span>一个完整的渠道插件，可对照指南阅读。</span></a></li>
</ul>

## 你的数据存放在哪里 {#where-your-data-lives}

你的产物库、会话、文件和设置都存放在 `~/.zettelekasten/`。备份这个文件夹就能保留你的整个工作区；也可以在 `zett start` 之前设置 `ZETT_STORAGE_ROOT`，把它放到别处。你发给模型的消息仍会发送到你所选的模型服务商，所以不要发送你不希望该服务商处理的内容。
