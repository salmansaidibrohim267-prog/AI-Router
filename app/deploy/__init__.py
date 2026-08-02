"""Deployment pipeline subsystem (Stage 10.10).

Quality gates, smoke tests, rollback tests, deployment verification and
GitOps manifest validation for production rollouts.
"""

from .config import DeployConfig
from .exceptions import (
    DeployError,
    GitOpsError,
    QualityGateError,
    RollbackTestError,
    SigningGateError,
    SmokeTestError,
    VerificationError,
)
from .gates import GateResult, QualityGate, QualityGateRunner
from .gitops import DeploymentPipeline, GitOpsManifest, GitOpsValidator, create_deployment_pipeline
from .verification import (
    DeploymentVerifier,
    RollbackTester,
    SmokeResult,
    SmokeStep,
    SmokeTester,
)

__all__ = [
    "DeployConfig",
    "QualityGate",
    "GateResult",
    "QualityGateRunner",
    "SmokeStep",
    "SmokeResult",
    "SmokeTester",
    "RollbackTester",
    "DeploymentVerifier",
    "GitOpsManifest",
    "GitOpsValidator",
    "DeploymentPipeline",
    "create_deployment_pipeline",
    "DeployError",
    "QualityGateError",
    "SmokeTestError",
    "RollbackTestError",
    "VerificationError",
    "GitOpsError",
    "SigningGateError",
]
