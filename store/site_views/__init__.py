"""站点视图声明目录（协议 v3）：一域一文件，本文件聚合下发。

纯壳准则：业务声明只允许存在于 CommAND（业务容器），以数据形式经 /meta/site
下发给 CommWEB；CommWEB 代码内零业务内容。会员定制页面 = 改对应域文件，
重注册后热生效（拉取刷新）。可用模板清单（list.panel / sidebar.filter /
flow.lifeflow）见 CommWEB protocol/slotTemplates.tsx 注册表——声明只能引用
已注册模板名，未知模板前端降级占位不报错。
"""

from __future__ import annotations

from store.site_views.tools import TOOLS_VIEW
from store.site_views.flows import FLOWS_VIEW
from store.site_views.tasks import TASKS_VIEW
from store.site_views.workspace import WORKSPACE_VIEW
from store.site_views.settings import SETTINGS_VIEW
from store.site_views.ocr import OCR_VIEW
from store.site_views.templates import TEMPLATES_VIEW
from store.site_views.translate import TRANSLATE_VIEW

BUILTIN_SITE_VIEWS: list[dict] = sorted(
    [
        TOOLS_VIEW,
        FLOWS_VIEW,
        TASKS_VIEW,
        WORKSPACE_VIEW,
        SETTINGS_VIEW,
        OCR_VIEW,
        TEMPLATES_VIEW,
        TRANSLATE_VIEW,
    ],
    key=lambda v: v["sort"],
)
