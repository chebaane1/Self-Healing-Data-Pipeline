from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "pipeline.duckdb"


def main():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(DATABASE_PATH))
    try:
        connection.execute(
            """
            CREATE OR REPLACE TABLE raw_orders (
                order_id INTEGER,
                customer_id INTEGER,
                amount VARCHAR,
                order_date DATE
            )
            """
        )
        connection.execute(
            """
            INSERT INTO raw_orders VALUES
                (1, 101, '49.99', DATE '2026-10-30'),
                (2, 102, '125.00', DATE '2026-10-31'),
                (3, 103, 'INVALID', DATE '2026-11-01')
            """
        )
        print(f"Created raw_orders in {DATABASE_PATH}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()