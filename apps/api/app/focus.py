"""争议焦点规则初筛。

不做语义推理：按关键词命中固定规则，返回焦点、双方可能主张、对应法条与
证据清单。所有法条均按法名 + 条号回查数据库原文，查不到即不输出，避免
凭空生成条号。结果仅供律师复核，不构成法律意见。
"""

from app import db

CIVIL_CODE = "中华人民共和国民法典"
INTERPRETATION = "最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释（一）"
CONSTRUCTION_LAW = "中华人民共和国建筑法"

RULES = (
    {
        "focus": "实际施工人身份",
        "triggers": ("实际施工人", "转包", "违法分包", "挂靠", "包工头", "垫资"),
        "claims": {
            "原告": "已实际投入资金、材料与劳务，系实际施工人，有权向发包人主张欠付工程款",
            "被告": "无施工资质、无合同关系，款项已结清或应由合同相对方承担",
        },
        "citations": (
            (INTERPRETATION, "第四十三条"),
            (INTERPRETATION, "第一条"),
            (CIVIL_CODE, "第七百九十一条"),
        ),
        "evidence": (
            ("施工合同或转包协议", ("合同", "协议", "转包")),
            ("实际投入凭证（垫资、材料、人工付款）", ("垫资", "材料", "人工", "转账", "付款")),
            ("竣工验收或交付资料", ("验收", "竣工", "交付")),
            ("发包人欠付金额证据", ("欠付", "未付", "结算", "对账")),
        ),
    },
    {
        "focus": "合同效力",
        "triggers": ("合同无效", "未招标", "中标无效", "资质", "借用资质", "背离中标"),
        "claims": {
            "原告": "合同有效，应按约定结算；即使无效，工程验收合格仍可参照约定主张折价补偿",
            "被告": "合同因违法分包、无资质或规避招标而无效，结算依据不成立",
        },
        "citations": (
            (INTERPRETATION, "第一条"),
            (CIVIL_CODE, "第七百九十一条"),
            (CIVIL_CODE, "第八百零六条"),
        ),
        "evidence": (
            ("招投标文件与中标通知", ("招标", "投标", "中标")),
            ("施工资质证书", ("资质", "许可")),
            ("中标合同与备案合同", ("备案", "中标", "合同")),
            ("进场与履约记录", ("进场", "履行", "开工")),
        ),
    },
    {
        "focus": "结算依据",
        "triggers": ("结算", "工程款", "签证", "决算", "审计", "欠付", "已付"),
        "claims": {
            "原告": "应以实际完成的工程量与签证、决算资料结算，欠付部分应支付并计息",
            "被告": "结算未完成审计、签证未经确认，付款条件未成就",
        },
        "citations": (
            (CIVIL_CODE, "第七百九十九条"),
            (INTERPRETATION, "第十七条"),
        ),
        "evidence": (
            ("结算书或决算审计报告", ("结算", "决算", "审计")),
            ("签证与设计变更单", ("签证", "变更")),
            ("付款凭证与对账记录", ("付款", "转账", "对账")),
            ("往来函件与催告", ("函", "通知", "催告")),
        ),
    },
    {
        "focus": "质量抗辩",
        "triggers": ("质量", "验收", "不合格", "返修", "裂缝", "渗漏", "检测"),
        "claims": {
            "原告": "工程已验收合格或缺陷属保修范围，不影响工程款支付",
            "被告": "质量不合格，依约可拒付、减付或要求修复费用",
        },
        "citations": (
            (CIVIL_CODE, "第七百九十九条"),
            (CONSTRUCTION_LAW, "第六十二条"),
            (INTERPRETATION, "第十一条"),
        ),
        "evidence": (
            ("竣工验收记录", ("验收", "合格", "竣工")),
            ("质量检测或鉴定报告", ("检测", "鉴定", "报告")),
            ("修复通知与费用凭证", ("返修", "修复", "整改", "费用")),
            ("质量保修书", ("保修", "质保")),
        ),
    },
    {
        "focus": "工期顺延",
        "triggers": ("工期", "顺延", "逾期竣工", "停工", "窝工", "进度"),
        "claims": {
            "原告": "延误系发包人原因或不可抗力，工期应顺延，逾期违约金不成立",
            "被告": "承包人自身原因导致逾期，应承担违约责任",
        },
        "citations": (
            (INTERPRETATION, "第十条"),
            (INTERPRETATION, "第十一条"),
        ),
        "evidence": (
            ("开工令与竣工报告", ("开工", "竣工", "报告")),
            ("监理日志与进度记录", ("监理", "日志", "记录")),
            ("工期顺延签证", ("顺延", "签证", "确认")),
            ("停工与复工通知", ("停工", "暂停", "复工")),
        ),
    },
    {
        "focus": "建设工程价款优先受偿权",
        "triggers": ("优先受偿", "优先权", "折价", "拍卖", "抵押权", "查封"),
        "claims": {
            "原告": "承包人对工程折价或拍卖价款享有优先受偿权，优于抵押权",
            "被告": "行使期限已过、范围不符或已放弃优先权",
        },
        "citations": (
            (CIVIL_CODE, "第八百零七条"),
            (INTERPRETATION, "第三十六条"),
            (INTERPRETATION, "第四十一条"),
            (INTERPRETATION, "第四十二条"),
        ),
        "evidence": (
            ("欠付工程款金额证据", ("欠付", "未付", "结算")),
            ("优先权行使期限起算材料", ("竣工", "交付", "起诉", "仲裁")),
            ("折价协议或拍卖申请", ("折价", "拍卖", "协议")),
            ("抵押与查封情况", ("抵押", "查封", "第三人")),
        ),
    },
)

_SHORT_NAMES = {CIVIL_CODE: "民法典", CONSTRUCTION_LAW: "建筑法", INTERPRETATION: "建工司法解释（一）"}


def _statutes(conn, citations) -> list[dict]:
    resolved = []
    for law_name, article_no in citations:
        row = conn.execute(
            "SELECT law_name, article_no, text, source_url FROM statutes "
            "WHERE law_name = ? AND article_no = ?",
            (law_name, article_no),
        ).fetchone()
        if row:
            resolved.append(
                {
                    "law_name": row["law_name"],
                    "short_name": _SHORT_NAMES.get(row["law_name"], row["law_name"]),
                    "article_no": row["article_no"],
                    "text": row["text"],
                    "source_url": row["source_url"],
                }
            )
    return resolved


def analyze(facts: str) -> list[dict]:
    text = facts.strip()
    conn = db.connect()
    try:
        results = []
        for rule in RULES:
            matched = [word for word in rule["triggers"] if word in text]
            if not matched:
                continue
            results.append(
                {
                    "focus": rule["focus"],
                    "matched_keywords": matched,
                    "claims": rule["claims"],
                    "statutes": _statutes(conn, rule["citations"]),
                    "evidence": [
                        {
                            "item": item,
                            "status": "文中提及" if any(word in text for word in keywords) else "待补充",
                        }
                        for item, keywords in rule["evidence"]
                    ],
                }
            )
        return results
    finally:
        conn.close()
