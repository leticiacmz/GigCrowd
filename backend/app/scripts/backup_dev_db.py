"""A safety copy of the development database, taken before a reset.

Dumped to plain JSON so it can be read back without MongoDB, and so a reset is
never the last remaining copy of anything.
"""
import json
import os

from pymongo import MongoClient

URI = "mongodb://localhost:27017"
NAME = "gigcrowd"
OUT = os.environ["BACKUP_DIR"]


def main() -> int:
    client = MongoClient(URI)
    database = client[NAME]

    os.makedirs(OUT, exist_ok=True)

    counts = {}

    for name in sorted(database.list_collection_names()):
        if name.startswith("system."):
            continue

        documents = list(database[name].find({}))

        with open(
            os.path.join(OUT, f"{name}.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                [
                    {key: str(value) for key, value in doc.items()}
                    for doc in documents
                ],
                handle,
                ensure_ascii=False,
            )

        counts[name] = len(documents)

    print(json.dumps(counts, indent=2))
    print(f"total documents: {sum(counts.values())}")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
