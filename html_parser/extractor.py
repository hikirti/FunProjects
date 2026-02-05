"""
Module 2: Rule-based Data Extractor.

Extracts structured content blocks from HTML using metadata from the analyzer.
Each block represents a logical unit (paragraph, heading, list item) with
its text content and associated links.
"""

import re
from bs4 import BeautifulSoup
from lxml import etree

from .schemas import Metadata, ExtractionResult, Link, ContentBlock, SelectorList
from .logger import get_module_logger

logger = get_module_logger("extractor")

# Block-level elements that represent logical content units
BLOCK_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'td', 'th',
              'blockquote', 'figcaption', 'dt', 'dd', 'caption', 'div']

# Inline elements whose text should be included
INLINE_TAGS = ['span', 'strong', 'em', 'b', 'i', 'u', 'small', 'mark',
               'sub', 'sup', 'code', 'abbr', 'cite', 'q', 'time']

# Link elements
LINK_TAGS = ['a', 'area']

# Pattern to clean HTML-like garbage from text
HTML_GARBAGE_PATTERN = re.compile(r'<+\s*/?[\w]*\s*>?')


class Extractor:
    """Extracts structured content blocks from HTML."""

    # Regex patterns for hidden inline styles
    HIDDEN_PATTERNS = [
        re.compile(r'display\s*:\s*none', re.IGNORECASE),
        re.compile(r'visibility\s*:\s*hidden', re.IGNORECASE),
    ]

    def __init__(self, include_metadata: bool = False):
        self.include_metadata = include_metadata
        self._declared_charset = None

    def _is_hidden(self, elem) -> bool:
        """Check if element is hidden via inline style."""
        style = elem.get('style', '')
        if not style:
            return False
        return any(p.search(style) for p in self.HIDDEN_PATTERNS)

    def _fix_encoding(self, text: str) -> str:
        """
        Re-encode text with declared charset and decode as UTF-8.

        If the HTML was declared as e.g. windows-1252 but the bytes were
        decoded as UTF-8, the text will contain mojibake. This method
        reverses that by re-encoding with the declared charset and
        decoding as UTF-8.

        Falls back to the original text if the round-trip fails.
        """
        if not self._declared_charset or self._declared_charset.lower() in ('utf-8', 'utf8'):
            return text
        try:
            raw_bytes = text.encode(self._declared_charset)
            return raw_bytes.decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
            return text

    def extract(self, html: str, metadata: Metadata, script_content: list[str] = None,
                declared_charset: str = None) -> ExtractionResult:
        """
        Extract content blocks from HTML.

        Args:
            html: HTML string
            metadata: Metadata from analyzer
            script_content: HTML from document.write() calls
            declared_charset: Charset declared in the HTML document

        Returns:
            ExtractionResult with content blocks
        """
        self._declared_charset = declared_charset
        warnings = []
        logger.info("Starting extraction")

        try:
            soup = BeautifulSoup(html, 'html5lib')
        except Exception as e:
            logger.error(f"HTML parsing failed: {e}")
            return ExtractionResult(blocks=[], warnings=[f"Parse error: {e}"])

        # Find main content elements
        main_elements = self._select_elements(soup, html, metadata.content_zones.main, warnings)
        if not main_elements:
            warnings.append("No main content found, using body")
            main_elements = [soup.find('body')] if soup.find('body') else []

        # Build exclusion set
        excluded = self._build_exclusion_set(soup, html, metadata.content_zones.exclude)

        # Extract blocks from main content
        blocks = []
        processed = set()

        for main_elem in main_elements:
            if main_elem is None:
                continue
            for block in self._extract_blocks(main_elem, excluded, metadata, processed):
                blocks.append(block)

        # Extract standalone links (not inside block elements)
        for main_elem in main_elements:
            if main_elem is None:
                continue
            for block in self._extract_standalone_links(main_elem, excluded, metadata, processed):
                blocks.append(block)

        # Extract content from document.write() scripts
        if script_content:
            for script_html in script_content:
                script_blocks = self._extract_from_script_content(script_html, metadata)
                blocks.extend(script_blocks)
                if script_blocks:
                    logger.info(f"Extracted {len(script_blocks)} blocks from document.write()")

        logger.info(f"Extracted {len(blocks)} content blocks")
        return ExtractionResult(blocks=blocks, warnings=warnings)

    def _get_link_text(self, link_elem) -> str:
        """
        Get link text excluding block-level descendants.

        In malformed HTML like <a>text<p>more</p></a>, the <p> may end up
        nested inside the <a>. We only want the direct/inline text of the
        link, not text from block children (which get extracted separately).
        """
        texts = []
        for child in link_elem.children:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    texts.append(text)
            elif hasattr(child, 'name'):
                if child.name in BLOCK_TAGS:
                    continue  # Skip block elements nested inside links
                if child.name in INLINE_TAGS:
                    texts.append(child.get_text(separator=' ', strip=True))
        return ' '.join(texts)

    def _clean_text(self, text: str) -> str:
        """
        Clean HTML-like garbage from text.

        Removes patterns like:
        - <<<< /p>
        - < /div>
        - <<tag>>
        """
        cleaned = HTML_GARBAGE_PATTERN.sub('', text)
        # Collapse multiple spaces created by removal
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned.strip()

    def _select_elements(self, soup: BeautifulSoup, html: str,
                         selectors: SelectorList, warnings: list) -> list:
        """Select elements using CSS and XPath selectors."""
        elements = []
        seen = set()

        # CSS selectors
        for css in selectors.css:
            try:
                for elem in soup.select(css):
                    if id(elem) not in seen:
                        elements.append(elem)
                        seen.add(id(elem))
            except Exception as e:
                logger.warning(f"Invalid CSS '{css}': {e}")
                warnings.append(f"Invalid CSS: {css}")

        # XPath selectors
        for xpath in selectors.xpath:
            try:
                tree = etree.HTML(html)
                for lxml_elem in tree.xpath(xpath):
                    soup_elem = self._find_matching_soup_element(lxml_elem, soup)
                    if soup_elem and id(soup_elem) not in seen:
                        elements.append(soup_elem)
                        seen.add(id(soup_elem))
            except Exception as e:
                logger.warning(f"Invalid XPath '{xpath}': {e}")
                warnings.append(f"Invalid XPath: {xpath}")

        return elements

    def _find_matching_soup_element(self, lxml_elem, soup: BeautifulSoup):
        """Find BeautifulSoup element matching an lxml element."""
        tag = lxml_elem.tag
        attribs = dict(lxml_elem.attrib)

        # Try by id first
        if 'id' in attribs:
            found = soup.find(id=attribs['id'])
            if found:
                return found

        # Try by class
        if 'class' in attribs:
            found = soup.find(tag, class_=attribs['class'])
            if found:
                return found

        # Fallback to first matching tag
        candidates = soup.find_all(tag)
        return candidates[0] if candidates else None

    def _build_exclusion_set(self, soup: BeautifulSoup, html: str,
                             exclude_selectors: SelectorList) -> set:
        """Build set of element IDs to exclude."""
        excluded = set()
        elements = self._select_elements(soup, html, exclude_selectors, [])

        for elem in elements:
            excluded.add(id(elem))
            for desc in elem.descendants:
                if hasattr(desc, 'name'):
                    excluded.add(id(desc))

        return excluded

    def _extract_blocks(self, container, excluded: set,
                        metadata: Metadata, processed: set) -> list[ContentBlock]:
        """Extract content blocks from a container element."""
        blocks = []

        for tag in BLOCK_TAGS:
            for elem in container.find_all(tag):
                # Skip excluded or already processed
                if id(elem) in excluded or id(elem) in processed:
                    continue

                # Skip hidden elements
                if self._is_hidden(elem):
                    continue

                # Skip if any parent is excluded
                if self._has_excluded_parent(elem, excluded):
                    continue

                # Extract raw text and links
                raw_text = self._get_text(elem, metadata.extraction_hints)
                links = self._get_links(elem, excluded, metadata.extraction_hints)

                # raw = browser truth (mojibake preserved)
                # text = encoding-corrected + cleaned
                cleaned_text = self._clean_text(self._fix_encoding(raw_text))

                # Only add blocks with content
                if cleaned_text or raw_text.strip() or links:
                    blocks.append(ContentBlock(
                        tag=tag,
                        text=cleaned_text,
                        raw=raw_text.strip(),
                        links=links
                    ))
                    processed.add(id(elem))

        return blocks

    def _has_excluded_parent(self, elem, excluded: set) -> bool:
        """Check if element has an excluded ancestor."""
        for parent in elem.parents:
            if id(parent) in excluded:
                return True
        return False

    def _get_text(self, elem, hints) -> str:
        """Extract non-link text from element (raw, before cleanup)."""
        texts = []

        for child in elem.children:
            if isinstance(child, str):
                texts.append(child)
            elif hasattr(child, 'name'):
                if child.name in LINK_TAGS:
                    continue  # Skip link text
                if self._is_hidden(child):
                    continue  # Skip hidden elements
                if child.name in INLINE_TAGS:
                    texts.append(self._get_text(child, hints))
                if hints.include_alt_text and child.name == 'img':
                    alt = child.get('alt', '')
                    if alt:
                        texts.append(f" {alt} ")

        result = ''.join(texts)
        if hints.collapse_whitespace:
            result = re.sub(r'\s+', ' ', result)
        return result

    def _get_links(self, elem, excluded: set, hints) -> list[Link]:
        """Extract links from element."""
        links = []

        for link_elem in elem.find_all(LINK_TAGS):
            if id(link_elem) in excluded:
                continue
            if self._is_hidden(link_elem):
                continue

            href = link_elem.get('href', '').strip()
            if not href or href.startswith('javascript:') or href == '#':
                continue

            # Get link text (excludes block-level descendants)
            raw_text = self._get_link_text(link_elem)

            # Try alt text for image-only links
            if not raw_text and hints.include_alt_text:
                img = link_elem.find('img')
                if img:
                    raw_text = img.get('alt', '').strip()

            # raw = browser truth, text = encoding-corrected + cleaned
            cleaned_text = self._clean_text(self._fix_encoding(raw_text))

            links.append(Link(href=href, text=cleaned_text, raw=raw_text))

        return links

    def _extract_standalone_links(self, container, excluded: set,
                                   metadata: Metadata, processed: set) -> list[ContentBlock]:
        """
        Extract links that aren't inside any block-level element.
        These become their own content blocks.
        """
        blocks = []

        for link_elem in container.find_all(LINK_TAGS):
            if id(link_elem) in excluded or id(link_elem) in processed:
                continue

            # Check if link is inside a block element (container boundary first)
            inside_block = False
            for parent in link_elem.parents:
                if parent == container:
                    break
                if parent.name in BLOCK_TAGS:
                    inside_block = True
                    break

            if inside_block:
                continue

            # Skip if parent is excluded
            if self._has_excluded_parent(link_elem, excluded):
                continue

            href = link_elem.get('href', '').strip()
            if not href or href.startswith('javascript:') or href == '#':
                continue

            raw_text = self._get_link_text(link_elem)

            if not raw_text and metadata.extraction_hints.include_alt_text:
                img = link_elem.find('img')
                if img:
                    raw_text = img.get('alt', '').strip()

            # raw = browser truth, text = encoding-corrected + cleaned
            cleaned_text = self._clean_text(self._fix_encoding(raw_text))

            blocks.append(ContentBlock(
                tag='a',
                text='',
                raw='',
                links=[Link(href=href, text=cleaned_text, raw=raw_text)]
            ))
            processed.add(id(link_elem))

        return blocks


    def _extract_from_script_content(self, script_html: str, metadata: Metadata) -> list[ContentBlock]:
        """
        Extract content blocks from document.write() HTML.

        These blocks are marked with tag prefix 'script:' to indicate
        they came from JavaScript.
        """
        blocks = []

        try:
            soup = BeautifulSoup(script_html, 'html5lib')
            body = soup.find('body')
            if not body:
                return blocks

            processed = set()

            # Extract regular blocks
            for tag in BLOCK_TAGS:
                for elem in body.find_all(tag):
                    if id(elem) in processed:
                        continue

                    raw_text = self._get_text(elem, metadata.extraction_hints)
                    links = self._get_links(elem, set(), metadata.extraction_hints)
                    cleaned_text = self._clean_text(self._fix_encoding(raw_text))

                    if cleaned_text or raw_text.strip() or links:
                        blocks.append(ContentBlock(
                            tag=f"script:{tag}",  # Mark as script-generated
                            text=cleaned_text,
                            raw=raw_text.strip(),
                            links=links
                        ))
                        processed.add(id(elem))

            # Extract standalone links from script content
            for link_elem in body.find_all(LINK_TAGS):
                if id(link_elem) in processed:
                    continue

                # Check if inside a block element (body boundary first)
                inside_block = False
                for parent in link_elem.parents:
                    if parent == body:
                        break
                    if parent.name in BLOCK_TAGS:
                        inside_block = True
                        break

                if inside_block:
                    continue

                href = link_elem.get('href', '').strip()
                if not href or href.startswith('javascript:') or href == '#':
                    continue

                raw_text = self._get_link_text(link_elem)
                cleaned_text = self._clean_text(self._fix_encoding(raw_text))

                blocks.append(ContentBlock(
                    tag='script:a',  # Mark as script-generated
                    text='',
                    raw='',
                    links=[Link(href=href, text=cleaned_text, raw=raw_text)]
                ))
                processed.add(id(link_elem))

        except Exception as e:
            logger.warning(f"Failed to parse document.write content: {e}")

        return blocks


def extract(html: str, metadata: Metadata, script_content: list[str] = None,
            declared_charset: str = None) -> ExtractionResult:
    """Convenience function to extract content from HTML."""
    return Extractor().extract(html, metadata, script_content, declared_charset=declared_charset)
