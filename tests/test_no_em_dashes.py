"""The tileset has no em dash glyph, so the project writes plain hyphens everywhere."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)
TEXT_SUFFIXES = {".py", ".md", ".js", ".html", ".css", ".toml", ".txt", ".json", ".yml", ".yaml"}


def _tracked_text_files() -> list[Path]:
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / name for name in listed.splitlines() if Path(name).suffix in TEXT_SUFFIXES]


def test_no_tracked_file_contains_an_em_dash():
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in _tracked_text_files()
        if path.exists()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if EM_DASH in line
    ]
    assert not offenders, f"{len(offenders)} lines contain an em dash, e.g. {offenders[:5]}"
