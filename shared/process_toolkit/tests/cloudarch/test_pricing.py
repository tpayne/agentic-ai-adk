from process_toolkit.cloudarch.pricing import _catalog_failure_reason


class _FakeNoCredentialsError(Exception):
    pass


def test_missing_credentials_message_explains_the_data_is_free_but_the_api_call_is_signed():
    _FakeNoCredentialsError.__name__ = "NoCredentialsError"
    reason = _catalog_failure_reason("AWS", _FakeNoCredentialsError())
    assert "AWS_ACCESS_KEY_ID" in reason
    assert "pricing:GetProducts" in reason
    assert "free" in reason
