# 协议 v3 槽位声明指南（site_views/）

会员用本目录声明页面 UI：**一域一文件**，改文件 → 重注册 seed → `/meta/site`
下发 → CommWEB 槽位渲染器按声明组装页面，**前端零发版**（拉取刷新热生效）。

## 机制

```
site_views/<域>.py  →  seed(lifespan)  →  PG site_views.props(JSONB)
                    →  GET /meta/site  →  CommWEB slotsOf(props) → SlotRenderer
```

- `props.slots` 嵌套在视图声明内，无需迁移；无 `slots` 的视图走前端内置形态（v2 兼容）。
- 未知模板名 / 非法 props：前端**降级占位卡**，不报错不白屏。
- 已落地域：tools / flows / tasks（sidebar + list 双槽）；detail 弹窗与动作
  （打开详情、发起运行）为前端内置语义，暂不进声明。

## 页眉渲染模型（`props.nav`，可选）

声明视图在页眉里怎么出现。缺省 = `tab`（平铺主导航项）；`nav` 为**向后兼容字段**，
老 CommWEB 忽略它、新 CommWEB 据此渲染。

| `nav.kind` | 页眉形态 | 伴随字段 |
|------|------|------|
| `tab`（缺省） | 主导航平铺项，链接到该视图路由 | — |
| `menu` | 主导航下拉父项（点击出下拉，不跳转） | `props.defaultLabel`：下拉首项（父视图自身）文案 |
| `child` | 归入某 `menu` 的下拉里 | `group`：父项视图 id；`label`：下拉文案（缺省用 title） |
| `header` | 页眉右侧状态栏功能区（如「设置」下拉） | `label`；`order`（小的在前，同一宿主内排序） |
| `hidden` | 不占导航；**路由仍注册**，可被 `openView` 当弹窗面板调起 | — |

```python
"props": {"nav": {"kind": "child", "group": "work", "label": "翻译工作台"}}
```

约束（`tests/test_site_manifest.py::test_builtin_nav_model_is_coherent` 静态校验）：
`kind` 合法；`child.group` 必须指向存在的 `menu` 项且带 `label`；`menu` 必须给
`defaultLabel`；`header` 必须给 `label`。**拼错 group 名会让整条视图在页眉里消失**——
这正是该测试存在的理由。

## 模板清单（CommWEB 注册表，只能引用以下模板名）

### `list.panel` — 列表面板（DataListPanel 包装）

| prop | 类型 | 说明 |
|------|------|------|
| `layout` | `"card"` \| `"row"` | 卡片 / 行形态 |
| `renderer` | string | 行/卡渲染器名（见下） |
| `searchPlaceholder` | string | 搜索框占位文案 |
| `emptyText` | string | 空态文案 |
| `pagination` | `false` \| `{pageSize: number}` | 分页 |
| `density` | `"default"` \| `"compact"` | 行密度 |
| `bordered` | boolean | 边框 |

### `sidebar.filter` — 筛选侧栏（FilterSidebar 包装）

| prop | 类型 | 说明 |
|------|------|------|
| `width` | number | 侧栏宽度 px |
| `bordered` | boolean | 边框 |

侧栏分组数据由页面壳组装（tools=两级目录 / flows=流类型 / tasks=任务归类）。

### `flow.lifeflow` — 生命周期流条（LifeFlow 包装，预置）

| prop | 类型 | 说明 |
|------|------|------|
| `direction` | `"horizontal"` \| `"vertical"` | 方向 |

## 行/卡渲染器（`renderer` 可选值）

`tool-card` / `tool-row`（工具）、`flow-card` / `flow-row`（流）、
`task-card` / `task-row`（任务）。未注册名降级为默认行渲染。

## data 声明（可选，slot 级）

```python
"data": {"path": "/ocr/templates", "params": {"enabled": True}, "staleTime": 30}
```

约束：仅 `GET`；`path` 必须以 `/` 开头、禁外部 URL 与路径穿越（`..` / `//`）；
`params` 仅 string/number/boolean。props 全树**禁函数与组件引用**（安全白名单）。

## 示例

见 `flows.py`（最简完整示例：sidebar + list 双槽 + row 渲染器）。
