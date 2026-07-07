"""
Unit tests for the Kanban workflow state machine.

Covers all valid transitions, role enforcement, super-admin reset
capabilities, and edge cases for both ``can_transition`` and
``transition`` methods.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import User, UserRole
from app.workflow.stage_enum import WorkflowStage
from app.workflow.workflow_engine import WorkflowEngine, WorkflowError


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_product(stage: WorkflowStage) -> MagicMock:
    """Create a mock Product with the given workflow_stage."""
    product = MagicMock()
    product.id = 1
    product.sku = "SKU-001"
    product.name = "Test Product"
    product.description = "A test product description"
    product.category_id = None
    product.segment_id = None
    product.workflow_stage = stage
    return product


def _make_user(role: UserRole) -> MagicMock:
    """Create a mock User with the given role."""
    user = MagicMock(spec=User)
    user.id = 42
    user.role = role
    return user


# ══════════════════════════════════════════════════════════════════════════════
# can_transition — valid transitions
# ══════════════════════════════════════════════════════════════════════════════


class TestCanTransitionValid:
    """Every structurally valid transition with the correct minimum role."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    @pytest.mark.parametrize(
        "user_role",
        [UserRole.EDITOR, UserRole.ADMIN, UserRole.SUPER_ADMIN],
    )
    def test_ingest_to_draft_editor_and_above(self, user_role: UserRole) -> None:
        """Editors, admins, and super_admins can move ingest → draft."""
        product = _make_product(WorkflowStage.INGEST)
        assert self.engine.can_transition(
            product, WorkflowStage.INGEST, WorkflowStage.DRAFT, user_role
        ) is True

    @pytest.mark.parametrize(
        "user_role",
        [UserRole.EDITOR, UserRole.ADMIN, UserRole.SUPER_ADMIN],
    )
    def test_draft_to_review_editor_and_above(self, user_role: UserRole) -> None:
        """Editors, admins, and super_admins can move draft → review."""
        product = _make_product(WorkflowStage.DRAFT)
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.REVIEW, user_role
        ) is True

    @pytest.mark.parametrize(
        "user_role",
        [UserRole.ADMIN, UserRole.SUPER_ADMIN],
    )
    def test_review_to_approved_admin_and_above(self, user_role: UserRole) -> None:
        """Only admins (and above) can approve a review."""
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.APPROVED, user_role
        ) is True

    @pytest.mark.parametrize(
        "user_role",
        [UserRole.EDITOR, UserRole.ADMIN, UserRole.SUPER_ADMIN],
    )
    def test_review_to_draft_request_changes(self, user_role: UserRole) -> None:
        """Editors and above can request changes (review → draft)."""
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.DRAFT, user_role
        ) is True

    @pytest.mark.parametrize(
        "user_role",
        [UserRole.ADMIN, UserRole.SUPER_ADMIN],
    )
    def test_approved_to_exported_admin_and_above(self, user_role: UserRole) -> None:
        """Only admins (and above) can export approved content."""
        product = _make_product(WorkflowStage.APPROVED)
        assert self.engine.can_transition(
            product, WorkflowStage.APPROVED, WorkflowStage.EXPORTED, user_role
        ) is True


