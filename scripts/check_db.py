import sys
from pathlib import Path
from collections import defaultdict


db_file = '/Users/marc/Downloads/database-dump.txt'

guids = set()
rows = set()
idx = defaultdict(list)

c = 0
for line in open(db_file):
	c += 1
	if c > 100000:
		break
	line = line.strip().split('(')[1].split(')')[0]
	fields = line.split(',')[1:4]
	guid = fields[0].strip("'")
	ftype = fields[1].strip("'")
	path = fields[2].strip("'")
	path = '/'.join(Path(path).parts[5:])
	guids.add(guid)
	rows.add(f'{guid}\t{ftype}\t{path}')
	idx[guid].append(f'{path}')

sys.stderr.write(f'ROWS: {len(rows)}\n')
sys.stderr.write(f'GUIDS: {len(idx)}\n')

for guid in idx:
	if len(idx[guid]) > 2:
		print(f'[{guid}] [{len(idx[guid])}]')
		for x in idx[guid][:10]:
			print('  ', x)