import tempfile

import lancedb


def run_prefilter_check():
    db = lancedb.connect(tempfile.mkdtemp(prefix="outskill-kb-"))
    rows = [
        {
            "id": i,
            "vector": [float(i)] * 8,
            "category": "pm" if i < 3 else "financial",
        }
        for i in range(20)
    ]
    table = db.create_table("t", rows)
    return table.search([0.0] * 8).where("category = 'pm'", prefilter=True).limit(5).to_list()


def main():
    hits = run_prefilter_check()
    print(len(hits))
    print([hit["category"] for hit in hits])


if __name__ == "__main__":
    main()
