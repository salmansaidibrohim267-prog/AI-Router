from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.memory.store import MemoryStore, SQLiteStore

logger = logging.getLogger(__name__)


class ApprovalCheckpoint:
    def __init__(
        self,
        checkpoint_id: str,
        workflow_id: str,
        step_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
    ):
        self.checkpoint_id = checkpoint_id
        self.workflow_id = workflow_id
        self.step_id = step_id
        self.prompt = prompt
        self.context = context or {}
        self.status: str = "pending"
        self.created_at: float = time.time()
        self.decided_at: float = 0.0
        self.decided_by: str = ""
        self.notes: str = ""


class ApprovalManager:
    def __init__(self, store: MemoryStore | None = None):
        self._store = store or SQLiteStore()
        self._pending: dict[str, ApprovalCheckpoint] = {}

    def create_checkpoint(
        self,
        workflow_id: str,
        step_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> ApprovalCheckpoint:
        checkpoint_id = uuid.uuid4().hex[:12]
        cp = ApprovalCheckpoint(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            step_id=step_id,
            prompt=prompt,
            context=context,
        )
        self._pending[checkpoint_id] = cp
        self._store.set(
            f"approval:{checkpoint_id}",
            {
                "checkpoint_id": checkpoint_id,
                "workflow_id": workflow_id,
                "step_id": step_id,
                "prompt": prompt,
                "context": context,
                "status": "pending",
                "created_at": cp.created_at,
            },
        )
        logger.info(f"Approval checkpoint created: {checkpoint_id} (workflow={workflow_id}, step={step_id})")
        return cp

    def approve(self, checkpoint_id: str, user: str = "", notes: str = "") -> bool:
        cp = self._pending.get(checkpoint_id)
        if not cp or cp.status != "pending":
            return False
        cp.status = "approved"
        cp.decided_at = time.time()
        cp.decided_by = user
        cp.notes = notes
        self._store.set(
            f"approval:{checkpoint_id}",
            {
                "checkpoint_id": checkpoint_id,
                "status": "approved",
                "decided_at": cp.decided_at,
                "decided_by": user,
                "notes": notes,
            },
        )
        logger.info(f"Checkpoint {checkpoint_id} approved by {user}")
        return True

    def reject(self, checkpoint_id: str, user: str = "", notes: str = "") -> bool:
        cp = self._pending.get(checkpoint_id)
        if not cp or cp.status != "pending":
            return False
        cp.status = "rejected"
        cp.decided_at = time.time()
        cp.decided_by = user
        cp.notes = notes
        self._store.set(
            f"approval:{checkpoint_id}",
            {
                "checkpoint_id": checkpoint_id,
                "status": "rejected",
                "decided_at": cp.decided_at,
                "decided_by": user,
                "notes": notes,
            },
        )
        logger.info(f"Checkpoint {checkpoint_id} rejected by {user}")
        return True

    def get_status(self, checkpoint_id: str) -> str:
        cp = self._pending.get(checkpoint_id)
        if cp:
            return cp.status
        data = self._store.get(f"approval:{checkpoint_id}")
        return data.get("status", "unknown") if data else "unknown"

    def list_pending(self) -> list[ApprovalCheckpoint]:
        return [cp for cp in self._pending.values() if cp.status == "pending"]

    def list_all(self) -> list[dict[str, Any]]:
        result = []
        for key in self._store.keys("approval:*"):
            data = self._store.get(key)
            if data:
                result.append(data)
        return result

    def clean_completed(self) -> int:
        count = 0
        for cpid in list(self._pending.keys()):
            cp = self._pending[cpid]
            if cp.status != "pending":
                del self._pending[cpid]
                count += 1
        return count

    async def wait_for_decision(
        self,
        checkpoint_id: str,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> str:
        start = time.time()
        while time.time() - start < timeout:
            status = self.get_status(checkpoint_id)
            if status in ("approved", "rejected"):
                return status
            await __import__("asyncio").sleep(poll_interval)
        return "timeout"
