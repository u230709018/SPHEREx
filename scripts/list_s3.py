"""
List every SPHEREx Level-2 image in the public AWS copy (s3://nasa-irsa-spherex) and save
one line per exposure (all six detectors share the same exposure id).

Written with the assistance of an AI coding assistant (Claude, Anthropic); see README "Use of AI".
"""
import json, re, sys, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

B = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/"
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
OUT = Path(__file__).resolve().parents[1] / "data" / "index"


def list_page(prefix, token=None, delimiter=None):
    q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
    if token: q["continuation-token"] = token
    if delimiter: q["delimiter"] = delimiter
    for attempt in range(6):
        try:
            x = urllib.request.urlopen(B + "?" + urllib.parse.urlencode(q), timeout=60).read()
            return ET.fromstring(x)
        except Exception:
            import time; time.sleep(2 ** attempt)
    raise RuntimeError(prefix)


def subdirs(prefix):
    r = list_page(prefix, delimiter="/")
    return [p.find("s:Prefix", NS).text for p in r.findall("s:CommonPrefixes", NS)]


def keys(prefix):
    out, tok = [], None
    while True:
        r = list_page(prefix, tok)
        out += [(c.find("s:Key", NS).text, int(c.find("s:Size", NS).text)) for c in r.findall("s:Contents", NS)]
        if r.find("s:IsTruncated", NS).text != "true":
            return out
        tok = r.find("s:NextContinuationToken", NS).text


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    weeks = []
    for rel in ("dr1/level2/", "qr3/level2/"):
        weeks += subdirs(rel)
    print(len(weeks), "week folders", flush=True)
    pat = re.compile(r"level2_(?P<obs>.+?)D(?P<det>[1-6])_spx_.*\.fits$")
    files = []
    with ThreadPoolExecutor(24) as pool:
        for i, ks in enumerate(pool.map(keys, weeks), 1):
            files += [(k, s) for k, s in ks if pat.search(k)]
            if i % 10 == 0:
                print(f"{i}/{len(weeks)} weeks, {len(files)} files", flush=True)
    (OUT / "s3_files.json").write_text(json.dumps(files))
    print("done", len(files), "files", flush=True)
