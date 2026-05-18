"""semantic 模块 —— Prompt 模板与版本管理。

每个 prompt 模板有独立版本号，下游 semantic.json 记录 prompt_version。
修改 prompt 时必须升级版本号，确保 reproducibility。
"""

# ---------------------------------------------------------------------------
# v1 — 初始版本
# ---------------------------------------------------------------------------

SYSTEM_V1 = """\
你是一个信息结构分析师。你的任务是从视频转录文本中提取结构化信息。

核心原则：
- 你提取的是「信息点」，不是「总结」
- 保留原文的表达方式和语气，不要改写为书面语
- 不要添加原文没有的内容
- 不要使用「本视频讨论了…」「作者指出…」等论文腔
- 每个信息点必须引用具体的 segment_id

信息点类型：
- problem: 提出的问题、矛盾、困境
- step: 方法、步骤、流程
- pitfall: 陷阱、误区、常见错误
- conclusion: 结论、观点、判断
- context: 重要背景信息（非以上四类但不可忽略）

输出格式：严格 JSON，不要输出 markdown 代码块。"""

CHAPTER_DETECT_V1 = """\
以下是一段视频的转录文本。请检测其中的逻辑章节边界。

每个 segment 格式: [id:N] ts:START-END text:TEXT

{segments_text}

请输出 JSON 数组，每个元素为一个章节：
[
  {{
    "id": "ch01",
    "title": "章节主题（简短，≤15字，提取核心话题而非描述）",
    "first_segment_id": 0,
    "last_segment_id": 23
  }},
  ...
]

规则：
- 章节数量由内容自然决定，短视频 1-3 章，长视频 3-8 章
- 在主题明显转换处切分，不要在句子中间切
- 每个章节应覆盖一个完整的话题单元
- 如果视频很短（≤5 个 segment），可以只有 1 个章节
- title 要具体，不要用「开头」「中间」「结尾」等空洞词
- 直接输出 JSON，不要输出任何其他文字"""

EXTRACT_V1 = """\
以下是一个视频章节的转录文本。

章节: {chapter_title}
时间范围: {start_ts}s - {end_ts}s

每个 segment 格式: [id:N] ts:START-END text:TEXT

{segments_text}

从以上文本中提取所有信息点。每个信息点必须：

1. 引用至少一个 segment_id（你只能提取原文中明确存在的信息）
2. 内容用白话表达，保持原文的语气和表达习惯
3. 不要改写为「标准书面语」
4. 不要添加「本段讨论了…」「作者认为…」等套话
5. 如果某一类信息点不存在（如没有陷阱），该类型数组为空

输出严格 JSON（不要 markdown 代码块）：
{{
  "points": [
    {{
      "type": "problem|step|pitfall|conclusion|context",
      "content": "信息点内容 — 高密度，白话，不泛化",
      "refs": [
        {{"segment_id": 0, "quote": "原文关键短句（≤30字）"}}
      ],
      "confidence": 0.0-1.0
    }}
  ]
}}

confidence 评分标准：
- 0.9-1.0: 原文明确表达，无可争议
- 0.7-0.9: 原文清晰表达，需少量推断
- 0.5-0.7: 需要一定推断，但合理
- <0.5: 推测成分较大，标记低置信度

规则：
- 信息密度优先：宁可少而精，不要多而空
- 如果原文信息量很低（闲聊、过渡），points 可以为空数组
- 不要为了凑数而生成泛化内容"""

# ---------------------------------------------------------------------------
# 版本注册表
# ---------------------------------------------------------------------------

PROMPTS = {
    "v1": {
        "system": SYSTEM_V1,
        "chapter_detect": CHAPTER_DETECT_V1,
        "extract": EXTRACT_V1,
    },
}

LATEST = "v1"


def get_prompt(version: str, name: str) -> str:
    """获取指定版本的 prompt 模板。"""
    if version not in PROMPTS:
        raise ValueError(f"未知 prompt 版本: {version}。可用: {list(PROMPTS.keys())}")
    if name not in PROMPTS[version]:
        raise ValueError(f"未知 prompt 名称: {name}。可用: {list(PROMPTS[version].keys())}")
    return PROMPTS[version][name]


def list_versions() -> list[str]:
    return list(PROMPTS.keys())
