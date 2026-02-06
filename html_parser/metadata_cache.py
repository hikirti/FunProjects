"""
File-based metadata cache for storing and retrieving LLM-generated selectors.

Benefits:
- Cost savings: Don't call LLM for pages we've seen before
- Speed: Skip LLM call for cached structures
- Manual override: Edit cached metadata if LLM got it wrong
- Debugging: Audit what the LLM decided
"""

import json
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime

from .schemas import Metadata
from .logger import get_module_logger

logger = get_module_logger("metadata_cache")


class MetadataCache:
    """
    File-based cache for HTML metadata.

    Stores metadata as JSON files in a cache directory.
    Files are named by hash of the HTML structure (not content).
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize metadata cache.

        Args:
            cache_dir: Directory to store cache files.
                      Defaults to ./metadata_cache/
        """
        if cache_dir is None:
            cache_dir = Path.cwd() / "metadata_cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Metadata cache initialized at: {self.cache_dir}")

    def _generate_cache_key(self, html: str, source_name: Optional[str] = None) -> str:
        """
        Generate a cache key for the HTML.

        Uses source_name if provided (e.g., filename), otherwise
        hashes the HTML structure.
        """
        if source_name:
            # Prefer source_name (e.g. filename) as the cache key because it's
            # human-readable and makes the cache directory easy to audit/edit.
            # Sanitize for filesystem safety: keep only alnum, dash, underscore, dot.
            safe_name = "".join(c if c.isalnum() or c in '-_.' else '_' for c in source_name)
            return safe_name.replace('.html', '').replace('.htm', '')

        # No source name — hash the HTML content as a fallback key.
        # Only hash the first 10KB: the structural selectors we care about are
        # determined by the page's DOM skeleton, which is almost always in the
        # first few KB.  Hashing the full (potentially multi-MB) document would
        # be slow for no benefit, since two pages with different bodies but the
        # same structure would still get the same selectors.
        html_sample = html[:10000]
        # 12 hex chars (48 bits) is enough to avoid collisions in practice
        return hashlib.md5(html_sample.encode('utf-8', errors='replace')).hexdigest()[:12]

    def get(self, html: str, source_name: Optional[str] = None) -> Optional[Metadata]:
        """
        Retrieve cached metadata for HTML.

        Args:
            html: HTML content (used for key generation if no source_name)
            source_name: Optional source identifier (e.g., filename)

        Returns:
            Metadata if cached, None otherwise
        """
        cache_key = self._generate_cache_key(html, source_name)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            logger.debug(f"Cache miss for key: {cache_key}")
            return None

        try:
            data = json.loads(cache_file.read_text())
            metadata = Metadata(**data['metadata'])
            logger.info(f"Cache hit for key: {cache_key}")
            return metadata
        except Exception as e:
            logger.warning(f"Failed to load cached metadata: {e}")
            return None

    def put(
        self,
        html: str,
        metadata: Metadata,
        source_name: Optional[str] = None,
        extra_info: Optional[dict] = None
    ) -> str:
        """
        Store metadata in cache.

        Args:
            html: HTML content
            metadata: Metadata to cache
            source_name: Optional source identifier
            extra_info: Optional extra information to store

        Returns:
            Cache key used
        """
        cache_key = self._generate_cache_key(html, source_name)
        cache_file = self.cache_dir / f"{cache_key}.json"

        cache_data = {
            "cache_key": cache_key,
            "source_name": source_name,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata.model_dump(),
            "extra_info": extra_info or {}
        }

        cache_file.write_text(json.dumps(cache_data, indent=2))
        logger.info(f"Cached metadata with key: {cache_key} -> {cache_file}")

        return cache_key

    def exists(self, html: str, source_name: Optional[str] = None) -> bool:
        """Check if metadata is cached."""
        cache_key = self._generate_cache_key(html, source_name)
        cache_file = self.cache_dir / f"{cache_key}.json"
        return cache_file.exists()

    def delete(self, html: str, source_name: Optional[str] = None) -> bool:
        """Delete cached metadata."""
        cache_key = self._generate_cache_key(html, source_name)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            cache_file.unlink()
            logger.info(f"Deleted cache for key: {cache_key}")
            return True
        return False

    def clear(self) -> int:
        """Clear all cached metadata. Returns count of deleted files."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        logger.info(f"Cleared {count} cached metadata files")
        return count

    def list_cached(self) -> list[dict]:
        """List all cached metadata entries."""
        entries = []
        for cache_file in sorted(self.cache_dir.glob("*.json")):
            try:
                data = json.loads(cache_file.read_text())
                entries.append({
                    "cache_key": data.get("cache_key"),
                    "source_name": data.get("source_name"),
                    "created_at": data.get("created_at"),
                    "file": str(cache_file)
                })
            except Exception:
                pass
        return entries


# Singleton default cache — shared across Analyzer instances to avoid creating
# multiple watchers on the same directory.
_default_cache: Optional[MetadataCache] = None


def get_default_cache() -> MetadataCache:
    """Get or create the default cache instance."""
    global _default_cache
    if _default_cache is None:
        _default_cache = MetadataCache()
    return _default_cache
