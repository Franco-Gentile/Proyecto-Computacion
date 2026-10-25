"""Tests para verificar la estructura base de paquetes del repositorio (Issue #1)."""

import importlib
from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parent.parent

REQUIRED_PACKAGES = (
    "common",
    "common.domain",
    "common.application",
    "common.infrastructure",
    "server",
    "worker",
    "supervisor",
    "client",
    "db",
    "docs",
    "tests",
)


class TestPackageStructure(unittest.TestCase):
    """Pruebas de aceptación para la estructura de directorios y paquetes."""

    def test_package_directory_and_init_exist(self) -> None:
        """Verifica que cada paquete tenga su directorio y su archivo __init__.py."""
        for package_name in REQUIRED_PACKAGES:
            with self.subTest(package=package_name):
                relative_path = Path(*package_name.split("."))
                package_dir = ROOT_DIR / relative_path
                init_file = package_dir / "__init__.py"

                self.assertTrue(
                    package_dir.is_dir(),
                    f"El directorio '{relative_path}' no existe.",
                )
                self.assertTrue(
                    init_file.is_file(),
                    f"El archivo '{relative_path}/__init__.py' no existe.",
                )

    def test_package_is_importable(self) -> None:
        """Verifica que cada paquete pueda importarse limpiamente en Python."""
        for package_name in REQUIRED_PACKAGES:
            with self.subTest(package=package_name):
                module = importlib.import_module(package_name)
                self.assertIsNotNone(module)


if __name__ == "__main__":
    unittest.main()
