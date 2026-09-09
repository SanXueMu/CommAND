"""command_shared 纯函数测试：零外部依赖，永远可跑。"""

from command_shared.normalize import normalize_dates
from command_shared.verify import is_code_like, retranslate_prompt, verify_pair
from store.key_repo import mask_key


class TestNormalizeDates:
    def test_iso_date_replaced(self):
        norm, mapping = normalize_dates("报告出具日 2023-11-16 完成")
        assert norm == "报告出具日 [[DATE_1]] 完成"
        assert mapping == {"[[DATE_1]]": "2023-11-16"}

    def test_multiple_dates_numbered(self):
        norm, mapping = normalize_dates("2023/11/16 至 2023/12/31")
        assert "[[DATE_1]]" in norm and "[[DATE_2]]" in norm
        assert len(mapping) == 2

    def test_dmy_date(self):
        norm, mapping = normalize_dates("16/11/2023")
        assert norm == "[[DATE_1]]"
        assert mapping == {"[[DATE_1]]": "16/11/2023"}

    def test_no_date_untouched(self):
        assert normalize_dates("no dates here") == ("no dates here", {})


class TestIsCodeLike:
    def test_pure_digits(self):
        assert is_code_like("141002401003677") is True
        assert is_code_like("3,361.215") is True

    def test_code_string(self):
        assert is_code_like("PO202004291012") is True
        assert is_code_like("KTD2V79R-D6") is True

    def test_translatable_not_code(self):
        assert is_code_like("Audit Report") is False
        assert is_code_like("hello world 123") is False
        assert is_code_like("") is False


class TestVerifyPair:
    def test_number_missing_fails(self):
        ok, reason = verify_pair("发票金额 12,000 元", "发票金额元")
        assert ok is False and reason.startswith("missing_number:")

    def test_placeholder_preserved_passes(self):
        assert verify_pair("日期 [[DATE_1]]", "Date [[DATE_1]]") == (True, "")

    def test_placeholder_lost_fails(self):
        ok, reason = verify_pair("日期 [[DATE_1]]", "日期")
        assert ok is False and reason.startswith("missing_placeholder:")

    def test_no_letter_must_be_identical(self):
        assert verify_pair("2644", "2644") == (True, "")
        assert verify_pair("2644", "2650")[0] is False

    def test_untranslated_english_fails(self):
        ok, reason = verify_pair("Audit Report of Financial Statements", "Audit Report of Financial Statements")
        assert ok is False and reason == "untranslated"

    def test_truncated_long_text_fails(self):
        src = "The auditor shall perform the audit in accordance with the standards. " * 2
        assert verify_pair(src, "短译文")[1] == "truncated"

    def test_empty_source_passes(self):
        assert verify_pair("", "") == (True, "")


class TestRetranslatePrompt:
    def test_hint_for_known_reason(self):
        prompt = retranslate_prompt("Hello world", "untranslated")
        assert prompt.startswith("The text was left untranslated")

    def test_unknown_reason_returns_source(self):
        assert retranslate_prompt("abc", "weird:1") == "abc"


class TestMaskKey:
    def test_long_key_shows_last4(self):
        assert mask_key("sk-1234567890") == "****7890"

    def test_short_key_fully_masked(self):
        assert mask_key("abc") == "****"
