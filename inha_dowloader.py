#!/usr/bin/python3 -u
import re

from argparse import ArgumentParser
from ast import literal_eval
from functools import partial
from pathlib import Path
from sys import stdout
from urllib.request import urlopen, urlretrieve


class ProgressCBHandler(object):
    """Base handler for image download progress callbacks, does nothing."""

    def on_start(self, context: dict):
        """Called when a new image is to be processed"""
        pass

    def on_progress(self, context: dict):
        """Called every time a block of data has been downloaded"""
        pass

    def on_completion(self, context: dict, skipped: bool = False, cancelled: bool = False):
        """Called when an image has finished dowlnloading.

        'skipped' will be True if the dowload was skipped because of an existing file,
        and 'cancelled' will be True when the dowload was interrupted.
        """
        pass


class StdoutCBHandler(ProgressCBHandler):
    """Logs download progress to stdout, make it unbuffered for best results"""

    def on_progress(self, context: dict):
        if context["transferred"]:
            stdout.write("\b" * 17)
        tot = str(context["transferred"]).rjust(11)
        stdout.write(f"{tot} bytes")

    def on_start(self, context: dict):
        percentage = context["processed_images"] / context["total_images"] * 100
        stdout.write(f"[{percentage:.1f}%] {context['current_image']}: ")

    def on_completion(self, context: dict, skipped: bool = False, cancelled: bool = False):
        if skipped:
            stdout.write("skipped")
        elif cancelled:
            stdout.write("cancelled")
        stdout.write("\n")


class ParseError(Exception):
    """Raised when the index page can't be parsed"""
    pass


class INHAAlbumDownloader(object):
    """Downloads albums from the inha website"""
    BASE_URL = "https://bibliotheque-numerique.inha.fr/i/?IIIF={iiif}/iiif/{image}.tif/full/full/0/native.jpg"  # noqa: E501

    PATTERNS = {
        # Things to find in the album's index page
        "image_list": re.compile(r"var images = ([^;]+);"),
        "iiif": re.compile(r"'server': '/medias([a-f/0-9-]+)',"),
        "title": re.compile(r"<title>\s*(.*)\s*</title>")
    }

    @classmethod
    def parse_album_page(cls, page: str) -> dict:
        """Tries to find a match in the index page for every regex in PATTERNS."""
        results = {}
        for name, pattern in cls.PATTERNS.items():
            match = pattern.search(page)
            if not match:
                # That probably means that either the page is not the expected one (wrong url),
                # or that somebody changed the website's code.
                raise ParseError(f"{name} not found")
            results[name] = match.group(1)
        return results

    def __init__(self, album_url: str, cb_handler: ProgressCBHandler = None):
        """Gets the title and the list of images from the album pages"""
        opened = urlopen(album_url)
        albumpage = opened.read().decode("utf8")
        parsed = self.parse_album_page(albumpage)

        self.image_names = literal_eval(parsed["image_list"])
        # No / in file paths, never seen one yet but better safe than sorry
        self.title = parsed["title"].replace("/", "_")
        self.iiif = parsed["iiif"]
        self.callback_handler = cb_handler or StdoutCBHandler()

    @property
    def image_count(self):
        """The number of images in the album"""
        return len(self.image_names)

    def image_url(self, image: str) -> str:
        """Gets the download url for a given image."""
        return self.BASE_URL.format(image=image, iiif=self.iiif)

    def _urlretrieve_cb(self, transferred: int, block_size: int, _total_size: int, context: dict):
        """Callback for urlretrieve, updates the current dowload context and calls on_progress.
        The servers don't send any content-length headers, so _total_size is always -1.
        """
        in_bytes = transferred * block_size
        context["transferred"] += in_bytes
        context["total_transferred"] += in_bytes
        self.callback_handler.on_progress(context)

    def dowload(self, directory: str = None, only: set = None):
        """Download image to disk.

        directory:
            Optional directory name to dowload images to, it will be created if it doesn't exist.
            Defaults to the album's title.

        only:
            Optional set of images (from self.images) to be downloaded.
            If not given, all images will be.
        """
        assert only.issubset(self.image_names)  # TODO: proper exception

        # The context object that will be passed to callbacks in self.callback_handler
        dl_context = {
            "current_image": None,
            "processed_images": 0,
            "transferred": 0,
            "total_transferred": 0,
            "total_images": len(only) if only else self.image_count,
        }

        # urlretrieve doesn't know about our context, we need to handle that with a partial
        urlretrieve_cb = partial(self._urlretrieve_cb, context=dl_context)

        outdir = Path(directory or self.title)
        if not outdir.exists():
            outdir.mkdir()

        # Enumerate our images, starting with 1
        for count, i in enumerate(self.image_names, 1):
            # The image's number seems to be the part after the last underscore
            name, num = i.rsplit("_", 1)
            # Where to download the file
            outfile = outdir / f"{num}.jpg"
            # The image's downloadable URL
            url = self.image_url(i)
            dl_context.update(
                current_image=outfile,
                transferred=0,
                current_image_url=url,
            )
            # Skip images that were not asked for, if there are any
            if only and i not in only:
                continue

            self.callback_handler.on_start(dl_context)
            if outfile.exists():
                # The output file exists, on to the next one then
                dl_context["processed_images"] += 1
                self.callback_handler.on_completion(dl_context, skipped=True)
                continue

            try:
                # Dowload the file to disk
                urlretrieve(url, outfile, urlretrieve_cb)
                dl_context["processed_images"] += 1
            except KeyboardInterrupt:  # TODO handle exceptions from urlretrieve
                # Delete potentially semi-downloaded files
                try:
                    outfile.unlink()
                except FileNotFoundError:
                    pass
                self.callback_handler.on_completion(dl_context, cancelled=True)
                break
            self.callback_handler.on_completion(dl_context)


class RangeList(list):

    def __init__(self, page_ranges: str):
        """Parses a list of ranges in the 1-3,5,7,10-19 format"""
        only = set()
        for i in page_ranges.split(","):
            # either "3" or "3-5"
            start, ok, end = i.partition("-")
            start = int(start)
            if ok:
                end = int(end)
                if start >= end:
                    raise ValueError(f"Invalid range {i!r}: {start} must be < {end}")
                only.update(range(start, end + 1))
            else:
                only.add(start)
        super().__init__(only)


def main():
    psr = ArgumentParser()
    psr.add_argument("album_url", help="The album URL, probably something like "
                     "https://bibliotheque-numerique.inha.fr/viewer/ALBUM_NUMBER")
    psr.add_argument("-o", "--output-dir", metavar="DIR", type=Path,
                     help="Directory to store dowloaded images to. Defaults to the album's name,"
                          "and will be created if it does not exist.")
    psr.add_argument("-i", "--images", metavar="RANGE", type=RangeList, default=[],
                     help="Image range(s) to dowload, ex. '1-3,5,7,10-15'. "
                           "Default is to dowload all the album's images.")
    args = psr.parse_args()
    dl = INHAAlbumDownloader(args.album_url)
    if args.images and max(args.images) > dl.image_count:
        psr.error(f"Asked for images up to {max(args.images)} but there are only {dl.image_count}")
    # Convert the list of pages to image names
    only = {dl.image_names[i-1] for i in args.images}
    dl.dowload(args.output_dir, only)


if __name__ == "__main__":
    main()
