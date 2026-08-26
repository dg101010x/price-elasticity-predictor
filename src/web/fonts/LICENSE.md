# Bundled webfonts

Both families are used under the **SIL Open Font License 1.1**
(<https://scripts.sil.org/OFL>), which permits bundling and redistribution
with the software that uses them.

| File | Family | Designer / foundry | Source |
|---|---|---|---|
| `archivo-400-700.woff2` | Archivo (variable: weight 400–700, width 75–112%) | Omnibus-Type | <https://fonts.google.com/specimen/Archivo> |
| `ibm-plex-mono-400.woff2` | IBM Plex Mono Regular | Mike Abbink, Bold Monday / IBM | <https://fonts.google.com/specimen/IBM+Plex+Mono> |
| `ibm-plex-mono-600.woff2` | IBM Plex Mono SemiBold | Mike Abbink, Bold Monday / IBM | <https://fonts.google.com/specimen/IBM+Plex+Mono> |

These are the **latin subsets only**, taken from the Google Fonts CDN build.
They are served from `/fonts/*` by `src/api.py` rather than fetched from
`fonts.gstatic.com`, so the page renders identically on networks that block
third-party hosts.

To refresh them, re-download the `latin` `@font-face` sources from:

```
https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..112,400..700&family=IBM+Plex+Mono:wght@400;600&display=swap
```
