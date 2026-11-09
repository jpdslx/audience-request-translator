"""Run the audience tool.

    python3 -m audience path/to/request.json     one request
    python3 -m audience --examples               the six example requests (no AI needed)

Answers are printed and saved to output/. Built audiences also get a CSV of the people in them and
the query for Analytics. Live requests (output/request.json) get their own file names, so a new
request never overwrites an earlier one.
"""
import csv
import datetime
import glob
import json
import os
import re
import sys

from .engine import run
from .render import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")


def request_name(spec):
    """Time plus the first words of the request, e.g. 2026-11-08_1012_app-users-in-portugal-who."""
    words = re.findall(r"[a-z0-9]+", spec.get("request", "").lower())[:5]
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    base = "_".join([stamp, "-".join(words) or "request"])
    name, n = base, 2
    while os.path.exists(os.path.join(OUT, name + ".md")):  # two runs in the same second
        name, n = "%s_%d" % (base, n), n + 1
    return name


def answer(path):
    with open(path) as fh:
        spec = json.load(fh)
    result = run(spec)
    os.makedirs(OUT, exist_ok=True)
    name = os.path.splitext(os.path.basename(path))[0]
    if name == "request":
        name = request_name(spec)
    files = None
    if result["verdict"] == "build":
        files = ("output/%s_audience.csv" % name, "output/%s_query.sql" % name)
        with open(os.path.join(OUT, name + "_query.sql"), "w") as fh:
            fh.write(result["sql"] + "\n")
    text = render(result, files)
    with open(os.path.join(OUT, name + ".md"), "w") as fh:
        fh.write(text)
    if result["verdict"] == "build":
        with open(os.path.join(OUT, name + "_audience.csv"), "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["email_hash"])
            writer.writerows([p] for p in result["people"])
    return text


def main(args):
    if args == ["--examples"]:
        paths = sorted(glob.glob(os.path.join(ROOT, "examples", "*.json")))
    elif len(args) == 1:
        paths = args
    else:
        print(__doc__)
        return 1
    for path in paths:
        print(answer(path))
        print("---\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
