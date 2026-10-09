# textbooks/

Generated corpus files (`<subject>_<grade>[_<part>].json`) from
`python scripts/ingest_textbooks.py <pdf-folder> --write`. Empty until you ingest
the KTBS PDFs; the ingest report lists chapters found per book.

Currently empty apart from this file, so textbook-grounded generation is not active: chapters come from
`backend/data/syllabus.json` until you ingest books. With `REQUIRE_TEXTBOOK=true` and nothing ingested, every
generation request is refused.
