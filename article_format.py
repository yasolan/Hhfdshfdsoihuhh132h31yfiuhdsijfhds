import html
import re
from markupsafe import Markup

CODE_FENCE_RE = re.compile(r'```([\s\S]*?)```')
TABLE_LINE_RE = re.compile(r'^\s*\|.+\|\s*$')
SEPARATOR_CELL_RE = re.compile(r'^:?-+:?$')


def _inline_format(text):
    """text must already be HTML-escaped"""
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    s = re.sub(r'\*(?!\*)([^*<]+?)\*(?!\*)', r'<em>\1</em>', s)
    s = re.sub(r'\+\+(.+?)\+\+', r'<u>\1</u>', s)
    return s


def _is_table_line(line):
    return bool(TABLE_LINE_RE.match(line))


def _parse_table_row(line):
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def _is_separator_row(cells):
    if not cells:
        return False
    return all(SEPARATOR_CELL_RE.fullmatch(cell.replace(' ', '')) for cell in cells if cell != '')


def _render_table(lines):
    rows = [_parse_table_row(line) for line in lines]
    if len(rows) < 1:
        return ''

    header = rows[0]
    body_start = 1
    if len(rows) > 1 and _is_separator_row(rows[1]):
        body_start = 2

    parts = ['<table class="wiki-table"><thead><tr>']
    for cell in header:
        parts.append(f'<th>{_inline_format(html.escape(cell))}</th>')
    parts.append('</tr></thead><tbody>')

    for row in rows[body_start:]:
        parts.append('<tr>')
        for cell in row:
            parts.append(f'<td>{_inline_format(html.escape(cell))}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table>')
    return ''.join(parts)


def _format_plain_text(text):
    if not text:
        return ''

    lines = text.split('\n')
    chunks = []
    i = 0

    while i < len(lines):
        if _is_table_line(lines[i]):
            table_lines = []
            while i < len(lines) and _is_table_line(lines[i]):
                table_lines.append(lines[i])
                i += 1
            chunks.append(_render_table(table_lines))
        else:
            block_lines = []
            while i < len(lines) and not _is_table_line(lines[i]):
                block_lines.append(lines[i])
                i += 1
            if block_lines:
                chunks.append(_format_paragraph_block(block_lines))
    return ''.join(chunks)


def _format_paragraph_block(lines):
    parts = []
    buffer = []

    def flush():
        if not buffer:
            return
        inner = '<br>'.join(
            _inline_format(html.escape(line)) if line else ''
            for line in buffer
        )
        parts.append(f'<p class="wiki-paragraph">{inner}</p>')
        buffer.clear()

    for line in lines:
        if line.strip() == '':
            flush()
        else:
            buffer.append(line)
    flush()
    return ''.join(parts)


def format_article_content(text):
    if not text:
        return Markup('')

    result = []
    pos = 0
    for match in CODE_FENCE_RE.finditer(text):
        before = text[pos:match.start()]
        if before:
            result.append(_format_plain_text(before))
        code = html.escape(match.group(1).strip('\n'))
        result.append(f'<pre class="wiki-code-block"><code>{code}</code></pre>')
        pos = match.end()

    tail = text[pos:]
    if tail:
        result.append(_format_plain_text(tail))

    return Markup(''.join(result))


def _strip_for_excerpt(text):
    """Plain text for previews: no tables, no code blocks."""
    if not text:
        return ''
    text = CODE_FENCE_RE.sub(' ', text)
    lines = [line for line in text.split('\n') if not _is_table_line(line)]
    return ' '.join(' '.join(lines).split())


def format_article_excerpt(text, max_len=160):
    plain = _strip_for_excerpt(text)
    if len(plain) > max_len:
        plain = plain[:max_len].rstrip() + '…'
    if not plain:
        return Markup('')
    return Markup(_inline_format(html.escape(plain)))
