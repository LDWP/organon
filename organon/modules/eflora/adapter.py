"""Network access to eFloras.org.

It hosts the Flora of North America, China and Pakistan on one platform.
No structured API was found: the same species may have a separate record
per regional flora (`flora_id`) on the search results page, extracted by
a targeted regular expression rather than a fragile positional split.
"""

from __future__ import annotations

import re

from organon.core.http import OwnedClientMixin

BASE_URL = "http://www.efloras.org"

# 1 = Flora of North America, 2 = Flora of China, 5 = Flora of Pakistan:
# the only floras whose coverage is judged reliable for this module.
VALID_FLORA_IDS = {1, 2, 5}

_RESULT_RE = re.compile(r"florataxon\.aspx\?flora_id=(\d+)&taxon_id=(\d+)'[^>]*>\s*<b>([^<]+)</b>")


class EfloraAdapter(OwnedClientMixin):
    """Raw eFloras client."""

    async def search(self, name: str) -> list[tuple[int, int, str]]:
        """Return `(flora_id, taxon_id, displayed name)` results.

        Filtered to the valid floras but not yet to the searched name
        (left to module.py).
        """
        resp = await self._client.get(
            f"{BASE_URL}/browse.aspx", params={"flora_id": 0, "name_str": name}
        )
        resp.raise_for_status()
        out = []
        for fid_s, tid_s, found_name in _RESULT_RE.findall(resp.text):
            fid = int(fid_s)
            if fid in VALID_FLORA_IDS:
                out.append((fid, int(tid_s), found_name.strip()))
        return out
