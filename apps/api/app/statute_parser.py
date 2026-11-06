"""法条文本解析：HTML 转纯文本，按「第X条」切分条文。"""

import html
import re
from dataclasses import dataclass

_SCRIPT_BLOCK = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_BREAK_TAG = re.compile(r"</(p|div|h[1-6]|li|tr)|<br\s*/?>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_ARTICLE_HEAD = re.compile(r"^第[一二三四五六七八九十百千零]+条")
_ARTICLE_MARK = re.compile(r"第[一二三四五六七八九十百千零]+条")
# 页面页脚与导航文字，混进条文正文会污染引用
_FOOTER_LINE = re.compile(
    r"^(责任编辑[:：]|扫一扫|相关稿件|链接[:：]|版权所有|京ICP|运维保障|返回|顶部"
    r"|全国人大全国政协|中华人民共和国司法部|中国人大网|中国政府网|司法部信息中心"
    r"|主办单位|运行维护单位|网站标识码|网站纠错|打印本页|字号|国务院客户端"
    r"|电脑版|客户端|小程序|微博|微信|邮箱|注册|登录|退出)"
)

_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_UNITS = {"十": 10, "百": 100, "千": 1000}


@dataclass
class Article:
    article_no: str
    index: int
    text: str


def html_to_text(raw: str) -> str:
    """去掉标签与脚本，块级标签换成换行，并清理孤立尖括号。"""
    text = _SCRIPT_BLOCK.sub("\n", raw)
    text = _BREAK_TAG.sub("\n", text)
    text = _ANY_TAG.sub("", text)
    text = html.unescape(text)
    text = text.replace("\u3000", " ")  # 全角空格
    lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip().strip(">").strip()
        if not line or re.fullmatch(r"[<>/=*\-—·]+", line):
            continue
        if _FOOTER_LINE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def cn_numeral_to_int(numeral: str) -> int:
    """中文数字转整数，支持到千位，如 八百零七 → 807。"""
    total = 0
    current = 0
    for char in numeral:
        if char in _DIGITS:
            current = _DIGITS[char]
        elif char in _UNITS:
            unit = _UNITS[char]
            total += (current or 1) * unit
            current = 0
        else:
            raise ValueError(f"无法识别的中文数字字符: {char}")
    return total + current


def parse_articles(text: str) -> list[Article]:
    """按行首的「第X条」切分，正文中的法条引用不会误切。"""
    articles: list[Article] = []
    current_no: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_no is None:
            return
        body = "\n".join(current_lines).strip()
        if body:
            numeral = _ARTICLE_MARK.match(current_no).group()[1:-1]
            articles.append(
                Article(
                    article_no=current_no,
                    index=cn_numeral_to_int(numeral),
                    text=body,
                )
            )

    for line in text.split("\n"):
        head = _ARTICLE_HEAD.match(line)
        if head:
            flush()
            current_no = head.group()
            current_lines = [line[len(current_no) :].strip(" 　:：")]
        elif current_no is not None:
            current_lines.append(line)
    flush()
    if articles:
        # 末条正文之后是网页页脚垃圾。法规末条固定为施行日期条款，
        # 以「施行。」为语义边界截断，比逐条匹配页脚文本可靠。
        last = articles[-1]
        lines = last.text.split("\n")
        for position in range(len(lines) - 1, -1, -1):
            if "施行。" in lines[position]:
                last.text = "\n".join(lines[: position + 1])
                break
    return articles


def validate_articles(articles: list[Article], expected_count: int | None = None) -> None:
    """解析结果的自检，不通过就报错，避免脏数据入库。"""
    if not articles:
        raise ValueError("未解析到任何条文")
    if expected_count is not None and len(articles) != expected_count:
        raise ValueError(f"条文数不符：解析 {len(articles)} 条，预期 {expected_count} 条")
    numbers = [item.index for item in articles]
    if len(set(numbers)) != len(numbers):
        raise ValueError("存在重复条文号")
    if numbers[0] != 1:
        raise ValueError(f"首条不是第一条，而是 {numbers[0]}")
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("条文号不连续或有乱序")
