from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import ksylian_agent
from ksylian_agent_app.backups import backup_manifest, backup_manifest_path
from ksylian_agent_app.minecraft import normalize_cpu_limit, normalize_ram, ram_to_bytes
from ksylian_agent_app.mods import mod_metadata_from_fabric, mod_metadata_from_toml, parse_mod_toml_fallback
from ksylian_agent_app.security import ensure_child_path, is_relative_path
from ksylian_agent_app.storage import slugify


class AgentSmokeTests(unittest.TestCase):
    def test_agent_shim_exports_fastapi_app(self) -> None:
        self.assertEqual(ksylian_agent.app.title, "Ksylian Host Agent")


class NormalizationTests(unittest.TestCase):
    def test_slugify_normalizes_server_names(self) -> None:
        self.assertEqual(slugify("Hello Ksylian!"), "hello-ksylian")
        self.assertEqual(slugify("   "), "server")

    def test_normalize_ram_accepts_minecraft_units(self) -> None:
        self.assertEqual(normalize_ram("2048M", "1G"), "2048M")
        self.assertEqual(normalize_ram("2g", "1G"), "2G")
        self.assertEqual(normalize_ram("bad", "1G"), "1G")

    def test_ram_to_bytes_and_cpu_clamp(self) -> None:
        self.assertEqual(ram_to_bytes("2G"), 2 * 1024**3)
        self.assertEqual(ram_to_bytes("512M"), 512 * 1024**2)
        self.assertEqual(normalize_cpu_limit(1), 10)
        self.assertEqual(normalize_cpu_limit(999), 400)


class PathSafetyTests(unittest.TestCase):
    def test_child_path_cannot_escape_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(is_relative_path(root / "server" / "world", root))
            with self.assertRaises(Exception):
                ensure_child_path(root, "../outside")


class ModMetadataTests(unittest.TestCase):
    def test_fabric_metadata_extracts_loader_side_and_dependencies(self) -> None:
        metadata = mod_metadata_from_fabric(
            {
                "id": "fabric-api",
                "name": "Fabric API",
                "version": "1.0.0",
                "environment": "*",
                "depends": {"minecraft": ">=1.20", "fabricloader": ">=0.16"},
            },
        )
        self.assertEqual(metadata["loader"], "fabric")
        self.assertEqual(metadata["side"], "both")
        self.assertEqual({item.id for item in metadata["dependencies"]}, {"minecraft", "fabricloader"})

    def test_forge_toml_fallback_extracts_mod_and_dependency(self) -> None:
        parsed = parse_mod_toml_fallback(
            """
            [[mods]]
            modId = "examplemod"
            displayName = "Example Mod"
            version = "1.2.3"

            [[dependencies.examplemod]]
            modId = "forge"
            mandatory = true
            versionRange = "[47,)"
            """,
        )
        metadata = mod_metadata_from_toml(parsed, "forge")
        self.assertEqual(metadata["id"], "examplemod")
        self.assertEqual(metadata["name"], "Example Mod")
        self.assertEqual(metadata["dependencies"][0].id, "forge")


class BackupHelperTests(unittest.TestCase):
    def test_backup_manifest_reads_sidecar_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "server-20260723.tar.gz"
            archive.write_bytes(b"placeholder")
            manifest_path = backup_manifest_path(archive)
            manifest_path.write_text(json.dumps({"server_id": "server", "archive_sha256": "abc"}))

            self.assertEqual(backup_manifest(archive)["server_id"], "server")


if __name__ == "__main__":
    unittest.main()
