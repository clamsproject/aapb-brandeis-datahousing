DROP TABLE IF EXISTS map;
CREATE TABLE IF NOT EXISTS map (
	GUID	TEXT NOT NULL,
	file_type	TEXT NOT NULL,
	server_path	TEXT NOT NULL,
	date_created TEXT NOT NULL,
	date_last_accessed TEXT
);

