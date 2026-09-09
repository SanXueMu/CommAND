# tools/ — 小工具落位区

每目录一工具，目录名即 `<域>/<工具名>`：

```
tools/
└── <域>/<工具名>/
    ├── tool.toml              # Manifest：户口（必填）
    ├── input.schema.json      # JSON Schema 2020-12（可内联进 tool.toml）
    ├── output.schema.json
    └── main.py                # 可执行体（任意语言，随 runtime.kind 而定）
```

- `tool.id` 必须为点分三段 `<域>.<对象>.<动作>`（如 `text.llm.translate`），且与目录路径一致；
- 注册方式：`uv run main.py register` 或 `POST /api/tools/scan`（含协议合规性检查，失败明细返回，不阻塞其他工具）。

协议全文见《CommAND 架构蓝图》第二章：Tool Protocol v1。
