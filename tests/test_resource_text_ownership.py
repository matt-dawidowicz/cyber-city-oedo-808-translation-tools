from __future__ import annotations

import unittest

from cyber_oedo.runtime.resource_text_ownership import (
    RESOURCE_DIRECTORY_DESCRIPTOR_BYTES,
    RESOURCE_DIRECTORY_NAME_BYTES,
    TRACK2_ABSOLUTE_LBA,
)


class ResourceTextOwnershipConstantsTests(unittest.TestCase):
    def test_directory_contract_is_explicit(self) -> None:
        self.assertEqual(RESOURCE_DIRECTORY_NAME_BYTES, 10)
        self.assertEqual(RESOURCE_DIRECTORY_DESCRIPTOR_BYTES, 6)
        self.assertEqual(TRACK2_ABSOLUTE_LBA, 0x0E06)


if __name__ == "__main__":
    unittest.main()
