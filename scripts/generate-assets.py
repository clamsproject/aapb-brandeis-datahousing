"""

Utility script to generate some empty asset files with randomly 
generated names.

Useful for development only.

"""

import random
import string
from pathlib import Path

assets_dir = Path('/Users/Shared/aapb/assets-small')
assets_dir.mkdir(exist_ok=True)
(assets_dir / 'video').mkdir(exist_ok=True)
(assets_dir / 'text').mkdir(exist_ok=True)


def generate_random_string(length):
    # Using lower case letters and digits to meet AAPB identifier syntax
    characters = string.ascii_lowercase + string.digits
    # Generate and join random characters, but make sure there is at least
    # one digit in it. GUIDs always have at least one, without it the code
    # will consider the entire GUID to be a meaningful suffix.
    while True:
    	s = ''.join(random.choices(characters, k=length))
    	if any(char.isdigit() for char in s):
    		return s


guids = [generate_random_string(12) for i in range(10)]


with open('assets.txt', 'w') as fh:

	def create_path(path: Path):
		print(path)
		path.touch()
		fh.write(f'{str(path)}\n')

	paths = []
	for guid in guids[:6]:
		paths.append(assets_dir / 'video' / f'cpb-aacip-{guid}.mp4')
		paths.append(assets_dir / 'text' / f'cpb-aacip-{guid}.txt')
	for guid in guids[6:8]:
		paths.append(assets_dir / 'text' / f'cpb-aacip-{guid}.txt')
	for guid in guids[8:10]:
		paths.append(assets_dir / 'video' / f'cpb-aacip-{guid}.mp4')
	for p in paths:
		create_path(p)
