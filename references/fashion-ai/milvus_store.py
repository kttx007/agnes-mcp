from pymilvus import MilvusClient, DataType, AnnSearchRequest, RRFRanker

import config


def get_client() -> MilvusClient:
    return MilvusClient(uri=config.MILVUS_URI, token=config.MILVUS_TOKEN)


def create_collection(client: MilvusClient) -> None:
    if client.has_collection(config.COLLECTION_NAME):
        client.drop_collection(config.COLLECTION_NAME)

    schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("product_id", DataType.VARCHAR, max_length=20)
    schema.add_field("category", DataType.VARCHAR, max_length=50)
    schema.add_field("color", DataType.VARCHAR, max_length=50)
    schema.add_field("style", DataType.VARCHAR, max_length=50)
    schema.add_field("season", DataType.VARCHAR, max_length=50)
    schema.add_field("sales_count", DataType.INT64)
    schema.add_field("description", DataType.VARCHAR, max_length=500)
    schema.add_field("price", DataType.FLOAT)
    schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=config.EMBED_DIM)
    schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="dense_vector", index_type="FLAT", metric_type="COSINE")
    index_params.add_index(field_name="sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")

    client.create_collection(config.COLLECTION_NAME, schema=schema, index_params=index_params)
    print(f"Collection '{config.COLLECTION_NAME}' created with hybrid schema.")


def insert_products(client: MilvusClient, products: list[dict],
                    dense_vecs: list, sparse_vecs: list[dict]) -> None:
    rows = []
    for i, p in enumerate(products):
        rows.append({
            "product_id": p["product_id"],
            "category": p["category"],
            "color": p["color"],
            "style": p["style"],
            "season": p["season"],
            "sales_count": int(p["sales_count"]),
            "description": p["description"],
            "price": float(p["price"]),
            "dense_vector": dense_vecs[i].tolist(),
            "sparse_vector": sparse_vecs[i],
        })
    res = client.insert(config.COLLECTION_NAME, rows)
    print(f"Insert response: {res}")
    client.flush(config.COLLECTION_NAME)
    stats = client.get_collection_stats(config.COLLECTION_NAME)
    print(f"Inserted {stats.get('row_count', 'unknown')} products into Milvus.")


def hybrid_search(client: MilvusClient, query_dense: list[float],
                  query_sparse: dict, filter_expr: str,
                  top_k: int = None) -> list[dict]:
    if top_k is None:
        top_k = config.TOP_K

    dense_req = AnnSearchRequest(
        data=[query_dense],
        anns_field="dense_vector",
        param={"metric_type": "COSINE"},
        limit=20,
        expr=filter_expr,
    )
    sparse_req = AnnSearchRequest(
        data=[query_sparse],
        anns_field="sparse_vector",
        param={"metric_type": "IP"},
        limit=20,
        expr=filter_expr,
    )

    results = client.hybrid_search(
        collection_name=config.COLLECTION_NAME,
        reqs=[dense_req, sparse_req],
        ranker=RRFRanker(k=60),
        limit=top_k,
        output_fields=["product_id", "category", "color", "style", "season",
                       "sales_count", "description", "price"],
    )
    return results[0] if results else []
