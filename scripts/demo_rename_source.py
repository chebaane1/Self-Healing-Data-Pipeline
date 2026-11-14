from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_INITIALIZER = PROJECT_ROOT / "scripts" / "init_source.py"
ORIGINAL_COLUMN = "amount VARCHAR,"
RENAMED_COLUMN = "total_amount VARCHAR,"


def main() -> int:
    source = SOURCE_INITIALIZER.read_text(encoding="utf-8")
    if RENAMED_COLUMN in source:
        print("Source column is already named total_amount.")
        return 0
    if source.count(ORIGINAL_COLUMN) != 1:
        raise RuntimeError("Expected exactly one 'amount VARCHAR,' source declaration.")

    SOURCE_INITIALIZER.write_text(
        source.replace(ORIGINAL_COLUMN, RENAMED_COLUMN, 1),
        encoding="utf-8",
    )
    print("Renamed the generated source column: amount -> total_amount.")
    print("Now launch the pipeline from the app when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())