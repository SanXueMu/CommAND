"""CommOCR 内置任务模板原样拷贝（来源 commocr/server/config/builtin_templates.py，2026-09-05 定格版）。仅注册脚本 scripts/register_ocr_flows.py 使用，运行时零依赖。"""
"""内置任务模版：识别发票凭证 + 识别历史合同 + 识别决算审定表（2026-09-05 定格）。

- 识别发票凭证：2001 年 4-12 月实战口径（backups/task_v4 提示词）+
  后处理钩子——钩子源码由 server 核心 2026-09-04 解耦时整体迁入
  （原 validation.py 金额函数 + pipeline.py 页级业务块，行为逐字保留，
  等价性由 tests/test_hooks.py 对照 tests/fixtures/voucher_golden.json 锁定）。
- 识别历史合同：杨通佳/廖道蓉批次实战提示词（三线索字段，配合合同视图）。
- 识别决算审定表：中国铁塔川决批次逐站明细表（每页多条记录 + 合计行），
  lenient_fields 宽松规整应对 2017→2022 跨年列漂移；钩子做金额归一与勾稽校验，
  配合「决算审定表视图（内置）」（group.mode=record 逐记录一行）。

模板库（templates.json）只作首次建库种子，此后增删改内置不再自动同步（恢复出厂=删 templates.json）。
"""

