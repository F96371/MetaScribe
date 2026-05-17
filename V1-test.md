# AI 视频知识重构工厂（V1）实施文档

> 目标：
>
> 输入一个 YouTube / B站 视频链接。
>
> 输出一个：
>
> * 高信息密度
> * 自动结构化
> * 自动 SVG 可视化
> * 可离线打开
> * 单页 HTML 知识页
>
> 不做 SaaS。
> 不做登录。
> 不做支付。
> 不做复杂 Agent。
> 不做过度架构。
>
> V1 只验证：
>
> “有没有人愿意为这个结果付钱。”

---

# 一、项目原则（必须遵守）

## 1. 不重复造轮子

能用现成的：

* yt-dlp
* ffmpeg
* Whisper
* Playwright
* Jinja2
* cc-switch

就不要自己重写。

---

## 2. 单线程 Pipeline

不要：

* 多 Agent
* LangGraph
* CrewAI
* 自动调度系统

V1 不需要。

直接：

```text
视频
→ 下载
→ 转录
→ 语义结构化
→ SVG 意图生成
→ HTML 渲染
→ PNG 截图
```

即可。

---

## 3. AI 不直接生成 SVG

AI 只生成：

```json
{
  "type":"timeline"
}
```

然后：

SVG Renderer 再绘制。

否则后期一定炸。

---

## 4. 所有模块独立运行

每个模块：

* 单独输入
* 单独输出
* 单独测试

禁止：

一个 prompt 干全部事情。

---

# 二、技术栈（V1）

# 语言

推荐：

```text
Python
```

原因：

* AI 工具链成熟
* Whisper 方便
* ffmpeg 方便
* SVG 方便
* JSON 方便

---

# 前端渲染

推荐：

```text
Jinja2 + HTML + CSS
```

不要 React。

V1 不需要。

因为：

* React 太重
* hydration 没意义
* 只是静态知识页

---

# 截图

推荐：

```text
Playwright
```

不要 Puppeteer。

Playwright 更稳。

---

# 模型切换

使用：

```text
cc-switch
```

参考：

