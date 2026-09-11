"""CommOCR 用户自定义视图移植（源：CommOCR views.json 的 6 个非内置视图）。

由 CommOCR JSON 程序化生成——保留 spec 原样，仅换可读 id 并留存 source_id 溯源。
内置于 ocr_views.py 的 5 个 builtin 视图不在此列。
"""

COMMOCR_USER_VIEWS: list[dict] = [
    {
        "id": "user.blueprint.info",
        "source_id": "894e25fd",
        "name": "平面图信息清单",
        "spec": {
            "name": "平面图信息清单",
            "columns": [
                "文件名",
                "页码",
                "记录类型",
                "图纸名称",
                "图号",
                "公司负责人",
                "日期",
                "说明内容",
                "印章遮挡"
            ],
            "absent_values": [
                "",
                "未见",
                "未出现"
            ],
            "filters": [
                {
                    "field": "记录类型",
                    "op": "contains_any",
                    "value": "",
                    "values": [
                        "图纸信息",
                        "风险提示页"
                    ]
                }
            ],
            "group": {
                "mode": "none",
                "field": "",
                "blank_joins_previous": True,
                "untitled_label": "（起始无标题页）"
            },
            "aggregates": [
                {
                    "column": "文件名",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "页码",
                    "op": "page",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "记录类型",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "图纸名称",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "图号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "公司负责人",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "日期",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "说明内容",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "印章遮挡",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                }
            ],
            "verdict": None,
            "sort": [
                {
                    "column": "文件名",
                    "order": "asc"
                },
                {
                    "column": "页码",
                    "order": "asc"
                }
            ],
            "split": None
        },
    },
    {
        "id": "user.blueprint.table",
        "source_id": "fbcd1352",
        "name": "平面图表格明细",
        "spec": {
            "name": "平面图表格明细",
            "columns": [
                "表格名称",
                "文件名",
                "页码",
                "行号",
                "序号",
                "名称",
                "规格型号",
                "配置",
                "厂家",
                "单位",
                "数量",
                "备注"
            ],
            "absent_values": [
                "",
                "未见",
                "未出现"
            ],
            "filters": [
                {
                    "field": "记录类型",
                    "op": "eq",
                    "value": "表格行",
                    "values": []
                }
            ],
            "group": {
                "mode": "record",
                "field": "",
                "blank_joins_previous": True,
                "untitled_label": "（起始无标题页）"
            },
            "aggregates": [
                {
                    "column": "表格名称",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "文件名",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "页码",
                    "op": "page",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "行号",
                    "op": "first_value",
                    "field": "row_number",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "序号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "名称",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "规格型号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "配置",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "厂家",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单位",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "数量",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "备注",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                }
            ],
            "verdict": None,
            "sort": [
                {
                    "column": "表格名称",
                    "order": "asc"
                },
                {
                    "column": "文件名",
                    "order": "asc"
                },
                {
                    "column": "页码",
                    "order": "asc"
                },
                {
                    "column": "行号",
                    "order": "asc"
                }
            ],
            "split": {
                "field": "表格名称",
                "untitled_label": "(未命名表格)",
                "hide_empty_columns": True
            }
        },
    },
    {
        "id": "user.english.docs",
        "source_id": "41791058",
        "name": "英文单据还原视图",
        "spec": {
            "name": "英文单据还原视图",
            "columns": [
                "文件名",
                "页码",
                "记录类型",
                "单据类型",
                "单据编号",
                "单据日期",
                "条目号",
                "工作内容",
                "数量",
                "单位",
                "单价",
                "金额",
                "合计金额",
                "开具方",
                "接收方",
                "站点编号",
                "站点地址",
                "供应商代码",
                "联系人",
                "联系方式",
                "交货地址",
                "开票地址",
                "交货日期",
                "交货条款",
                "付款条款",
                "保修条款",
                "备注",
                "页数与版本",
                "开具方联系",
                "接收方联系",
                "签署说明",
                "签章情况"
            ],
            "absent_values": [
                "",
                "未见",
                "未出现"
            ],
            "filters": [],
            "group": {
                "mode": "none",
                "field": "",
                "blank_joins_previous": True,
                "untitled_label": "（起始无标题页）"
            },
            "aggregates": [
                {
                    "column": "文件名",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "页码",
                    "op": "page",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "记录类型",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单据类型",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单据编号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单据日期",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "条目号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "工作内容",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "数量",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单位",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单价",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "金额",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "合计金额",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "开具方",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "接收方",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "站点编号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "站点地址",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "供应商代码",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "联系人",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "联系方式",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "交货地址",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "开票地址",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "交货日期",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "交货条款",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "付款条款",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "保修条款",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "备注",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "页数与版本",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "开具方联系",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "接收方联系",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "签署说明",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "签章情况",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                }
            ],
            "verdict": None,
            "sort": [
                {
                    "column": "文件名",
                    "order": "asc"
                },
                {
                    "column": "页码",
                    "order": "asc"
                }
            ],
            "split": None
        },
    },
    {
        "id": "user.contract.table",
        "source_id": "3c502220",
        "name": "09合同表格明细（双Sheet）",
        "spec": {
            "name": "09合同表格明细（双Sheet）",
            "columns": [],
            "absent_values": [
                "",
                "未见",
                "未出现"
            ],
            "filters": [],
            "group": {
                "mode": "record",
                "field": "",
                "blank_joins_previous": True,
                "untitled_label": ""
            },
            "aggregates": [
                {
                    "column": "文件名",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "页码",
                    "op": "page",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "合同类型",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "日期",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "采购单号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "甲方合同编号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "序号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "名称",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "规格型号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单位",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "数量",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "单价",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "金额",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "备注",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                }
            ],
            "verdict": None,
            "sort": [
                {
                    "column": "文件名",
                    "order": "asc"
                },
                {
                    "column": "页码",
                    "order": "asc"
                }
            ],
            "split": {
                "field": "合同类型",
                "untitled_label": "（未识别类型）",
                "hide_empty_columns": True
            }
        },
    },
    {
        "id": "user.risk.list",
        "source_id": "36c0b177",
        "name": "风险提示清单",
        "spec": {
            "name": "风险提示清单",
            "columns": [
                "文件名",
                "页码",
                "序号",
                "名称",
                "说明内容"
            ],
            "absent_values": [
                "",
                "未见",
                "未出现"
            ],
            "filters": [
                {
                    "field": "记录类型",
                    "op": "eq",
                    "value": "风险提示",
                    "values": []
                }
            ],
            "group": {
                "mode": "record",
                "field": "",
                "blank_joins_previous": True,
                "untitled_label": "（起始无标题页）"
            },
            "aggregates": [
                {
                    "column": "文件名",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "页码",
                    "op": "page",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "行号",
                    "op": "first_value",
                    "field": "row_number",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "序号",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "名称",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "说明内容",
                    "op": "first_value",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                }
            ],
            "verdict": None,
            "sort": [
                {
                    "column": "文件名",
                    "order": "asc"
                },
                {
                    "column": "页码",
                    "order": "asc"
                },
                {
                    "column": "行号",
                    "order": "asc"
                }
            ],
            "split": None
        },
    },
    {
        "id": "user.contract.keywords",
        "source_id": "368b2b52",
        "name": "02合同关键词视图",
        "spec": {
            "name": "02合同关键词视图",
            "columns": [
                "合同名称",
                "起始页",
                "结束页",
                "页数",
                "判定",
                "人物证据",
                "类型证据"
            ],
            "absent_values": [
                "",
                "未见",
                "未出现"
            ],
            "filters": [],
            "group": {
                "mode": "value_run",
                "field": "合同名称线索",
                "blank_joins_previous": True,
                "untitled_label": "（起始无标题页）"
            },
            "aggregates": [
                {
                    "column": "合同名称",
                    "op": "group_key",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "起始页",
                    "op": "page_start",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "结束页",
                    "op": "page_end",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "页数",
                    "op": "page_count",
                    "field": "",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "人物证据",
                    "op": "evidence",
                    "field": "关键人物出现方式",
                    "sep": "；",
                    "clip": 40
                },
                {
                    "column": "类型证据",
                    "op": "evidence",
                    "field": "类型线索",
                    "sep": "；",
                    "clip": 40
                }
            ],
            "verdict": {
                "column": "判定",
                "rules": [
                    {
                        "label": "命中",
                        "when": {
                            "all": [
                                {
                                    "field": "关键人物出现方式",
                                    "op": "contains_any",
                                    "value": "",
                                    "values": [
                                        "项目负责人",
                                        "其他身份"
                                    ]
                                },
                                {
                                    "field": "类型线索",
                                    "op": "nonempty",
                                    "value": "",
                                    "values": []
                                }
                            ],
                            "any": []
                        }
                    },
                    {
                        "label": "排除",
                        "when": {
                            "all": [
                                {
                                    "field": "关键人物出现方式",
                                    "op": "nonempty",
                                    "value": "",
                                    "values": []
                                },
                                {
                                    "field": "类型线索",
                                    "op": "nonempty",
                                    "value": "",
                                    "values": []
                                }
                            ],
                            "any": []
                        }
                    }
                ],
                "default": "不匹配"
            },
            "sort": [],
            "split": None
        },
    },
]
