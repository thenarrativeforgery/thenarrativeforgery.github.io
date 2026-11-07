# Re-minting the book PDF

The PDF handed out by the receipts ring (`tnf_pdf20160715220260715.pdf`) is built from the
text in `index.html`. After any edit to the chapters, the Compendium, the mechanism filters
or the ledger, re-mint it so the download matches the site:

```sh
pip install -r tools/pdf/requirements.txt   # once
python3 tools/pdf/build_pdf.py              # overwrites the PDF, dated today
```

Options: `--date "November 6, 2026"` sets the "Compiled …" line on the last page;
`--out path.pdf` writes somewhere else (useful for checking before replacing);
`--src` reads a different copy of the site page.

What it reads from `index.html`: `INTRO_TEXT`, `CHAPTER_TEXT`, `CHAPTERS` (titles),
`MECHANISMS` (titles and chapter filters, which become each chapter's "Mechanisms
Deployed" box and each mechanism's "Cross-referenced in" list), `MECHANISM_FULL`
(definition, neural basis, chapter examples, sources) and `LEDGER` (the count on the
last page). The title-page synopsis and the Volume Two prefatory note are kept in
`build_pdf.py` itself.

Prose follows the site reader's rules: a short all-caps paragraph is a section head
(the first one in a chapter is its dateline), the first ordinary paragraph is the lead,
a short paragraph wrapped in quotation marks is a block quote, and lines starting `* `
are a bulleted list. Straight quotes become typographic ones; web addresses become links.

`fonts/` holds Anton, Lora (static Regular, Bold and Italic instances of the variable
font) and Courier Prime under the SIL Open Font License, and DejaVu Serif for the one
glyph the others lack (→). `img/` holds the artwork: cover, exhibit plates per chapter
(Chapter 11 has two), mechanism illustrations, badges, seal and logo. To change a plate,
replace the file with the same name.

The build runs twice so the table of contents carries real page numbers; it stops with
an error if the second pass paginates differently from the first.