VOUCHER_POSTPROCESS_CODE = '''
"""凭证页级后处理：金额归一 → 借贷/大写三方校验（不平写备注）
→ 合计大写清洗 → 大写空缺程序换算兜底。零 API 成本。"""

import re as _re  # 钩子命名空间已预置 re/json/math，此行仅为兼容独立运行

_CN_DIGITS = {
    "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "零": 0, "〇": 0,
}
_CN_SECTION_UNITS = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}
_CN_MAGNITUDES = {"万": 10_000, "亿": 100_000_000}
_CN_NOISE = set("人民币（()）:： ,，.。￥¥")


def parse_cn_amount(text):
    """中文大写金额 → 数值（float，保留两位）；无法可靠解析返回 None。"""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    s_nocomma = s.replace(",", "").replace("，", "")
    m = _re.search(r"\\d[\\d.]*", s_nocomma)
    has_cn = any(ch in _CN_DIGITS or ch in _CN_SECTION_UNITS or ch in _CN_MAGNITUDES
                 or ch in ("元", "圆", "角", "分") for ch in s)
    if m and not has_cn:
        digits = "".join(ch for ch in m.group(0) if ch.isdigit())
        if digits:
            norm = normalize_amount(digits)
            try:
                return float(norm)
            except ValueError:
                return None
    for ch in _CN_NOISE:
        s = s.replace(ch, "")
    if not s:
        return None

    total = 0
    section = 0
    cur = None
    yuan = None
    jiao = fen = None

    def _flush_yuan():
        return total + section + (cur or 0)

    for ch in s:
        if ch in _CN_DIGITS:
            cur = _CN_DIGITS[ch]
        elif ch in _CN_SECTION_UNITS:
            section += (cur if cur is not None else 1) * _CN_SECTION_UNITS[ch]
            cur = None
        elif ch in _CN_MAGNITUDES:
            mag = _CN_MAGNITUDES[ch]
            if mag == 10_000:
                total = (total + section + (cur or 0)) * mag
            else:
                total = (total + section + (cur or 0)) * mag
            section = 0
            cur = None
        elif ch in ("元", "圆"):
            yuan = _flush_yuan()
            total = section = 0
            cur = None
        elif ch == "角":
            jiao = cur if cur is not None else 0
            cur = None
        elif ch == "分":
            fen = cur if cur is not None else 0
            cur = None
        elif ch in ("整", "正"):
            continue
        else:
            return None
    if yuan is None:
        yuan = _flush_yuan()
    value = yuan + (jiao or 0) / 10 + (fen or 0) / 100
    return round(value, 2) if value else 0.0


def _to_cents(text):
    """金额字符串 → 整数分；空/非法返回 None。"""
    if text is None:
        return None
    s = str(text).strip().replace(",", "").replace("，", "")
    if not s:
        return None
    try:
        return int(round(float(s) * 100))
    except ValueError:
        return None


def normalize_amount(text):
    """金额原始数字串 → 两位小数金额：小数点固定在倒数第 2 位之前。

    "1140000" → "11400.00"；"9040" → "90.40"；"42" → "0.42"。
    空 → ""；含无法解析的杂字符时原样返回，交由大写校验兜底标记。
    """
    if text is None:
        return ""
    s = str(text).strip().replace(",", "").replace("，", "")
    if not s:
        return ""
    if s.isdigit():
        if len(s) <= 2:
            return f"{int(s) / 100:.2f}"
        return f"{s[:-2]}.{s[-2:]}"
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return str(text).strip()


def _fmt_cents(cents):
    return f"{cents / 100:.2f}"


def page_amount_check(records):
    """对一页分录做程序校验：借方合计 = 贷方合计 = 合计大写。"""
    borrow = credit = 0
    anchors = []
    for record in records:
        b = _to_cents(record.get("借方金额"))
        c = _to_cents(record.get("贷方金额"))
        if b is not None:
            borrow += b
        if c is not None:
            credit += c
        a = parse_cn_amount(record.get("合计大写"))
        if a is not None:
            anchors.append(int(round(a * 100)))
    if anchors and len(set(anchors)) == 1:
        anchor = anchors[0]
    elif anchors:
        anchor = "CONFLICT"
    else:
        anchor = None

    balanced = borrow == credit
    anchor_ok = anchor is None or (anchor != "CONFLICT" and anchor == borrow == credit)

    if balanced and anchor_ok:
        return {"ok": True, "borrow": borrow, "credit": credit, "anchor": anchor, "note": ""}

    parts = [f"校验不平：借{_fmt_cents(borrow)} 贷{_fmt_cents(credit)}"]
    if anchor == "CONFLICT":
        parts.append("合计大写各行不一致(疑串行)")
    elif anchor is not None:
        parts.append(f"合计大写{_fmt_cents(anchor)}")
    return {"ok": False, "borrow": borrow, "credit": credit, "anchor": anchor,
            "note": "，".join(parts)}


_CN_D = "零壹贰叁肆伍陆柒捌玖"


def _four_digits(n):
    """0-9999 → 大写段（不带段字）：3000→叁仟, 9040→玖仟零肆拾, 1005→壹仟零伍, 0→""。"""
    out = []
    for pos in (3, 2, 1, 0):
        d = n // 10 ** pos % 10
        if d:
            out.append(_CN_D[d] + ["", "拾", "佰", "仟"][pos])
        elif out and not out[-1].startswith("零"):
            out.append("零")
    res = ""
    for seg in out:
        if seg == "零" and (not res or res.endswith("零")):
            continue
        res += seg
    return res.rstrip("零")


def to_cn_upper(amount):
    """数值 → 人民币大写：735.0→柒佰叁拾伍元整, 3105.92→叁仟壹佰零伍元玖角贰分。"""
    cents = round(abs(amount) * 100)
    yuan, jiao, fen = cents // 100, cents // 10 % 10, cents % 10
    if yuan == 0 and jiao == 0 and fen == 0:
        return "零元整"
    secs = []
    n = yuan
    while n > 0:
        secs.append(n % 10000)
        n //= 10000
    int_str = ""
    for si in range(len(secs) - 1, -1, -1):
        seg = _four_digits(secs[si])
        if seg:
            int_str += seg + ["", "万", "亿", "万亿"][si]
        elif int_str and any(_four_digits(secs[k]) for k in range(si)):
            int_str += "零"
    if int_str.endswith("零"):
        int_str = int_str.rstrip("零")
    tail = int_str + "元" if int_str else ""
    if fen == 0 and jiao == 0:
        tail += "整"
    elif fen == 0:
        tail += _CN_D[jiao] + "角整"
    else:
        if jiao > 0:
            tail += _CN_D[jiao] + "角"
        elif int_str:
            tail += "零"
        tail += _CN_D[fen] + "分"
    return tail


def transform_page(records, ctx):
    # 1) 金额归一：模型输出的原始数字串 → 定点两位小数（幂等，兼容旧格式）
    for record in records:
        for field in ("借方金额", "贷方金额"):
            record[field] = normalize_amount(record.get(field))

    # 2) 程序校验：借方合计 = 贷方合计 = 合计大写；不平则写备注交人工核查
    #    「合计」行（科目汇总表）不计入借贷统计，仅作合计参考
    summary_rows = [r for r in records if str(r.get("总账科目") or "").strip() == "合计"]
    body_rows = [r for r in records if str(r.get("总账科目") or "").strip() != "合计"]
    verdict = page_amount_check(body_rows)
    if not verdict["ok"]:
        borrow = f"{verdict['borrow'] / 100:.2f}"
        credit = f"{verdict['credit'] / 100:.2f}"
        if summary_rows:
            s_borrow = sum(_to_cents(str(r.get("借方金额") or "")) for r in summary_rows)
            s_credit = sum(_to_cents(str(r.get("贷方金额") or "")) for r in summary_rows)
            same = "，源表合计数相同" if s_borrow == s_credit else ""
            note = (f"校验不平，借：{borrow}，贷：{credit}，"
                    f"合计：{s_borrow / 100:.2f}/{s_credit / 100:.2f}{same}，需人工核查。")
        elif isinstance(verdict["anchor"], int) and verdict["anchor"] in (verdict["borrow"], verdict["credit"]):
            note = (f"校验不平，借：{borrow}，贷：{credit}，"
                    f"合计：{verdict['anchor'] / 100:.2f}，需人工核查。")
        elif isinstance(verdict["anchor"], int):
            dx = f"{verdict['anchor'] / 100:.2f}"
            total = f"{max(verdict['borrow'], verdict['credit']) / 100:.2f}"
            note = (f"校验不平且合计识别有歧义，借：{borrow}，贷：{credit}，"
                    f"合计大写：{dx}，合计：{total}，需人工核查")
        else:
            note = f"校验不平，借：{borrow}，贷：{credit}，需人工核查。"
        review = ctx.get("review")
        if review:
            review(verdict["note"])
        for record in records:
            record["备注"] = note

    # 3) 兜底①：合计大写只保留汉字形态；含数字/￥符号一律视为误抄，清空
    for record in records:
        dx = str(record.get("合计大写") or "")
        if dx and any(ch.isdigit() or ch in "￥¥" for ch in dx):
            record["合计大写"] = ""

    # 4) 兜底②：纸面没有手写大写（大写字段为空）时，
    #    用合计数字程序换算人民币大写填入（锚口径与备注一致）
    if summary_rows:
        s_borrow = sum(_to_cents(str(r.get("借方金额") or "")) for r in summary_rows)
        s_credit = sum(_to_cents(str(r.get("贷方金额") or "")) for r in summary_rows)
        anchor_cents = s_borrow if s_borrow == s_credit else max(s_borrow, s_credit)
    else:
        anchor_cents = (verdict["borrow"] if verdict["borrow"] == verdict["credit"]
                        else max(verdict["borrow"], verdict["credit"]))
    if anchor_cents > 0 and not any(str(r.get("合计大写") or "").strip() for r in records):
        dx_value = to_cn_upper(anchor_cents / 100)
        for record in records:
            record["合计大写"] = dx_value
    return records
'''.strip()


