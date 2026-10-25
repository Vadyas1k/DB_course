import os
import shutil

import storage


class MiniDBError(Exception):
    pass


TYPE_INT = "INT"
TYPE_STRING = "STRING"
TYPE_FLOAT = "FLOAT"
VALID_TYPES = {TYPE_INT, TYPE_STRING, TYPE_FLOAT}


def parse_value(col_type, raw):
    if raw is None or raw == "":
        if col_type == TYPE_STRING:
            return ""
        raise MiniDBError("Пустое значение для типа " + col_type)
    if col_type == TYPE_INT:
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise MiniDBError("Ожидается INT, получено: " + repr(raw))
    if col_type == TYPE_FLOAT:
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise MiniDBError("Ожидается FLOAT, получено: " + repr(raw))
    return str(raw)


def compare_values(op, left, right):
    if op == "=":
        return left == right
    if op == "!=":
        return left != right
    if op in (">", "<", ">=", "<="):
        try:
            if op == ">":
                return left > right
            if op == "<":
                return left < right
            if op == ">=":
                return left >= right
            if op == "<=":
                return left <= right
        except TypeError:
            return False
    return False


class Condition:
    def __init__(self, column, op, value):
        self.column = column
        self.op = op
        self.value = value


class Filter:
    # Несколько условий сразу: logic только "AND" или "OR"
    def __init__(self, conditions, logic="AND"):
        self.conditions = conditions
        self.logic = logic.upper()


def check_one_condition(table_info, row, condition):
    col_names = [c["name"] for c in table_info["columns"]]
    if condition.column not in col_names:
        raise MiniDBError("Неизвестный столбец: " + condition.column)
    idx = col_names.index(condition.column)
    col_type = table_info["columns"][idx]["type"]
    left = parse_value(col_type, row[idx])
    right = parse_value(col_type, condition.value)
    return compare_values(condition.op, left, right)


def row_matches(table_info, row, condition):
    if condition is None:
        return True
    if isinstance(condition, Condition):
        return check_one_condition(table_info, row, condition)
    if isinstance(condition, Filter):
        if condition.logic == "AND":
            for c in condition.conditions:
                if not check_one_condition(table_info, row, c):
                    return False
            return True
        if condition.logic == "OR":
            for c in condition.conditions:
                if check_one_condition(table_info, row, c):
                    return True
            return False
    raise MiniDBError("Некорректное условие фильтра")


def row_to_dict(table_info, row):
    result = {}
    for i, col in enumerate(table_info["columns"]):
        raw = row[i] if i < len(row) else ""
        try:
            result[col["name"]] = parse_value(col["type"], raw)
        except MiniDBError:
            result[col["name"]] = raw
    return result


