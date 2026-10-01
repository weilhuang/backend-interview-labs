"""Ordinary directory-header regression; no compressed or PAX sample archives."""
import copy
from pathlib import Path
import sys
import tarfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_toolchain import idea_members, validate_members


class VendorDirectoryTests(unittest.TestCase):
    def directory(self):
        item = tarfile.TarInfo('root/lib')
        item.type = tarfile.DIRTYPE
        item.mode = 0o755
        return item

    def test_identical_empty_directories_coalesce_only_for_pinned_archive(self):
        item = self.directory()
        members, rows = idea_members([item, copy.copy(item)], True)
        self.assertEqual(len(members), 1)
        validate_members(rows, 'root', 1)
        with self.assertRaises(ValueError):
            idea_members([item, copy.copy(item)], False)

    def test_different_directory_metadata_is_not_coalesced(self):
        item = self.directory()
        for field, value in [('mode', 0o700), ('uid', 1), ('gid', 1),
                             ('uname', 'other'), ('gname', 'other'), ('mtime', 1),
                             ('size', 1), ('linkname', 'other')]:
            changed = copy.copy(item)
            setattr(changed, field, value)
            with self.assertRaises(ValueError, msg=field):
                idea_members([item, changed], True)

    def test_file_and_directory_declarations_still_cannot_share_path(self):
        directory = self.directory()
        file = tarfile.TarInfo('root/lib')
        for declarations in ([directory, file], [file, directory], [file, copy.copy(file)]):
            _, rows = idea_members(declarations, True)
            with self.assertRaises(ValueError):
                validate_members(rows, 'root', 1)


if __name__ == '__main__':
    unittest.main()
