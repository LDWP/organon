"""TLS trust of the WFO adapter (issue #54)."""

from __future__ import annotations

from organon.modules.wfo.adapter import WfoAdapter


def _subject_cns(adapter: WfoAdapter) -> set[str]:
    ctx = adapter._client._transport._pool._ssl_context  # type: ignore[attr-defined]
    return {
        value
        for cert in ctx.get_ca_certs()
        for rdn in cert["subject"]
        for key, value in rdn
        if key == "commonName"
    }


async def test_trusts_geotrust_intermediate_missing_from_server_chain():
    """list.worldfloraonline.org sends only its leaf certificate."""
    async with WfoAdapter() as adapter:
        cns = _subject_cns(adapter)
    assert "GeoTrust TLS RSA CA G1" in cns
    assert "DigiCert Global Root G2" in cns  # public roots stay trusted
