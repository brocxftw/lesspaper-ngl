from lesspaper_ngl.core.redaction import csv_safe, redact, redact_text


def test_recursive_redaction_removes_credentials_and_tokens() -> None:
    value = {
        "api_key": "sk-secret",
        "nested": {
            "authorization": "Bearer abc.def",
            "url": "https://example.test/callback?token=secret&safe=yes",
        },
    }
    result = redact(value)
    assert result["api_key"] == "[REDACTED]"
    assert result["nested"]["authorization"] == "[REDACTED]"
    assert "secret" not in result["nested"]["url"]
    assert "safe=yes" in result["nested"]["url"]


def test_text_and_csv_sanitization() -> None:
    assert redact_text("Bearer abc123") == "Bearer [REDACTED]"
    assert "/documents/private/file.pdf" not in redact_text("Failed /documents/private/file.pdf")
    assert csv_safe("=IMPORTXML('https://bad')").startswith("'=")