class MiniDB:
    def __init__(self, db_dir):
        self.db_dir = os.path.abspath(db_dir)
        self.tables = {}
        self._indexes = {}
        if os.path.isdir(self.db_dir):
            self.tables = storage.read_schema(self.db_dir)
            self._refresh_all_indexes()

    def exists(self):
        return os.path.isdir(self.db_dir) and os.path.isfile(storage.schema_path(self.db_dir))

    def list_tables(self):
        return sorted(self.tables.keys())

    def _column_index(self, table_name, col_name):
        info = self.tables[table_name]
        names = [c["name"] for c in info["columns"]]
        if col_name not in names:
            raise MiniDBError("Столбец не найден: " + col_name)
        return names.index(col_name)

    def _pk_index(self, table_name):
        info = self.tables[table_name]
        pk = info.get("pk")
        if not pk:
            raise MiniDBError("У таблицы нет первичного ключа")
        return self._column_index(table_name, pk)

    def _refresh_index(self, table_name):
        if table_name not in self.tables:
            return
        pk_idx = self._pk_index(table_name)
        self._indexes[table_name] = storage.rebuild_index(self.db_dir, table_name, pk_idx)

    def _refresh_all_indexes(self):
        for name in self.tables:
            self._refresh_index(name)

    def create_table(self, name, columns, primary_key, foreign_keys=None):
        name = name.strip()
        if not name:
            raise MiniDBError("Имя таблицы не может быть пустым")
        if name in self.tables:
            raise MiniDBError("Таблица уже существует: " + name)
        if not columns:
            raise MiniDBError("Нужен хотя бы один столбец")
        col_defs = []
        col_names = set()
        for col in columns:
            cname = col["name"]
            ctype = col["type"].upper()
            if ctype not in VALID_TYPES:
                raise MiniDBError("Недопустимый тип: " + ctype)
            if cname in col_names:
                raise MiniDBError("Дублирующийся столбец: " + cname)
            col_names.add(cname)
            col_defs.append({"name": cname, "type": ctype})
        if primary_key not in col_names:
            raise MiniDBError("PRIMARY KEY должен быть среди столбцов")
        pk_type = None
        for c in col_defs:
            if c["name"] == primary_key:
                pk_type = c["type"]
        if pk_type != TYPE_INT:
            raise MiniDBError("PRIMARY KEY должен быть типа INT")
        fks = []
        if foreign_keys:
            for fk in foreign_keys:
                fks.append(
                    {
                        "column": fk["column"],
                        "ref_table": fk["ref_table"],
                        "ref_column": fk["ref_column"]
                    }
                )
        self.tables[name] = {"columns": col_defs, "pk": primary_key, "fks": fks}
        storage.write_schema(self.db_dir, self.tables)
        path = storage.table_data_path(self.db_dir, name)
        if not os.path.isfile(path):
            with open(path, "w", encoding="utf-8"):
                pass
        self._refresh_index(name)

    def _check_fks(self, table_name, row_dict):
        info = self.tables[table_name]
        for fk in info.get("fks", []):
            col = fk["column"]
            if col not in row_dict or row_dict[col] is None:
                continue
            ref_table = fk["ref_table"]
            ref_col = fk["ref_column"]
            if ref_table not in self.tables:
                raise MiniDBError("Нет таблицы для FK: " + ref_table)
            ref_val = parse_value(TYPE_INT, row_dict[col])
            if not self._row_exists_by_pk(ref_table, ref_col, ref_val):
                raise MiniDBError( "Нарушение FK: " + col + "=" + str(ref_val) + " не найден в " + ref_table + "." + ref_col)

    def _row_exists_by_pk(self, table_name, pk_column, pk_value):
        pk_idx = self._column_index(table_name, pk_column)
        for row in storage.read_all_rows(self.db_dir, table_name):
            if pk_idx < len(row) and int(row[pk_idx]) == int(pk_value):
                return True
        return False

    def _check_referential_on_delete(self, table_name, pk_value):
        for tname, info in self.tables.items():
            for fk in info.get("fks", []):
                if fk["ref_table"] == table_name and fk["ref_column"] == info.get("pk"):
                    col_idx = self._column_index(tname, fk["column"])
                    for row in storage.read_all_rows(self.db_dir, tname):
                        if col_idx < len(row) and int(row[col_idx]) == int(pk_value):
                            raise MiniDBError("Нельзя удалить запись " + str(pk_value) + " из " + table_name + ": на неё ссылается " + tname)

    def insert(self, table_name, data):
        if table_name not in self.tables:
            raise MiniDBError("Таблица не найдена: " + table_name)
        info = self.tables[table_name]
        pk = info["pk"]
        row_dict = {}
        for col in info["columns"]:
            cname = col["name"]
            if cname in data and data[cname] is not None and data[cname] != "":
                row_dict[cname] = parse_value(col["type"], data[cname])
            elif cname == pk:
                row_dict[cname] = None
            else:
                row_dict[cname] = parse_value(col["type"], "" if col["type"] == TYPE_STRING else 0)

        if row_dict.get(pk) is None:
            new_id = storage.get_next_id(self.db_dir, table_name)
            row_dict[pk] = new_id
            next_id = new_id + 1
            # storage.set_next_id(self.db_dir, table_name, new_id + 1)
        else:
            new_id = int(row_dict[pk])
            if self.get_by_id(table_name, new_id) is not None:
                raise MiniDBError("Дублирующийся первичный ключ: " + str(new_id))
            next_id = storage.get_next_id(self.db_dir, table_name)
            if new_id >= next_id:
                next_id = new_id + 1
                # storage.set_next_id(self.db_dir, table_name, next_id)

        self._check_fks(table_name, row_dict)

        storage.set_next_id(self.db_dir, table_name, next_id)

        names = [c["name"] for c in info["columns"]]
        row = [row_dict[n] for n in names]
        storage.append_row(self.db_dir, table_name, row)
        self._refresh_index(table_name)
        return row_dict[pk]

    def select(self, table_name, columns=None, where=None):
        if table_name not in self.tables:
            raise MiniDBError("Таблица не найдена: " + table_name)
        info = self.tables[table_name]
        all_names = [c["name"] for c in info["columns"]]
        if columns is None:
            out_names = all_names
        else:
            out_names = []
            for c in columns:
                if c not in all_names:
                    raise MiniDBError("Неизвестный столбец: " + c)
                out_names.append(c)
        result = []
        for row in storage.read_all_rows(self.db_dir, table_name):
            if row_matches(info, row, where):
                d = row_to_dict(info, row)
                result.append({k: d[k] for k in out_names})
        return result

    def get_by_id(self, table_name, row_id, use_index=True):
        if table_name not in self.tables:
            raise MiniDBError("Таблица не найдена: " + table_name)
        info = self.tables[table_name]
        pk_idx = self._pk_index(table_name)
        if use_index:
            if table_name not in self._indexes:
                self._refresh_index(table_name)
            row = storage.find_row_by_id_index(
                self.db_dir, table_name, pk_idx, row_id, self._indexes[table_name]
            )
        else:
            row = storage.find_row_by_id_sequential(
                self.db_dir, table_name, pk_idx, row_id
            )
        if row is None:
            return None
        return row_to_dict(info, row)

    def update(self, table_name, row_id, data):
        if table_name not in self.tables:
            raise MiniDBError("Таблица не найдена: " + table_name)
        info = self.tables[table_name]
        pk = info["pk"]
        pk_idx = self._pk_index(table_name)
        rows = storage.read_all_rows(self.db_dir, table_name)
        found = False
        new_rows = []
        for row in rows:
            if pk_idx < len(row) and int(row[pk_idx]) == int(row_id):
                found = True
                d = row_to_dict(info, row)
                all_names = [c["name"] for c in info["columns"]]
                for key, val in data.items():
                    if key == pk:
                        raise MiniDBError("Нельзя менять первичный ключ")
                    if key not in d:
                        raise MiniDBError("Неизвестный столбец: " + key)
                for key, val in data.items():
                    idx = all_names.index(key)
                    col_type = info["columns"][idx]["type"]
                    d[key] = parse_value(col_type, val)
                self._check_fks(table_name, d)
                new_rows.append([d[n] for n in all_names])
            else:
                new_rows.append(row)
        if not found:
            raise MiniDBError("Запись не найдена: id=" + str(row_id))
        storage.write_all_rows(self.db_dir, table_name, new_rows)
        self._refresh_index(table_name)

    def delete(self, table_name, row_id):
        if table_name not in self.tables:
            raise MiniDBError("Таблица не найдена: " + table_name)
        pk_idx = self._pk_index(table_name)
        self._check_referential_on_delete(table_name, row_id)
        rows = storage.read_all_rows(self.db_dir, table_name)
        new_rows = []
        found = False
        for row in rows:
            if pk_idx < len(row) and int(row[pk_idx]) == int(row_id):
                found = True
            else:
                new_rows.append(row)
        if not found:
            raise MiniDBError("Запись не найдена: id=" + str(row_id))
        storage.write_all_rows(self.db_dir, table_name, new_rows)
        self._refresh_index(table_name)

    def experiments_with_names(self):
        # JOIN experiments + имена из datasets и models
        if "experiments" not in self.tables:
            raise MiniDBError("Нет таблицы experiments")
        exp_rows = self.select("experiments")
        ds_map = {}
        if "datasets" in self.tables:
            for d in self.select("datasets"):
                ds_map[d["id"]] = d
        md_map = {}
        if "models" in self.tables:
            for m in self.select("models"):
                md_map[m["id"]] = m
        result = []
        for e in exp_rows:
            ds = ds_map.get(e["dataset_id"])
            md = md_map.get(e["model_id"])
            if ds is None or md is None:
                continue
            result.append(
                {
                    "experiment_id": e["id"],
                    "dataset_name": ds["name"],
                    "model_name": md["name"],
                    "accuracy": e["accuracy"],
                    "status": e["status"],
                }
            )
        return result

    def backup(self, backup_dir):
        if not self.exists():
            raise MiniDBError("База не существует: " + self.db_dir)
        backup_dir = os.path.abspath(backup_dir)
        if os.path.exists(backup_dir):
            raise MiniDBError("Каталог резервной копии уже существует: " + backup_dir)
        shutil.copytree(self.db_dir, backup_dir)

    def restore(self, backup_dir, target_dir=None):
        backup_dir = os.path.abspath(backup_dir)
        if not os.path.isdir(backup_dir):
            raise MiniDBError("Резервная копия не найдена: " + backup_dir)
        if not os.path.isfile(storage.schema_path(backup_dir)):
            raise MiniDBError("В резервной копии нет schema.txt")
        dest = target_dir or self.db_dir
        dest = os.path.abspath(dest)
        if os.path.exists(dest):
            raise MiniDBError(
                "Целевой каталог уже существует. Удалите или выберите другой путь: " + dest
            )
        shutil.copytree(backup_dir, dest)
        self.db_dir = dest
        self.tables = storage.read_schema(self.db_dir)
        self._refresh_all_indexes()


def init_default_schema(db):
    # Таблицы из задания лабы
    if "datasets" not in db.list_tables():
        db.create_table(
            "datasets",
            [
                {"name": "id", "type": TYPE_INT},
                {"name": "name", "type": TYPE_STRING},
                {"name": "task", "type": TYPE_STRING},
                {"name": "size", "type": TYPE_INT},
            ],
            primary_key="id",
        )
    if "models" not in db.list_tables():
        db.create_table(
            "models",
            [
                {"name": "id", "type": TYPE_INT},
                {"name": "name", "type": TYPE_STRING},
                {"name": "version", "type": TYPE_STRING},
            ],
            primary_key="id",
        )
    if "experiments" not in db.list_tables():
        db.create_table(
            "experiments",
            [
                {"name": "id", "type": TYPE_INT},
                {"name": "dataset_id", "type": TYPE_INT},
                {"name": "model_id", "type": TYPE_INT},
                {"name": "accuracy", "type": TYPE_FLOAT},
                {"name": "status", "type": TYPE_STRING},
            ],
            primary_key="id",
            foreign_keys=[
                {"column": "dataset_id", "ref_table": "datasets", "ref_column": "id"},
                {"column": "model_id", "ref_table": "models", "ref_column": "id"},
            ],
        )
