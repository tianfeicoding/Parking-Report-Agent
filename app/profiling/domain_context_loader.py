"""领域上下文加载器。

本文件把用户可选输入的处理说明和领域文件归一化为结构化上下文。
v1 不做复杂 RAG，只保留默认停车经营分析准则和本次任务上下文。
"""

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


DEFAULT_BUSINESS_PRIORITIES = [
    "关注实收率和收入回收情况",
    "关注优惠、抵扣、免费金额对实收的影响",
    "关注零实收交易是否需要复核",
    "关注支付方式和渠道结构",
    "关注长时停车和收费高峰时段",
]

DEFAULT_RISK_RULES = [
    "应收金额大于 0 且实收金额为 0 的记录需要结合优惠/抵扣来源复核。",
    "实际抵扣额占应收金额比例较高时，应关注优惠核销和会员权益成本。",
    "超过 12 小时的长时停车可能影响车位周转，也可能代表入出场记录异常。",
]


@dataclass(frozen=True)
class DomainContextPack:
    business_priorities: list[str]
    known_policies: list[str]
    report_preferences: list[str]
    domain_terms: dict[str, str]
    risk_rules: list[str]
    source_files: list[str]


def _extract_docx_text(path: Path) -> str:
    """用标准库从 docx 中提取段落文本，避免 Phase 5 引入 python-docx 重依赖。"""
    with ZipFile(path) as docx:
        xml_bytes = docx.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    texts = [node.text or "" for node in root.findall(".//w:t", namespace)]
    return "\n".join(text for text in texts if text.strip())


def _read_context_file(path: Path) -> str:
    """读取领域上下文文件，支持 txt/md/docx。"""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    return ""


def load_domain_context(
    domain_context_paths: list[str] | None = None,
    instructions: str | None = None,
) -> DomainContextPack:
    """把默认规则、用户处理说明和可选领域文件合并为领域上下文包。"""
    known_policies: list[str] = []
    source_files: list[str] = []

    for raw_path in domain_context_paths or []:
        path = Path(raw_path)
        text = _read_context_file(path).strip()
        if text:
            known_policies.append(text)
            source_files.append(path.name)

    report_preferences = []
    if instructions and instructions.strip():
        report_preferences.append(instructions.strip())

    return DomainContextPack(
        business_priorities=DEFAULT_BUSINESS_PRIORITIES,
        known_policies=known_policies,
        report_preferences=report_preferences,
        domain_terms={
            "出口贴码": "车主在出口扫码完成支付",
            "会员积分": "会员权益或营销积分支付方式",
            "优惠券": "优惠核销类支付方式",
        },
        risk_rules=DEFAULT_RISK_RULES,
        source_files=source_files,
    )
