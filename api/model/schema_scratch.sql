DROP TABLE IF EXISTS map;
CREATE VIRTUAL TABLE IF NOT EXISTS map USING fts5(
	GUID, file_type, server_path, date_created, date_last_accessed, tokenize="trigram");

