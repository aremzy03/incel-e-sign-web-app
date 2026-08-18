"""
Tests for S3 signing-artifact cleanup during workflow reset.
"""

import uuid
from unittest.mock import MagicMock, patch

from signatures.services.reset_workflow import _delete_signing_artifacts_for_document


def test_delete_signing_artifacts_prefixes_list_with_aws_location(settings):
    settings.USE_S3 = True
    settings.AWS_LOCATION = "incel-esign-dev"
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"

    envelope_id = uuid.uuid4()
    document_id = uuid.uuid4()
    object_key = f"incel-esign-dev/signing/{envelope_id}/{document_id}/v1.pdf"

    mock_client = MagicMock()
    mock_client.list_objects_v2.return_value = {
        "Contents": [{"Key": object_key}],
        "IsTruncated": False,
    }

    with patch(
        "signatures.services.reset_workflow.get_boto3_s3_client",
        return_value=mock_client,
    ):
        deleted = _delete_signing_artifacts_for_document(
            envelope_id=envelope_id,
            document_id=document_id,
        )

    assert deleted == 1
    mock_client.list_objects_v2.assert_called_once_with(
        Bucket="test-bucket",
        Prefix=f"incel-esign-dev/signing/{envelope_id}/{document_id}/",
    )
    mock_client.delete_objects.assert_called_once_with(
        Bucket="test-bucket",
        Delete={"Objects": [{"Key": object_key}]},
    )
