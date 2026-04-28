"""

Create code to create a bunch of MMIF files given the list of assets.

Generated lines look like this

mmif source video:<path-to-assets>/video/GUID.{mp4,text} > GUID.mmif

There could be two documents instead of the one in the example above.

"""

from pathlib import Path


assets = [
    '/Users/Shared/data/clams/aapb/assets-small/text/aapb-0rwUZMehIIAY.txt',
    ('/Users/Shared/data/clams/aapb/assets-small/text/aapb-6sEFeLNvHHZf.txt',
     '/Users/Shared/data/clams/aapb/assets-small/video/aapb-6sEFeLNvHHZf.mp4'),
    ('/Users/Shared/data/clams/aapb/assets-small/text/aapb-B3hpd0cw37bc.txt',
     '/Users/Shared/data/clams/aapb/assets-small/video/aapb-B3hpd0cw37bc.mp4'),
    ('/Users/Shared/data/clams/aapb/assets-small/text/aapb-GmAEZt3AMRpw.txt',
     '/Users/Shared/data/clams/aapb/assets-small/video/aapb-GmAEZt3AMRpw.mp4'),
    ('/Users/Shared/data/clams/aapb/assets-small/video/aapb-Q4xAzXlXgeil.mp4',
     '/Users/Shared/data/clams/aapb/assets-small/text/aapb-Q4xAzXlXgeil.txt'),
    ('/Users/Shared/data/clams/aapb/assets-small/text/aapb-ReTNa18zbKVU.txt',
     '/Users/Shared/data/clams/aapb/assets-small/video/aapb-ReTNa18zbKVU.mp4'),
    ('/Users/Shared/data/clams/aapb/assets-small/text/aapb-SPkrCC1tT7VO.txt',
     '/Users/Shared/data/clams/aapb/assets-small/video/aapb-SPkrCC1tT7VO.mp4'),
    '/Users/Shared/data/clams/aapb/assets-small/text/aapb-viWRWU8rFDho.txt',
    '/Users/Shared/data/clams/aapb/assets-small/video/aapb-A2uWNWR7hQUC.mp4',
    '/Users/Shared/data/clams/aapb/assets-small/video/aapb-nuPpS4oWhcHF.mp4'
]


def combine_asset(assets: tuple | str) -> list:
    if type(asset) == str:
        return [asset]
    return assets

for asset in assets:
    docs = combine_asset(asset)
    specs = 'mmif source'
    for doc in docs:
        path = Path(doc)
        doctype = path.parent.name
        specs += f' {doctype}:{doc}'
    specs += f' > {path.stem}.mmif'
    print(specs)






