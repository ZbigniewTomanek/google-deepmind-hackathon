from pydantic_agents_playground.cli import main
from pydantic_agents_playground.pipeline import run_demo


def test_run_demo_processes_all_seed_messages_with_test_model(tmp_path, capsys) -> None:
    db_path = tmp_path / "demo.sqlite"

    summary = run_demo(str(db_path), use_test_model=True, reset_db=True)
    captured = capsys.readouterr()

    assert summary.processed_messages == 10
    assert summary.db_path == str(db_path)
    assert summary.row_counts["messages"] == 10
    assert summary.row_counts["processing_runs"] == 10
    assert "msg-001 classes=0 properties=0 canonical_facts=0 mentions=0" in captured.out
    assert "msg-010 classes=0 properties=0 canonical_facts=0 mentions=0" in captured.out


def test_cli_main_runs_demo_and_prints_final_summary(tmp_path, capsys) -> None:
    db_path = tmp_path / "cli-demo.sqlite"

    exit_code = main(["--db-path", str(db_path), "--use-test-model", "--reset-db"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert db_path.exists()
    assert "Processed 10 messages into" in captured.out
    assert "processing_runs: 10" in captured.out
