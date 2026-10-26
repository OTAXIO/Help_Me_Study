# 格式检查：源、转换与显示分开

适用于生成前规范、写前检查、转换后验收和已有笔记的精确修复；通用规范在[排版](formatting.md)。没有真实页面位置时只修规则/样例，不能声称修好截图页面。局部格式修复沿用原大纲，不重做审批。

## 1. 检查路线

1. 确定目标和接口格式：Markdown、增强 Markdown、原生块/富文本、Word/PDF/HTML。阅读当前工具契约，不猜接口。
2. 取原始片段、上下文、对应本地源；分清无效源、重复转义、不支持扩展、把标记当纯文本和显示问题。
3. 生成/转换后抽取关键结构做断言：标题文字/级别、强调片段、列表起始/层级、代码原文、表头及所有单元格、链接/图片元数据。不是只数标记。
4. 目标原生节点可用则检查真实类型/样式。只有 Markdown 导出时不伪称已查原生属性；工具只提供部分页/分页未取全要标覆盖范围。
5. 最终看真实页面或文档渲染。回读合法 `**` 不等于泄漏；回读无星号也不证明加粗。源/节点/显示分别报告。

## 2. 可选只读工具

脚本：[format_audit.py](../scripts/format_audit.py)。状态工具/安装器仍只用标准库；Markdown 检查和预览另需 [requirements-format.txt](../requirements-format.txt)，优先已有环境，无依赖时明确说明或用现有等价解析工具，不能假装纯正则完整校验。

以下 `$FORMAT_TOOL` 为脚本实际绝对路径，替换示例路径。

```powershell
python "$FORMAT_TOOL" audit "<笔记.md>" --expect "<结构期望.json>"
python "$FORMAT_TOOL" audit "<笔记.md>" --expect "<结构期望.json>" --output "<新检查记录.json>"
python "$FORMAT_TOOL" preview "<笔记.md>" --output "<新预览.html>"
python "$FORMAT_TOOL" audit-notion "<原生块快照.json>" --expect "<原生结构期望.json>"
```

本工具不修改源、不自动修复、不联网、不写 Notion。输出不能覆盖输入/期望文件，已有输出不覆盖。退出码 0 表示所选结构检查无错误，1 表示断言/结构错误，2 为输入/依赖/文件错误；**0 不代表全格式/数学/目标平台已验证**。`requires_review` 告警必须结合意图检查，不自动删标记。

`commonmark` 是通用解析；默认 `notes` 在其上启用表格和删除线。它不是 Notion 专有渲染器，任务项/callout/脚注/页面块/折叠等扩展需按目标原生能力核验。数学只在明显候选区保护告警，不验证公式语法、含义或排版。远端资源和锚点访问不自动检查。

当前 Notion 增强 Markdown 已支持的页面/mention 等标签不能仅因通用预览显示为文字就删除。先核对实际契约，资源块和扩展走目标原生检查，通用解析的告警不是清理授权。

预览转原生 HTML，原始 HTML 默认转义，远程图片不自动加载，本地图片转换为本地引用。它仅验证选定 CommonMark 扩展的结构和通用显示，不证明 Notion、Word、PDF 或公式显示。正式文档仍需目标渲染。

## 3. 期望结构

见 [format-expect.example.json](../templates/format-expect.example.json)。按本次内容写期望，不把示例当每篇笔记固定模板。

- `elements`：按 kind 和字段匹配，count 默认 1；支持 heading(level/text)、strong/emphasis/strike、bullet_list、ordered_list(start)、list_item、quote、separator、code_block(text/language)、code_inline、link(text/href)、image(text/src)、table 等观察结果。
- `tables`：完整表格的行/列文本矩阵，核对数据未被解析截断，不只看有无表格。
- `source_contains`：必须原样保留的代码/公式片段；只能证明源仍在，不能证明公式正确或渲染成功。

没有期望时只报告观察与有限结构错误；不能凭解析不报错猜作者意图。未闭围栏按本套件规范报错；文本中的残留标记是需复核告警，合法字面语法应使用代码/目标支持的表示，不全局清理。

## 4. 原生 Notion 快照

仅接收实际原生 block 数组，或 `{results: [...], has_more: false}`。子块须放 `children` 或对应内容的 `children`（数组或分页对象），这是本地快照约定，不宣称当前连接器支持同样写入字段。Markdown 导出 JSON 不冒充原生快照。

检查 rich_text annotations、标题/代码/公式/列表/图片/表格等部分结构；未知类型标人工复核，分页未完报错，子块未附标覆盖不足。相邻粗体 span 合并作语义比较，代码 span 不被当泄漏。快照存在不证明当前权限/访问，也不证明实际显示，需真实回读/查看。

## 5. 修复与记录

先存修前片段与必要资源结构。源错就精确改源，转换错改映射/序列化，不反复改正确文本掩盖转换问题。结构化参数正确序列化，禁止反复转义、全局删星号/反斜杠。代码、数学、路径、通配符、语法示例受保护；保留内容、层级、资源和数字单位。

修后重验受影响片段和关联引用，报告原因证据、改动、前后样例、自动/结构/视觉检查与未做部分；不是所有问题都需脚本，不可靠的自动修复不添加。
