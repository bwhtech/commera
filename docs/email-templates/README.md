# Customer email and PDF templates

Templates for Commera's customer emails and PDFs (#100), built on the Espresso design in #171. Nothing in the app uses them yet.

- `emails/`: 14 React Email templates. Every email shares the components in `kit/components.tsx`. Order confirmation and shipped also have a Lookbook layout.
- `pdfs/`: 4 Jinja templates for an A4 page printed by headless Chrome: order confirmation, tax invoice, credit note and packing slip. They extend `kit/pdf_layout.html.j2` and use `kit/pdf_macros.html.j2`.
- `kit/tokens.json`: the frappe-ui colours, type and spacing both formats share.

Renders of every template, at desktop and phone width, are in #550.
