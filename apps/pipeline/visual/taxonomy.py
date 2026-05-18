"""visual 模块 —— SVG 类型分类与路由规则。

SVG 类型从真实语义导出，非装饰。
每类有明确的触发条件、数据结构模板、布局建议。
"""

# ---------------------------------------------------------------------------
# SVG 类型注册表
# ---------------------------------------------------------------------------

SVG_TYPES = {
    "flowchart": {
        "label": "流程图",
        "description": "步骤序列、流程、方法路径",
        "semantic_trigger": "step ≥ 3",
        "data_template": {
            "nodes": [],   # [{id, label, type: "start"|"process"|"decision"|"end"}]
            "edges": [],   # [{from, to, label}]
        },
        "layout_hint": "vertical",
    },
    "matrix": {
        "label": "对比矩阵",
        "description": "多实体 × 多属性的横向对比",
        "semantic_trigger": "problem + conclusion 涉及 ≥2 个对比对象",
        "data_template": {
            "columns": [],  # [attr_name, ...]
            "rows": [],     # [{label, cells: [value, ...]}]
        },
        "layout_hint": "grid",
    },
    "timeline": {
        "label": "时间线",
        "description": "带时间戳的事件序列",
        "semantic_trigger": "多个点含时间关键词 (年/月/日/阶段) 且 ≥3",
        "data_template": {
            "events": [],  # [{ts, label, detail}]
        },
        "layout_hint": "horizontal",
    },
    "chain": {
        "label": "因果链",
        "description": "原因→结果→后续影响的因果推导",
        "semantic_trigger": "problem + conclusion ≥3 且存在因果关系",
        "data_template": {
            "nodes": [],   # [{id, label, type: "cause"|"effect"|"both"}]
            "edges": [],   # [{from, to, relation}]
        },
        "layout_hint": "horizontal",
    },
    "layered": {
        "label": "分层结构图",
        "description": "层级/分类/从属关系",
        "semantic_trigger": "context 包含层级关键词 (层/级/分类/上层/下层) 或结论含分层逻辑",
        "data_template": {
            "layers": [],  # [{level, label, items: [str, ...]}]
        },
        "layout_hint": "vertical",
    },
    "decision_tree": {
        "label": "决策树",
        "description": "判断分支、选择路径、条件→结果",
        "semantic_trigger": "pitfall ≥ 2 或 step 含条件分支",
        "data_template": {
            "root": {},    # {question, branches: [{condition, outcome, sub_branches}]}
        },
        "layout_hint": "horizontal",
    },
    "checklist": {
        "label": "风险/检查清单",
        "description": "注意事项、常见错误、检查项",
        "semantic_trigger": "pitfall ≥ 2 且非决策型",
        "data_template": {
            "items": [],   # [{label, severity: "critical"|"warning"|"info", detail}]
        },
        "layout_hint": "vertical",
    },
}


# ---------------------------------------------------------------------------
# 路由规则 —— 决定章节→SVG 类型的映射
# ---------------------------------------------------------------------------

def route(chapter: dict) -> dict | None:
    """基于章节的 semantic point 类型分布，返回最佳 SVG 类型和置信度，或 None（不需要图）。

    规则顺序决定优先级（先匹配的先生效）。
    返回: {"svg_type": str, "confidence": float, "rationale": str} | None
    """
    points = chapter.get("points", [])
    if not points:
        return None

    # 计数
    counts = {}
    for p in points:
        t = p["type"]
        counts[t] = counts.get(t, 0) + 1

    total = len(points)
    step_n = counts.get("step", 0)
    pitfall_n = counts.get("pitfall", 0)
    problem_n = counts.get("problem", 0)
    conclusion_n = counts.get("conclusion", 0)
    context_n = counts.get("context", 0)

    # ---------- 最小触发门槛 ----------
    if total < 3:
        return None  # 信息量不足，不做图

    # ---------- 规则 1: step 主导 → flowchart ----------
    if step_n >= 3:
        return {
            "svg_type": "flowchart",
            "confidence": min(0.95, 0.6 + step_n / total),
            "rationale": f"{step_n} 个步骤型信息点，适合流程图呈现方法路径",
        }

    # ---------- 规则 2: pitfall ≥ 2 → checklist 或 decision_tree ----------
    if pitfall_n >= 2:
        if step_n >= 1 or problem_n >= 2:
            return {
                "svg_type": "decision_tree",
                "confidence": min(0.95, 0.6 + (pitfall_n + step_n) / total),
                "rationale": f"{pitfall_n} 个陷阱 + {step_n} 个步骤，适合决策树呈现判断路径",
            }
        return {
            "svg_type": "checklist",
            "confidence": min(0.95, 0.6 + pitfall_n / total),
            "rationale": f"{pitfall_n} 个陷阱型信息点，适合风险清单呈现",
        }

    # ---------- 规则 3: problem + conclusion 主导 → chain ----------
    if problem_n + conclusion_n >= 5 and problem_n >= 2:
        return {
            "svg_type": "chain",
            "confidence": min(0.95, 0.6 + (problem_n + conclusion_n) / total),
            "rationale": f"{problem_n} 个问题 + {conclusion_n} 个结论，适合因果链呈现推导关系",
        }

    # ---------- 规则 4: conclusion + context 含对比 → matrix ----------
    if problem_n + conclusion_n >= 4:
        # 检测是否有对比语义
        all_text = " ".join(
            p.get("content", "") for p in points
            if p["type"] in ("problem", "conclusion")
        )
        compare_keywords = ["对比", "差异", "区别", "vs", "相比", "不同", " whereas ", " however ",
                           "另一方面", "但是", "而", "versus", "unlike", "相比之下"]
        if any(kw in all_text.lower() for kw in compare_keywords):
            return {
                "svg_type": "matrix",
                "confidence": 0.75,
                "rationale": "结论/问题含对比语义，适合矩阵呈现多维度对比",
            }
        # 否则退回到 chain
        return {
            "svg_type": "chain",
            "confidence": 0.65,
            "rationale": f"{problem_n} 个问题 + {conclusion_n} 个结论，因果链呈现",
        }

    # ---------- 规则 5: context 主导 → timeline 或 layered ----------
    if context_n >= total * 0.5:
        all_text = " ".join(p.get("content", "") for p in points)
        temporal_keywords = ["年", "月", "日", "阶段", "时期", "先后", "起初", "后来", "最初",
                            "year", "month", "phase", "stage", "initially", "later", "first"]
        if any(kw in all_text.lower() for kw in temporal_keywords):
            return {
                "svg_type": "timeline",
                "confidence": 0.7,
                "rationale": f"{context_n} 个背景信息点含时间标记，适合时间线呈现",
            }
        return {
            "svg_type": "layered",
            "confidence": 0.6,
            "rationale": f"{context_n} 个背景信息点，适合分层结构呈现",
        }

    # ---------- 规则 6: 混合类型 → 柔性判断 ----------
    if step_n >= 1 and problem_n >= 1:
        return {
            "svg_type": "flowchart",
            "confidence": 0.55,
            "rationale": "步骤+问题混合，流程图呈现分析路径",
        }

    # ---------- 默认：不触发 ----------
    return None


def get_data_template(svg_type: str) -> dict:
    """获取指定 SVG 类型的数据结构模板。"""
    if svg_type not in SVG_TYPES:
        raise ValueError(f"未知 SVG 类型: {svg_type}")
    import copy
    return copy.deepcopy(SVG_TYPES[svg_type]["data_template"])


def list_types() -> list[str]:
    return list(SVG_TYPES.keys())


def type_info(svg_type: str) -> dict:
    return SVG_TYPES.get(svg_type, {})
