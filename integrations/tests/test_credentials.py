"""
Unit tests for integration credential generate / hash / verify helpers.
"""

from django.test import TestCase

from integrations.services.credentials import (
    generate_client_id,
    generate_client_secret,
    hash_client_secret,
    issue_credentials,
    rotate_secret_hash,
    verify_client_secret,
)


class CredentialHelpersTest(TestCase):
    """Test cases for client secret generation, hashing, and verification."""

    def test_generate_client_id_has_prefix_and_is_unique(self):
        """client_id values start with int_ and successive calls differ."""
        first = generate_client_id()
        second = generate_client_id()
        self.assertTrue(first.startswith("int_"))
        self.assertTrue(second.startswith("int_"))
        self.assertNotEqual(first, second)

    def test_generate_client_secret_is_high_entropy(self):
        """Generated secrets are non-empty and unique across calls."""
        first = generate_client_secret()
        second = generate_client_secret()
        self.assertGreaterEqual(len(first), 32)
        self.assertNotEqual(first, second)

    def test_hash_and_verify_matching_secret(self):
        """A hashed secret verifies successfully against the original."""
        raw_secret = generate_client_secret()
        secret_hash = hash_client_secret(raw_secret)
        self.assertNotEqual(raw_secret, secret_hash)
        self.assertTrue(verify_client_secret(raw_secret, secret_hash))

    def test_verify_rejects_wrong_secret(self):
        """Verification fails when the candidate secret does not match."""
        raw_secret = generate_client_secret()
        secret_hash = hash_client_secret(raw_secret)
        self.assertFalse(verify_client_secret("definitely-wrong-secret", secret_hash))

    def test_verify_rejects_empty_inputs(self):
        """Empty secret or hash must not verify as True."""
        secret_hash = hash_client_secret(generate_client_secret())
        self.assertFalse(verify_client_secret("", secret_hash))
        self.assertFalse(verify_client_secret(generate_client_secret(), ""))
        self.assertFalse(verify_client_secret("", ""))

    def test_issue_credentials_returns_verifiable_triple(self):
        """issue_credentials returns client_id, raw secret, and matching hash."""
        client_id, raw_secret, secret_hash = issue_credentials()
        self.assertTrue(client_id.startswith("int_"))
        self.assertTrue(verify_client_secret(raw_secret, secret_hash))
        self.assertNotIn(raw_secret, secret_hash)

    def test_rotate_secret_hash_invalidates_previous(self):
        """A rotated hash verifies the new secret and rejects the old one."""
        old_secret = generate_client_secret()
        old_hash = hash_client_secret(old_secret)
        new_secret, new_hash = rotate_secret_hash()
        self.assertTrue(verify_client_secret(new_secret, new_hash))
        self.assertFalse(verify_client_secret(old_secret, new_hash))
        self.assertFalse(verify_client_secret(new_secret, old_hash))
