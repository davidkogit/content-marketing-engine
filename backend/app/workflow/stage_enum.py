"""
Workflow stage enum — canonical import point for the workflow package.

Re-exports the ``WorkflowStage`` enum from the models layer so that the
workflow engine and its consumers have a dedicated, discoverable import
path without coupling directly to the ORM model module.
"""

from app.models.product import WorkflowStage

__all__ = ["WorkflowStage"]
