"""
Tests for ENVIRONMENT normalization and AWS_LOCATION derivation.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured

from esign.environment import (
    normalize_environment,
    resolve_aws_location,
    validate_aws_location,
)


def test_normalize_environment_defaults_to_development_when_debug():
    assert normalize_environment(None, debug=True) == "development"
    assert normalize_environment("", debug=True) == "development"
    assert normalize_environment("   ", debug=True) == "development"


def test_normalize_environment_defaults_to_production_when_not_debug():
    assert normalize_environment(None, debug=False) == "production"


def test_normalize_environment_accepts_known_values_case_insensitively():
    assert normalize_environment(" Staging ", debug=False) == "staging"
    assert normalize_environment("DEVELOPMENT", debug=False) == "development"
    assert normalize_environment("production", debug=True) == "production"


def test_normalize_environment_rejects_unknown_values():
    with pytest.raises(ImproperlyConfigured, match="ENVIRONMENT must be one of"):
        normalize_environment("prod", debug=False)


def test_resolve_aws_location_derives_prefix_from_environment():
    assert resolve_aws_location("development", None) == "incel-esign-dev"
    assert resolve_aws_location("staging", None) == "incel-esign-staging"
    assert resolve_aws_location("production", None) == "incel-esign-app"


def test_resolve_aws_location_honors_explicit_override():
    assert resolve_aws_location("staging", " custom-prefix/ ") == "custom-prefix"


def test_resolve_aws_location_treats_blank_explicit_as_unset():
    assert resolve_aws_location("development", "") == "incel-esign-dev"


def test_validate_aws_location_blocks_non_prod_from_production_prefix():
    with pytest.raises(ImproperlyConfigured, match="incel-esign-app"):
        validate_aws_location("development", "incel-esign-app")
    with pytest.raises(ImproperlyConfigured, match="incel-esign-app"):
        resolve_aws_location("staging", "incel-esign-app")


def test_validate_aws_location_allows_production_prefix_in_production():
    validate_aws_location("production", "incel-esign-app")
    assert resolve_aws_location("production", "incel-esign-app") == "incel-esign-app"
