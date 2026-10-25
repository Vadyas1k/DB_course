import os
import sys

from minidb import MiniDB, init_default_schema

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "data")


def count_rows(db, table):
    return len(db.select(table))


def seed(db, force=False):
    init_default_schema(db)
    if not force and count_rows(db, "datasets") >= 5:
        print("Данные уже есть (datasets >= 5). Используйте --force для повторного заполнения.")
        return False

    if force:
        for t in ["experiments", "models", "datasets"]:
            if t not in db.list_tables():
                continue
            rows = list(db.select(t))
            for r in rows:
                db.delete(t, r["id"])

    datasets = [
        {"name": "MNIST", "task": "classification", "size": 70000},
        {"name": "CIFAR-10", "task": "classification", "size": 60000},
        {"name": "IMDB Reviews", "task": "sentiment", "size": 50000},
        {"name": "Boston Housing", "task": "regression", "size": 506},
        {"name": "Titanic", "task": "classification", "size": 891},
    ]
    for d in datasets:
        db.insert("datasets", d)

    models = [
        {"name": "LogisticRegression", "version": "1.0"},
        {"name": "RandomForest", "version": "2.1"},
        {"name": "ResNet18", "version": "0.9"},
        {"name": "BERT-base", "version": "3.2"},
        {"name": "XGBoost", "version": "1.5"},
    ]
    for m in models:
        db.insert("models", m)

    experiments = [
        (1, 1, 0.91, "completed"),
        (1, 2, 0.88, "completed"),
        (2, 3, 0.76, "running"),
        (3, 4, 0.82, "completed"),
        (4, 5, 0.65, "failed"),
        (5, 1, 0.79, "completed"),
        (2, 2, 0.84, "completed"),
        (1, 3, 0.93, "completed"),
        (3, 1, 0.71, "running"),
        (4, 4, 0.69, "completed"),
        (5, 5, 0.77, "completed"),
        (2, 1, 0.86, "completed"),
        (3, 3, 0.80, "completed"),
        (1, 5, 0.90, "completed"),
        (4, 2, 0.67, "failed"),
        (5, 3, 0.74, "running"),
        (2, 4, 0.85, "completed"),
        (3, 5, 0.78, "completed"),
        (4, 1, 0.70, "completed"),
        (5, 2, 0.81, "completed"),
    ]
    for dataset_id, model_id, accuracy, status in experiments:
        db.insert(
            "experiments",
            {
                "dataset_id": dataset_id,
                "model_id": model_id,
                "accuracy": accuracy,
                "status": status,
            },
        )
    print("Добавлено: 5 datasets, 5 models, 20 experiments.")
    return True


def main():
    db_path = DEFAULT_DB
    force = "--force" in sys.argv
    for arg in sys.argv[1:]:
        if arg != "--force" and not arg.startswith("-"):
            db_path = arg
    os.makedirs(db_path, exist_ok=True)
    db = MiniDB(db_path)
    seed(db, force=force)


if __name__ == "__main__":
    main()