VOUCHER_FIELDS = [
    "日期", "凭证类别", "凭证号", "摘要", "总账科目", "明细科目",
    "借方金额", "贷方金额", "附件", "领款人", "合计大写", "备注",
]

VOUCHER_RULES = [
    '- 通用：所有字段值都必须是字符串；没有内容时填空字符串 ""。同一张凭证的日期、凭证类别、凭证号要填到每一条分录中。借贷平衡由程序校验，你不需要自己算合计，严禁为凑平删行、并行或改数字。',
    '- 【区域一：表头】凭证左上角日期填"日期"；抬头类别字（收/付/转，或"收款凭证/付款凭证/转账凭证"）取一个代表字填"凭证类别"；其旁的编号（如"总37号"）填"凭证号"。年份注意 0 与 2 的位置：2000 严禁读成 2020 或 2002。月份笔形易混：1、7、11 仔细区分；"元月"就是 1 月，照抄"元月"或写"1月"均可。',
    '- 【区域二：表体行——摘要+总账科目+明细科目】严格按水平行对齐：摘要、总账科目、明细科目取自凭证表格的同一水平行，第 n 行摘要/明细科目只属于第 n 行的分录，该行空白就填 ""。现金/银行存款行的摘要栏通常空白，这是正常形态——摘要写在业务行（对方科目行），货币资金行摘要栏无手写文字就填 ""，严禁把业务行的摘要分配给它。摘要是否填写的唯一依据是该行摘要格内有无手写字迹，与科目类型无关：现金/银行存款行写了摘要就照抄在该行，业务行摘要格空白才填 ""。摘要逐行判断：只转写与该行同一水平线上的摘要文字，该行摘要带内无字就填 ""；手迹跨行书写时归属字迹中心所在的行。摘要栏完全空白的表体行也是独立分录，必须单独输出一条，严禁与相邻行合并。严禁把一行摘要与另一行的科目/金额拼到同一条分录，严禁把摘要文字里的词填进明细科目。',
    '- 【区域三：表体借贷金额栏】金额只输出纯数字串，禁止输出小数点、逗号、货币符号或大写；没有金额填 ""。金额栏为分位格（格上方印有 佰拾万仟佰拾元角分 位值表头），把写有数字的格子从左到右全部照抄成一个纯数字串：一格一数、一格不落，最左侧空白格忽略，小数点位置由程序统一处理，严禁自行判断数量级或补小数点。角分格写的 0 也必须照抄（格子依次为 9、0、4、0 时输出 "9040"，严禁漏抄末尾的 0）；栏内的印刷小数点/分隔圆点不是数字，跳过不抄（格子依次为 5、5、5、·、0、0 时输出 "55500"，严禁把圆点当成 1 抄成 "555100"）。手写金额常连笔，以下形近数字务必分辨关键特征后再抄：2 与 0——2 的尾部有弯钩、圈不闭合，0 是闭合椭圆无尾巴，严禁把带尾巴的 2 抄成 0；3 与 2——3 有两个上半圈，2 只有一个弯；9 与 0——9 有下垂尾巴，0 无尾；7 与 1——7 顶部有横，1 是纯竖笔。借贷方向看数字物理写在借方还是贷方金额栏，严禁凭科目性质猜测。',
    '- 【区域四：版面转分录】这批老式收款/付款/转账凭证金额只填一行，必须转成规范借贷双行分录——收款凭证：第一行借 现金/银行存款（填"总账科目"），第二行贷 对方科目；付款凭证：第一行借 对方科目，第二行贷 现金/银行存款；转账凭证按科目与金额栏实际位置。对方科目是一级科目的填"总账科目"，其后/下方紧跟的人名或细目才是"明细科目"；现金、银行存款行的"明细科目"填 ""。每行分录只能有一个科目及其明细，严禁输出科目混排的版面转写行。科目/金额栏有几条物理行就输出几条分录；某行只能认出金额或科目之一时也要照常输出并在"备注"说明。',
    '- 【区域五：合计人民币区】凭证下方合计行内"合计人民币（大写）"栏：判断该栏的唯一依据是栏内有无手写汉字字迹。栏内有手写大写汉字时原样转写进"合计大写"字段（如"叁仟元正"、"伍仟肆佰肆拾元肆角肆分"），不要换算成数字、不要改写用字；栏内没有手写大写汉字时一律填 ""。合计数字格里的数字与"合计大写"字段毫无关系——即使大写栏空白、旁边的合计数字格填了数字，"合计大写"也只能填 ""，严禁把数字格的数字照抄过来、严禁把数字换算成大写汉字——换算等于编造。"合计大写"字段只接受中文汉字（壹贰叁肆伍陆柒捌玖拾佰仟万亿、元角分、整正零），阿拉伯数字或￥符号一律不是大写内容。大写位值字 佰/仟/万 形近注意分辨：佰是人旁百、仟是人旁千、万是独立字，严禁把佰读成仟或万；角分位前的"拾"只在纸面真有时转写，严禁自行插入或漏抄。每条分录行都填同一个值。',
    '- 【区域六：最下两行+最后列】凭证倒数第二行右侧印有"领款人"（收款凭证印作"缴款人"）：只看印刷标签右侧紧邻的填写格，格内有手写签名填该名字；红色印章一律不填（无论盖在哪里）；倒数第一行是财务主管/记帐/审核/出纳等各类人的签字行，整行内容不需要识别、严禁从中取名字。摘要、明细科目里出现的人名严禁填入领款人；格内空白或痕迹难辨时填 ""。最右列为"附件"栏：原始单据张数，可能竖排书写（数字在上、量词"张"在下），重点辨认竖排数字，原样填写（如"3张"或"叁张"）；竖排模糊时尽量按笔画推断并在"备注"说明，栏空白填 ""。',
    '- 【区域七：科目汇总表页（左右双栏）】若整页是一张科目汇总表（通常无摘要列、无领款人栏，表格分左右两个区域，每个区域各有自己的科目名称列和借方/贷方金额栏）：逐栏逐行转写——先左区从上到下、再右区从上到下，每行输出一条分录：科目名称填"总账科目"，金额照抄进对应的借方或贷方金额栏。每个科目的借方、贷方两列金额格都可能填了数字，两列各自照抄、一列都不能丢。日期填表头日期，摘要、明细科目、领款人填 ""。严禁只识别半边区域、严禁把左右两栏的行串到一起。',
    '- "备注"字段：仅当某字段识别不确定、字迹模糊或疑似串行时简要说明（如"领款人字迹模糊"）；全部清晰则填 ""。不要在此写借贷平衡情况。',
]

