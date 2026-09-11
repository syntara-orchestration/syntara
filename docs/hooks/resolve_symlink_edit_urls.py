"""MkDocs hook: rewrite edit URLs for symlinked docs to point to the real path."""

import os
import re


def on_page_markdown(markdown, *, page, config, files):
    src_path = page.file.abs_src_path
    real_path = os.path.realpath(src_path)

    if real_path != os.path.abspath(src_path):
        repo_root = os.path.dirname(config["docs_dir"])
        real_rel = os.path.relpath(real_path, repo_root)
        repo_url = config.get("repo_url", "").rstrip("/")
        edit_uri = config.get("edit_uri", "")
        if repo_url and edit_uri:
            # Extract "edit/<branch>/" from edit_uri (e.g., "edit/devel/docs/")
            match = re.match(r"(edit/[^/]+/)", edit_uri)
            edit_prefix = match.group(1) if match else "edit/devel/"
            page.edit_url = f"{repo_url}/{edit_prefix}{real_rel}"

    return markdown
