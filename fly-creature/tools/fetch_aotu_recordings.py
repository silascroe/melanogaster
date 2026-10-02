"""Fetch only the two public NoP1 archives; validate before keeping them."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

ARCHIVES = {
    "AOTU019 Motion Pulse NoP1.zip": (269524276, "6ebc8edd2bb348fa14b9dbd8f2cbea01"),
    "AOTU025 Motion Pulse NoP1.zip": (229423097, "ebeace816547366b8325182f80a08a5b"),
}


def fetch(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (size, checksum) in ARCHIVES.items():
        path = directory / name
        if path.exists():
            if path.stat().st_size == size and hashlib.md5(path.read_bytes()).hexdigest() == checksum:
                print(f"Verified existing {name}", flush=True)
                continue
            raise ValueError(f"Existing archive fails checksum: {path}")
        partial = path.with_suffix(".zip.partial")
        url = "https://zenodo.org/api/records/15474938/files/" + urllib.parse.quote(name) + "/content"
        digest = hashlib.md5()
        count = 0
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as target:
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
                digest.update(chunk)
                count += len(chunk)
                if count % (32 * 1024 * 1024) == 0:
                    print(f"{name}: {count / 1e6:.0f}/{size / 1e6:.0f} MB", flush=True)
        if count != size or digest.hexdigest() != checksum:
            raise ValueError(f"Downloaded archive fails checksum: {partial}")
        partial.replace(path)
        print(f"Verified {name}: {count} bytes, MD5 {checksum}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    fetch(parser.parse_args().data_dir)
