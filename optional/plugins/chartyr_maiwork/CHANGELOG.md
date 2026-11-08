# QQBridge integration 0.16.8 (2026-11-08)

- 明确静态网页请求按既定规则确定性自动放行，其他任务仍由模型审核。
- 会话模块不再追加第二句模型生成的开工话；开工提示统一为协调器的一条固定文本。

# QQBridge integration 0.16.7 (2026-11-08)

- 纯前端 SVG/CSS/Canvas 绘制网页动画不再被协调器误判为需要生图模型；真实图片生成仍走现有媒体插件。

# QQBridge integration 0.16.6 (2026-11-08)

- 把一次性待批请求重审推迟到插件依赖与后台循环全部就绪后，避免热加载早期丢失审核协程。

# QQBridge integration 0.16.5 (2026-11-08)

- 自动审核能力预检以当前请求标题为准，避免引用消息里的「画图」把网页请求误判成生图。
- 任务真正进入 running 后，按任务与需求版本发送一次固定开工提示「好的你等一下，我去帮你做出来」。
- 热加载后重审一次 12:11 被误拦且仍无任务的 `R-1` 网页请求，不重复接单、不修改来源消息。

# QQBridge integration 0.16.4 (2026-11-08)

- Raise Gemini 3.8 Flash reasoning effort to HIGH for all five MaiWork job profiles.
- Register LOW, MEDIUM and HIGH as supported effort levels for the current model entry.
- Keep quick judgment and session triage at their explicit LOW setting; ordinary chat routing is unchanged.

# QQBridge integration 0.16.3 (2026-11-08)

- Public share pages display the current generating model instead of the fixed MaiWork byline.

## 0.16.2 (2026-11-08)

- Convert complete HTML documents in QQ private chats, and in unserved groups, to a file in the original session.
- Preserve short prose around the document as chat text; never paste the full HTML or its code fence.
- Keep group delivery receipts and @ notices for served groups; private file delivery needs no @ notice.

## 0.16.1 (2026-11-08)

- Flash MEDIUM task model via a private Responses gateway; ordinary chat routing unchanged.
- Use the existing bounded Docker worker image for networkless command execution.
- Claim explicit artifact requests once, preserve full-HTML-to-file guard, and deliver both group files and temporary public pages.
- Narrow automatic approval to public research, reports, static pages and task attachments; external actions need owner approval.
- Share one daily proactive-message budget across news, ideas and goal results; drawing remains owned by Vertex media.
