"""Check module-level coverage thresholds from coverage.xml."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_THRESHOLDS: dict[str, float] = {
    "kubemin_agent/bus/queue.py": 80.0,
    "kubemin_agent/channels/telegram.py": 80.0,
    "kubemin_agent/channels/feishu.py": 80.0,
    "kubemin_agent/cli/ui.py": 80.0,
}


def _collect_rates(xml_path: Path) -> dict[str, float]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    rates: dict[str, float] = {}

    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        line_rate = class_node.attrib.get("line-rate")
        if not filename or line_rate is None:
            continue
        try:
            rates[filename] = float(line_rate) * 100.0
        except ValueError:
            continue
    return rates


def _resolve_rate(rates: dict[str, float], module_path: str) -> float | None:
    normalized_targets = {
        module_path,
        module_path.removeprefix("kubemin_agent/"),
    }
    for filename, rate in rates.items():
        for target in normalized_targets:
            if filename == target or filename.endswith(target):
                return rate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check module-level coverage thresholds.")
    parser.add_argument(
        "coverage_xml",
        nargs="?",
        default="coverage.xml",
        help="Path to coverage xml report (default: coverage.xml)",
    )
    args = parser.parse_args()

    xml_path = Path(args.coverage_xml)
    if not xml_path.exists():
        print(f"[coverage-check] coverage report not found: {xml_path}")
        return 1

    rates = _collect_rates(xml_path)
    failures: list[str] = []

    print("[coverage-check] Module coverage thresholds")
    for module_path, threshold in DEFAULT_THRESHOLDS.items():
        rate = _resolve_rate(rates, module_path)
        if rate is None:
            failures.append(f"{module_path}: missing from coverage report")
            print(f"  - {module_path}: MISSING (required >= {threshold:.1f}%)")
            continue
        status = "PASS" if rate >= threshold else "FAIL"
        print(f"  - {module_path}: {rate:.2f}% (required >= {threshold:.1f}%) [{status}]")
        if rate < threshold:
            failures.append(
                f"{module_path}: {rate:.2f}% < required {threshold:.1f}%"
            )

    if failures:
        print("[coverage-check] FAILED")
        for item in failures:
            print(f"  * {item}")
        return 1

    print("[coverage-check] PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
