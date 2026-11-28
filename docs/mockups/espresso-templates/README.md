# Espresso email and PDF templates

Design mockups for Commera's customer emails and PDFs, built from the Espresso sample in #171. Nothing in the app uses them yet.

Open `index.html` for the gallery. `out/` holds the rendered emails (desktop 720px and mobile 390px) and PDFs.

Rebuild with `npm install` and `./render.sh`. The PDF step needs jinja2, pymupdf and pillow.

Notes:
- Headless Chrome won't go below 500px wide, so `shoot_mobile.sh` takes the 390px phone shots with agent-browser.
- `render_pdf.py` passes the order to Jinja as an object, not a dict: on a dict, `doc.items` resolves to the `dict.items` method.
