"""Word 模板说明提取。

本文件从 docx 模板中提取章节标题和占位说明，作为 Agent 的模板上下文输入。
v1 使用标准库解析 OOXML，避免过早引入文档处理重依赖。
"""

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class TemplateInstructions:
    title: str | None
    sections: list[str]
    placeholders: list[str]
    raw_text: str


def _extract_docx_text(path: Path) -> list[str]:
    """从 docx document.xml 中提取段落文本。"""
    with ZipFile(path) as docx:
        xml_bytes = docx.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(texts).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def extract_template_instructions(template_path: str | Path) -> TemplateInstructions:
    """提取模板标题、章节名和占位说明。"""
    path = Path(template_path)
    paragraphs = _extract_docx_text(path)
    sections = [
        text
        for text in paragraphs
        if text.startswith(("一、", "二、", "三、", "四、", "五、"))
    ]
    placeholders = [text for text in paragraphs if "【" in text or "[" in text]

    return TemplateInstructions(
        title=paragraphs[0] if paragraphs else None,
        sections=sections,
        placeholders=placeholders,
        raw_text="\n".join(paragraphs),
    )
