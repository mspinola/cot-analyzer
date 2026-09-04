"""What /citpy/view will open, and what it refuses.

Two failures live here, one of each kind:

* **Refusing a real note.** The app's global URL sync round-trips every query
  through `URLSearchParams`, which percent-encodes a path's separators, so the
  page's old `search.split('=')[1]` saw `%2FUsers%2F...` and denied a file
  sitting right there on disk (reported from a local run, 2026-08-31). The
  parse must decode, and must survive a second parameter riding along.
* **Opening something that is not a note.** The guard this replaces accepted
  any path starting with `/Users`, which on a Mac-hosted instance is every
  file the server user can read, on a page with no login.

Store-free: the notes directory is a tmp_path, passed in.
"""
import dash
import pytest

# `dash.register_page` runs at import of the page module and refuses to run
# without an app; the parsing and the path guard are what is under test.
dash.Dash(__name__, use_pages=True, pages_folder='')

import pages.citpy.citpy_view as view  # noqa: E402


@pytest.fixture()
def notes(tmp_path):
    root = tmp_path / "citrini_outputs"
    (root / "2026-08-30").mkdir(parents=True)
    note = root / "2026-08-30" / "2026-08-30_citrindex.md"
    note.write_text("| Ticker |\n|---|\n| GLD |\n")
    (root / "2026-08-30" / "2026-08-30_citrindex.csv").write_text("Ticker\nGLD\n")
    (tmp_path / "secret.md").write_text("not a note")
    return root, note


# ── reading the query ─────────────────────────────────────────────────────────

def test_the_path_survives_url_encoding_and_extra_params():
    encoded = "?file=%2Fnotes%2F2026-08-30%2Fa.md"
    assert view.requested_path(encoded) == "/notes/2026-08-30/a.md"
    # The global sync appends its own params; the old split lost the path here.
    assert view.requested_path(
        "?file=/notes/a.md&date=2026-08-25") == "/notes/a.md"
    assert view.requested_path("?date=2026-08-25&file=/notes/a.md") == "/notes/a.md"
    assert view.requested_path("?date=2026-08-25") is None
    assert view.requested_path("") is None
    assert view.requested_path(None) is None


# ── deciding what to open ─────────────────────────────────────────────────────

def test_a_note_inside_the_directory_resolves(notes):
    root, note = notes
    assert view.resolve_note(str(note), notes_dir=str(root)) == str(note.resolve())


def test_paths_outside_the_notes_directory_are_refused(notes):
    root, note = notes
    outside = root.parent / "secret.md"
    assert view.resolve_note(str(outside), notes_dir=str(root)) is None
    # The traversal spelling, and the one the old `/Users` clause waved through.
    assert view.resolve_note(f"{root}/../secret.md", notes_dir=str(root)) is None
    assert view.resolve_note("/Users/someone/.ssh/id_rsa", notes_dir=str(root)) is None
    assert view.resolve_note("/etc/passwd", notes_dir=str(root)) is None
    assert view.resolve_note(str(root), notes_dir=str(root)) is None
    assert view.resolve_note(None, notes_dir=str(root)) is None


def test_a_symlink_pointing_out_is_refused(notes, tmp_path):
    """`..` never appears in this one, which is why the check is containment of
    the RESOLVED path rather than a string test."""
    root, _ = notes
    secret = tmp_path / "secret.md"
    link = root / "2026-08-30" / "innocent.md"
    link.symlink_to(secret)
    assert view.resolve_note(str(link), notes_dir=str(root)) is None


def test_only_the_listed_extensions_open(notes):
    """/citpy lists .md and .txt; the sibling .csv the generator writes is not
    viewable by hand-typed URL either."""
    root, note = notes
    csv = note.with_suffix(".csv")
    assert csv.exists()
    assert view.resolve_note(str(csv), notes_dir=str(root)) is None
