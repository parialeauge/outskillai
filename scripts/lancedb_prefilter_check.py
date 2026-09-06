import tempfile

import lancedb


def build_table():
    db = lancedb.connect(tempfile.mkdtemp(prefix="outskill-kb-"))
    rows = [
        {
            "id": i,
            "vector": [float(i)] * 8,
            "category": "pm" if i < 3 else "financial",
        }
        for i in range(20)
    ]
    return db.create_table("t", rows)


def run_where_check():
    table = build_table()
    return table.search().where("category = 'pm'").to_list()


def run_prefilter_check():
    table = build_table()
    return table.search([0.0] * 8).where("category = 'pm'", prefilter=True).limit(5).to_list()


def main():
    where_hits = run_where_check()
    prefilter_hits = run_prefilter_check()
    print(len(where_hits))
    print([hit["category"] for hit in where_hits])
    print(len(prefilter_hits))
    print([hit["category"] for hit in prefilter_hits])


if __name__ == "__main__":
    main()
