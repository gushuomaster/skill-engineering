from pathlib import Path
import runpy


MODULE = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "run.py"))


def test_default_generation_is_self_consistent_for_srs(tmp_path: Path) -> None:
    generated = MODULE["generate"](tmp_path)

    assert tuple(path.name for path in generated) == ("SRS.docx",)
