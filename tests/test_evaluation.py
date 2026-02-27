"""Tests for execution evaluator behavior."""

from __future__ import annotations

import pytest

from kubemin_agent.control.evaluation import HybridEvaluator
from kubemin_agent.control.validator import ValidationResult
from kubemin_agent.providers.base import LLMProvider, LLMResponse


class StaticJudgeProvider(LLMProvider):
    """Simple provider stub for evaluator tests."""

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    async def chat(self, *args, **kwargs):  # type: ignore[override]
        return LLMResponse(content=self._content)

    def get_default_model(self) -> str:
        return "stub"


def _base_validation() -> ValidationResult:
    return ValidationResult(
        passed=True,
        reason="",
        severity="info",
        policy_id="ok",
        redactions=[],
        sanitized_result="",
    )


def _trace_events() -> list[dict]:
    return [
        {
            "step_index": 1,
            "phase": "tool_call",
            "action": "tool:read_file",
            "observation_summary": "{\"path\": \"README.md\"}",
            "error": "",
        },
        {
            "step_index": 2,
            "phase": "tool_observation",
            "action": "tool:read_file",
            "observation_summary": "loaded content",
            "error": "",
        },
    ]


@pytest.mark.asyncio
async def test_hybrid_evaluator_rule_only_mode() -> None:
    evaluator = HybridEvaluator(provider=None, warn_threshold=60, llm_judge_enabled=False)

    result = await evaluator.evaluate(
        agent_name="general",
        task_description="请总结 README 并给出结论和建议",
        final_output="总结如下：功能已完成。结论：当前状态稳定。建议下一步增加测试覆盖。",
        trace_events=_trace_events(),
        validation=_base_validation(),
    )

    assert result.llm_score is None
    assert result.overall_score == result.rule_score
    assert result.passed is True


@pytest.mark.asyncio
async def test_hybrid_evaluator_falls_back_on_invalid_llm_json() -> None:
    evaluator = HybridEvaluator(
        provider=StaticJudgeProvider("not-json"),
        warn_threshold=60,
        llm_judge_enabled=True,
    )

    result = await evaluator.evaluate(
        agent_name="general",
        task_description="检查配置并提供建议",
        final_output="已检查配置，建议保留默认值。",
        trace_events=_trace_events(),
        validation=_base_validation(),
    )

    assert result.llm_score is None
    assert result.overall_score == result.rule_score
    assert "completeness" in result.dimension_scores


@pytest.mark.asyncio
async def test_hybrid_evaluator_merges_llm_score() -> None:
    judge_output = (
        '{"correctness": 80, "relevance": 70, "actionability": 90, '
        '"reasons": ["overall good"]}'
    )
    evaluator = HybridEvaluator(
        provider=StaticJudgeProvider(judge_output),
        warn_threshold=60,
        llm_judge_enabled=True,
    )

    result = await evaluator.evaluate(
        agent_name="general",
        task_description="读取文件并生成总结建议",
        final_output="总结如下：执行成功。结论：可继续推进。建议：补充边界测试。",
        trace_events=_trace_events(),
        validation=_base_validation(),
    )

    assert result.llm_score == 80
    assert result.overall_score == round(result.rule_score * 0.6 + 80 * 0.4)
    assert result.dimension_scores["correctness"] == 80
    assert result.dimension_scores["actionability"] == 90