VOUCHER_EXAMPLE = [
    {"日期": "2000年1月15日", "凭证类别": "付", "凭证号": "总37号", "摘要": "",
     "总账科目": "现金", "明细科目": "", "借方金额": "", "贷方金额": "85000",
     "附件": "2张", "领款人": "张三", "合计大写": "捌佰伍拾元整", "备注": ""},
    {"日期": "2000年1月15日", "凭证类别": "付", "凭证号": "总37号", "摘要": "付办公用品款",
     "总账科目": "管理费用", "明细科目": "办公用品", "借方金额": "85000", "贷方金额": "",
     "附件": "2张", "领款人": "张三", "合计大写": "捌佰伍拾元整", "备注": ""},
    {"日期": "2000年1月18日", "凭证类别": "收", "凭证号": "总02号", "摘要": "存现 现金交款单.0121719#",
     "总账科目": "现金", "明细科目": "", "借方金额": "1000000", "贷方金额": "",
     "附件": "1张", "领款人": "", "合计大写": "", "备注": ""},
    {"日期": "2000年1月18日", "凭证类别": "收", "凭证号": "总02号", "摘要": "",
     "总账科目": "银行存款", "明细科目": "", "借方金额": "", "贷方金额": "1000000",
     "附件": "1张", "领款人": "", "合计大写": "", "备注": ""},
]

