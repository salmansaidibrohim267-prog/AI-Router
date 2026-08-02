from __future__ import annotations

import csv
import html
import io
import json
import os
from typing import Any

from .config import EvaluationConfig
from .exceptions import ReportGenerationError
from .models import BenchmarkResult, EvaluationResult

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; color: #222; }}
h1, h2 {{ border-bottom: 1px solid #ddd; padding-bottom: .3rem; }}
table {{ border-collapse: collapse; margin: 1rem 0; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: .4rem .7rem; text-align: left; }}
th {{ background: #f4f4f4; }}
.pass {{ color: #1a7f37; font-weight: bold; }}
.fail {{ color: #cf222e; font-weight: bold; }}
.na {{ color: #888; }}
</style></head>
<body>
<h1>{title}</h1>
<p>Generated: {generated} &mdash; Dataset: {dataset} ({dataset_type}) &mdash; Duration: {duration} ms</p>
{gate_html}
{body}
</body></html>
"""


class ReportGenerator:
    def __init__(self, config: EvaluationConfig | None = None):
        self._config = config or EvaluationConfig()

    def to_json(self, result: EvaluationResult | BenchmarkResult) -> str:
        return json.dumps(result.to_dict(), indent=2, default=str)

    def to_markdown(self, result: EvaluationResult | BenchmarkResult) -> str:
        lines: list[str] = []
        if isinstance(result, BenchmarkResult):
            lines.append(f"# Benchmark: {result.name}")
            lines.append("")
            lines.append(
                f"- Dataset: **{result.dataset_name}** ({result.dataset_type})"
            )
            lines.append(f"- Duration: {result.duration_ms} ms")
            if result.gate is not None:
                lines.append(f"- Quality Gate: **{'PASSED' if result.gate['passed'] else 'FAILED'}**")
            lines.append("")
            for sub in result.results:
                lines.extend(self._markdown_section(sub, level=2))
            return "\n".join(lines)
        lines.extend(self._markdown_section(result, level=1))
        return "\n".join(lines)

    def _markdown_section(self, result: EvaluationResult, level: int) -> list[str]:
        lines = [f"{'#' * level} {result.evaluator}", ""]
        lines.append(f"Samples: {len(result.samples)} | Duration: {result.duration_ms} ms")
        if result.error:
            lines.append(f"**Error:** {result.error}")
        lines.extend(["", "| Metric | Value | Min | Max | Passed |", "| --- | ---: | ---: | ---: | ---: |"])
        for metric in result.metrics:
            passed = (
                "✅" if metric.passed else "❌"
                if metric.passed is False
                else "—"
            )
            min_val = metric.threshold_min if metric.threshold_min is not None else "—"
            max_val = metric.threshold_max if metric.threshold_max is not None else "—"
            lines.append(
                f"| {metric.name} | {metric.value} | {min_val} | {max_val} | {passed} |"
            )
        return lines

    def to_html(self, result: EvaluationResult | BenchmarkResult) -> str:
        if isinstance(result, BenchmarkResult):
            body_parts: list[str] = []
            for sub in result.results:
                body_parts.append(self._html_section(sub))
            gate_html = self._gate_html(result.gate)
            return _HTML_TEMPLATE.format(
                title=html.escape(result.name),
                generated=json.dumps(result.started_at, default=str),
                dataset=html.escape(result.dataset_name),
                dataset_type=html.escape(result.dataset_type),
                duration=result.duration_ms,
                gate_html=gate_html,
                body="\n".join(body_parts),
            )
        return _HTML_TEMPLATE.format(
            title=html.escape(result.evaluator),
            generated=json.dumps(result.started_at, default=str),
            dataset="—",
            dataset_type="—",
            duration=result.duration_ms,
            gate_html="",
            body=self._html_section(result),
        )

    def _gate_html(self, gate: dict[str, Any] | None) -> str:
        if gate is None:
            return ""
        passed = bool(gate.get("passed"))
        cls = "pass" if passed else "fail"
        return f'<p>Quality Gate: <span class="{cls}">{"PASSED" if passed else "FAILED"}</span></p>'

    def _html_section(self, result: EvaluationResult) -> str:
        rows: list[str] = []
        for metric in result.metrics:
            if metric.passed is None:
                cls, passed = "na", "—"
            else:
                cls = "pass" if metric.passed else "fail"
                passed = "PASS" if metric.passed else "FAIL"
            rows.append(
                f"<tr><td>{html.escape(metric.name)}</td><td>{metric.value}</td>"
                f"<td>{metric.threshold_min if metric.threshold_min is not None else '—'}</td>"
                f"<td>{metric.threshold_max if metric.threshold_max is not None else '—'}</td>"
                f'<td class="{cls}">{passed}</td></tr>'
            )
        error_html = (
            f"<p style='color:#cf222e'>Error: {html.escape(result.error)}</p>" if result.error else ""
        )
        return (
            f"<h2>{html.escape(result.evaluator)}</h2>"
            f"<p>Samples: {len(result.samples)} | Duration: {result.duration_ms} ms</p>"
            f"{error_html}"
            f"<table><tr><th>Metric</th><th>Value</th><th>Min</th><th>Max</th><th>Passed</th></tr>"
            f"{''.join(rows)}</table>"
        )

    def to_csv(self, result: EvaluationResult | BenchmarkResult) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["evaluator", "metric", "value", "samples", "threshold_min", "threshold_max", "passed"])
        sub_results: list[EvaluationResult] = (
            result.results if isinstance(result, BenchmarkResult) else [result]
        )
        for sub in sub_results:
            for metric in sub.metrics:
                writer.writerow(
                    [
                        sub.evaluator,
                        metric.name,
                        metric.value,
                        metric.samples,
                        metric.threshold_min if metric.threshold_min is not None else "",
                        metric.threshold_max if metric.threshold_max is not None else "",
                        metric.passed if metric.passed is not None else "",
                    ]
                )
        return buffer.getvalue()

    def generate(
        self,
        result: EvaluationResult | BenchmarkResult,
        formats: tuple[str, ...] | None = None,
        directory: str | None = None,
    ) -> dict[str, str]:
        formats = formats or self._config.report_formats
        directory = directory or self._config.report_dir
        os.makedirs(directory, exist_ok=True)
        base = result.name if isinstance(result, BenchmarkResult) else result.evaluator
        outputs: dict[str, str] = {}
        renderers = {
            "json": ("json", self.to_json),
            "markdown": ("md", self.to_markdown),
            "html": ("html", self.to_html),
            "csv": ("csv", self.to_csv),
        }
        for fmt in formats:
            if fmt not in renderers:
                raise ReportGenerationError(f"Unsupported report format {fmt!r}")
            ext, renderer = renderers[fmt]
            path = os.path.join(directory, f"{base}.{ext}")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(renderer(result))
            outputs[fmt] = path
        return outputs