class TestCanTransitionSuperAdminReset:
    """Super admin can reset *any* stage back to INGEST."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    @pytest.mark.parametrize(
        "from_stage",
        [
            WorkflowStage.INGEST,
            WorkflowStage.DRAFT,
            WorkflowStage.REVIEW,
            WorkflowStage.APPROVED,
            WorkflowStage.EXPORTED,
        ],
    )
    def test_super_admin_can_reset_any_stage(self, from_stage: WorkflowStage) -> None:
        """Super admin may move any stage → ingest (except ingest → ingest)."""
        product = _make_product(from_stage)
        assert self.engine.can_transition(
            product, from_stage, WorkflowStage.INGEST, UserRole.SUPER_ADMIN
        ) is True

    def test_super_admin_can_do_nonstandard_transition(self) -> None:
        """Super admin bypasses all gating — even transitions not in the
        normal DAG (e.g. draft → approved directly)."""
        product = _make_product(WorkflowStage.DRAFT)
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.APPROVED, UserRole.SUPER_ADMIN
        ) is True


# ══════════════════════════════════════════════════════════════════════════════
# can_transition — invalid transitions
# ══════════════════════════════════════════════════════════════════════════════


class TestCanTransitionInvalidSameStage:
    """Moving to the same stage is always invalid."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    @pytest.mark.parametrize("stage", list(WorkflowStage))
    def test_same_stage_returns_false_for_viewer(self, stage: WorkflowStage) -> None:
        product = _make_product(stage)
        assert self.engine.can_transition(product, stage, stage, UserRole.VIEWER) is False

    @pytest.mark.parametrize("stage", list(WorkflowStage))
    def test_same_stage_returns_false_for_editor(self, stage: WorkflowStage) -> None:
        product = _make_product(stage)
        assert self.engine.can_transition(product, stage, stage, UserRole.EDITOR) is False

    @pytest.mark.parametrize("stage", list(WorkflowStage))
    def test_same_stage_returns_false_for_admin(self, stage: WorkflowStage) -> None:
        product = _make_product(stage)
        assert self.engine.can_transition(product, stage, stage, UserRole.ADMIN) is False

    @pytest.mark.parametrize("stage", list(WorkflowStage))
    def test_same_stage_returns_false_for_super_admin(self, stage: WorkflowStage) -> None:
        product = _make_product(stage)
        assert self.engine.can_transition(
            product, stage, stage, UserRole.SUPER_ADMIN
        ) is False


class TestCanTransitionInvalidWrongDirection:
    """Transitions that skip stages or go backwards (without reset) are invalid."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    def test_ingest_to_review_skip_draft(self) -> None:
        """Cannot jump from ingest straight to review."""
        product = _make_product(WorkflowStage.INGEST)
        assert self.engine.can_transition(
            product, WorkflowStage.INGEST, WorkflowStage.REVIEW, UserRole.ADMIN
        ) is False

    def test_draft_to_approved_skip_review(self) -> None:
        """Cannot jump from draft straight to approved."""
        product = _make_product(WorkflowStage.DRAFT)
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.APPROVED, UserRole.ADMIN
        ) is False

    def test_review_to_exported_skip_approved(self) -> None:
        """Cannot jump from review straight to exported."""
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.EXPORTED, UserRole.ADMIN
        ) is False

    def test_exported_to_draft_not_allowed(self) -> None:
        """Cannot go backwards from exported to draft (except reset)."""
        product = _make_product(WorkflowStage.EXPORTED)
        assert self.engine.can_transition(
            product, WorkflowStage.EXPORTED, WorkflowStage.DRAFT, UserRole.ADMIN
        ) is False

    def test_exported_to_review_not_allowed(self) -> None:
        """Cannot go backwards from exported to review (except reset)."""
        product = _make_product(WorkflowStage.EXPORTED)
        assert self.engine.can_transition(
            product, WorkflowStage.EXPORTED, WorkflowStage.REVIEW, UserRole.ADMIN
        ) is False

    def test_approved_to_draft_not_allowed(self) -> None:
        """Cannot go backwards from approved to draft (except reset)."""
        product = _make_product(WorkflowStage.APPROVED)
        assert self.engine.can_transition(
            product, WorkflowStage.APPROVED, WorkflowStage.DRAFT, UserRole.ADMIN
        ) is False


# ══════════════════════════════════════════════════════════════════════════════
# can_transition — role enforcement
# ══════════════════════════════════════════════════════════════════════════════


class TestCanTransitionRoleEnforcementViewer:
    """A VIEWER cannot perform any transition (including reset)."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    def test_viewer_cannot_ingest_to_draft(self) -> None:
        product = _make_product(WorkflowStage.INGEST)
        assert self.engine.can_transition(
            product, WorkflowStage.INGEST, WorkflowStage.DRAFT, UserRole.VIEWER
        ) is False

    def test_viewer_cannot_draft_to_review(self) -> None:
        product = _make_product(WorkflowStage.DRAFT)
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.REVIEW, UserRole.VIEWER
        ) is False

    def test_viewer_cannot_review_to_approved(self) -> None:
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.APPROVED, UserRole.VIEWER
        ) is False

    def test_viewer_cannot_request_changes(self) -> None:
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.DRAFT, UserRole.VIEWER
        ) is False

    def test_viewer_cannot_approved_to_exported(self) -> None:
        product = _make_product(WorkflowStage.APPROVED)
        assert self.engine.can_transition(
            product, WorkflowStage.APPROVED, WorkflowStage.EXPORTED, UserRole.VIEWER
        ) is False

    def test_viewer_cannot_reset(self) -> None:
        """Viewers cannot reset to ingest from any stage."""
        product = _make_product(WorkflowStage.DRAFT)
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.INGEST, UserRole.VIEWER
        ) is False


