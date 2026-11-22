from app.core import i18n


def test_ar_en_same_keys():
    assert set(i18n.AR) == set(i18n.EN)


def test_placeholders_match():
    import re
    for k in i18n.EN:
        assert sorted(re.findall(r"\{\w+\}", i18n.EN[k])) == sorted(re.findall(r"\{\w+\}", i18n.AR[k])), k
