#!/usr/bin/env python3
"""Create a mildly hardened production HTML file for the static VanGioi site.

This is a deterrent, not source-code security: the browser must still receive
and execute the JavaScript. Keep the editable source in index.html and apply
this transform only to the deploy ZIP.
"""
from __future__ import annotations
import re
import subprocess


def _compact_js(source: str) -> str:
    """Token-aware compacting, preferring the TypeScript JS parser when present.

    The parser prints a normalized JS AST (preserving semantics); a scanner then
    removes trivia only when adjoining tokens remain lexically distinct. This
    safely removes most whitespace/newlines without a third-party minifier.
    If the parser is unavailable, the script is left unchanged to avoid unsafe regex-based rewriting.
    """
    node_script = r"""
const fs = require('fs');
const ts = require('typescript');
const input = fs.readFileSync(0, 'utf8');
const file = ts.createSourceFile('vg.js', input, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
if (file.parseDiagnostics && file.parseDiagnostics.length) { process.exit(3); }
const normalized = ts.createPrinter({removeComments:true, newLine:ts.NewLineKind.LineFeed}).printFile(file);
const scanner = ts.createScanner(ts.ScriptTarget.Latest, true, ts.LanguageVariant.Standard, normalized);
const tokens = [];
for (;;) {
  const kind = scanner.scan();
  if (kind === ts.SyntaxKind.EndOfFileToken) break;
  const start = scanner.getTokenPos(), end = scanner.getTextPos();
  tokens.push({kind, text:normalized.slice(start, end), start, end});
}
function needsSpace(a, b) {
  const pair = ts.createScanner(ts.ScriptTarget.Latest, true, ts.LanguageVariant.Standard, a.text + b.text);
  const k1 = pair.scan(), t1 = pair.getTokenText();
  const k2 = pair.scan(), t2 = pair.getTokenText();
  const k3 = pair.scan();
  return !(k1 === a.kind && t1 === a.text && k2 === b.kind && t2 === b.text && k3 === ts.SyntaxKind.EndOfFileToken);
}
let out = '';
for (let i = 0; i < tokens.length; i++) {
  const token = tokens[i];
  if (i) {
    const gap = normalized.slice(tokens[i-1].end, token.start);
    if (gap.length && needsSpace(tokens[i-1], token)) out += ' ';
  }
  out += token.text;
}
process.stdout.write(out + '\n');
"""
    try:
        result = subprocess.run(["node", "-e", node_script], input=source,
                                text=True, capture_output=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return source


def protect_html(source: str) -> str:
    """Compact inline scripts and require the page's basic shortcut guard."""
    def replace_script(match: re.Match[str]) -> str:
        attrs, body = match.group(1), match.group(2)
        if re.search(r"\bsrc\s*=", attrs, re.I) or not body.strip():
            return match.group(0)
        return "<script" + attrs + ">" + _compact_js(body) + "</script>"

    output = re.sub(r"<script([^>]*)>(.*?)</script>", replace_script,
                    source, flags=re.I | re.S)
    if 'id="vg-web-guard"' not in output:
        raise ValueError("Thiếu bộ chặn phím tắt bảo vệ cơ bản trong index.html")
    # Production output should not ship explicit source-map references.
    output = re.sub(r"\n?\s*//[#@]\s*sourceMappingURL=.*?(?=\n|$)", "", output)
    return output