class TestCanTransitionRoleEnforcementEditor:
    """An EDITOR can do ingest→draft, draft→review, review→draft
    but NOT review→approved, approved→exported, or reset."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    def test_editor_cannot_review_to_approved(self) -> None:
        """Editors cannot approve — that requires admin."""
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.APPROVED, UserRole.EDITOR
        ) is False

    def test_editor_cannot_approved_to_exported(self) -> None:
        """Editors cannot export — that requires admin."""
        product = _make_product(WorkflowStage.APPROVED)
        assert self.engine.can_transition(
            product, WorkflowStage.APPROVED, WorkflowStage.EXPORTED, UserRole.EDITOR
        ) is False

    def test_editor_cannot_reset(self) -> None:
        """Editors cannot reset to ingest — super_admin only."""
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.INGEST, UserRole.EDITOR
        ) is False


class TestCanTransitionRoleEnforcementAdmin:
    """An ADMIN can do everything except reset (super_admin only)."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    def test_admin_cannot_reset_draft_to_ingest(self) -> None:
        product = _make_product(WorkflowStage.DRAFT)
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.INGEST, UserRole.ADMIN
        ) is False

    def test_admin_cannot_reset_review_to_ingest(self) -> None:
        product = _make_product(WorkflowStage.REVIEW)
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.INGEST, UserRole.ADMIN
        ) is False

    def test_admin_cannot_reset_exported_to_ingest(self) -> None:
        product = _make_product(WorkflowStage.EXPORTED)
        assert self.engine.can_transition(
            product, WorkflowStage.EXPORTED, WorkflowStage.INGEST, UserRole.ADMIN
        ) is False

    def test_admin_can_do_all_normal_transitions(self) -> None:
        """Admin can do ingest→draft, draft→review, review→approved,
        approved→exported."""
        product = _make_product(WorkflowStage.INGEST)
        assert self.engine.can_transition(
            product, WorkflowStage.INGEST, WorkflowStage.DRAFT, UserRole.ADMIN
        ) is True
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.REVIEW, UserRole.ADMIN
        ) is True
        assert self.engine.can_transition(
            product, WorkflowStage.REVIEW, WorkflowStage.APPROVED, UserRole.ADMIN
        ) is True
        assert self.engine.can_transition(
            product, WorkflowStage.APPROVED, WorkflowStage.EXPORTED, UserRole.ADMIN
        ) is True


