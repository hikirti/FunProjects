"""
Preprocessor module for rule-based HTML cleanup.

This module normalizes HTML before it's sent to the LLM analyzer:
- Sanitizes raw HTML string (fixes common malformations)
- Normalizes encoding to UTF-8
- Removes script and style content (but preserves structure info)
- Performs basic structural cleanup

Design principle: NEVER FAIL on bad HTML. Always produce usable output.
"""

import re
from typing import Optional
from bs4 import BeautifulSoup, Comment

from .logger import get_module_logger
from .exceptions import PreprocessorError

logger = get_module_logger("preprocessor")


class Preprocessor:
    """
    Rule-based HTML preprocessor.

    Normalizes HTML for consistent analysis while preserving
    content structure for extraction.
    """

    # Elements whose content should be removed but tag preserved for structure
    CONTENT_STRIP_ELEMENTS = ['script', 'style', 'noscript']

    # Elements that are purely non-content
    REMOVE_ELEMENTS = ['meta', 'link']

    # WHATWG encoding spec: browsers remap these charsets.
    # https://encoding.spec.whatwg.org/#names-and-labels
    WHATWG_CHARSET_MAP = {
        'iso-8859-1': 'windows-1252',
        'iso8859-1': 'windows-1252',
        'iso88591': 'windows-1252',
        'latin-1': 'windows-1252',
        'latin1': 'windows-1252',
        'us-ascii': 'windows-1252',
        'ascii': 'windows-1252',
        'iso-8859-9': 'windows-1254',
        'iso-8859-11': 'windows-874',
    }

    @staticmethod
    def detect_charset_from_bytes(raw_bytes: bytes) -> str:
        """
        Detect charset from raw HTML bytes by scanning the first 2048 bytes
        for <meta charset=...> or <meta http-equiv="Content-Type" content="...; charset=...">.

        Applies WHATWG browser charset mapping (e.g. iso-8859-1 → windows-1252)
        so that decoded text matches what a browser actually displays.

        Returns the browser-equivalent charset or 'utf-8' as default.
        """
        head = raw_bytes[:2048]
        try:
            head_str = head.decode('ascii', errors='ignore')
        except Exception:
            return 'utf-8'

        charset = None

        # <meta charset="...">
        m = re.search(r'<meta[^>]+charset=["\']?\s*([^\s"\';>]+)', head_str, re.IGNORECASE)
        if m:
            charset = m.group(1).strip().lower()

        # <meta http-equiv="Content-Type" content="...; charset=...">
        if not charset:
            m = re.search(
                r'<meta[^>]+content=["\'][^"\']*charset=([^\s"\';>]+)',
                head_str, re.IGNORECASE
            )
            if m:
                charset = m.group(1).strip().lower()

        if not charset:
            return 'utf-8'

        # Apply WHATWG browser mapping
        return Preprocessor.WHATWG_CHARSET_MAP.get(charset, charset)

    def __init__(self, preserve_structure: bool = True):
        """
        Initialize preprocessor.

        Args:
            preserve_structure: If True, keeps empty tags for structure info.
                              If False, removes them completely.
        """
        self.preserve_structure = preserve_structure

    def _sanitize_html(self, html: str) -> tuple[str, list[str]]:
        """
        Sanitize raw HTML string before parsing.

        Fixes common malformations at the string level so parsers
        don't choke on them.

        Args:
            html: Raw HTML string

        Returns:
            Tuple of (sanitized HTML, list of warnings)
        """
        warnings = []
        sanitized = html

        # 1. Remove/replace invalid bytes (non-UTF8 compatible)
        try:
            # Try to encode as UTF-8, replacing errors
            sanitized = sanitized.encode('utf-8', errors='replace').decode('utf-8')
        except Exception:
            pass

        # 2. Remove NULL bytes
        if '\x00' in sanitized:
            sanitized = sanitized.replace('\x00', '')
            warnings.append("Removed NULL bytes")

        # 3. Fix double angle brackets: <<p>> -> <p>
        double_bracket_pattern = r'<{2,}(\/?[a-zA-Z][^>]*?)>{2,}'
        if re.search(double_bracket_pattern, sanitized):
            sanitized = re.sub(double_bracket_pattern, r'<\1>', sanitized)
            warnings.append("Fixed double angle brackets")

        # 4. Fix stray angle brackets not part of tags: <<<< -> (removed)
        # But preserve legitimate tags
        stray_brackets = r'<(?![a-zA-Z\/!])'
        if re.search(stray_brackets, sanitized):
            sanitized = re.sub(stray_brackets, '&lt;', sanitized)
            warnings.append("Escaped stray angle brackets")

        # 5. Fix malformed attributes: href=="/path" -> href="/path"
        malformed_attr_pattern = r'(\w+)==(["\'])'
        if re.search(malformed_attr_pattern, sanitized):
            sanitized = re.sub(malformed_attr_pattern, r'\1=\2', sanitized)
            warnings.append("Fixed malformed attributes (double equals)")

        # 6. Fix unclosed quotes in attributes (basic heuristic)
        # Look for patterns like href="value followed by > without closing quote
        # This is tricky, so we do a conservative fix

        # 7. Remove orphan closing tags that appear before any content
        # e.g., </span></footer></section> at weird places
        orphan_pattern = r'</(?:span|div|p|footer|section|header|article|aside|nav)>\s*(?=</)'
        if re.search(orphan_pattern, sanitized, re.IGNORECASE):
            # Don't remove, just note it - html5lib handles this
            pass

        # 8. Normalize line endings
        sanitized = sanitized.replace('\r\n', '\n').replace('\r', '\n')

        # 9. Remove control characters (except newline, tab)
        control_chars = ''.join(
            chr(c) for c in range(32) if c not in (9, 10, 13)  # tab, newline, carriage return
        )
        if any(c in sanitized for c in control_chars):
            sanitized = sanitized.translate(str.maketrans('', '', control_chars))
            warnings.append("Removed control characters")

        # 10. Encoding artifacts are now preserved intentionally (mojibake = browser truth).
        # Encoding correction happens in the extractor via _fix_encoding().

        logger.debug(f"Sanitization complete. {len(warnings)} fixes applied.")
        return sanitized, warnings

    def process(self, html: str, source_encoding: Optional[str] = None,
                declared_charset: Optional[str] = None) -> dict:
        """
        Process raw HTML and return normalized version.

        Args:
            html: Raw HTML string
            source_encoding: Optional hint for source encoding
            declared_charset: Charset detected from raw bytes (for encoding-aware extraction)

        Returns:
            dict with:
                - normalized_html: Cleaned HTML string
                - detected_encoding: Encoding that was detected/used
                - declared_charset: Charset from byte-level detection
                - original_html: Original HTML (for Module 2)
                - sanitized_html: HTML after string-level fixes (for Module 2)
                - warnings: List of warnings encountered
        """
        warnings = []
        detected_encoding = source_encoding or "utf-8"

        # Step 0: Sanitize raw HTML string BEFORE parsing
        sanitized_html, sanitize_warnings = self._sanitize_html(html)
        warnings.extend(sanitize_warnings)

        try:
            # Parse with html5lib for maximum tolerance of malformed HTML
            soup = BeautifulSoup(sanitized_html, 'html5lib')

            # Try to detect encoding from meta tags
            meta_encoding = self._detect_encoding_from_meta(soup)
            if meta_encoding:
                detected_encoding = meta_encoding
                logger.debug(f"Detected encoding from meta: {meta_encoding}")

        except Exception as e:
            logger.warning(f"html5lib parsing failed, trying lxml: {e}")
            warnings.append(f"html5lib parsing failed: {str(e)}")

            try:
                soup = BeautifulSoup(sanitized_html, 'lxml')
            except Exception as e2:
                logger.warning(f"lxml parsing also failed: {e2}")
                warnings.append(f"lxml parsing failed: {str(e2)}")
                # Last resort: basic parser
                soup = BeautifulSoup(sanitized_html, 'html.parser')

        # Remove comments
        self._remove_comments(soup)

        # Strip content from script/style but preserve tags if needed
        script_style_info = self._process_script_style(soup)
        if script_style_info['script_count'] > 0:
            warnings.append(
                f"Removed content from {script_style_info['script_count']} script tags"
            )
        if script_style_info['style_count'] > 0:
            warnings.append(
                f"Removed content from {script_style_info['style_count']} style tags"
            )

        # Detect anomalies
        anomalies = self._detect_anomalies(html, soup)

        # Get normalized HTML string
        normalized_html = str(soup)

        return {
            "normalized_html": normalized_html,
            "detected_encoding": detected_encoding,
            "declared_charset": declared_charset or detected_encoding,
            "original_html": html,
            "sanitized_html": sanitized_html,
            "warnings": warnings,
            "anomalies": anomalies,
            "script_style_info": script_style_info
        }

    def _detect_encoding_from_meta(self, soup: BeautifulSoup) -> Optional[str]:
        """Detect encoding from meta charset or content-type tags."""
        # Check <meta charset="...">
        meta_charset = soup.find('meta', charset=True)
        if meta_charset:
            return meta_charset.get('charset')

        # Check <meta http-equiv="Content-Type" content="...; charset=...">
        meta_content_type = soup.find(
            'meta',
            attrs={'http-equiv': lambda x: x and x.lower() == 'content-type'}
        )
        if meta_content_type:
            content = meta_content_type.get('content', '')
            if 'charset=' in content.lower():
                charset_part = content.lower().split('charset=')[-1]
                return charset_part.split(';')[0].strip()

        return None

    def _remove_comments(self, soup: BeautifulSoup) -> int:
        """Remove HTML comments. Returns count of removed comments."""
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        count = len(comments)
        for comment in comments:
            comment.extract()
        return count

    def _extract_document_write_content(self, script_text: str) -> list[str]:
        """
        Extract HTML content from document.write() calls.

        Args:
            script_text: JavaScript code that may contain document.write()

        Returns:
            List of HTML strings found in document.write() calls
        """
        html_contents = []

        # Pattern to match document.write("...") or document.write('...')
        # Handles both single and double quotes
        patterns = [
            r'document\.write\s*\(\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*\)',
            r"document\.write\s*\(\s*'([^'\\]*(?:\\.[^'\\]*)*)'\s*\)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, script_text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                # Unescape JavaScript string escapes
                html = match.replace(r'\"', '"').replace(r"\'", "'")
                html = html.replace(r'\n', '\n').replace(r'\t', '\t')
                if html.strip():
                    html_contents.append(html)

        return html_contents

    def _process_script_style(self, soup: BeautifulSoup) -> dict:
        """
        Process script and style elements.

        Extracts document.write() content before removing script content.
        Removes their content but can preserve the empty tags
        to indicate where dynamic content might be.
        """
        info = {
            'script_count': 0,
            'style_count': 0,
            'script_srcs': [],
            'inline_scripts_had_content': False,
            'document_write_content': []  # HTML extracted from document.write()
        }

        # Process script tags
        for script in soup.find_all('script'):
            info['script_count'] += 1

            # Track external script sources
            if script.get('src'):
                info['script_srcs'].append(script.get('src'))

            # Check if inline script had content and extract document.write()
            if script.string and script.string.strip():
                info['inline_scripts_had_content'] = True

                # Extract HTML from document.write() calls
                doc_write_html = self._extract_document_write_content(script.string)
                info['document_write_content'].extend(doc_write_html)

            # Clear content
            script.clear()

            if not self.preserve_structure:
                script.decompose()

        # Process style tags
        for style in soup.find_all('style'):
            info['style_count'] += 1
            style.clear()

            if not self.preserve_structure:
                style.decompose()

        # Process noscript tags
        for noscript in soup.find_all('noscript'):
            noscript.clear()
            if not self.preserve_structure:
                noscript.decompose()

        return info

    def _detect_anomalies(self, original_html: str, soup: BeautifulSoup) -> list[str]:
        """Detect structural anomalies in the HTML."""
        anomalies = []

        # Check for common malformed patterns in original HTML
        if '<<' in original_html:
            anomalies.append("double_angle_brackets")

        if '</' in original_html and original_html.count('</') != original_html.count('<'):
            # Rough heuristic for unclosed tags
            anomalies.append("possible_unclosed_tags")

        # Check for orphan closing tags (closing tags without opening)
        # This is a simplified check
        orphan_patterns = ['</span>', '</div>', '</p>', '</footer>', '</section>']
        for pattern in orphan_patterns:
            if original_html.lower().count(pattern) > 0:
                # Count opening vs closing
                tag_name = pattern[2:-1]
                opening_count = original_html.lower().count(f'<{tag_name}')
                closing_count = original_html.lower().count(f'</{tag_name}>')
                if closing_count > opening_count:
                    anomalies.append(f"orphan_closing_{tag_name}")

        # Check for malformed attributes
        if '==' in original_html and 'href==' in original_html.lower():
            anomalies.append("malformed_href_attribute")

        # Check for mixed tag case (not really an anomaly but worth noting)
        if 'HREF=' in original_html or 'SRC=' in original_html:
            anomalies.append("uppercase_attributes")

        # Check for inline event handlers (potential script interaction)
        event_handlers = ['onclick', 'onload', 'onerror', 'onmouseover']
        for handler in event_handlers:
            if handler in original_html.lower():
                anomalies.append("has_event_handlers")
                break

        return anomalies


def preprocess(html: str, source_encoding: Optional[str] = None,
               declared_charset: Optional[str] = None) -> dict:
    """
    Convenience function to preprocess HTML.

    Args:
        html: Raw HTML string
        source_encoding: Optional encoding hint
        declared_charset: Charset detected from raw bytes

    Returns:
        Preprocessed result dict
    """
    preprocessor = Preprocessor()
    return preprocessor.process(html, source_encoding, declared_charset=declared_charset)
