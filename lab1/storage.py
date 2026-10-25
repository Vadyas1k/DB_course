import os
import struct

FIELD_SEP = "\t"
ESCAPE = "\\"


def escape_string(value):
    if value is None:
        return ""
    s = str(value)
    s = s.replace(ESCAPE, ESCAPE + ESCAPE)
    s = s.replace("\n", ESCAPE + "n")
    s = s.replace("\r", ESCAPE + "r")
    s = s.replace(FIELD_SEP, ESCAPE + "t")
    return s


def unescape_string(s):
    if s is None:
        return ""
    result = []
    i = 0
    while i < len(s):
        if s[i] == ESCAPE and i + 1 < len(s):
            n = s[i + 1]
            if n == ESCAPE:
                result.append(ESCAPE)
            elif n == "n":
                result.append("\n")
            elif n == "r":
                result.append("\r")
            elif n == "t":
                result.append(FIELD_SEP)
            else:
                result.append(n)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def encode_row(values):
    return FIELD_SEP.join(escape_string(v) for v in values) + "\n"


def decode_row(line):
    line = line.rstrip("\n\r")
    if not line:
        return []
    parts = []
    current = []
    i = 0
    while i < len(line):
        if line[i] == ESCAPE and i + 1 < len(line):
            current.append(line[i : i + 2])
            i += 2
        elif line[i] == FIELD_SEP:
            parts.append(unescape_string("".join(current)))
            current = []
            i += 1
        else:
            current.append(line[i])
            i += 1
    parts.append(unescape_string("".join(current)))
    return parts


SCHEMA_FILENAME = "schema.txt"
META_FILENAME = "meta.txt"


def schema_path(db_dir):
    return os.path.join(db_dir, SCHEMA_FILENAME)


def meta_path(db_dir):
    return os.path.join(db_dir, META_FILENAME)


def table_data_path(db_dir, table_name):
    return os.path.join(db_dir, table_name + ".dat")


def table_index_path(db_dir, table_name):
    return os.path.join(db_dir, table_name + ".idx")


def read_schema(db_dir):
    path = schema_path(db_dir)
    if not os.path.isfile(path):
        return {}
    tables = {}
    current = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("TABLE "):
                name = line[6:].strip()
                current = {"columns": [], "pk": None, "fks": []}
                tables[name] = current
            elif line.startswith("COL ") and current is not None:
                parts = line[4:].split()
                col_name = parts[0]
                col_type = parts[1].upper()
                flags = parts[2:] if len(parts) > 2 else []
                current["columns"].append({"name": col_name, "type": col_type})
                if "PK" in flags:
                    current["pk"] = col_name
            elif line.startswith("FK ") and current is not None:
                # FK col ref_table ref_col
                parts = line[3:].split()
                if len(parts) >= 3:
                    current["fks"].append(
                        {"column": parts[0], "ref_table": parts[1], "ref_column": parts[2]}
                    )
    return tables


def write_schema(db_dir, tables):
    os.makedirs(db_dir, exist_ok=True)
    path = schema_path(db_dir)
    lines = []
    for name, info in sorted(tables.items()):
        lines.append("TABLE " + name)
        for col in info["columns"]:
            flags = []
            if info.get("pk") == col["name"]:
                flags.append("PK")
            line = "COL " + col["name"] + " " + col["type"]
            if flags:
                line += " " + " ".join(flags)
            lines.append(line)
        for fk in info.get("fks", []):
            lines.append(
                "FK "
                + fk["column"]
                + " "
                + fk["ref_table"]
                + " "
                + fk["ref_column"]
            )
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def read_meta(db_dir):
    path = meta_path(db_dir)
    meta = {}
    if not os.path.isfile(path):
        return meta
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                meta[key.strip()] = val.strip()
    return meta


def write_meta(db_dir, meta):
    os.makedirs(db_dir, exist_ok=True)
    path = meta_path(db_dir)
    with open(path, "w", encoding="utf-8") as f:
        for key in sorted(meta.keys()):
            f.write(key + "=" + meta[key] + "\n")


def meta_key_next_id(table_name):
    return "next_id_" + table_name


def get_next_id(db_dir, table_name):
    meta = read_meta(db_dir)
    key = meta_key_next_id(table_name)
    if key not in meta:
        return 1
    return int(meta[key])


def set_next_id(db_dir, table_name, next_id):
    meta = read_meta(db_dir)
    meta[meta_key_next_id(table_name)] = str(next_id)
    write_meta(db_dir, meta)


def read_all_rows(db_dir, table_name):
    path = table_data_path(db_dir, table_name)
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(decode_row(line))
    return rows


def write_all_rows(db_dir, table_name, rows):
    os.makedirs(db_dir, exist_ok=True)
    path = table_data_path(db_dir, table_name)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(encode_row(row))


def append_row(db_dir, table_name, values):
    os.makedirs(db_dir, exist_ok=True)
    path = table_data_path(db_dir, table_name)
    line = encode_row(values)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def rebuild_index(db_dir, table_name, pk_column_index):
    # id -> байтовый offset строки в .dat (после любого изменения файла пересобираем)
    data_path = table_data_path(db_dir, table_name)
    idx_path = table_index_path(db_dir, table_name)
    index = {}
    if not os.path.isfile(data_path):
        with open(idx_path, "wb") as f:
            pass
        return index
    with open(data_path, "rb") as f:
        offset = 0
        while True:
            line = f.readline()
            if not line:
                break
            text = line.decode("utf-8")
            fields = decode_row(text)
            if fields and pk_column_index < len(fields):
                try:
                    pk_val = int(fields[pk_column_index])
                    index[pk_val] = offset
                except ValueError:
                    pass
            offset += len(line)
    with open(idx_path, "wb") as f:
        for pk_val in sorted(index.keys()):
            f.write(struct.pack("<q", pk_val))
            f.write(struct.pack("<q", index[pk_val]))
    return index


def load_index(db_dir, table_name):
    idx_path = table_index_path(db_dir, table_name)
    index = {}
    if not os.path.isfile(idx_path):
        return index
    with open(idx_path, "rb") as f:
        data = f.read()
    pos = 0
    while pos + 16 <= len(data):
        pk_val, offset = struct.unpack("<qq", data[pos : pos + 16])
        index[pk_val] = offset
        pos += 16
    return index


def read_row_at_offset(db_dir, table_name, offset):
    path = table_data_path(db_dir, table_name)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        f.seek(offset)
        line = f.readline()
    if not line:
        return None
    return decode_row(line.decode("utf-8"))


def find_row_by_id_sequential(db_dir, table_name, pk_index, row_id):
    for row in read_all_rows(db_dir, table_name):
        if pk_index < len(row) and str(row[pk_index]) == str(row_id):
            return row
    return None


def find_row_by_id_index(db_dir, table_name, pk_index, row_id, index):
    offset = index.get(int(row_id))
    if offset is None:
        return None
    row = read_row_at_offset(db_dir, table_name, offset)
    if row is None:
        return None
    if pk_index < len(row) and int(row[pk_index]) == int(row_id):
        return row
    return None
