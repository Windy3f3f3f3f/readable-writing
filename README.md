# readable-writing

一个让 Coding Agent 和写作 Agent 更会说人话的中文写作 Skill。

Agent 工作久了，很容易沉浸在自己的执行语言里：满篇是状态标签、文件路径、箭头链、检查项和
局部细节。它自己知道事情是怎么推进的，人却很难从这些信息里看出结论、证据和下一步。另一种
常见情况是让 Agent 写报告、周报或技术材料，事实虽然都对，成文却有明显的 AI 味：结构像模板，
句子像翻译，段落缺少自然的推进。

`readable-writing` 就是为这两个场景做的。

## 两个主要场景

### 1. 让 Coding Agent 的进度对人类可读

Coding Agent 连续调查、改代码和跑验证后，通常会沿用工作记忆里的表达方式：

- 用 `Done / Pending / Blocked` 和大量勾叉代替完整判断；
- 把命令、路径、commit、日志和中间状态堆在一起；
- 只讲自己做了什么，不先讲问题是否解决；
- 默认读者看过此前的对话，省略关键背景和因果关系。

这些信息适合 Agent 维持执行状态，却不适合人类快速跟进。这个 Skill 会要求 Agent 重新站到读者
一侧：先说结果，再解释证据；区分过程记录和正式汇报；保留必要的文件、数字和失败点，但把它们
组织成可以独立阅读的进度说明。

例如，可以这样要求 Agent：

```text
使用 $readable-writing 汇报这轮修改。让我不用翻前面的对话，也能看懂解决了什么、怎么验证、
还有什么没完成。
```

### 2. 降低 Agent 所写文档的 AI 味

当 Agent 写报告、周报、技术分享、研发交接、README 或研究笔记时，这个 Skill 会同时处理两层
问题：

1. 文档层：写给谁、读完要知道什么、结论和证据按什么顺序出现；
2. 语言层：句子是否自然，段落是否连贯，有没有翻译腔、套话、标签墙和过度列表化。

它不会为了“像人”而虚构实验经历，也不会把专业书面语强行改成口语。数字、引用、命令、路径、
模型名和必要术语必须保留；原文已经自然时，也可以直接建议不改。

```text
使用 $readable-writing，把这些实验笔记整理成给算法同事看的技术报告。保留全部事实和数字，
减少模板感和 AI 味。
```

## 这个 Skill 是怎么来的

它不是从一份通用的“AI 常用词黑名单”拼出来的。最初的问题来自真实的 Agent 协作：Agent 做事
没有问题，但写出的进度和材料越来越像给自己看的运行面板，人类需要反复追问，才能重新拼出
完整故事。

我们随后检查了一批 AI 生成的科研进度、技术报告和开发记录，又用专业中文范文反向校准。结果
发现，真实高频问题并不只是“套话太多”，反而更常见于信息压缩过度：满屏加粗、箭头串因果、
状态交给 emoji、括号层层嵌套、中英文概念来回切换。很多网上流传的去 AI 味规则还会误伤正常
的专业表达，例如一律拆短句、一律删除被动句，或者把术语全部翻成中文。

所以这个 Skill 把规则分成了三层：

- 先判断文档类型和读者，防止进度汇报写成执行日志、交接说明写成平台需求；
- 再组织结论、证据和段落，让读者不依赖上下文也能跟上；
- 最后才处理翻译腔、符号装饰、弱动词、列表滥用等句子问题。

## 它是怎么实现的

核心入口是 [SKILL.md](SKILL.md)。它规定五条写作底线和两套工作流：写新文档时先列有证据的
段首判断，修改已有文档时先判断文档类型，再逐段重写。

详细知识按需加载：

- [文档类型与发布门禁](references/document-profiles.md) 区分进度、发布稿、技术分享、研发交接和
  口头讲解；
- [中文报告规则](references/zh-report-rules.md) 收录真实文档中反复出现的负面模式；
- [正向写作手感](references/positive-style.md) 说明自然的专业中文应该怎样组织句子、段落和证据；
- [examples/](examples/) 展示从散点笔记到成文、从仪表盘体到自然正文的完整过程；
- [scripts/](scripts/) 和 [fixtures/](fixtures/) 用确定性检查守住高频问题，并防止规则调整后误伤
  正常文本。

这种结构采用渐进加载：Agent 平时只看到 Skill 的名称和描述；触发后读取 `SKILL.md`；详细规则和
示例只在任务需要时加载。因此，规则可以足够具体，又不会每次都占满上下文。

## 安装

把仓库克隆到 Agent 使用的 Skill 目录：

```bash
# TraeX / TraeCode
git clone https://github.com/Windy3f3f3f3f/readable-writing.git ~/.trae/skills/readable-writing

# Codex
git clone https://github.com/Windy3f3f3f3f/readable-writing.git ~/.codex/skills/readable-writing

# Claude Code
git clone https://github.com/Windy3f3f3f3f/readable-writing.git ~/.claude/skills/readable-writing
```

安装后新建会话，或使用客户端提供的 Skill 刷新命令。

## 使用方式

可以直接点名 `$readable-writing`，也可以自然描述“说人话”“让进度更好跟进”“降低 AI 味”
“改掉翻译腔”等需求。Skill 的 description 已包含这些触发场景。

这个 Skill 只负责内容结构和中文表达。它不会核验论文引用、替代事实调查，也不负责 PPT 排版或
飞书文档 API 操作。

## 来源与 License

规则综合了真实 Agent 文档的错误分析、专业中文范文统计和多份公开写作材料。完整来源和第三方
许可证见 [LICENSE-NOTES.md](LICENSE-NOTES.md)。

本项目采用 MIT License。
