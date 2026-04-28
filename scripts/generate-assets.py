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
    # Characters to choose from (letters and digits)
    characters = string.ascii_letters + string.digits
    # Generate and join random characters
    return ''.join(random.choices(characters, k=length))


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