VOUCHER_TEMPLATE = (
    "请识别凭证图片中的会计分录，并严格按照以下要求输出：\n"
    "1. 只输出合法的 JSON 数组，不要输出 Markdown 代码块、解释或其他文字。\n"
    "2. 数组中的每条记录必须只包含以下 {field_count} 个字段，字段名必须完全一致：\n"
    "   {fields}。\n"
    "{rules}\n"
    "\n"
    "输出结构示例：\n"
    "{example}"
)

CONTRACT_FIELDS = ["合同名称线索", "关键人物出现方式", "类型线索"]

CONTRACT_TEMPLATE = (
    "请提取图片中（合同扫描件单页）的客观线索，严格按照以下要求输出：\n"
    "1. 只输出合法的 JSON 数组，不要输出 Markdown 代码块、解释或其他文字。\n"
    '2. 数组中的每条记录必须只包含以下 3 个字段，字段名必须完全一致：\n'
    '   "合同名称线索"、"关键人物出现方式"、"类型线索"。\n'
    "3. 关键人物：廖道蓉；目标类型：「财务收支」「内控建设」。\n"
    "\n"
    "字段规则：\n"
    '- "合同名称线索"：本页可见的合同/文件标题原文；本页无标题（正文页、落款页、骑缝页等）填 "未见"。\n'
    '- "关键人物出现方式"：关键人物在本页的出现方式，多处出现逐条列出用"；"分隔。取值："未出现"（本页未出现）、"法定代表人"（仅以法定代表人、法定责任人身份出现，如落款签字栏）、"项目负责人"、"其他身份：写明具体身份"。同页双重身份（如既为法定代表人又标注项目负责人）时逐条都列出。\n'
    '- "类型线索"：本页出现的「财务收支」或「内控建设」相关表述，摘录原文短语（每条不超过 30 字），多处用"；"分隔；本页无相关内容填 "未见"。\n'
    '- 只记录本页图像中实际可见的文字，不臆造、不推断同义词；"未见"/"未出现"是合法值；所有字段值都必须是非空字符串。\n'
    "\n"
    "输出结构示例：\n"
    '[{"合同名称线索": "某某公司2026年度财务收支审计业务约定书", "关键人物出现方式": "未出现", "类型线索": "审计范围为财务收支的真实性、合法性"}]'
)

