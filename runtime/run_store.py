from pathlib import Path
import json
import re
from typing import Any, Dict
from uuid import UUID
from datetime import datetime
from .schemas import RunReport, RunInput
from ..config import settings

class SensitiveDataMasker:
    """
    Basic masker for sensitive data in logs/inputs.
    """
    # Simple regexes for common secrets
    PATTERNS = [
        (r'([a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,5})', '<EMAIL>'),
        (r'(Bearer\s+)[a-zA-Z0-9\-\._~+/]+=*', r'\1<TOKEN>'),
        (r'(password|passwd|pwd|secret|key)\s*[:=]\s*["\']?([^"\',\s]+)["\']?', r'\1: <REDACTED>'),
    ]

    @classmethod
    def mask(cls, text: str) -> str:
        if not text:
            return text
        for pattern, replacement in cls.PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

class RunStore:
    """
    Manages persistence of run artifacts.
    Structure:
    ~/.kubemin-agent/runs/
      <run_id>/
        input.json
        report.json
        tools/
          <tool_name>_<seq>.json
    """
    
    def __init__(self):
        self.base_dir = settings.run_store_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_run_dir(self, run_id: UUID) -> Path:
        run_dir = self.base_dir / str(run_id)
        run_dir.mkdir(exist_ok=True)
        (run_dir / "tools").mkdir(exist_ok=True)
        return run_dir

    def save_input(self, run_input: RunInput):
        run_dir = self._get_run_dir(run_input.run_id)
        # Mask query just in case
        masked_input = run_input.model_copy()
        masked_input.query = SensitiveDataMasker.mask(masked_input.query)
        
        with open(run_dir / "input.json", "w") as f:
            f.write(masked_input.model_dump_json(indent=2))

    def save_tool_output(self, run_id: UUID, tool_name: str, seq: int, output: Any):
        run_dir = self._get_run_dir(run_id)
        # Naive masking for tool output if strict string
        if isinstance(output, str):
            output = SensitiveDataMasker.mask(output)
        
        # If dict/list, we might want to mask values recursively, 
        # but for v1 let's assume raw json dump is acceptable 
        # if specific fields are not explicitly targeted.
        # Improvement: Recurse and mask strings.
        
        file_path = run_dir / "tools" / f"{seq:03d}_{tool_name}.json"
        with open(file_path, "w") as f:
            if isinstance(output, str):
                f.write(output)
            else:
                json.dump(output, f, indent=2, default=str)

    def save_report(self, report: RunReport):
        run_dir = self._get_run_dir(report.run_id)
        with open(run_dir / "report.json", "w") as f:
            f.write(report.model_dump_json(indent=2, by_alias=True))
            
    def load_report(self, run_id: str) -> RunReport:
        run_dir = self.base_dir / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {run_id} not found")
            
        with open(run_dir / "report.json", "r") as f:
            data = json.load(f)
            return RunReport(**data)

run_store = RunStore()
