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
from ksylian_agent_app.hashing import file_digest
from ksylian_agent_app.imports import preview_existing_server
import ksylian_agent_app.manifest as manifest_module
from ksylian_agent_app.manifest import save_manifest
from ksylian_agent_app.minecraft import normalize_cpu_limit, normalize_ram, ram_to_bytes
from ksylian_agent_app.mods import mod_metadata_from_fabric, mod_metadata_from_toml, parse_mod_toml_fallback
from ksylian_agent_app.mod_sources import write_mod_source
from ksylian_agent_app.players import normalize_player_name, parse_online_players, player_action_command
from ksylian_agent_app.schemas import StoredServer
from ksylian_agent_app.schemas import PlayerActionRequest
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

    def test_file_digest_returns_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.txt"
            path.write_text("ksylian")

            self.assertEqual(
                file_digest(path, "sha256"),
                "f07b83a9c5c0a44e5fb8453e8530f160daae42d61a220bbc0cd328aa4af002ec",
            )


class ManifestHelperTests(unittest.TestCase):
    def test_manifest_preserves_curseforge_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous_data_dir = manifest_module.DATA_DIR
            previous_append_log = manifest_module.append_action_log
            manifest_module.DATA_DIR = root / "agent-data"
            manifest_module.append_action_log = lambda *_args, **_kwargs: None
            mods_dir = root / "mods"
            mods_dir.mkdir()
            mod_file = mods_dir / "example.jar"
            mod_file.write_bytes(b"not-a-real-jar")
            server = StoredServer(
                id="example",
                name="Example",
                type="forge",
                pack="Forge",
                version="1.20.1",
                port=25565,
                service="example.service",
                path=str(root),
                backup_path=str(root / "world"),
                address="127.0.0.1:25565",
                created_at="test",
                managed=False,
            )
            write_mod_source(server, "example.jar", source="curseforge", project_id="123", file_id="456")

            try:
                manifest = save_manifest(server)
            finally:
                manifest_module.DATA_DIR = previous_data_dir
                manifest_module.append_action_log = previous_append_log

            self.assertEqual(manifest.mods[0].source, "curseforge")
            self.assertEqual(manifest.mods[0].project_id, "123")
            self.assertEqual(manifest.mods[0].file_id, "456")


class ImportPreviewTests(unittest.TestCase):
    def test_import_preview_detects_forge_server_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.properties").write_text("server-port=25570\n")
            (root / "forge-1.20.1-47.2.0.jar").write_bytes(b"jar")
            (root / "mods").mkdir()

            preview = preview_existing_server(str(root), "Imported Forge")

            self.assertEqual(preview.type, "forge")
            self.assertEqual(preview.version, "1.20.1")
            self.assertEqual(preview.java_runtime, "17")
            self.assertEqual(preview.port, 25570)


class PlayerHelperTests(unittest.TestCase):
    def test_parse_online_players_from_rcon_list(self) -> None:
        self.assertEqual(
            parse_online_players("There are 2 of a max of 20 players online: Steve, Alex"),
            ["Steve", "Alex"],
        )

    def test_player_name_validation_and_command(self) -> None:
        self.assertEqual(normalize_player_name("Steve_123"), "Steve_123")
        with self.assertRaises(Exception):
            normalize_player_name("../bad")
        command = player_action_command(PlayerActionRequest(action="kick", player="Steve", reason="AFK"))
        self.assertEqual(command, "kick Steve AFK")


if __name__ == "__main__":
    unittest.main()
