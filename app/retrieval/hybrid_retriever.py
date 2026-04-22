import hashlib
from collections import defaultdict


def reciprocal_rank_fusion(result_lists: list[list[dict]], k: int = 60) -> list[dict]:
    scores:      dict[str, float] = defaultdict(float)
    content_map: dict[str, dict]  = {}
    for results in result_lists:
        for rank, item in enumerate(results):
            # Prefer parent_id to fuse child and parent chunks pointing to the same document
            doc_id = item.get("parent_id") or item.get("metadata", {}).get("parent_id")
            if not doc_id:
                doc_id = hashlib.md5(item["content"].encode()).hexdigest()
            scores[doc_id]     += 1.0 / (k + rank + 1)
            content_map[doc_id] = item
    return [
        {**content_map[d], "rrf_score": scores[d]}
        for d in sorted(scores, key=scores.get, reverse=True)
    ]