SHENBAO_FIELDS = [
    "项目名称", "项目编码", "项目类型", "建设方式",
    "批复概算", "审计调整概算", "实际执行概算",
    "送审金额", "审计调整金额", "审定金额", "备注",
]

SHENBAO_TEMPLATE = (
    "请识别这张中国铁塔项目决算审定表扫描页。页面通常是逐项目明细表格（每行一个项目），"
    "也可能是纯封面页或只有合计行与签字区的末页。请提取表格数据，并严格遵守：\n"
    "1. 只输出合法的 JSON 数组，不要输出 Markdown 代码块、注释或任何解释文字。\n"
    "2. 数组中每条记录对应表格中的一行，必须只包含以下 {field_count} 个字段，"
    "字段名必须完全一致：{fields}。\n"
    "{rules}\n"
    "\n"
    "输出结构示例：\n"
    "{example}"
)

SHENBAO_RULES = [
    '所有字段值都必须是字符串；单元格为空、"—"、"-"或无法辨认时填 ""；只照抄纸面可见内容，不臆造、不推算。',
    '"项目名称"：本行项目/工程名称原文（各年度版本列名可能为"项目名称""工程名称"等，按语义对应）；合计行填 "合计"。',
    '"项目编码"：项目编码/项目代码列原文（字母数字混合照抄）；空白填 ""。',
    '"项目类型"：项目分类原文（如 新建/改造/扩容/搬迁 等）；空白填 ""。',
    '"建设方式"：建设方式列原文（如 自建/合建/共建 等）；空白填 ""。',
    '"批复概算""审计调整概算""实际执行概算"：概算三列数值，只输出阿拉伯数字与小数点，'
    '去掉千分位逗号、空格和货币单位（如 "250,000.00" → "250000.00"）；空白或"—"填 ""。',
    '"送审金额""审计调整金额""审定金额"：金额三列数值，只输出阿拉伯数字与小数点，'
    '去掉千分位逗号、空格和货币单位；"审计调整金额"为负数时保留负号照抄（如 "-433.77"）；空白或"—"填 ""。',
    '"备注"：纸面如有备注/说明列则照抄，无备注列填 ""（系统校验标记会写在此字段，模型无须处理）。',
    '单元格跨行合并时，合并值只归属可见的第一行，其余行该字段填 ""，不要复制。',
    '"项目名称"等文字列在单元格内折行时仍是同一行记录，以表格横线划分行，'
    '不要把折行文字拆成多条记录；金额与文字必须取自同一表格行，严禁跨行拼接。',
    "一页含多个表格分区时，按行序依次输出全部分区数据行。",
    '末页只有合计行与签字区（送审单位/审计单位/审定单位、日期、复核人、制表人等）时，'
    '输出一条合计记录："项目名称"填 "合计"，各行金额列照抄合计值，其余填 ""；完全没有表格数据的页面输出 []。',
]

SHENBAO_EXAMPLE = [
    {"项目名称": "中国铁塔XX市州分公司2015年昭觉百货公司小区新建室分项目", "项目编码": "5100002015A0012345",
     "项目类型": "新建", "建设方式": "自建",
     "批复概算": "250000.00", "审计调整概算": "250000.00", "实际执行概算": "238000.00",
     "送审金额": "21165.73", "审计调整金额": "-433.77", "审定金额": "20731.96", "备注": ""},
    {"项目名称": "合计", "项目编码": "", "项目类型": "", "建设方式": "",
     "批复概算": "", "审计调整概算": "", "实际执行概算": "",
     "送审金额": "610173.68", "审计调整金额": "-12500.00", "审定金额": "597673.68", "备注": ""},
]

