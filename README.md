# Help Me Study

为大学课程作业、中文 Notion 笔记与 PPT 演讲稿准备的个人技能套件。总入口按需调用五个子技能；共享规则只维护一份。

**默认交付为未压缩的 `submit`。只有你明确说“打包/压缩”后才创建归档，包括老师要求的 ZIP 和 Overleaf 源码包。**

**正式报告必须使用 LaTeX 并编译 PDF：完整源工程留在工作目录的 `report/`，最终 PDF 放 `submit/`。Markdown 只作内部草稿或说明，不能替代报告。** 用户不必每次重申；编译受阻时保留源码并说明尚未完成，不能自行换格式。用户明确改格式或教师要求存在冲突时，按[报告路线](skills/help-me-shared/references/report.md)处理。

[完整最终 Prompt](docs/FINAL_PROMPT.zh-CN.md)保存本次所有要求，包括不确定时适度询问、笔记先审大纲、文献研读、评分覆盖和排版标准。

v1.1 增加[演讲与报告增量 Prompt](docs/SPEECH_REPORT_PROMPT.zh-CN.md)：演讲先确认风格/时长/听众目标，核对主语、人称与时间；报告用项目问题、实验对照及实验关系组织层层推进的论证。

v1.2 增加[完整格式修复 Prompt](docs/FORMAT_PROMPT.zh-CN.md)及[格式检查流程](skills/help-me-shared/references/format-validation.md)：标题、段落、行内样式、列表、公式、代码、表格、资源和引用按目标规范生成；源结构、转换节点和最终显示分开验收。格式工具只报告问题，不批量改笔记。

v1.2.1 将 LaTeX/PDF 报告要求落实到总入口、作业入口、要求摘要、调用提示与交付验收，防止以 Markdown 草稿结束报告任务。规则走查与实际校验范围见[验证记录](qa/validation-v1.2.1.md)。

## 技能

| 名称 | 用途 |
|---|---|
| [help-me-study](skills/help-me-study/SKILL.md) | 组合任务入口与路由 |
| [help-me-assignment](skills/help-me-assignment/SKILL.md) | 老师要求、字幕、文献和评分核验 |
| [help-me-homework](skills/help-me-homework/SKILL.md) | 解答/代码/实验/LaTeX 报告，整理 submit |
| [help-me-notes](skills/help-me-notes/SKILL.md) | 先结构大纲，确认后正文、公式和配图 |
| [help-me-notion-sync](skills/help-me-notion-sync/SKILL.md) | 页面定位、层级、资源保留、同步和回读 |
| [help-me-speech](skills/help-me-speech/SKILL.md) | PPT 演讲稿，个人表达、段落衔接、主体与时间核验 |

## 安装

需要 Python 3.10+。状态工具及安装器仅用标准库；开发校验需要 PyYAML 和格式解析依赖。先克隆仓库，再在仓库根目录：

```powershell
git clone https://github.com/OTAXIO/Help_Me_Study.git
cd Help_Me_Study
python scripts/install.py --dry-run
python scripts/install.py
```

默认写入 `$CODEX_HOME/skills`，未配置时为 `~/.codex/skills`。可选自定义目标（父目录）：

```powershell
python scripts/install.py --target "<用户技能父目录>" --dry-run
python scripts/install.py --target "<用户技能父目录>"
```

安装器把六个技能和 `help-me-shared` 一起安装到同一父目录，保持相对引用。**不要只装单个 SKILL.md**，共享脚本和 references 也需要。普通安装遇同名目录会停止。宿主未刷新发现时可刷新/重启；当前聊天的目录快照不保证即时更新。

### 更新已有安装

```powershell
python scripts/install.py --update --dry-run
python scripts/install.py --update
```

更新按安装回执核对文件哈希；v1.0 无回执的安装使用仓库中已知旧版基线。只替换与已知版本一致的文件，用户自行改动或未知同名文件会在写入前报冲突；没有强制覆盖选项。额外自建文件保留，不自动删除旧文件。可用 `--target` 指定技能父目录。

被替换的文件先以未压缩形式备份，位置见命令输出。安装回执和备份在用户状态目录的 `installations/`，可用 `--state-dir` 指定；不放源仓库或技能目标内。Notion 映射、任务大纲回执与凭据不修改。若发生文件系统 I/O 中断，可能部分更新；保留输出中的备份并检查状态后重试，不把逐文件原子替换说成全套事务。

本仓库制作/推送不等于已经安装进你的全局技能目录。也不会自动连接 Notion 或配置 Canvas 凭据。

## 使用

