"""
Intake pipeline for geolocation-aware sales and pricing observations.

    data/raw/<date>/<source>.jsonl  -->  clean  -->  data/processed/*.parquet

This package is the part of the collection plan that is the same no matter
where the rows come from: one schema, the validation and de-duplication rules,
enrichment, and a daily yield check. It deliberately contains no scrapers.
Whether a given marketplace permits scraping, or offers a partner API, is a
per-site decision about terms of service; a collector for one is just
something that writes JSONL in one of the shapes `schema.ADAPTERS` knows.
"""
