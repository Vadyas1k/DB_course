import os
import sys

from minidb import Condition, Filter, MiniDB, MiniDBError, init_default_schema

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data")


def print_rows(rows):
    if not rows:
        print("(нет записей)")
        return
    for row in rows:
        print(row)


def input_int(prompt, allow_empty=False):
    while True:
        s = input(prompt).strip()
        if allow_empty and s == "":
            return None
        try:
            return int(s)
        except ValueError:
            print("Введите целое число.")


def input_float(prompt, allow_empty=False):
    while True:
        s = input(prompt).strip()
        if allow_empty and s == "":
            return None
        try:
            return float(s)
        except ValueError:
            print("Введите число.")


def choose_table(db):
    tables = db.list_tables()
    if not tables:
        print("Таблиц нет.")
        return None
    for i, name in enumerate(tables, 1):
        print(str(i) + ". " + name)
    n = input_int("Номер таблицы: ")
    if n is None or n < 1 or n > len(tables):
        print("Неверный номер.")
        return None
    return tables[n - 1]


def parse_one_condition(db, table_name, text):
    info = db.tables[table_name]
    col_names = [c["name"] for c in info["columns"]]
    parts = text.strip().split()
    if len(parts) < 3:
        raise MiniDBError("Формат: столбец оператор значение")
    col, op, val = parts[0], parts[1], " ".join(parts[2:])
    if col not in col_names:
        raise MiniDBError("Неизвестный столбец: " + col)
    if op not in ("=", "!=", ">", "<", ">=", "<="):
        raise MiniDBError("Неизвестный оператор: " + op)
    return Condition(col, op, val)


def parse_simple_condition(db, table_name):
    info = db.tables[table_name]
    col_names = [c["name"] for c in info["columns"]]
    print("Столбцы:", ", ".join(col_names))
    print("Операторы: =, !=, >, <, >=, <=  (можно AND / OR)")
    line = input("Условие (пусто = все записи): ").strip()
    if not line:
        return None
    line = line.replace(" and ", " AND ").replace(" or ", " OR ")
    try:
        if " OR " in line:
            parts = [p.strip() for p in line.split(" OR ")]
            conds = [parse_one_condition(db, table_name, p) for p in parts]
            return Filter(conds, "OR")
        if " AND " in line:
            parts = [p.strip() for p in line.split(" AND ")]
            conds = [parse_one_condition(db, table_name, p) for p in parts]
            return Filter(conds, "AND")
        return parse_one_condition(db, table_name, line)
    except MiniDBError as e:
        print("Ошибка:", e)
        return False


def cmd_insert(db, table_name):
    info = db.tables[table_name]
    data = {}
    for col in info["columns"]:
        name = col["name"]
        ctype = col["type"]
        if name == info.get("pk"):
            v = input(name + " (INT, пусто = авто): ").strip()
            if v:
                data[name] = v
            continue
        if ctype == "INT":
            data[name] = input_int(name + " (INT): ", allow_empty=True) or 0
        elif ctype == "FLOAT":
            data[name] = input_float(name + " (FLOAT): ", allow_empty=True) or 0.0
        else:
            data[name] = input(name + " (STRING): ").strip()
    try:
        new_id = db.insert(table_name, data)
        print("Добавлено, id =", new_id)
    except MiniDBError as e:
        print("Ошибка:", e)


def cmd_update(db, table_name):
    row_id = input_int("ID записи для изменения: ")
    if row_id is None:
        return
    info = db.tables[table_name]
    data = {}
    for col in info["columns"]:
        name = col["name"]
        if name == info.get("pk"):
            continue
        val = input(name + " (новое значение, пусто = не менять): ").strip()
        if val:
            data[name] = val
    if not data:
        print("Нечего обновлять.")
        return
    try:
        db.update(table_name, row_id, data)
        print("Обновлено.")
    except MiniDBError as e:
        print("Ошибка:", e)


def cmd_delete(db, table_name):
    row_id = input_int("ID записи для удаления: ")
    if row_id is None:
        return
    try:
        db.delete(table_name, row_id)
        print("Удалено.")
    except MiniDBError as e:
        print("Ошибка:", e)


def run_cli(db_path):
    os.makedirs(db_path, exist_ok=True)
    db = MiniDB(db_path)
    init_default_schema(db)
    while True:
        print()
        print("=== MiniDB ===")
        print("База:", db_path)
        print("1. Список таблиц")
        print("2. Показать записи таблицы")
        print("3. Добавить запись")
        print("4. Найти с условием")
        print("5. Изменить запись")
        print("6. Удалить запись")
        print("7. Эксперименты с названиями dataset и model (JOIN)")
        print("8. Выход")
        choice = input("Выбор: ").strip()
        try:
            if choice == "1":
                tables = db.list_tables()
                if tables:
                    for t in tables:
                        print("-", t)
                else:
                    print("(пусто)")
            elif choice == "2":
                t = choose_table(db)
                if t:
                    cols = input("Столбцы через запятую (пусто = все): ").strip()
                    col_list = None
                    if cols:
                        col_list = [c.strip() for c in cols.split(",")]
                    rows = db.select(t, columns=col_list)
                    print_rows(rows)
            elif choice == "3":
                t = choose_table(db)
                if t:
                    cmd_insert(db, t)
            elif choice == "4":
                t = choose_table(db)
                if t:
                    where = parse_simple_condition(db, t)
                    if where is not False:
                        rows = db.select(t, where=where)
                        print_rows(rows)
            elif choice == "5":
                t = choose_table(db)
                if t:
                    cmd_update(db, t)
            elif choice == "6":
                t = choose_table(db)
                if t:
                    cmd_delete(db, t)
            elif choice == "7":
                rows = db.experiments_with_names()
                print_rows(rows)
            elif choice == "8":
                print("Выход.")
                break
            else:
                print("Выберите пункт 1–8.")
        except MiniDBError as e:
            print("Ошибка:", e)
        except KeyboardInterrupt:
            print("\nВыход.")
            break


def main():
    db_path = DEFAULT_DB
    if len(sys.argv) > 1:
        if sys.argv[1] == "seed":
            from seed_data import seed

            path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DB
            os.makedirs(path, exist_ok=True)
            seed(MiniDB(path), force="--force" in sys.argv)
            return
        if sys.argv[1] == "backup":
            path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DB
            backup_to = sys.argv[3] if len(sys.argv) > 3 else path + "_backup"
            db = MiniDB(path)
            try:
                db.backup(backup_to)
                print("Резервная копия:", backup_to)
            except MiniDBError as e:
                print("Ошибка:", e)
            return
        if sys.argv[1] == "restore":
            backup_from = sys.argv[2]
            target = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_DB + "_restored"
            db = MiniDB(DEFAULT_DB)
            try:
                db.restore(backup_from, target)
                print("Восстановлено в:", target)
            except MiniDBError as e:
                print("Ошибка:", e)
            return
        db_path = sys.argv[1]
    run_cli(db_path)


if __name__ == "__main__":
    main()
