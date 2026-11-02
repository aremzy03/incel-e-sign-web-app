"""
IntegrationUserLink upsert helpers.

Maps a partner external_user_id to an e-sign CustomUser per integration.
"""

from __future__ import annotations

import logging

from django.db import transaction

from integrations.models import Integration, IntegrationUserLink

logger = logging.getLogger(__name__)


def upsert_integration_user_link(
    *,
    integration: Integration,
    user,
    external_user_id: str,
) -> IntegrationUserLink:
    """
    Upsert a stable partner-user link after token exchange resolves a user.

    Lookup prefers ``(integration, external_user_id)``. If that row is missing
    but the user already has a link for this integration, the external id is
    updated. Unique ``(integration, user)`` is preserved.

    Args:
        integration: The authenticated Integration.
        user: Resolved CustomUser.
        external_user_id: Partner's stable user identifier.

    Returns:
        IntegrationUserLink: The created or updated link row.
    """
    external_user_id = (external_user_id or "").strip()
    if not external_user_id:
        raise ValueError("external_user_id must be non-empty")

    with transaction.atomic():
        link = (
            IntegrationUserLink.objects.select_for_update()
            .filter(integration=integration, external_user_id=external_user_id)
            .first()
        )
        if link is not None:
            if link.user_id != user.id:
                # Free the (integration, user) slot if another row holds it.
                IntegrationUserLink.objects.filter(
                    integration=integration,
                    user=user,
                ).exclude(pk=link.pk).delete()
                link.user = user
                link.save(update_fields=["user"])
                logger.info(
                    "Updated IntegrationUserLink user client_id=%s link_id=%s",
                    integration.client_id,
                    link.id,
                )
            return link

        link = (
            IntegrationUserLink.objects.select_for_update()
            .filter(integration=integration, user=user)
            .first()
        )
        if link is not None:
            link.external_user_id = external_user_id
            link.save(update_fields=["external_user_id"])
            logger.info(
                "Updated IntegrationUserLink external_user_id client_id=%s link_id=%s",
                integration.client_id,
                link.id,
            )
            return link

        link = IntegrationUserLink.objects.create(
            integration=integration,
            user=user,
            external_user_id=external_user_id,
        )
        logger.info(
            "Created IntegrationUserLink client_id=%s link_id=%s",
            integration.client_id,
            link.id,
        )
        return link
