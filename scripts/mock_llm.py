"""本地 mock LLM（OpenAI 兼容）：批次 4 冒烟用，真 key 上线后弃用。

协议应答：分隔符批翻 → 逐段回「{原文}·中文」（保留数字/占位符/字母词，
必含中文字符，可过保真质检）；单条重译 → 纯文本。
启动：uv run python scripts/mock_llm.py [port]   # 纯标准库，零依赖
"""
from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

_SEP_RE = re.compile(r"###(\d+)###\n?(.*?)(?=###\d+###|$)", re.S)
_SPEC_RE = re.compile(r"OCR 识别任务配置生成器")
_FIELDS_RE = re.compile(r"字段只能是：(\[.*?\])")


def _zh(text: str) -> str:
    return f"{text}·中文" if text.strip() else text

_SPEC_JSON = json.dumps({
    "task_spec": {"fields": ["标题", "日期", "金额"], "record_mode": "page",
                  "rules": "金额两位小数；缺席填未见", "template": "你是文档识别专家",
                  "example": {"标题": "示例", "日期": "2026-01-01", "金额": "100.00"}},
    "postprocess": [{"name": "smoke", "code": "def transform_page(records, ctx):\n"
                     "    return records"}],
    "view_spec": {"name": "冒烟视图", "columns": ["标题", "金额"],
                  "group": {"mode": "record"},
                  "aggregates": [{"column": "标题", "op": "first_value", "field": "标题"},
                                 {"column": "金额", "op": "join_values", "field": "金额"}]},
}, ensure_ascii=False)


def _vl_answer(text: str) -> str:
    if _SPEC_RE.search(text):
        return _SPEC_JSON
    match = _FIELDS_RE.search(text)
    fields = json.loads(match.group(1)) if match else ["内容"]
    record = {f: (f"100.00" if "金额" in f else f"测试{f}") for f in fields}
    return json.dumps([record], ensure_ascii=False)


def _answer(content) -> str:
    if isinstance(content, list):  # VL 多模态消息：取 text 部分
        text = next((p.get("text", "") for p in content if p.get("type") == "text"), "")
        return _vl_answer(text)
    user = str(content)
    if _SPEC_RE.search(user):
        return _SPEC_JSON
    found = {int(m.group(1)): m.group(2) for m in _SEP_RE.finditer(user)}
    if found:
        return "\n".join(f"###{k}###\n{_zh(v.strip())}" for k, v in sorted(found.items()))
    src = user.split("Source:")[-1].strip() or user
    return _zh(src)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        user = body.get("messages", [{}])[-1].get("content", "")
        resp = {
            "id": "mock", "object": "chat.completion", "model": body.get("model", "mock"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": _answer(user)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
        payload = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # 静默
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), Handler).serve_forever()
