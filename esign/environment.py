"""
Resolve ENVIRONMENT and AWS_LOCATION for shared-bucket S3 prefixes.

The same S3 bucket is namespaced per deploy target via AWS_LOCATION.
STAGING_KEY_PREFIX (draft PDFs) is a document-lifecycle folder, not an environment.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

VALID_ENVIRONMENTS = ("development", "staging", "production")
PRODUCTION_AWS_LOCATION = "incel-esign-app"
AWS_LOCATION_BY_ENVIRONMENT = {
    "development": "incel-esign-dev",
    "staging": "incel-esign-staging",
    "production": PRODUCTION_AWS_LOCATION,
}


def normalize_environment(value: str | None, *, debug: bool) -> str:
    """
    Return a canonical environment name.

    Args:
        value (str | None): Raw ENVIRONMENT env var.
        debug (bool): Django DEBUG flag used when value is unset.

    Returns:
        str: One of VALID_ENVIRONMENTS.

    Raises:
        ImproperlyConfigured: If value is set but not a known environment.
    """
    if value is None or not str(value).strip():
        return "development" if debug else "production"

    normalized = str(value).strip().lower()
    if normalized not in VALID_ENVIRONMENTS:
        raise ImproperlyConfigured(
            f"ENVIRONMENT must be one of {', '.join(VALID_ENVIRONMENTS)}, got {value!r}."
        )
    return normalized


def validate_aws_location(environment: str, location: str) -> None:
    """
    Reject non-production deploys that would write under the production prefix.

    Args:
        environment (str): Canonical ENVIRONMENT value.
        location (str): Resolved AWS_LOCATION prefix.

    Raises:
        ImproperlyConfigured: If a non-production environment uses the prod prefix.
    """
    if environment != "production" and location == PRODUCTION_AWS_LOCATION:
        raise ImproperlyConfigured(
            f"ENVIRONMENT={environment!r} cannot use AWS_LOCATION={PRODUCTION_AWS_LOCATION!r}. "
            "Use incel-esign-dev or incel-esign-staging, or set ENVIRONMENT=production."
        )


def resolve_aws_location(environment: str, explicit: str | None) -> str:
    """
    Choose the S3 key prefix for this environment.

    Args:
        environment (str): Canonical ENVIRONMENT value.
        explicit (str | None): AWS_LOCATION override from env, if any.

    Returns:
        str: Bucket prefix without leading or trailing slashes.

    Raises:
        ImproperlyConfigured: If environment is unknown or the prod prefix is used off production.
    """
    if explicit is not None and str(explicit).strip():
        location = str(explicit).strip().strip("/")
    else:
        try:
            location = AWS_LOCATION_BY_ENVIRONMENT[environment]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"ENVIRONMENT must be one of {', '.join(VALID_ENVIRONMENTS)}, got {environment!r}."
            ) from exc

    validate_aws_location(environment, location)
    return location