SHENBAO_POSTPROCESS_CODE = '''
"""审定表页级后处理：金额归一 → 行级勾稽（|审计调整|≈|送审-审定|，符号无关）→ 页内合计校验。

差值写备注前缀并触发 review 提示；零 API 成本。
跨页文件级合计不在页级钩子能力内，由导出脚本兜底。
"""

import re as _re  # 钩子命名空间已预置 re/json/math，此行仅为兼容独立运行

_TOL = 0.05
_AMOUNT_COLS = ("批复概算", "审计调整概算", "实际执行概算",
                "送审金额", "审计调整金额", "审定金额")
_EMPTY_CELLS = {"", "—", "-", "–", "/", "－", "——"}


def _parse_amount(text):
    """金额字符串 → float；空/占位/非法返回 None。"""
    if text is None:
        return None
    s = str(text).strip().replace(",", "").replace("，", "").replace("元", "").strip()
    if s in _EMPTY_CELLS:
        return None
    try:
        return float(s)
    except ValueError:
        m = _re.search(r"\\d+(?:\\.\\d+)?", s)
        return float(m.group(0)) if m else None


def _norm_amount(text):
    """金额单元格 → 两位小数字符串；空/占位 → ""；无法解析原样返回。"""
    if text is None:
        return ""
    s = str(text).strip().replace(",", "").replace("，", "").replace("元", "").strip()
    if s in _EMPTY_CELLS:
        return ""
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return str(text).strip()


def _append_note(record, note):
    old = str(record.get("备注", "") or "").strip()
    record["备注"] = f"{old}；{note}" if old else note


def _is_total_row(rec):
    name = str(rec.get("项目名称", "") or "").strip()
    return name in {"合计", "总计", "小计"} or (len(name) <= 6 and name.endswith("合计"))


def transform_page(records, ctx):
    page = ctx.get("page", "?")
    review = ctx.get("review")
    # 1) 金额归一：六金额列两位小数
    for rec in records:
        for col in _AMOUNT_COLS:
            rec[col] = _norm_amount(rec.get(col))
    # 2) 行级勾稽：|审计调整金额| ≈ |送审金额 - 审定金额|（符号无关）
    for rec in records:
        ss = _parse_amount(rec.get("送审金额"))
        sd = _parse_amount(rec.get("审定金额"))
        tz = _parse_amount(rec.get("审计调整金额"))
        if None in (ss, sd, tz):
            continue
        diff = abs(tz) - abs(ss - sd)
        if abs(diff) > _TOL:
            note = f"勾稽差{diff:+.2f}"
            _append_note(rec, note)
            if review:
                review(f"第{page}页 {rec.get('项目名称', '?')[:20]} {note}")
    # 3) 页内合计校验：本页同时出现合计行与明细行时比对金额三列
    details = [r for r in records if not _is_total_row(r)]
    totals = [r for r in records if _is_total_row(r)]
    if totals and details:
        for col in ("送审金额", "审计调整金额", "审定金额"):
            tv = _parse_amount(totals[0].get(col))
            if tv is None:
                continue
            s = sum(_parse_amount(r.get(col)) or 0.0 for r in details)
            diff = tv - s
            if abs(diff) > _TOL:
                note = f"合计{col}差{diff:+.2f}"
                _append_note(totals[0], note)
                if review:
                    review(f"第{page}页 {note}")
    return records
'''

BUILTIN_TASK_TEMPLATES = [
    {
        "id": "builtin-voucher",
        "name": "识别发票凭证",
        "model": None,
        "fields": list(VOUCHER_FIELDS),
        "prompt": {
            "template": VOUCHER_TEMPLATE,
            "rules": list(VOUCHER_RULES),
            "example": [dict(item) for item in VOUCHER_EXAMPLE],
        },
        "input_path": "",
        "output_path": "",
        "postprocess": [
            {"name": "凭证金额校验与大写兜底", "stage": "page",
             "code": VOUCHER_POSTPROCESS_CODE},
        ],
        "created_at": "",
        "updated_at": "",
    },
    {
        "id": "builtin-contract",
        "name": "识别历史合同",
        "model": None,
        "fields": list(CONTRACT_FIELDS),
        "prompt": {"template": CONTRACT_TEMPLATE, "rules": None, "example": None},
        "input_path": "",
        "output_path": "",
        "postprocess": [],
        "created_at": "",
        "updated_at": "",
    },
    {
        "id": "builtin-shenbao",
        "name": "识别决算审定表",
        "model": None,
        "fields": list(SHENBAO_FIELDS),
        "lenient_fields": True,
        "prompt": {
            "template": SHENBAO_TEMPLATE,
            "rules": list(SHENBAO_RULES),
            "example": [dict(item) for item in SHENBAO_EXAMPLE],
        },
        "input_path": "",
        "output_path": "",
        "postprocess": [
            {"name": "审定表金额归一与勾稽校验", "stage": "page",
             "code": SHENBAO_POSTPROCESS_CODE},
        ],
        "created_at": "",
        "updated_at": "",
    },
]
