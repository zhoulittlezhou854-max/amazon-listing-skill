from pathlib import Path

from modules.csv_parser import parse_keyword_feedback_table


def test_parse_keyword_feedback_table_detects_sources_and_risks(tmp_path: Path):
    path = tmp_path / "feedback.csv"
    path.write_text(
        "\n".join(
            [
                "Keyword,Traffic Source,Search Volume,Conversion Rate",
                "body camera,Organic,1200,2.4",
                "helmet mount vlog camera,SP,800,1.2",
                "gopro alternative,Organic,500,0.8",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_keyword_feedback_table(str(path))

    assert parsed["summary"]["total"] == 3
    assert parsed["summary"]["organic"] == 2
    assert parsed["summary"]["sp"] == 1
    assert any(row["keyword"] == "body camera" and row["source"] == "organic" for row in parsed["rows"])
    assert any(row["keyword"] == "helmet mount vlog camera" and row["suggested_slot"] == "bullets" for row in parsed["rows"])
    assert any(row["keyword"] == "gopro alternative" and row["keep"] is False for row in parsed["rows"])
