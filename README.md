# Help Me Study

为大学课程作业与中文 Notion 笔记准备的个人技能套件。总入口按需调用四个子技能；共享规则只维护一份。

**默认交付为未压缩的 `submit`。只有你明确说“打包/压缩”后才创建归档，包括老师要求的 ZIP 和 Overleaf 源码包。**

[完整最终 Prompt](docs/FINAL_PROMPT.zh-CN.md)保存本次所有要求，包括不确定时适度询问、笔记先审大纲、文献研读、评分覆盖和排版标准。

## 技能

| 名称 | 用途 |
|---|---|
| [help-me-study](skills/help-me-study/SKILL.md) | 组合任务入口与路由 |
| [help-me-assignment](skills/help-me-assignment/SKILL.md) | 老师要求、字幕、文献和评分核验 |
| [help-me-homework](skills/help-me-homework/SKILL.md) | 解答/代码/实验/LaTeX 报告，整理 submit |
| [help-me-notes](skills/help-me-notes/SKILL.md) | 先结构大纲，确认后正文、公式和配图 |
| [help-me-notion-sync](skills/help-me-notion-sync/SKILL.md) | 页面定位、层级、资源保留、同步和回读 |

## 安装

需要 Python 3.10+。运行工具及安装器仅用标准库；开发校验另需 PyYAML。先克隆仓库，再在仓库根目录：

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

安装器把五个技能和 `help-me-shared` 一起安装到同一父目录，保持相对引用。**不要只装单个 SKILL.md**，共享脚本和 references 也需要。已有同名文件夹时停止，不覆盖旧版本。更新请先比较差异并保留所需改动，再由你决定替换方式；用户状态独立保存。宿主未刷新发现时可重启/刷新技能列表；当前聊天的技能目录快照不保证即时更新。

本仓库制作/推送不等于已经安装进你的全局技能目录。也不会自动连接 Notion 或配置 Canvas 凭据。

## 使用

```text
用 $help-me-assignment 核验这个作业的老师要求、课堂补充和评分细则，先不实现。
用 $help-me-homework 完成这个作业，代码放 code、报告放 report，submit 先不要压缩。
用 $help-me-notes 整理这门课，先给我章节结构、页面层级和详细大纲。
用 $help-me-notion-sync 更新我已经确认的笔记，保留附件和原有章节。
用 $help-me-study 完成这门课的作业并补充复习笔记。
```

作业先展示要求摘要，明确后继续；笔记大纲须用户确认后才生成完整正文或改正式页面。重要歧义询问，低影响常规细节自行决定；已确认的选择复用。

## 依赖与能力边界

- Canvas/课堂字幕：按需调用当前已安装的 `sjtu-canvas-skill`，由其现有配置加载凭据。仓库不复制该技能、不含凭据。
- 文献：按需 `nature-reader`、`nature-paper-card`、`nature-ref-verifier`、`nature-downloader`。
- 报告/图：按需 `nature-writing`、`nature-polishing`、`nature-figure`；老师模板和课程要求优先，不强套期刊结构。
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

也可对安装目标运行 `python scripts/validate_suite.py --skills-root "<技能父目录>"`。已有 PyYAML 时无需安装开发依赖。

行为场景与验证范围见 [qa/scenarios.md](qa/scenarios.md)，实际执行结果见 [qa/validation.md](qa/validation.md)。本地辅助工具测试和结构检查不能证明模型会在所有任务中正确决策，也不等于完成一次真实 Canvas/Notion 端到端演练。
