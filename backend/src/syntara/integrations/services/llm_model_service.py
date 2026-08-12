"""LLM Model Service for CRUD operations on discovered LLM models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

import structlog
from sqlalchemy import func
from sqlmodel import col, select, update

from syntara.core.exceptions import SafeValueError
from syntara.core.services import BaseService
from syntara.integrations.exceptions import LLMModelNotFoundError
from syntara.integrations.models.llm_model import (
    LLMModel,
    LLMModelBulkUpdateResponse,
    LLMModelListResponse,
    LLMModelRead,
    LLMModelUpdate,
)

logger = structlog.stdlib.get_logger(__name__)


class LLMModelService(BaseService):
    """Service for LLM model list/update/bulk operations."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and user context."""
        super().__init__(session, user)

    async def _get_model_detail_for_integration(self, integration_id: UUID, model_id: UUID) -> LLMModel:
        """Fetch a model and verify it belongs to the specified integration."""
        model = await self.session.get(LLMModel, model_id)
        if not model or model.integration_id != integration_id:
            logger.warning(
                "LLM model not found for integration",
                model_id=str(model_id),
                integration_id=str(integration_id),
            )
            raise LLMModelNotFoundError(model_id)
        return model

    async def list_models(
        self,
        limit: int = 100,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> LLMModelListResponse:
        """List LLM models with filtering, sorting, and pagination."""
        return await self.list_resources(
            model=LLMModel,
            response_type=LLMModelListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=query_params_items,
            include_total=include_total,
        )

    async def get_model_detail(self, integration_id: UUID, model_id: UUID) -> LLMModelRead:
        """Get an LLM model by ID, scoped to an integration."""
        model = await self._get_model_detail_for_integration(integration_id, model_id)
        return LLMModelRead.model_validate(model)

    async def update_model(
        self,
        integration_id: UUID,
        model_id: UUID,
        data: LLMModelUpdate,
    ) -> LLMModelRead:
        """Update an LLM model (enable/disable, set as default), scoped to an integration."""
        model = await self._get_model_detail_for_integration(integration_id, model_id)
        if data.is_default is True:
            effective_enabled = data.enabled if data.enabled is not None else model.enabled
            if not effective_enabled:
                msg = "Cannot set a disabled model as default"
                raise SafeValueError(msg)
            await self.session.exec(
                update(LLMModel)
                .where(
                    LLMModel.integration_id == integration_id,  # type: ignore[arg-type]
                    col(LLMModel.id) != model_id,
                )
                .values(is_default=False)
            )
            logger.info(
                "Cleared previous default model",
                integration_id=str(integration_id),
                new_default_model_id=str(model_id),
            )
        elif data.is_default is False and model.is_default is True:
            logger.warning(
                "Unsetting default model — integration will have no default",
                integration_id=str(integration_id),
                model_id=str(model_id),
            )
        if data.enabled is False and model.is_default:
            model.is_default = False
            logger.info(
                "Clearing default flag on disabled model",
                integration_id=str(integration_id),
                model_id=str(model_id),
            )
        for field in data.model_fields_set:
            value = getattr(data, field)
            if value is not None:
                setattr(model, field, value)
        model.updated_at = datetime.now(UTC)
        await self.session.commit()
        logger.info(
            "Updated LLM model",
            model_id=str(model_id),
            integration_id=str(integration_id),
            updated_fields=list(data.model_fields_set),
        )
        return LLMModelRead.model_validate(model)

    async def bulk_update_models(
        self,
        integration_id: UUID,
        model_ids: list[UUID],
        *,
        enabled: bool,
    ) -> LLMModelBulkUpdateResponse:
        """Bulk enable/disable LLM models, scoped to an integration."""
        now = datetime.now(UTC)
        count_query = (
            select(func.count())
            .select_from(LLMModel)
            .where(
                col(LLMModel.id).in_(model_ids),
                LLMModel.integration_id == integration_id,
            )
        )
        total_matching = await self.session.scalar(count_query) or 0

        skipped_count = len(model_ids) - total_matching
        if skipped_count > 0:
            logger.warning(
                "Bulk update included model IDs not found in integration",
                integration_id=str(integration_id),
                requested_count=len(model_ids),
                not_found_count=skipped_count,
                enabled=enabled,
            )

        await self.session.exec(
            update(LLMModel)
            .where(
                col(LLMModel.id).in_(model_ids),
                LLMModel.integration_id == integration_id,  # type: ignore[arg-type]
            )
            .values(enabled=enabled, updated_at=now)
        )
        if not enabled:
            await self.session.exec(
                update(LLMModel)
                .where(
                    col(LLMModel.id).in_(model_ids),
                    LLMModel.integration_id == integration_id,  # type: ignore[arg-type]
                    col(LLMModel.is_default).is_(True),
                )
                .values(is_default=False)
            )
        await self.session.commit()
        logger.info(
            "Bulk update completed",
            integration_id=str(integration_id),
            updated_count=total_matching,
            skipped_count=skipped_count,
            enabled=enabled,
        )
        return LLMModelBulkUpdateResponse(
            updated_count=total_matching,
            skipped_count=skipped_count,
            updated_at=now,
        )
