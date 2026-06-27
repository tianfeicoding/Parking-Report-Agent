"""数据 profile 测试。

本文件验证支付分布、停车时长、领域上下文和模板说明提取。
"""

from decimal import Decimal
from zipfile import ZipFile

from app.data.parking_csv_loader import load_parking_csv
from app.profiling.domain_context_loader import load_domain_context
from app.profiling.duration_profiler import build_duration_profile
from app.profiling.payment_profiler import build_payment_profile
from app.report.template_instructions import extract_template_instructions

CSV_HEADER = (
    "应收金额,实收金额(元),免费金额(元),充值卡扣费(元),抵扣金额(元),"
    "抵扣时长(小时),实际抵扣额(元),支付方式,支付渠道,收费时间,进车时间\n"
)


def write_csv(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(
        CSV_HEADER
        + "30,30,0,0.00,0,0,0,微信,线上支付,2026-04-30 10:00:00,2026-04-30 08:00:00\n"
        + "45,0,0,0.00,45,0,45,会员积分,线上支付,2026-04-30 13:30:00,2026-04-30 09:00:00\n"
        + "25,20,0,0.00,5,1,5,微信,出口贴码,2026-04-30 23:00:00,2026-04-30 10:00:00\n",
        encoding="utf-8-sig",
    )
    return path


def write_minimal_docx(tmp_path):
    path = tmp_path / "template.docx"
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>停车明细分析报告</w:t></w:r></w:p>
    <w:p><w:r><w:t>一、关键指标</w:t></w:r></w:p>
    <w:p><w:r><w:t>【填写指标】</w:t></w:r></w:p>
    <w:p><w:r><w:t>二、支付方式与渠道</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    with ZipFile(path, "w") as docx:
        docx.writestr("word/document.xml", xml)
    return path


def test_payment_profile_counts_and_amounts(tmp_path):
    data = load_parking_csv(write_csv(tmp_path))

    profile = build_payment_profile(data)

    assert profile.dominant_payment_method is not None
    assert profile.dominant_payment_method.name == "微信"
    assert profile.dominant_payment_method.count == 2
    assert profile.dominant_payment_method.collected_amount == Decimal("50")
    assert profile.dominant_payment_channel is not None
    assert profile.dominant_payment_channel.name == "线上支付"
    assert profile.dominant_payment_channel.count == 2


def test_duration_profile_buckets_and_hours(tmp_path):
    data = load_parking_csv(write_csv(tmp_path))

    profile = build_duration_profile(data)

    assert profile.average_hours == Decimal("6.50")
    assert profile.median_hours == Decimal("4.50")
    assert profile.max_hours == Decimal("13.00")
    assert profile.over_12h_count == 1
    buckets = {bucket.label: bucket.count for bucket in profile.duration_buckets_2h}
    assert buckets["2-4"] == 1
    assert buckets["4-6"] == 1
    assert buckets["12+"] == 1
    assert profile.entry_hour_distribution[8].count == 1
    assert profile.charge_hour_distribution[23].count == 1


def test_domain_context_loader_uses_defaults_and_instructions():
    context = load_domain_context(instructions="不要把会员积分直接判断为异常")

    assert context.business_priorities
    assert context.risk_rules
    assert context.report_preferences == ["不要把会员积分直接判断为异常"]
    assert context.domain_terms["会员积分"]


def test_template_instruction_extractor_reads_sections_and_placeholders(tmp_path):
    template_path = write_minimal_docx(tmp_path)

    instructions = extract_template_instructions(template_path)

    assert instructions.title == "停车明细分析报告"
    assert instructions.sections == ["一、关键指标", "二、支付方式与渠道"]
    assert instructions.placeholders == ["【填写指标】"]