# ══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestCanTransitionEdgeCases:
    """Edge-case behaviours for the permission gate."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    def test_exported_has_no_forward_transitions(self) -> None:
        """Once exported, the only valid transition is reset (super_admin only)."""
        product = _make_product(WorkflowStage.EXPORTED)
        for stage in WorkflowStage:
            if stage == WorkflowStage.INGEST:
                # Reset — only super_admin
                assert self.engine.can_transition(
                    product, WorkflowStage.EXPORTED, stage, UserRole.ADMIN
                ) is False
            else:
                assert self.engine.can_transition(
                    product, WorkflowStage.EXPORTED, stage, UserRole.ADMIN
                ) is False

    def test_product_parameter_does_not_affect_result(self) -> None:
        """can_transition ignores product state — it relies on from_stage."""
        # Even if product says EXPORTED but from_stage says DRAFT, the
        # DRAFT rules apply.
        product = _make_product(WorkflowStage.EXPORTED)
        assert self.engine.can_transition(
            product, WorkflowStage.DRAFT, WorkflowStage.REVIEW, UserRole.EDITOR
        ) is True


# ══════════════════════════════════════════════════════════════════════════════
# transition — integration-style tests
# ══════════════════════════════════════════════════════════════════════════════


class TestTransition:
    """Integration tests for the async ``transition`` method."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.engine = WorkflowEngine()

    @pytest.mark.asyncio
    async def test_valid_transition_updates_stage(self) -> None:
        """A valid transition advances the product's workflow_stage."""
        product = _make_product(WorkflowStage.INGEST)
        user = _make_user(UserRole.EDITOR)
        db = AsyncMock()

        # Simulate the max-version query returning 0 (no versions yet).
        db.execute.return_value.scalar_one.return_value = 0

        result = await self.engine.transition(
            product, WorkflowStage.DRAFT, user, db
        )

        assert result is product
        assert product.workflow_stage == WorkflowStage.DRAFT
        db.add.assert_called_once()  # a ProductVersion was added
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transition_writes_version_with_stage_metadata(self) -> None:
        """The ``ProductVersion`` row captures who, when, stages, and comment."""
        product = _make_product(WorkflowStage.DRAFT)
        user = _make_user(UserRole.EDITOR)
        db = AsyncMock()
        db.execute.return_value.scalar_one.return_value = 2  # previous max = 2

        await self.engine.transition(
            product, WorkflowStage.REVIEW, user, db, comment="Ready for PM"
        )

        # The version added to the session.
        args, _kwargs = db.add.call_args
        version = args[0]
        assert version.product_id == product.id
        assert version.version_number == 3  # max+1
        assert version.created_by == user.id
        assert "draft → review" in version.change_summary
        assert "Ready for PM" in version.change_summary
        snapshot = version.snapshot_json
        assert "draft" in snapshot  # original stage captured in snapshot

    @pytest.mark.asyncio
    async def test_transition_without_comment_omits_comment_field(self) -> None:
        """When no comment is provided, the summary still records stage info."""
        product = _make_product(WorkflowStage.REVIEW)
        user = _make_user(UserRole.ADMIN)
        db = AsyncMock()
        db.execute.return_value.scalar_one.return_value = 5

        await self.engine.transition(
            product, WorkflowStage.APPROVED, user, db
        )

        args, _kwargs = db.add.call_args
        version = args[0]
        assert "review → approved" in version.change_summary
        assert "Comment:" not in version.change_summary

    @pytest.mark.asyncio
    async def test_invalid_transition_raises_workflow_error(self) -> None:
        """Attempting a disallowed move raises ``WorkflowError``."""
        product = _make_product(WorkflowStage.REVIEW)
        user = _make_user(UserRole.EDITOR)  # editor can't approve
        db = AsyncMock()

        with pytest.raises(WorkflowError) as exc_info:
            await self.engine.transition(
                product, WorkflowStage.APPROVED, user, db
            )

        error = exc_info.value
        assert error.from_stage == WorkflowStage.REVIEW
        assert error.to_stage == WorkflowStage.APPROVED
        assert error.user_role == UserRole.EDITOR

    @pytest.mark.asyncio
    async def test_invalid_transition_does_not_touch_db(self) -> None:
        """When validation fails, no version is written and stage is unchanged."""
        original_stage = WorkflowStage.REVIEW
        product = _make_product(original_stage)
        user = _make_user(UserRole.EDITOR)
        db = AsyncMock()

        with pytest.raises(WorkflowError):
            await self.engine.transition(
                product, WorkflowStage.APPROVED, user, db
            )

        assert product.workflow_stage == original_stage
        db.add.assert_not_called()
        db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_transition_enforces_reset_gate(self) -> None:
        """A non-super_admin cannot reset to ingest via transition either."""
        product = _make_product(WorkflowStage.EXPORTED)
        user = _make_user(UserRole.ADMIN)
        db = AsyncMock()

        with pytest.raises(WorkflowError) as exc_info:
            await self.engine.transition(
                product, WorkflowStage.INGEST, user, db
            )

        assert "Reset requires super_admin" in exc_info.value.reason
