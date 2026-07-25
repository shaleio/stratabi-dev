# Third-Party Notices — StrataBI Developer Edition

StrataBI Developer Edition is distributed under the Shaleio Guild Community License
(see `LICENSE.md`). It **bundles** the third-party components listed below, each under
its own license. Those licenses apply to the corresponding files and are reproduced
here as required. Shaleio claims no ownership of these components.

The remaining assets under `stratabi/assets/` (the `guildmaster` themes, the Shaleio
logos/favicons, and the small loader/init glue scripts) are Shaleio's own work and are
covered by `LICENSE.md`.

---

## 1. Monaco Editor

- **Version:** 1.104.0
- **Location in this package:** `stratabi/assets/monaco/`
- **Project:** https://github.com/microsoft/monaco-editor
- **License:** MIT
- **Copyright:** © Microsoft Corporation. All rights reserved.

## 2. Plotly.js

- **Version:** 2.35.2
- **Location in this package:** `stratabi/assets/plotly.min.js`
- **Project:** https://github.com/plotly/plotly.js
- **License:** MIT
- **Copyright:** © 2016–2024 Plotly, Inc.

---

## MIT License

The following MIT License applies to **Monaco Editor** (© Microsoft Corporation) and to
**Plotly.js** (© 2016–2024 Plotly, Inc.), with the respective copyright notice above.

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Python dependencies (installed from PyPI, not bundled)

The runtime installs its Python dependencies from PyPI at install time — they are
**not** vendored into this repository, and each carries its own license (predominantly
MIT / BSD-3-Clause / Apache-2.0). Key runtime dependencies and their licenses:

| Package | License |
|---|---|
| dash | MIT |
| dash-bootstrap-components | Apache-2.0 |
| dash-ag-grid | MIT |
| plotly (Python) | MIT |
| plotly-resampler | MIT |
| pandas | BSD-3-Clause |
| pyarrow | Apache-2.0 |
| flask | BSD-3-Clause |
| boto3 / botocore | Apache-2.0 |
| python-dotenv | BSD-3-Clause |

Consult each project for its authoritative license text. This table is informational;
the bundled components above (Monaco, Plotly.js) are the ones whose licenses are
reproduced because their code is redistributed within this package.
