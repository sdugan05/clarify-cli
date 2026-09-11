from __future__ import annotations

import pytest

from clarify_cli.errors import UsageError
from clarify_cli.params import parse_csv_list, parse_filters, parse_kv, parse_sort


def test_parse_filters_variants():
    assert parse_filters(["stage=Won"]) == [("filter[stage]", "Won")]
    assert parse_filters(["amount[Greater than]=50000"]) == [
        ("filter[amount][Greater than]", "50000")
    ]
    assert parse_filters(["name=*Smith*", "x=null"]) == [
        ("filter[name]", "*Smith*"),
        ("filter[x]", "null"),
    ]
    assert parse_filters(["email_addresses[Contains]=@acme.com"]) == [
        ("filter[email_addresses][Contains]", "@acme.com")
    ]
    assert parse_filters(["person.company_id.name=Acme"]) == [
        ("filter[person.company_id.name]", "Acme")
    ]
    assert parse_filters(["filter[raw][Is]=v"]) == [("filter[raw][Is]", "v")]
    assert parse_filters(["a=b=c"]) == [("filter[a]", "b=c")]
    assert parse_filters(None) == []


@pytest.mark.parametrize("bad", ["novalue", "=x", "a[b]c=1", "[x]=1"])
def test_parse_filters_rejects_bad_input(bad):
    with pytest.raises(UsageError):
        parse_filters([bad])


def test_parse_sort_variants():
    assert parse_sort(None) == []
    assert parse_sort("amount") == [("sortOrder[column]", "amount"), ("sortOrder[dir]", "ASC")]
    assert parse_sort("amount:desc") == [
        ("sortOrder[column]", "amount"),
        ("sortOrder[dir]", "DESC"),
    ]
    assert parse_sort("-amount") == [("sortOrder[column]", "amount"), ("sortOrder[dir]", "DESC")]
    assert parse_sort("_created_at:ASC")[1] == ("sortOrder[dir]", "ASC")


@pytest.mark.parametrize("bad", ["amount:sideways", ":desc", "-"])
def test_parse_sort_rejects_bad_input(bad):
    with pytest.raises(UsageError):
        parse_sort(bad)


def test_parse_kv_and_csv_list():
    assert parse_kv(["page[limit]=5", "k=a=b"]) == [("page[limit]", "5"), ("k", "a=b")]
    with pytest.raises(UsageError):
        parse_kv(["nope"])
    assert parse_csv_list(" a, b ,,c") == ["a", "b", "c"]
    assert parse_csv_list(None) == []
