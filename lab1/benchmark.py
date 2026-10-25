import os
import shutil
import statistics
import tempfile
import time

from minidb import MiniDB, TYPE_INT, TYPE_STRING

REPEATS = 5
LOOKUPS = 200
ROW_COUNT = 1000


def make_bench_db(db_dir):
    if os.path.isdir(db_dir):
        shutil.rmtree(db_dir)
    db = MiniDB(db_dir)
    db.create_table(
        "bench",
        [
            {"name": "id", "type": TYPE_INT},
            {"name": "name", "type": TYPE_STRING},
        ],
        primary_key="id",
    )
    import storage as st

    rows = [[i, "row_" + str(i)] for i in range(1, ROW_COUNT + 1)]
    st.write_all_rows(db_dir, "bench", rows)
    st.set_next_id(db_dir, "bench", ROW_COUNT + 1)
    db._refresh_index("bench")
    return db


def run_sequential(db, ids):
    pk_idx = db._pk_index("bench")
    t0 = time.perf_counter()
    for rid in ids:
        storage_find = __import__("storage").find_row_by_id_sequential
        storage_find(db.db_dir, "bench", pk_idx, rid)
    return time.perf_counter() - t0


def run_indexed(db, ids):
    pk_idx = db._pk_index("bench")
    index = db._indexes["bench"]
    storage_find = __import__("storage").find_row_by_id_index
    t0 = time.perf_counter()
    for rid in ids:
        storage_find(db.db_dir, "bench", pk_idx, rid, index)
    return time.perf_counter() - t0


def main():
    base = tempfile.mkdtemp(prefix="minidb_bench_")
    try:
        db_dir = os.path.join(base, "db")
        db = make_bench_db(db_dir)
        import random

        random.seed(42)
        ids = [random.randint(1, ROW_COUNT) for _ in range(LOOKUPS)]

        seq_times = []
        idx_times = []
        for _ in range(REPEATS):
            seq_times.append(run_sequential(db, ids))
            idx_times.append(run_indexed(db, ids))

        print("MiniDB benchmark: поиск записи по id")
        print("Записей в таблице:", ROW_COUNT)
        print("Поисков за прогон:", LOOKUPS)
        print("Повторов:", REPEATS)
        print()
        print(
            "Последовательный поиск (с):",
            "min=", min(seq_times),
            "avg=", statistics.mean(seq_times),
            "max=", max(seq_times),
        )
        print(
            "Поиск по индексу (с):",
            "min=", min(idx_times),
            "avg=", statistics.mean(idx_times),
            "max=", max(idx_times),
        )
        avg_seq = statistics.mean(seq_times)
        avg_idx = statistics.mean(idx_times)
        if avg_idx > 0:
            print("Отношение avg(sequential)/avg(index):", round(avg_seq / avg_idx, 2))
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
