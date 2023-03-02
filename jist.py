#!/usr/bin/env python3

import logging
import re
import shutil
import subprocess
from argparse import ArgumentParser
from pathlib import Path
from typing import List, Optional

import nbformat

logger = logging.getLogger("jist")

# It's quite likely I'm missing something out here
# But I'm confident like, unicode in github handles doesn't exist
GIST_PATTERN = re.compile(r"https?://gist.github.com/(?P<GistId>[a-zA-Z0-9/_-]+)")

parser = ArgumentParser("jist", description="Upload Jupyter notebooks to github Gist")
parser.add_argument("notebook", nargs="+", type=Path)
parser.add_argument("--then-clear", action="store_true")


def find_gist_id(text: str) -> Optional[str]:
    match = GIST_PATTERN.search(text)
    if not match:
        return
    return match.group("GistId")


def find_gist_url(text: str) -> Optional[str]:
    match = GIST_PATTERN.search(text)
    if not match:
        return
    return match.group(0)


def gist_url_from_notebook(notebook: nbformat.NotebookNode) -> Optional[str]:

    if len(notebook.cells) == 0:
        return

    head = notebook.cells[0]
    if head.get("cell_type", None) != "markdown":
        return

    return find_gist_id(head.get("source", ""))


def update_gist_file(
    gh_exe: Path, gist_id: str, file: Path
) -> subprocess.CompletedProcess:
    args = [
        gh_exe,
        "gist",
        "edit",
        gist_id,
        "-f",
        file,  # Local file
        file.name,  # File name in the old gist
    ]
    logger.info("Running %s", args)
    proc = subprocess.run(
        args,
        # Non-zero exit status handled by subprocess:
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )

    return proc


def create_gist(gh_exe: Path, *files: Path) -> Optional[str]:
    args = [
        gh_exe,
        "gist",
        "create",
        *files,
    ]
    logger.info("Running %s", args)
    proc = subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )

    # If `gh` terminates with non-zero, subprocess already throws an exception
    # If we don't find the gist url, we return None
    return find_gist_id(proc.stdout.strip())


def prepend_gist_url(
    gist_url: str, notebook: nbformat.NotebookNode
) -> nbformat.NotebookNode:
    text = f"Rendered at {gist_url}"

    nbf_version = min(4, notebook.get("nbformat", 4))
    nbf = nbformat.versions[nbf_version]
    new_cell = nbf.new_markdown_cell(source=text)

    notebook.cells.insert(0, new_cell)

    return notebook


RM_META_FIELDS = {"collapsed", "scrolled"}


def strip_outputs(notebook: nbformat.NotebookNode) -> nbformat.NotebookNode:
    # Cf. https://github.com/jupyter/nbconvert/blob/68b496b7fcf4cfbffe9e1656ac52400a24cacc45/nbconvert/preprocessors/clearoutput.py#L11
    # NB: This is an in-place operation

    for cell in notebook.get("cells", []):
        if cell.get("cell_type", None) != "code":
            continue

        cell.outputs = []
        cell.execution_count = None

        if "metadata" in cell:
            for field in RM_META_FIELDS:
                cell.metadata.pop(field, None)

    return notebook


def main(args):
    GH = shutil.which("gh")

    if GH is None:
        parser.error("Couldn't find `gh` executable")

    then_clear: bool = args.then_clear
    notebooks: List[Path] = args.notebook

    for notebook in notebooks:
        parsed = nbformat.read(notebook, nbformat.NO_CONVERT)
        gist_id = gist_url_from_notebook(parsed)

        if gist_id:
            gist_url = f"https://gist.github.com/{gist_id}"
            logger.info("Existing gist id in %s: %s", notebook.name, gist_id)
            update_gist_file(Path(GH), gist_url, notebook)
        else:
            logger.info("Creating a new gist for %s", notebook.name)
            gist_id = create_gist(Path(GH), notebook)

            if not gist_id:
                logger.error(
                    "Not touching the file any further. Failed to generate a gist id for %s",
                    notebook.as_posix(),
                )
                continue

            gist_url = f"https://gist.github.com/{gist_id}"
            logger.info("Created a new gist at %s: %s", gist_url, notebook.name)

            logger.debug("Prepending gist url to %s", notebook.as_posix())
            parsed = prepend_gist_url(gist_url, parsed)

        if then_clear:
            logger.debug("Stripping outputs from %s", notebook.as_posix())
            parsed = strip_outputs(parsed)

        logger.debug("Writing %s", notebook.as_posix())
        nbformat.write(parsed, notebook)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    )

    main(parser.parse_args())
