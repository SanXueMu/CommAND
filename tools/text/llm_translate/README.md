# text.llm.translate

纯翻译工具：文本分段数组输入，逐段调用 LLM 翻译，输出译文分段数组。Translee 翻译能力的零耦合拆分体。

## 机制（全部内化，对管线零耦合）

| 机制 | 说明 |
|------|------|
| 编号直存 | 分段编号随原文送入 LLM，译文按编号回填，杜绝串段 |
| 三路线 | 分隔符直译 / JSON 结构化 / 逐条兜底，按段数自动选路 |
| 熔断 | 连续失败达阈值即停，不烧 token 不拖队列 |
| 质检重译 | 数字保真校验不过自动重译（环内消化，不外溢管线） |
| 字典缓存 | 重复段落命中缓存直接复用，跳过 LLM |

## 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `segments` | `string[]` | 待翻译文本分段 |
| `target_lang` | `string` | 目标语言 |
| `source_lang` | `string` | 源语言（可选，缺省自动检测） |

## 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `translations` | `string[]` | 与输入分段一一对应 |
| `review_flags` | `string[]` | 需人工复核的段落标记；非空时 CommWEB 表格行自动 ⚠️ 高亮 |

## 管线接线

```json
{ "tool": "text.llm.translate",
  "input": { "segments": "{{ prev.segments }}", "target_lang": "en" } }
```
