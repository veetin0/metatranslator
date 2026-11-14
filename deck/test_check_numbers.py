import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_numbers as cn  # noqa: E402


def test_decimal_and_percent_claims_match_rounded_results():
    text = "top-1 0.51 and 94% and 75.5%"
    assert cn.unmatched(text, [0.5123, 0.9401, 0.7546]) == []


def test_unknown_number_is_reported():
    assert cn.unmatched("accuracy 0.99", [0.5123]) == ["0.99"]
    assert cn.unmatched("accuracy 88%", [0.5123]) == ["88%"]


def test_css_and_comments_are_ignored(tmp_path):
    p = tmp_path / "d.html"
    p.write_text("<style>.a{opacity:0.5;width:50%}</style><!-- 0.77 --><p>hello</p>")
    assert cn.claims(cn.deck_text(str(p))) == []


def test_headline_values_collected_per_class_ignored(tmp_path):
    (tmp_path / "m9.json").write_text(
        '{"top1": 0.94, "bigru": {"top3": 0.98}, "per_class": {"A": {"top1": 0.3}}, "ok": true}')
    vals = cn.result_values(str(tmp_path))
    assert 0.94 in vals and 0.98 in vals and 0.3 not in vals
