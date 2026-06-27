"""报告图表渲染器。

本文件把确定性 profile 数据渲染成 PNG 图表。图表只来自清洗后的
真实数据，不由 LLM 生成或改写。
"""

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from app.profiling.duration_profiler import DurationProfile, HourBucket
from app.profiling.payment_profiler import DistributionItem, PaymentProfile


def _configure_chinese_font() -> None:
    """选择运行环境中可用的中文字体，确保图表文字正常渲染。"""
    preferred_fonts = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Microsoft YaHei",
        "PingFang SC",
        "SimHei",
        "Arial Unicode MS",
    ]
    installed_fonts = {font.name for font in font_manager.fontManager.ttflist}
    selected_font = next((name for name in preferred_fonts if name in installed_fonts), None)
    if selected_font:
        plt.rcParams["font.sans-serif"] = [selected_font, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


_configure_chinese_font()


@dataclass(frozen=True)
class RenderedChart:
    chart_id: str
    title: str
    path: Path


class ChartRenderer:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_all(
        self,
        payment_profile: PaymentProfile,
        duration_profile: DurationProfile,
    ) -> dict[str, RenderedChart]:
        """生成 Phase 7 要求的全部图表，并按 chart_id 返回。"""
        charts = [
            self._render_distribution(
                "payment_method_distribution",
                "支付方式分布",
                payment_profile.payment_methods,
                "payment_method_distribution.png",
            ),
            self._render_distribution(
                "payment_channel_distribution",
                "支付渠道分布",
                payment_profile.payment_channels,
                "payment_channel_distribution.png",
            ),
            self._render_simple_bars(
                "parking_duration_distribution",
                "停车时长分布",
                [_format_duration_label(bucket.label) for bucket in duration_profile.duration_buckets_2h],
                [bucket.count for bucket in duration_profile.duration_buckets_2h],
                "停车时长区间",
                "交易笔数",
                "parking_duration_distribution.png",
            ),
            self._render_hour_distribution(
                "entry_hour_distribution",
                "入场时段分布",
                duration_profile.entry_hour_distribution,
                "entry_hour_distribution.png",
            ),
            self._render_hour_distribution(
                "charge_hour_distribution",
                "收费时段分布",
                duration_profile.charge_hour_distribution,
                "charge_hour_distribution.png",
            ),
        ]
        return {chart.chart_id: chart for chart in charts}

    def _render_distribution(
        self,
        chart_id: str,
        title: str,
        items: list[DistributionItem],
        filename: str,
    ) -> RenderedChart:
        """渲染支付方式或支付渠道的 Top N 横向柱状图。"""
        top_items = items[:8]
        labels = [f"{item.name}（{item.count_pct}%）" for item in top_items] or ["暂无数据"]
        values = [item.count for item in top_items] or [0]
        path = self.output_dir / filename

        fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
        ax.barh(range(len(labels)), values, color="#2F6F73")
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("交易笔数")
        ax.set_title(title, fontsize=12, pad=10)
        ax.grid(axis="x", alpha=0.25)
        for index, value in enumerate(values):
            ax.text(value, index, f" {value}", va="center", fontsize=8)
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return RenderedChart(chart_id=chart_id, title=title, path=path)

    def _render_hour_distribution(
        self,
        chart_id: str,
        title: str,
        buckets: list[HourBucket],
        filename: str,
    ) -> RenderedChart:
        """渲染 0-23 点小时分布柱状图。"""
        return self._render_simple_bars(
            chart_id,
            title,
            [str(bucket.hour) for bucket in buckets],
            [bucket.count for bucket in buckets],
            "小时（0-23时）",
            "交易笔数",
            filename,
        )

    def _render_simple_bars(
        self,
        chart_id: str,
        title: str,
        labels: list[str],
        values: list[int],
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> RenderedChart:
        """渲染普通柱状图，用于时长和小时分布。"""
        path = self.output_dir / filename
        fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=160)
        positions = list(range(len(labels)))
        ax.bar(positions, values, color="#5E8C61")
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=12, pad=10)
        ax.grid(axis="y", alpha=0.25)
        ax.tick_params(axis="x", labelrotation=0, labelsize=8)
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return RenderedChart(chart_id=chart_id, title=title, path=path)


def _format_duration_label(label: str) -> str:
    """将内部时长分桶标签转换为报告使用的中文标签。"""
    if label.endswith("+"):
        return f"{label[:-1]}小时以上"
    return f"{label}小时"