[https://github.com/farion1231/cc-switch](https://github.com/farion1231/cc-switch)

---

# Whisper

推荐：

| 语言 | 模型       |
| -- | -------- |
| 中文 | turbo    |
| 英文 | small.en |

---

# 三、目录结构（冻结）

不要乱改。

```text
project/
│
├── apps/
│   ├── pipeline/
│   └── renderer/
│
├── packages/
│   ├── schemas/
│   ├── prompts/
│   ├── semantic-engine/
│   ├── visual-engine/
│   └── shared/
│
├── outputs/
├── temp/
├── tests/
└── assets/
```

---

# 四、完整 Pipeline

# Step 1：视频摄取（ingest）

## 目标

输入：

```text
视频 URL
```

输出：

```text
metadata.json
audio.mp3
cover.jpg
```

---

## 使用工具

```text
yt-dlp
ffmpeg
ffprobe
```

---

## 功能要求

### 1. 获取完整 metadata

包括：

* title
* uploader
* description
* tags
* chapters
* duration
* thumbnail
* upload_date

---

### 2. 下载最佳音频

格式：

```text
mp3
```

---

### 3. 校验时长

使用：

```text
ffprobe
```

校验：

```text
metadata.duration
vs
actual_audio_duration
```

如果差异 > 5%：

* 重试
* 标记异常

---

## 输出格式

```json
{
  "video_id":"xxx",
  "title":"xxx",
  "uploader":"xxx",
  "duration":1234,
  "chapters":[],
  "tags":[],
  "audio_path":"./audio.mp3"
}
```

---

# Step 2：转录（transcript）

## 输入

```text
audio.mp3
```

---

## 输出

```text
segments.json
```

---

## 使用工具

```text
Whisper
```

---

## 输出格式（固定）

```json
[
  {
    "start":12.3,
    "end":18.2,
    "text":"xxx"
  }
]
```

---

## 校验规则

最后一个 segment.end：

必须接近：

```text
audio duration
```

否则：

* 标记异常
* 重新转录

---

# Step 3：语义结构化（semantic-engine）

这是整个系统核心。

不是摘要。

是：

# “知识重构”

---

## 输入

```text
segments.json
metadata.json
```

---

## 输出

```text
chapters.json
```

---

## 输出结构（固定）

```json
[
  {
    "chapter_id":"001",
    "title":"为什么大多数人亏钱",
    "summary":"xxx",
    "problem":"xxx",
    "trap":"xxx",
    "steps":[],
    "conclusion":"xxx",
    "key_points":[],
    "quotes":[],
    "visual_hint":"causal_chain",
    "timestamp":"12:31"
  }
]
```

---

## Prompt 规则

AI 必须：

* 用白话
* 短句
* 高信息密度
* 避免 AI 味
* 不要流水账
* 不要强行总结
* 不要模板化语言

---

## 必须提炼

每章：

* 问题
* 陷阱
* 步骤
* 结论
* 关键观点

---

## 时间戳要求

必须可回跳视频。

例如：

```text
12:31
```

---

# Step 4：视觉意图生成（visual-engine）

AI 不直接画图。

AI 只决定：

# “该用什么图”

---

## 输入

```text
chapter.json
```

---

## 输出

```json
{
  "type":"comparison",
  "data":{
    "left":{},
    "right":{}
  }
}
```

---

# 支持的图类型（V1）

只做这几个。

不要贪。

---

## 1. flow

适合：

* 步骤
* 流程
* 操作路径

---

## 2. timeline

适合：

* 时间变化
* 发展顺序

---

## 3. comparison

适合：

* 对比
* 错误 vs 正确

---

## 4. hierarchy

适合：

* 分层
* 分类
* 结构

---

## 5. causal_chain

适合：

* 因果
* 连锁反应

---

## 6. checklist

适合：

* 风险
* 注意事项

---

# Step 5：SVG Renderer

## 输入

```json
visual.json
```

---

## 输出

```text
svg.html
```

---

## 原则

SVG 必须：

* 信息化
* 有箭头
* 有关系
* 有关键词
* 有层级

禁止：

* 装饰图
* 空洞图
* 纯美化

---

## 技术

推荐：

```text
SVG + Python
```

不要：

* canvas
* D3
* Mermaid

V1 太重。

---

# Step 6：HTML Renderer

## 输入

```text
chapters.json
svg
```

---

## 输出

```text
index.html
```

---

# 风格系统

使用：

```text
/themes
```

---

# V1 先做 5 套

## 1. apple

特点：

* 极简
* 卡片
* 大留白

---

## 2. notion

特点：

* 知识库感
* 信息密度高

---

## 3. bloomberg

特点：

* 金融感
* 专业感

---

## 4. minimal

特点：

* 纯白
* 超轻

---

## 5. youtube

特点：

* 高视觉冲击
* 大标题

---

## 自定义风格

允许：

```json
{
  "spacing":"large",
  "font":"Inter",
  "density":"high"
}
```

---

# Step 7：整页截图

## 使用工具

```text
Playwright
```

---

## 输出

```text
full.png
```

---

## 检查内容

自动检查：

* 空白
* 重叠
* 溢出
* 断行

---

# Step 8：切图

## 使用工具

```text
ffmpeg
imagemagick
```

---

## 规则

切片：

* 保留约 100px overlap
* 避免切断标题
* 避免切断 SVG

---

# 五、Prompt 结构（必须独立）

目录：

```text
/packages/prompts/
```

---

# 结构

```text
semantic/
visual/
summary/
```

---

# 版本化

```text
v1
v2
v3
```

---

# 禁止

Prompt 写死代码里。

后期一定地狱。

---

# 六、模型抽象层

# 不绑定 Claude

必须支持：

* Claude
* Gemini
* OpenAI
* DeepSeek

---

# 使用 cc-switch

参考：

[https://github.com/farion1231/cc-switch](https://github.com/farion1231/cc-switch)

---

# 统一接口

例如：

```python
model.generate(prompt)
```

---

# 七、V1 不做的东西

这些全部禁止。

---

# 不做：

* 用户系统
* 登录
* 支付
* SaaS
* 云部署
* 多 Agent
* 自动工作流平台
* RAG
* 向量数据库
* 知识图谱
* 多人协作
* React SSR
* 实时更新
* AI 自动排版
* AI 自动 CSS

---

# 八、测试视频（必须建立）

建立固定测试集。

每次改动必须跑。

---

# 至少包含：

| 类型    | 用途         |
| ----- | ---------- |
| 教程型   | flow       |
| 对比型   | comparison |
| 金融型   | 高密度知识      |
| 访谈型   | 长文本        |
| 时间线型  | timeline   |
| 风险分析型 | checklist  |

---

# 九、V1 成功标准

不是用户量。

而是：

---

# 目标：

10 个视频。

生成 10 个高质量案例。

发圈子。

有人愿意付费。

即可。

---

# 十、V2 才考虑的内容

V1 验证后再说。

---

# 后续可能方向

* 视频知识库
* 概念关系图谱
* 搜索
* AI 问答
* 多语言
* 小红书切片
* PDF 导出
* PPT 导出
* 自动发布
* SaaS

---

# 十一、当前真正目标

不是：

“做一个 AI 产品。”

而是：

# “做一个稳定的 AI 内容编译流水线。”

这个思维非常重要。
