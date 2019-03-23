# INHA-album-dl

No-dependencies, straightforward album dowloader script for https://bibliotheque-numerique.inha.fr albums

## Requirements

- Python 3.7
- Some disk space
- An internet connection

## Usage

From the horse's mouth:

```
$ ./inha_dowloader.py -h
usage: inha_dowloader.py [-h] [-o DIR] [-i RANGE] album_url

positional arguments:
  album_url             The album URL, probably something like
                        https://bibliotheque-
                        numerique.inha.fr/viewer/ALBUM_NUMBER

optional arguments:
  -h, --help            show this help message and exit
  -o DIR, --output-dir DIR
                        Directory to store dowloaded images to. Defaults to
                        the album's name,and will be created if it does not
                        exist.
  -i RANGE, --images RANGE
                        Image range(s) to dowload, ex. '1-3,5,7,10-15'.
                        Default is to dowload all the album's images.
```

## Example

Let's say I want to dowload the cool Strasbourg Cathedral pictures in the album at https://bibliotheque-numerique.inha.fr/viewer/13513/.
The album's title is way too long, so we'll override it with `cathédrale`, and we only want pages 11 and 15:

```bash
$ ./inha_dowloader.py https://bibliotheque-numerique.inha.fr/viewer/13513/ \
    --images 11,15 \
    --output-dir cathédrale
[0.0%] cathédrale/000011.jpg: 13679640576 bytes
[50.0%] cathédrale/000015.jpg: 14903525376 bytes
$ ls -l cathédrale/
total 30M
-rw-r--r-- 1 etienne etienne 15M mars  23 14:43 000011.jpg
-rw-r--r-- 1 etienne etienne 15M mars  23 14:43 000015.jpg
```

You now have two rad hi-res scans from an old book from 1745 in the `cathédrale` directory.