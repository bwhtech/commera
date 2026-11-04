# $theme_name

## Theme settings

Theme settings are the values a merchant can change without code: colours, fonts, corner radius, logo, social links.
They live in one Settings doctype per theme.

1. Open the Shop Theme record for $theme_name in Desk and click **Scaffold Theme Settings**.
   This creates the Single doctype `$theme_name Settings`.
2. Add fields to that doctype. The merchant edits them on the Theme screen in `/commera`.

A theme without its own Settings doctype uses its parent's.

### Read a setting in a template

Every page, section and block gets the settings as `theme`:

```jinja
<h1>{{ theme.tagline }}</h1>
{% for link in theme.social_links %}<a href="{{ link.url }}">{{ link.label }}</a>{% endfor %}
```

A field that has no value is `None`.

### Style tab fields become CSS variables

Every Settings doctype has a **Style** tab. Each field in that tab becomes a CSS variable on `:root`:
the name is `--theme-` plus the fieldname, with `_` changed to `-`. The value is written as typed.

| Field in the Style tab | Value | Variable |
| --- | --- | --- |
| `font` | `Poppins` | `--theme-font: Poppins;` |
| `font_size` | `2rem` | `--theme-font-size: 2rem;` |
| `font_weight` | `600` | `--theme-font-weight: 600;` |
| `primary_color` | `#0f766e` | `--theme-primary-color: #0f766e;` |

Use Data fields unless another type helps the merchant, such as Color for a colour picker.
No unit is added: type `2rem` or `2px`, or add the unit in your CSS with `calc(var(--theme-font-size) * 1rem)`.
An empty value writes no variable. A value with `;`, `{`, `}`, `<`, `>`, `\` or `/*` is left out.
Fields in other tabs are not variables; read them in templates as `theme.<field>`.

`{{ format_shop_theme_css() }}` in `<head>` writes the variables. Give each one a fallback in your CSS:

```css
@theme {
	--font-sans: var(--theme-font, system-ui), sans-serif;
	--text-base: var(--theme-font-size, 1rem);
	--color-primary: var(--theme-primary-color, #111827);
}
```
