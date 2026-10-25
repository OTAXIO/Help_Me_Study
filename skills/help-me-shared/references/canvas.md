# SJTU Canvas 与课堂证据

发现当前已安装 `sjtu-canvas-skill`，先读其 SKILL.md。按本次问题读取 review-workflow、incremental-review-updates 或 Windows 排查等需要的 reference，不默认全读。检查 CLI 文件和现有运行环境是否可用，不仅因 SKILL.md 存在就声称 CLI 可用。

1. 检查凭据是否已配置，仅确认存在不输出值；避免 `TOKEN` 缺失时交互挂起。API 用 TOKEN，视频/字幕还可能需 OC_COOKIE。
2. 从技能实际目录按当前文档运行 JSON CLI。中文课名先 `list-courses` 解析课程和学期，多结果查上下文再必要询问，不能猜 ID。
3. `list-assignments`、`list-files` 获取要求和材料 URL；URL 失效先重新获取。不猜下载链接。
4. `list-videos` 匹配日期/讲次/材料，再 `download-subtitle` 或 `study-note`。传入本次 work 下的输出位置，复用已核对缓存。
5. 映射课件页码、视频日期、时间戳、对应主题、老师强调与作业说明。不把整段转录粘作笔记，不把学生汇报误归老师要求。
6. 字幕无/噪声大时保留覆盖缺口；含混语音不能变成确定评分或作业要求。课件存在不能证明课堂已讲。

若解析失败，按当前技能提供的 Canvas tabs → external tool/sessionless launch → 视频资源客户端等实际入口回退，不硬编码历史课程/tool ID，也不把失败当不存在。缺 Cookie/权限时说明所缺，用户已有授权不重复索取。
