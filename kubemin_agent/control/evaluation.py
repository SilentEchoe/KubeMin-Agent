"""Execution evaluation for control plane task runs."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from kubemin_agent.control.validator import ValidationResult
from kubemin_agent.providers.base import LLMProvider


@dataclass
class EvaluationResult:
    """Evaluation output for one executed task."""

    overall_score: int
    dimension_scores: dict[str, int] = field(default_factory=dict)
    passed: bool = True
    warn_threshold: int = 60
    reasons: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    rule_score: int = 0
    llm_score: int | None = None


class ExecutionEvaluator(ABC):
    """Task execution evaluator interface."""

    @abstractmethod
    async def evaluate(
        self,
        *,
        agent_name: str,
        task_description: str,
        final_output: str,
        trace_events: list[dict[str, Any]],
        validation: ValidationResult,
    ) -> EvaluationResult:
        """Evaluate one execution and return a scoring result."""


class HybridEvaluator(ExecutionEvaluator):
    """
    Rule-first evaluator with optional LLM judge.

    The final score is a weighted composition:
      overall = 0.6 * rule_score + 0.4 * llm_score (if llm_score is available)
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        warn_threshold: int = 60,
        llm_judge_enabled: bool = True,
    ) -> None:
        self.provider = provider
        self.warn_threshold = warn_threshold
        self.llm_judge_enabled = llm_judge_enabled

    async def evaluate(
        self,
        *,
        agent_name: str,
        task_description: str,
        final_output: str,
        trace_events: list[dict[str, Any]],
        validation: ValidationResult,
    ) -> EvaluationResult:
        """Evaluate one task execution."""
        rule_dimensions = self._rule_dimensions(
            task_description=task_description,
            final_output=final_output,
            trace_events=trace_events,
            validation=validation,
        )
        rule_score = self._average_score(rule_dimensions.values())

        llm_dimensions: dict[str, int] = {}
        llm_reasons: list[str] = []
        llm_score: int | None = None
        if self.llm_judge_enabled and self.provider:
            llm_dimensions, llm_reasons = await self._judge_with_llm(
                agent_name=agent_name,
                task_description=task_description,
                final_output=final_output,
                trace_events=trace_events,
                validation=validation,
            )
            if llm_dimensions:
                llm_score = self._average_score(llm_dimensions.values())

        overall_score = (
            round(rule_score * 0.6 + llm_score * 0.4)
            if llm_score is not None
            else rule_score
        )
        passed = overall_score >= self.warn_threshold

        reasons = self._build_reasons(
            final_output=final_output,
            trace_events=trace_events,
            validation=validation,
            llm_reasons=llm_reasons,
        )
        suggestions = self._build_suggestions(rule_dimensions)

        merged_dimensions = dict(rule_dimensions)
        merged_dimensions.update(llm_dimensions)

        return EvaluationResult(
            overall_score=overall_score,
            dimension_scores=merged_dimensions,
            passed=passed,
            warn_threshold=self.warn_threshold,
            reasons=reasons,
            suggestions=suggestions,
            rule_score=rule_score,
            llm_score=llm_score,
        )

    def _rule_dimensions(
        self,
        *,
        task_description: str,
        final_output: str,
        trace_events: list[dict[str, Any]],
        validation: ValidationResult,
    ) -> dict[str, int]:
        """Compute deterministic rule-based dimensions."""
        return {
            "completeness": self._score_completeness(task_description, final_output),
            "execution_health": self._score_execution_health(trace_events, validation),
            "efficiency": self._score_efficiency(trace_events),
        }

    def _score_completeness(self, task_description: str, final_output: str) -> int:
        text = final_output.strip()
        if not text:
            return 0

        score = 35
        if len(text) >= 60:
            score += 20
        elif len(text) >= 30:
            score += 10

        task_keywords = self._extract_keywords(task_description)
        if task_keywords:
            output_lower = text.lower()
            hits = sum(1 for keyword in task_keywords if keyword.lower() in output_lower)
            score += round(35 * (hits / len(task_keywords)))

        output_lower = text.lower()
        if any(k in output_lower for k in ("结论", "summary", "建议", "next", "步骤", "建议")):
            score += 10

        return max(0, min(100, score))

    def _score_execution_health(
        self,
        trace_events: list[dict[str, Any]],
        validation: ValidationResult,
    ) -> int:
        score = 100
        tool_observations = [e for e in trace_events if e.get("phase") == "tool_observation"]
        if tool_observations:
            failed = sum(1 for e in tool_observations if bool(e.get("error")))
            score -= round(60 * (failed / len(tool_observations)))

        if not validation.passed:
            if validation.severity == "block":
                score -= 40
            else:
                score -= 20

        return max(0, min(100, score))

    def _score_efficiency(self, trace_events: list[dict[str, Any]]) -> int:
        tool_actions = [
            str(e.get("action") or "")
            for e in trace_events
            if e.get("phase") == "tool_call"
        ]
        total = len(tool_actions)
        if total == 0:
            return 90

        if total <= 3:
            score = 100
        elif total <= 6:
            score = 85
        elif total <= 10:
            score = 70
        else:
            score = 55

        unique_count = len(set(tool_actions))
        if unique_count > 0:
            repeat_ratio = 1 - (unique_count / total)
            score -= round(repeat_ratio * 30)

        return max(0, min(100, score))

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract lightweight keywords from task text."""
        tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_\\-]{4,}", text)
        stopwords = {"please", "task", "with", "this", "that", "from", "then", "步骤"}
        deduped: list[str] = []
        for token in tokens:
            lowered = token.lower()
            if lowered in stopwords:
                continue
            if lowered not in {d.lower() for d in deduped}:
                deduped.append(token)
            if len(deduped) >= 8:
                break
        return deduped

    async def _judge_with_llm(
        self,
        *,
        agent_name: str,
        task_description: str,
        final_output: str,
        trace_events: list[dict[str, Any]],
        validation: ValidationResult,
    ) -> tuple[dict[str, int], list[str]]:
        """Get semantic quality scores from LLM judge."""
        if not self.provider:
            return {}, []

        payload = {
            "agent_name": agent_name,
            "task_description": task_description[:1000],
            "final_output": final_output[:2000],
            "trace_summary": [
                {
                    "phase": event.get("phase", ""),
                    "action": event.get("action", ""),
                    "observation": str(event.get("observation_summary", ""))[:180],
                    "error": event.get("error", ""),
                }
                for event in trace_events[:12]
            ],
            "validation": {
                "passed": validation.passed,
                "severity": validation.severity,
                "reason": validation.reason,
                "policy_id": validation.policy_id,
            },
        }

        system_prompt = (
            "You are a strict execution-quality judge. "
            "Return JSON only with fields: correctness, relevance, actionability, reasons. "
            "Scores must be integers from 0 to 100."
        )

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                max_tokens=256,
                temperature=0.0,
            )
            if not response.content:
                return {}, []
            data = json.loads(self._extract_json_content(response.content))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LLM judge failed, fallback to rule score: {e}")
            return {}, []

        dims: dict[str, int] = {}
        for key in ("correctness", "relevance", "actionability"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                dims[key] = max(0, min(100, int(round(value))))

        reasons = data.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = []

        return dims, [str(item)[:160] for item in reasons[:3]]

    def _build_reasons(
        self,
        *,
        final_output: str,
        trace_events: list[dict[str, Any]],
        validation: ValidationResult,
        llm_reasons: list[str],
    ) -> list[str]:
        reasons: list[str] = []
        if not final_output.strip():
            reasons.append("输出为空或无有效内容")

        if not validation.passed:
            reasons.append(f"校验器告警: {validation.reason}")

        tool_failures = sum(
            1
            for event in trace_events
            if event.get("phase") == "tool_observation" and bool(event.get("error"))
        )
        if tool_failures > 0:
            reasons.append(f"工具调用失败次数: {tool_failures}")

        reasons.extend(llm_reasons)
        if not reasons:
            reasons.append("执行质量整体稳定")
        return reasons[:5]

    def _build_suggestions(self, rule_dimensions: dict[str, int]) -> list[str]:
        suggestions: list[str] = []
        if rule_dimensions.get("completeness", 0) < 60:
            suggestions.append("补充明确结论、关键依据与下一步建议")
        if rule_dimensions.get("execution_health", 0) < 60:
            suggestions.append("优先处理工具失败与校验告警，降低不确定执行")
        if rule_dimensions.get("efficiency", 0) < 60:
            suggestions.append("减少重复工具调用，优先合并同类操作")
        if not suggestions:
            suggestions.append("保持当前执行策略，继续监控质量趋势")
        return suggestions[:3]

    def _average_score(self, values: Any) -> int:
        score_values = [int(v) for v in values]
        if not score_values:
            return 0
        return int(round(sum(score_values) / len(score_values)))

    def _extract_json_content(self, llm_output: str) -> str:
        content = llm_output.strip()
        if not content.startswith("```"):
            return content

        lines = content.splitlines()
        if len(lines) < 3:
            return content

        body = lines[1:-1]
        if body and body[0].strip().lower() == "json":
            body = body[1:]
        return "\n".join(body).strip()
