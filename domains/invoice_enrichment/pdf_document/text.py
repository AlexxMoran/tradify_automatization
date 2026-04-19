from __future__ import annotations

import re
import unicodedata

import fitz


class TextRenderer:
    def __init__(self, line_height: float) -> None:
        self._line_height = line_height

    def wrap_cell_text(self, value: str, width: float, font_size: float) -> list[str]:
        normalized = self.prepare_cell_text(value).strip()
        if not normalized:
            return [""]

        wrapped_lines: list[str] = []
        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                wrapped_lines.append("")
                continue
            wrapped_lines.extend(self._wrap_line(line, width, font_size))
        return wrapped_lines or [normalized]

    def prepare_cell_text(self, value: str) -> str:
        text = str(value or "")
        text = text.replace("\u00a0", " ")
        text = text.replace("\u2010", "-").replace("\u2011", "-").replace("\u2012", "-")
        text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r"[^\x0a\x20-\x7e\u00c0-\u024f]", " ", text)
        return re.sub(r"[ ]{2,}", " ", text)

    def draw_multiline_text(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        lines: list[str],
        *,
        font_size: float,
        padding: float,
    ) -> None:
        inner_rect = fitz.Rect(
            rect.x0 + padding,
            rect.y0 + padding,
            rect.x1 - padding,
            rect.y1 - padding,
        )
        remaining = page.insert_textbox(
            inner_rect,
            "\n".join(lines),
            fontsize=font_size,
            fontname="helv",
            lineheight=1.0,
        )
        if remaining >= 0:
            return

        x = rect.x0 + padding
        y = rect.y0 + padding + font_size
        for line in lines:
            if y > rect.y1 - padding:
                break
            page.insert_text(
                fitz.Point(x, y),
                line,
                fontsize=font_size,
                fontname="helv",
            )
            y += self._line_height

    def _wrap_line(self, line: str, width: float, font_size: float) -> list[str]:
        words = line.split()
        if not words:
            return [""]

        lines: list[str] = []
        current = ""
        for word in words:
            if not current:
                if self._fits_width(word, width, font_size):
                    current = word
                    continue
                broken_parts = self._break_long_token(word, width, font_size)
                lines.extend(broken_parts[:-1])
                current = broken_parts[-1]
                continue

            candidate = f"{current} {word}"
            if self._fits_width(candidate, width, font_size):
                current = candidate
                continue

            lines.append(current)
            if self._fits_width(word, width, font_size):
                current = word
                continue

            broken_parts = self._break_long_token(word, width, font_size)
            lines.extend(broken_parts[:-1])
            current = broken_parts[-1]

        if current:
            lines.append(current)
        return lines

    def _break_long_token(
        self, token: str, width: float, font_size: float
    ) -> list[str]:
        if re.search(r"[/\-]", token):
            parts = self._break_token_by_delimiter(token, width, font_size)
            if parts:
                return parts
        return self._break_token_by_char(token, width, font_size)

    def _break_token_by_delimiter(
        self, token: str, width: float, font_size: float
    ) -> list[str]:
        parts = re.split(r"([/\-])", token)
        if len(parts) <= 1:
            return []

        lines: list[str] = []
        current = ""
        index = 0
        while index < len(parts):
            piece = parts[index]
            if not piece:
                index += 1
                continue

            if index + 1 < len(parts) and parts[index + 1] in {"/", "-"}:
                piece = f"{piece}{parts[index + 1]}"
                index += 1

            candidate = f"{current}{piece}"
            if current and self._fits_width(candidate, width, font_size):
                current = candidate
            elif not current and self._fits_width(piece, width, font_size):
                current = piece
            else:
                if current:
                    lines.append(current)
                if self._fits_width(piece, width, font_size):
                    current = piece
                else:
                    char_parts = self._break_token_by_char(piece, width, font_size)
                    lines.extend(char_parts[:-1])
                    current = char_parts[-1]
            index += 1

        if current:
            lines.append(current)
        return lines

    def _break_token_by_char(
        self, token: str, width: float, font_size: float
    ) -> list[str]:
        chunks: list[str] = []
        current = ""
        for char in token:
            candidate = f"{current}{char}"
            if current and not self._fits_width(candidate, width, font_size):
                chunks.append(current)
                current = char
                continue
            current = candidate
        if current:
            chunks.append(current)
        return chunks or [token]

    def _fits_width(self, value: str, width: float, font_size: float) -> bool:
        return fitz.get_text_length(value, fontname="helv", fontsize=font_size) <= width
