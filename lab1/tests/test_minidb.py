import os
import shutil
import tempfile
import unittest

from minidb import Condition, Filter, MiniDB, MiniDBError, init_default_schema
import storage


class TestMiniDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="minidb_test_")
        self.db = MiniDB(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_persistence(self):
        self.db.create_table(
            "t",
            [{"name": "id", "type": "INT"}, {"name": "name", "type": "STRING"}],
            primary_key="id",
        )
        self.db.insert("t", {"name": "hello"})
        db2 = MiniDB(self.tmp)
        rows = db2.select("t")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "hello")

    def test_crud(self):
        init_default_schema(self.db)
        did = self.db.insert("datasets", {"name": "A", "task": "cls", "size": 100})
        self.db.update("datasets", did, {"size": 200})
        row = self.db.get_by_id("datasets", did)
        self.assertEqual(row["size"], 200)
        self.db.delete("datasets", did)
        self.assertIsNone(self.db.get_by_id("datasets", did))

    def test_types(self):
        init_default_schema(self.db)
        with self.assertRaises(MiniDBError):
            self.db.insert("datasets", {"name": "X", "task": "t", "size": "not_int"})
        did = self.db.insert("datasets", {"name": "D", "task": "t", "size": 1})
        mid = self.db.insert("models", {"name": "M", "version": "1"})
        self.db.insert(
            "experiments",
            {"dataset_id": did, "model_id": mid, "accuracy": 0.5, "status": "ok"},
        )
        with self.assertRaises(MiniDBError):
            self.db.insert(
                "experiments",
                {"dataset_id": 999, "model_id": mid, "accuracy": 0.1, "status": "x"},
            )

    def test_pk_auto_and_duplicate(self):
        self.db.create_table(
            "t",
            [{"name": "id", "type": "INT"}, {"name": "v", "type": "INT"}],
            primary_key="id",
        )
        a = self.db.insert("t", {"v": 1})
        b = self.db.insert("t", {"v": 2})
        self.assertEqual(a, 1)
        self.assertEqual(b, 2)
        db2 = MiniDB(self.tmp)
        c = db2.insert("t", {"v": 3})
        self.assertEqual(c, 3)
        with self.assertRaises(MiniDBError):
            self.db.insert("t", {"id": 1, "v": 9})

    def test_filter_and_or(self):
        init_default_schema(self.db)
        self.db.insert("datasets", {"name": "A", "task": "cls", "size": 10})
        self.db.insert("datasets", {"name": "B", "task": "reg", "size": 20})
        rows = self.db.select(
            "datasets",
            where=Condition("size", ">", "15"),
        )
        self.assertEqual(len(rows), 1)
        rows = self.db.select(
            "datasets",
            where=Filter([Condition("task", "=", "cls"), Condition("size", "<", "100")], "AND"),
        )
        self.assertEqual(len(rows), 1)
        rows = self.db.select(
            "datasets",
            where=Filter([Condition("name", "=", "A"), Condition("name", "=", "B")], "OR"),
        )
        self.assertEqual(len(rows), 2)

    def test_fk_delete_block(self):
        init_default_schema(self.db)
        d = self.db.insert("datasets", {"name": "D", "task": "t", "size": 1})
        m = self.db.insert("models", {"name": "M", "version": "1"})
        self.db.insert(
            "experiments",
            {"dataset_id": d, "model_id": m, "accuracy": 0.9, "status": "done"},
        )
        with self.assertRaises(MiniDBError):
            self.db.delete("datasets", d)

    def test_join(self):
        init_default_schema(self.db)
        d = self.db.insert("datasets", {"name": "DS", "task": "t", "size": 1})
        m = self.db.insert("models", {"name": "MD", "version": "1"})
        self.db.insert(
            "experiments",
            {"dataset_id": d, "model_id": m, "accuracy": 0.77, "status": "ok"},
        )
        joined = self.db.experiments_with_names()
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0]["dataset_name"], "DS")
        self.assertEqual(joined[0]["model_name"], "MD")

    def test_index_after_changes(self):
        self.db.create_table(
            "t",
            [{"name": "id", "type": "INT"}, {"name": "name", "type": "STRING"}],
            primary_key="id",
        )
        rid = self.db.insert("t", {"name": "first"})
        self.assertEqual(self.db.get_by_id("t", rid, use_index=True)["name"], "first")
        self.db.update("t", rid, {"name": "second"})
        self.assertEqual(self.db.get_by_id("t", rid, use_index=True)["name"], "second")
        self.db.delete("t", rid)
        self.assertIsNone(self.db.get_by_id("t", rid, use_index=True))
        pk_idx = self.db._pk_index("t")
        off = self.db._indexes["t"].get(rid)
        if off is not None:
            row = storage.read_row_at_offset(self.db.db_dir, "t", off)
            self.assertTrue(row is None or int(row[pk_idx]) != rid)

    def test_backup_restore(self):
        init_default_schema(self.db)
        self.db.insert("datasets", {"name": "X", "task": "t", "size": 1})
        backup_dir = os.path.join(self.tmp, "backup")
        self.db.backup(backup_dir)
        restore_dir = os.path.join(self.tmp, "restored")
        db2 = MiniDB(self.tmp)
        db2.restore(backup_dir, restore_dir)
        db3 = MiniDB(restore_dir)
        self.assertEqual(len(db3.select("datasets")), 1)


if __name__ == "__main__":
    unittest.main()
