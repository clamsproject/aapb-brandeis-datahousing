"""

This is some code to populate an assets directory with empty files and then populate
the DB so we can benchmark performance.

It is for development and it is not needed to run the server in any way.

After you run this you should restart the server.

It uses a file that was at some point created from the WGBH data director on child.cs-i.

"""

from pathlib import Path


assets_file = '/Users/marc/Dropbox/projects/CLAMS/GBH/assets.txt'
assets_dir = '/Users/Shared/aapb/assets'


total_count = 0
for line in open(assets_file):
    directory, file_names = line.split('\t')
    prefix = '/llc_data/clams/wgbh/'
    directory = directory[len(prefix):]
    file_names = file_names.split()
    print(directory, len(file_names))
    file_count = 0
    for fname in file_names:
        if fname.startswith('cpb-aacip'):
            video_file = Path(assets_dir) / 'video' / directory / fname
            text_file = Path(assets_dir) / 'text' / directory / (video_file.stem + '.txt')
            video_file.parent.mkdir(parents=True, exist_ok=True)
            text_file.parent.mkdir(parents=True, exist_ok=True)
            video_file.touch()
            text_file.touch()
            file_count += 1
            total_count += 1
            # if file_count > 100: break


print(f'Created {total_count * 2} fake files')