```text
用 $help-me-assignment 核验这个作业的老师要求、课堂补充和评分细则，先不实现。
用 $help-me-homework 完成这个作业，代码放 code，LaTeX 报告及编译 PDF 放 report，最终材料整理到 submit，先不要压缩。
用 $help-me-notes 整理这门课，先给我章节结构、页面层级和详细大纲。
用 $help-me-notion-sync 更新我已经确认的笔记，保留附件和原有章节。
用 $help-me-speech 根据这份 PPT 写演讲稿，先问清风格、时长、听众与表达目标。
用 $help-me-study 完成这门课的作业并补充复习笔记。
```

作业先展示要求摘要，明确后继续；笔记大纲须确认后生成正文或改正式页；新演讲稿先确认风格、时长、听众与目标，只问缺项，不默认增加提纲审批。重要歧义询问，低影响细节自行决定；已确认选择复用。

## 依赖与能力边界

- Canvas/课堂字幕：按需调用当前已安装的 `sjtu-canvas-skill`，由其现有配置加载凭据。仓库不复制该技能、不含凭据。
- 文献：按需 `nature-reader`、`nature-paper-card`、`nature-ref-verifier`、`nature-downloader`。
- 报告/图：按需 `nature-writing`、`nature-polishing`、`nature-figure`；老师模板和课程要求优先，不强套期刊结构。
- 个人表达：优先用户授权样本；有可用风格工具时按需使用，无样本不声称充分拟合。正式/活泼借鉴通用组织和口头表达技巧，不移入他人身份、经历或独特文风。
- Notion：需要宿主实际提供读取、写入和资源能力。连接器缺失时仍可生成本地稿，但不能宣称已同步。
- PDF/Office：实际渲染和视觉核验依赖宿主已有文档工具，不包含 LaTeX 编译器。

外部技能缺失时可用等价已有能力，明确缺口。工作流规则不会自动创造外部工具、访问权限或用户同意。

## 本地目录与位置记录

新增任务创建 `work/code`、`work/report`、`work/submit`；冲突依次选择 work_codex、work_codex_2；继续原任务显式 resume。详见[运行工具](skills/help-me-shared/references/runtime.md)。

Notion 映射默认在 Windows `%LOCALAPPDATA%/HelpMeStudy/notion-map.json`，其他系统在 XDG 状态目录。可用 `HELP_ME_STUDY_STATE_DIR` 或命令选项更改，勿指向公开仓库。它保存课程/学期、父子页和核验时间，不修改宿主全局记忆。每次复用仍需读真实页面。

大纲回执保存 SHA-256；改动后旧确认失效。`--user-confirmed` 和 `--verified` 是对已经发生的人类确认/远程核验的记录，不是独立权限认证或网络验证。所有辅助 CLI 均不联网、不写 Notion、不打包、不提交课程作业。

## 开发验证

```powershell
python -m pip install -r requirements-dev.txt
python scripts/validate_suite.py
python -m unittest discover -s tests -v
```

也可对安装目标运行 `python scripts/validate_suite.py --skills-root "<技能父目录>"`。已具备 requirements-dev.txt 中依赖时无需重新安装。

### 可选格式检查

状态工具不需要 Markdown 库；`format_audit.py audit/preview` 另需 `markdown-it-py>=4,<5`（本次使用已有 4.0.0），依赖清单随共享目录安装。不会自动装包，缺失时明确报错或使用现有等价工具。

```powershell
python skills/help-me-shared/scripts/format_audit.py audit qa/cases/format-good.md --expect qa/cases/format-good.expect.json
python skills/help-me-shared/scripts/format_audit.py preview qa/cases/format-good.md --output "<新预览.html>"
python skills/help-me-shared/scripts/format_audit.py audit-notion qa/cases/notion-native-format.json --expect qa/cases/notion-native-format.expect.json
```

详见[格式检查边界](skills/help-me-shared/references/format-validation.md)。数学正确性/排版、平台扩展、远程访问和最终 Notion/Word/PDF 显示仍需目标工具检查。原生快照是合成示例，不是真实页面。本地预览禁用原始 HTML、不会自动加载远程图片，不代表目标平台渲染。

已有 Node/Playwright 时，可用 `qa/check-format-preview.cjs` 对生成的样例 HTML 做隔离浏览器 DOM 与截图检查；它不会安装浏览器或修改现有浏览器，使用单独无界面实例并阻止 HTTP(S) 请求。用 NODE_PATH 提供现有包，HELP_ME_STUDY_BROWSER_EXECUTABLE 可指定已有浏览器。该脚本只验证合成样例，不是任意页面验证器。

行为场景与验证范围见 [qa/scenarios.md](qa/scenarios.md)，当前结果见 [v1.2 验证记录](qa/validation-v1.2.md)，[v1.1](qa/validation-v1.1.md)和[v1.0](qa/validation.md)记录保留。工具测试/结构检查与合成预览不能证明模型在所有任务中正确，也不等于真实 Canvas/Notion 端到端验证。
