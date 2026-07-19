import json
from email.message import Message
from unittest.mock import patch

from tender_radar.sources.kimdis_connected_acts import (
    connected_acts_chain_url,
    connected_attachment_url,
    fetch_kimdis_connected_acts,
    parse_connected_acts_chain,
)


def test_connected_acts_request_urls() -> None:
    assert (
        connected_acts_chain_url("26PROC019367864")
        == "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/adamChain/26PROC019367864"
    )
    assert (
        connected_attachment_url("26PROC019367864")
        == "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/notice/attachment/26PROC019367864"
    )
    assert (
        connected_attachment_url("26AWRD019307980")
        == "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/auction/attachment/26AWRD019307980"
    )


def test_parse_connected_acts_chain_from_fixture() -> None:
    chain = parse_connected_acts_chain(
        json.dumps(
            {
                "requests": ["26REQ018840372"],
                "approvedRequests": ["26REQ018840419"],
                "notices": ["26PROC019367864"],
                "auctions": [],
                "contracts": ["26SYMV019000001"],
                "payments": None,
            }
        )
    )

    assert chain == {
        "requests": ["26REQ018840372"],
        "approvedRequests": ["26REQ018840419"],
        "notices": ["26PROC019367864"],
        "auctions": [],
        "contracts": ["26SYMV019000001"],
        "payments": [],
    }


def test_fetch_connected_acts_extracts_eshidis_from_linked_document(tmp_path) -> None:
    class Response:
        def __init__(self, body: bytes, content_type: str = "application/json") -> None:
            self._body = body
            self.headers = Message()
            self.headers["Content-Type"] = content_type

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return self._body

    chain_body = json.dumps(
        {
            "requests": ["26REQ018840372"],
            "approvedRequests": [],
            "notices": ["26PROC019367864"],
            "auctions": [],
            "contracts": [],
            "payments": [],
        }
    ).encode()
    document_body = (
        "Άρθρο 2.2 μέσω URL "
        "http://pwgopendata.eprocurement.gov.gr/actSearchErgwn/resources/search/221566"
    ).encode("utf-8")

    def fake_urlopen(request, timeout=None, context=None):
        url = request.full_url
        if "adamChain" in url:
            return Response(chain_body)
        return Response(document_body, content_type="application/xml")

    with patch("tender_radar.sources.kimdis_connected_acts.urlopen", side_effect=fake_urlopen):
        result = fetch_kimdis_connected_acts(
            "26PROC019367864",
            download_dir=tmp_path / "downloads",
            text_dir=tmp_path / "text",
        )

    assert result.chain_status == "FETCHED"
    assert result.linked_eshidis_ids == ["221566"]
    assert len(result.attachment_results) == 2
    assert result.attachment_results[0].local_path
