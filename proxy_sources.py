"""Read endpoint columns from public proxy tables."""

import base64
import binascii
import re
from html.parser import HTMLParser


_IP_FRAGMENT = r'"([0-9.]{1,128})"'
_INDEX = r"\d{1,3}(?:[+-]\d{1,3})?"


def _index(value):
    return sum(map(int, re.findall(r"[+-]?\d+", value)))


def _encoded_nova_ip(script):
    """Decode the site's limited data expressions without running JavaScript."""
    expression = re.fullmatch(r"\s*document\.write\((.{1,1500})\)\s*;?\s*", script)
    if not expression:
        return ""
    text = expression[1]

    def quoted(data):
        if not re.fullmatch(r"[0-9.]{0,128}", data):
            raise ValueError("Unexpected encoded IP")
        return f'"{data}"'

    def chars(match):
        shift = int(match[2])
        return quoted("".join(chr(int(code) - shift) for code in match[1].split(",")))

    def substring(match):
        count = int(match[2] or 1)
        value = match[1] * count
        start = max(0, _index(match[3]))
        end = len(value) if match[4] is None else max(0, _index(match[4]))
        return quoted(value[min(start, end):max(start, end)])

    try:
        text = re.sub(
            r'atob\("([A-Za-z0-9+/=]{1,128})"\)',
            lambda m: quoted(base64.b64decode(m[1], validate=True).decode("ascii")),
            text,
        )
        text = re.sub(
            r'\[([\d,]{1,256})\]\.map\(\(code\) => String\.fromCharCode\(code-(\d{1,3})\)\)\.join\(""\)',
            chars, text,
        )
        text = re.sub(_IP_FRAGMENT + r'\.split\(""\)\.reverse\(\)\.join\(""\)', lambda m: quoted(m[1][::-1]), text)
        text = re.sub(
            _IP_FRAGMENT + rf'(?:\.repeat\((\d{{1,2}})\))?\.substring\(({_INDEX})(?:,\s*({_INDEX}))?\)',
            substring, text,
        )
    except (ValueError, binascii.Error):
        return ""
    if not re.fullmatch(r'"[0-9.]*"(?:\.concat\("[0-9.]*"\))*', text):
        return ""
    return "".join(re.findall(r'"([0-9.]*)"', text))


class _ProxyTableParser(HTMLParser):
    def __init__(self, encoding):
        super().__init__()
        self.encoding = encoding
        self.rows = []
        self.row = None
        self.cell = None
        self.hidden = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag in ("script", "style"):
            self.hidden = tag
        elif tag == "span" and self.cell is not None and self.encoding == "proxyverity":
            attributes = dict(attrs)
            if "pv-ip-slot" in (attributes.get("class") or "").split():
                try:
                    encoded = attributes.get("data-p") or ""
                    endpoint = base64.b64decode(encoded, validate=True).decode("ascii")[::-1]
                    self.cell.append(endpoint)
                except (ValueError, binascii.Error):
                    pass

    def handle_endtag(self, tag):
        if tag == self.hidden:
            self.hidden = None
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = self.cell = None
        elif tag == "table":
            self.rows.append(None)

    def handle_data(self, data):
        if self.cell is not None:
            if self.hidden is None:
                self.cell.append(data)
            elif self.hidden == "script" and self.encoding == "proxynova":
                self.cell.append(_encoded_nova_ip(data))


def table_entries(text, encoding):
    parser = _ProxyTableParser(encoding)
    parser.feed(text)
    parser.close()
    address = port = protocol = None
    for row in parser.rows:
        if row is None:
            address = port = protocol = None
            continue
        cols = {" ".join(cell.lower().split()): i for i, cell in enumerate(row)}
        headers = ("ip", "ip address", "proxy ip", "ip address and port")
        header_address = next((cols[key] for key in headers if key in cols), None)
        if header_address is not None:
            address = header_address
            port = cols.get("port", cols.get("proxy port"))
            protocol = next((cols[key] for key in ("type", "protocol", "protocols") if key in cols), None)
            continue
        required = [column for column in (address, port, protocol) if column is not None]
        if address is not None and len(row) > max(required):
            yield row[address], row[port] if port is not None else None, row[protocol] if protocol is not None else None
