"""
Preprocessor module for rule-based HTML cleanup.

This module normalizes HTML before it's sent to the LLM analyzer:
- Sanitizes raw HTML string (fixes common malformations)
- Normalizes encoding to UTF-8
- Removes script and style content (but preserves structure info)
- Performs basic structural cleanup

Design principle: NEVER FAIL on bad HTML. Always produce usable output.

Pipeline position: Stage 1 of 3 (Preprocessor → Analyzer → Extractor).
Input:  raw HTML string (possibly malformed, any encoding)
Output: dict with normalized_html, original_html, sanitized_html, encoding info, warnings
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

    # Elements whose content should be removed but tag preserved for structure.
    # We keep the empty tags so the Analyzer can see where scripts/styles lived
    # in the DOM (useful for detecting dynamic-content patterns).
    CONTENT_STRIP_ELEMENTS = ['script', 'style', 'noscript']

    # Elements that are purely non-content
    REMOVE_ELEMENTS = ['meta', 'link']

    # WHATWG encoding spec: browsers silently remap these charsets.
    # https://encoding.spec.whatwg.org/#names-and-labels
    # For example, every browser treats "iso-8859-1" as "windows-1252" because
    # the two are identical for 0x00–0x7F but windows-1252 defines characters
    # in 0x80–0x9F that iso-8859-1 leaves as control codes.  We must match
    # browser behavior so decoded text looks the same as what the user sees.
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
        # Only scan the first 2KB — the HTML spec says charset declarations
        # must appear within the first 1024 bytes; we use 2048 for safety.
        head = raw_bytes[:2048]
        try:
            # Decode as ASCII with errors ignored — we only need to find the
            # charset string, not faithfully decode the whole document.
            head_str = head.decode('ascii', errors='ignore')
        except Exception:
            return 'utf-8'

        charset = None

        # Try the modern form first: <meta charset="...">
        m = re.search(r'<meta[^>]+charset=["\']?\s*([^\s"\';>]+)', head_str, re.IGNORECASE)
        if m:
            charset = m.group(1).strip().lower()

        # Fall back to legacy: <meta http-equiv="Content-Type" content="...; charset=...">
        if not charset:
            m = re.search(
                r'<meta[^>]+content=["\'][^"\']*charset=([^\s"\';>]+)',
                head_str, re.IGNORECASE
            )
            if m:
                charset = m.group(1).strip().lower()

        if not charset:
            return 'utf-8'

        # Apply WHATWG browser mapping so we decode the same way browsers do
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

        # --- Sanitization strategy ---
        # These fixes run in a deliberate order: byte-level first, then structural.
        # Each fix targets a specific class of real-world HTML breakage we've encountered.
        # We always check-then-fix (search before sub) to avoid unnecessary string copies.

        # 1. Replace invalid byte sequences with the Unicode replacement character.
        # This prevents downstream parsers from choking on non-UTF-8 garbage bytes.
        try:
            sanitized = sanitized.encode('utf-8', errors='replace').decode('utf-8')
        except Exception:
            pass

        # 2. NULL bytes crash many parsers and are never valid in HTML text content.
        if '\x00' in sanitized:
            sanitized = sanitized.replace('\x00', '')
            warnings.append("Removed NULL bytes")

        # 3. Double angle brackets (e.g. <<p>>) appear in copy-paste corruption.
        # Collapse them so the parser sees a normal tag.
        double_bracket_pattern = r'<{2,}(\/?[a-zA-Z][^>]*?)>{2,}'
        if re.search(double_bracket_pattern, sanitized):
            sanitized = re.sub(double_bracket_pattern, r'<\1>', sanitized)
            warnings.append("Fixed double angle brackets")

        # 4. Stray '<' not followed by a tag name — escape them to &lt; so they
        # don't confuse the parser into seeing phantom tags.
        stray_brackets = r'<(?![a-zA-Z\/!])'
        if re.search(stray_brackets, sanitized):
            sanitized = re.sub(stray_brackets, '&lt;', sanitized)
            warnings.append("Escaped stray angle brackets")

        # 5. Double-equals in attributes (href=="/path") is a common CMS bug.
        # Reduce to single equals so the attribute value is parsed correctly.
        malformed_attr_pattern = r'(\w+)==(["\'])'
        if re.search(malformed_attr_pattern, sanitized):
            sanitized = re.sub(malformed_attr_pattern, r'\1=\2', sanitized)
            warnings.append("Fixed malformed attributes (double equals)")

        # 6. Unclosed attribute quotes — too risky to fix heuristically; skipped.

        # 7. Orphan closing tags (e.g. </span></footer> without matching openers).
        # We detect but don't remove them — html5lib's tree builder handles
        # rebalancing better than a regex can.
        orphan_pattern = r'</(?:span|div|p|footer|section|header|article|aside|nav)>\s*(?=</)'
        if re.search(orphan_pattern, sanitized, re.IGNORECASE):
            pass

        # 8. Normalize line endings to \n for consistent downstream processing.
        sanitized = sanitized.replace('\r\n', '\n').replace('\r', '\n')

        # 9. Strip control characters (except tab/newline/CR) that can cause
        # invisible parsing failures or corrupt text output.
        control_chars = ''.join(
            chr(c) for c in range(32) if c not in (9, 10, 13)
        )
        if any(c in sanitized for c in control_chars):
            sanitized = sanitized.translate(str.maketrans('', '', control_chars))
            warnings.append("Removed control characters")

        # 10. Encoding artifacts (mojibake) are intentionally preserved here.
        # The raw text represents "browser truth".  Encoding correction happens
        # later in the Extractor via _fix_encoding(), which uses the declared
        # charset to attempt a proper round-trip.

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

        # --- Parser fallback chain: html5lib → lxml → html.parser ---
        # html5lib implements the full WHATWG parsing algorithm, so it handles
        # the worst malformed HTML (unclosed tags, misnested elements, etc.).
        # If it fails (rare — usually means a library bug), we fall back to lxml
        # (fast, C-based, tolerant but not WHATWG-compliant), and finally to
        # Python's built-in html.parser (least tolerant, but always available).
        try:
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
                # Last resort: built-in parser — always available, no C dependencies
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

        # Return multiple representations of the HTML so downstream stages can
        # choose what they need:
        #   normalized_html — for the Analyzer (LLM) to read structure
        #   original_html   — untouched input (useful for debugging)
        #   sanitized_html  — after string-level fixes but before DOM parsing
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

        Some pages inject visible content via document.write() in inline scripts.
        If we just strip script tags, that content is lost.  This method recovers
        the HTML strings passed to document.write() so the Extractor can process
        them as additional content blocks (tagged with a "script:" prefix).

        Args:
            script_text: JavaScript code that may contain document.write()

        Returns:
            List of HTML strings found in document.write() calls
        """
        html_contents = []

        # Two patterns: one for double-quoted strings, one for single-quoted.
        # Each handles escaped quotes inside the string (e.g. \").
        patterns = [
            r'document\.write\s*\(\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*\)',
            r"document\.write\s*\(\s*'([^'\\]*(?:\\.[^'\\]*)*)'\s*\)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, script_text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                # Unescape common JavaScript string escapes to recover the original HTML
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
            'script_srcs': [],              # External script URLs (for debugging/auditing)
            'inline_scripts_had_content': False,
            'document_write_content': []    # HTML recovered from document.write() — fed to Extractor
        }

        # Process script tags — extract useful content before clearing.
        # Order matters: we must grab document.write() HTML *before* calling .clear().
        for script in soup.find_all('script'):
            info['script_count'] += 1

            # Track external script sources (useful for debugging dynamic pages)
            if script.get('src'):
                info['script_srcs'].append(script.get('src'))

            # Inline scripts may contain document.write() with visible content
            if script.string and script.string.strip():
                info['inline_scripts_had_content'] = True
                doc_write_html = self._extract_document_write_content(script.string)
                info['document_write_content'].extend(doc_write_html)

            # Clear the script body to keep the DOM clean for the Analyzer.
            # If preserve_structure is True, the empty <script> tag remains as a
            # structural hint; otherwise, remove the element entirely.
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
