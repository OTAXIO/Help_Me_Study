# 本地运行工具

Python 3.10+，标准库，无网络、无压缩、无课程提交/Notion 写入、无宿主记忆修改。脚本为 [study_state.py](../scripts/study_state.py)，先解析实际安装目录，不能相对用户 cwd 猜路径。

以下 `$STATE_TOOL` 表示该脚本绝对路径，由调用端设置；命令中的任务路径、课名和学期替换为实际值，不复制示例当真实状态。

## 工作目录

```powershell
python "$STATE_TOOL" workspace init --task-dir "<任务目录>"
python "$STATE_TOOL" workspace init --task-dir "<任务目录>" --resume "<任务目录>/work"
```

新任务依次尝试 work、work_codex、work_codex_2……，以 mkdir 排他创建，不覆盖现有文件/目录；生成 code/report/submit 和任务清单。继续时显式 resume，检查目录与清单归属；不自动认领旧 work。工具不检测任意外部已存在压缩包，返回 `packaging_performed:false` 仅表示本次调用没有打包。

## 大纲回执

先写工作目录内的大纲文件，再：

```powershell
python "$STATE_TOOL" outline set --workspace "<工作目录>" --file "notes/outline.md"
python "$STATE_TOOL" outline status --workspace "<工作目录>"
```

向用户展示对应版本并等待真实确认后，才用 status 返回的 SHA-256：

```powershell
python "$STATE_TOOL" outline approve --workspace "<工作目录>" --sha256 "<实际指纹>" --user-confirmed
```

指纹变动后旧回执显示 changed/未批准，需判断是否超出已确认结构。CLI 记录代理对已有人类确认的陈述，不是独立权限系统；不能自行加 flag 假造同意。仅本地回执不触发正文或外部写入。

## 页面位置

用户状态位置优先级：`--state-dir` → `HELP_ME_STUDY_STATE_DIR` → Windows `%LOCALAPPDATA%/HelpMeStudy`，其他系统 `$XDG_STATE_HOME/HelpMeStudy` 或 `~/.local/state/HelpMeStudy`。不要指向公开仓库。读取没有状态时不建目录；损坏文件报错不覆盖。

```powershell
python "$STATE_TOOL" notion list
python "$STATE_TOOL" notion get --course "<课程名称>" --term "<学期>"
python "$STATE_TOOL" notion put --file "<本地映射.json>" --verified
```

结构示例见 [notion-map.example.json](../templates/notion-map.example.json)。示例是合成数据，不访问其链接。page_id 支持 32 位 hex 或 UUID；URL 必须是指向相同 ID 的 HTTPS Notion 链接。先把短链/自定义链接用真实工具解析为规范地址。章节/拓展 parent_id 必须形成无环且连通课程父页的树。

`--verified` 只记录已实际读取页面的陈述，脚本不验证网络访问。get 总提醒再读真实页面。同名多学期不自动选。改变同一课程学期的父页时，核对用户意图后才加 `--replace-parent`；更新其他字段按同一 course/term 替换。支持 list/get/put 查看和更正，不自动删除历史状态。

写采用排他锁和临时文件原子替换。存在锁时停止，确认持有进程状态后人工恢复，不能盲删锁。只允许映射字段，不存 Cookie/Token。

## 可选格式检查

见[格式检查与依赖](format-validation.md)。`study_state.py` 仍只用标准库；独立的 `format_audit.py` 在解析 Markdown/生成 HTML 预览时需 markdown-it-py，原生快照检查本身不需该解析器。工具不自动修复或上传，输出与视觉验证分开。
