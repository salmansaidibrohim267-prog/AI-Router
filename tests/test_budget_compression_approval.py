import pytest

from app.orchestration.budget import BudgetManager
from app.orchestration.compression import ContextCompressor, CompressionStats
from app.orchestration.approval import ApprovalManager


class TestBudgetManager:
    def test_initial_state(self):
        bm = BudgetManager({"max_cost": 5.0, "max_tokens": 1000})
        assert bm.total_cost == 0.0
        assert bm.total_tokens == 0
        assert bm.remaining_budget == 5.0
        assert bm.remaining_tokens == 1000

    def test_record_usage(self):
        from app.models import Usage
        bm = BudgetManager({"max_cost": 10.0})
        usage = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        bm.record(usage, cost=0.005, latency_ms=500)
        assert bm.total_tokens == 150
        assert bm.total_cost == 0.005
        assert bm.remaining_budget == 9.995

    def test_check_limits_exceeded(self):
        bm = BudgetManager({"max_cost": 0.01, "max_tokens": 100})
        allowed, msg = bm.check_limits(estimated_tokens=200)
        assert not allowed
        assert "budget" in msg.lower()

    def test_check_limits_ok(self):
        bm = BudgetManager({"max_cost": 10.0, "max_tokens": 10000})
        allowed, msg = bm.check_limits(estimated_tokens=50, estimated_cost=0.001)
        assert allowed

    def test_get_stats(self):
        bm = BudgetManager({"max_cost": 5.0})
        stats = bm.get_stats()
        assert stats["max_cost"] == 5.0
        assert stats["remaining_budget"] == 5.0

    def test_downgrade_suggestion(self):
        bm = BudgetManager({"max_cost": 0.001})
        from app.models import Usage
        usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        bm.record(usage, cost=0.003, latency_ms=100)
        suggestion = bm.get_downgrade_suggestion()
        assert isinstance(suggestion, str)

    def test_reset(self):
        bm = BudgetManager()
        from app.models import Usage
        bm.record(Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15), cost=0.01)
        bm.reset()
        assert bm.total_tokens == 0


class TestCompressionStats:
    def test_record_and_ratio(self):
        cs = CompressionStats()
        cs.record(1000, 200)
        assert cs.compression_count == 1
        assert cs.total_original_tokens == 1000
        assert cs.total_compressed_tokens == 200
        assert cs.ratio == 0.2

    def test_empty_ratio(self):
        cs = CompressionStats()
        assert cs.ratio == 1.0

    def test_to_dict(self):
        cs = CompressionStats()
        cs.record(800, 300)
        d = cs.to_dict()
        assert d["compression_count"] == 1
        assert d["ratio"] == 0.375


class TestApprovalManager:
    def test_create_checkpoint(self):
        mgr = ApprovalManager()
        cp = mgr.create_checkpoint("wf1", "step1", "Approve this?")
        assert cp.status == "pending"
        assert cp.workflow_id == "wf1"

    def test_approve(self):
        mgr = ApprovalManager()
        cp = mgr.create_checkpoint("wf1", "s1", "Go?")
        assert mgr.approve(cp.checkpoint_id, user="admin")
        assert mgr.get_status(cp.checkpoint_id) == "approved"

    def test_reject(self):
        mgr = ApprovalManager()
        cp = mgr.create_checkpoint("wf1", "s1", "Go?")
        assert mgr.reject(cp.checkpoint_id, user="admin")
        assert mgr.get_status(cp.checkpoint_id) == "rejected"

    def test_approve_already_decided(self):
        mgr = ApprovalManager()
        cp = mgr.create_checkpoint("wf1", "s1", "Go?")
        mgr.approve(cp.checkpoint_id)
        assert not mgr.reject(cp.checkpoint_id)

    def test_list_pending(self):
        mgr = ApprovalManager()
        mgr.create_checkpoint("wf1", "s1", "Go?")
        mgr.create_checkpoint("wf1", "s2", "Go2?")
        pending = mgr.list_pending()
        assert len(pending) == 2

    def test_clean_completed(self):
        mgr = ApprovalManager()
        cp = mgr.create_checkpoint("wf1", "s1", "Go?")
        mgr.approve(cp.checkpoint_id)
        cleaned = mgr.clean_completed()
        assert cleaned == 1
