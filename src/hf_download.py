"""Download helpers for the Moltbook observatory archive on Hugging Face.

File structure:
    Constants    dataset id, API / resolve URLs, local raw directory
    list_files   file listing (path, size) from the Hugging Face API
    download     fetch every file of one subset, skipping complete files
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.io_utils import REPO_ROOT

DATASET = "SimulaMet/moltbook-observatory-archive"
API_TREE = f"https://huggingface.co/api/datasets/{DATASET}/tree/main?recursive=true"
RESOLVE = f"https://huggingface.co/datasets/{DATASET}/resolve/main/"
UA = {"User-Agent": "swarm-lineage-research"}
RAW_DIR = REPO_ROOT / "data" / "raw" / "moltbook"


def list_files() -> list[dict[str, Any]]:
    """Return the dataset's file list with sizes.

    Returns:
        List of {'path', 'size'} dicts.
    """
    req = urllib.request.Request(API_TREE, headers=UA)
    items = json.load(urllib.request.urlopen(req, timeout=120))
    return [{"path": i["path"], "size": int(i.get("lfs", {}).get("size", i.get("size", 0)))}
            for i in items if i.get("type") == "file"]


def download(files: list[dict[str, Any]], subset: str) -> list[Path]:
    """Download every file of one subset into RAW_DIR, skipping complete files.

    Args:
        files: Output of list_files().
        subset: Subset directory name, e.g. 'agents'.

    Returns:
        Local paths of the subset's files, sorted.

    Raises:
        RuntimeError: If a file fails after 5 attempts.
    """
    todo = [f for f in files if f["path"].startswith(f"data/{subset}/")]
    paths = []
    for f in tqdm(todo, desc=f"download {subset}", unit="file"):
        dst = RAW_DIR / f["path"]
        paths.append(dst)
        if dst.exists() and dst.stat().st_size == f["size"]:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(5):
            try:
                req = urllib.request.Request(RESOLVE + f["path"], headers=UA)
                tmp = dst.with_suffix(".part")
                with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as out:
                    while chunk := r.read(1 << 20):
                        out.write(chunk)
                tmp.replace(dst)
                break
            except OSError:
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"download failed: {f['path']}")
    return sorted(paths)
