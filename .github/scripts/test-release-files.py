"""Check that release dependency gates fail closed and ZIPs preserve permissions."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree
import zipfile

spec = importlib.util.spec_from_file_location("release_files", Path(__file__).with_name("release-files.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
ROOT = Path(__file__).resolve().parents[2]
APP_PLANS = {
    "genefer16": "OCLcudaGFN16",
    "genefer17mega": "OCLcudaGFN17MEGA",
    "genefer18": "OCLcudaGFN18",
    "genefer19": "OCLcudaGFN19",
    "genefer20": "OCLcudaGFN20",
    "genefer": "OCLcudaGFN",
    "genefer_wr": "OCLcudaGFNWR",
    "genefer_extreme": "OCLcudaGFNEXTREME",
}


class ReleaseChecks(unittest.TestCase):
    def inspect(self, report, platform):
        with patch.object(release.subprocess, "check_output", return_value=report), contextlib.redirect_stdout(io.StringIO()):
            release.inspect_binary(Path("vibeferg"), platform)

    def test_linux_boundary(self):
        self.inspect("file format elf64-x86-64\n NEEDED libc.so.6\n NEEDED libOpenCL.so.1\n GLIBC_2.31\n GLIBC_2.2.5", "linux")
        for requirement in ["GLIBC_2.32", "GLIBC_2.34", "GLIBC_PRIVATE", "GLIBC_ABI_DT_RELR"]:
            with self.subTest(requirement=requirement), self.assertRaises(ValueError):
                self.inspect("file format elf64-x86-64\n NEEDED libc.so.6\n " + requirement, "linux")

    def test_linux_rejects_extra_libraries(self):
        for library in ["libgmp.so.10", "libstdc++.so.6", "libgcc_s.so.1", "libboinc.so.7"]:
            with self.subTest(library=library), self.assertRaises(ValueError):
                self.inspect("file format elf64-x86-64\n NEEDED " + library + "\n GLIBC_2.31", "linux")

    def test_windows_dependencies(self):
        self.inspect("file format pei-x86-64\n DLL Name: KERNEL32.dll\n DLL Name: OpenCL.dll\n DLL Name: api-ms-win-crt-runtime-l1-1-0.dll", "windows")
        for library in ["libgmp-10.dll", "libstdc++-6.dll", "libwinpthread-1.dll", "cudart64_12.dll"]:
            with self.subTest(library=library), self.assertRaises(ValueError):
                self.inspect("file format pei-x86-64\n DLL Name: " + library, "windows")

    def test_empty_and_wrong_format_fail(self):
        for platform in ["windows", "linux"]:
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                self.inspect("", platform)

    def test_archives_and_checksums(self):
        original = Path.cwd()
        templates = {name: (ROOT / "doc" / name).read_bytes()
                     for name in ("boinc-app_info.xml", "boinc-app_info-windows.xml")}
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                Path("build").mkdir()
                Path("doc").mkdir()
                for name in ["vibeferg", "vibeferg.exe"]:
                    Path("build", name).write_bytes(b"test executable")
                for name, contents in templates.items():
                    Path("doc", name).write_bytes(contents)
                env = dict(GENEFER_VARIANT="opencl", GITHUB_REF="refs/tags/v1.2.3",
                           GITHUB_SHA="a" * 40, GITHUB_REPOSITORY="example/genefer22", GITHUB_RUN_ID="123")
                with patch.dict(os.environ, env), patch.object(release, "inspect_binary"), contextlib.redirect_stdout(io.StringIO()):
                    for platform in ["windows", "linux"]:
                        release.package(platform)
                    release.checksums()
                for platform, name in [("windows", "vibeferg.exe"), ("linux", "vibeferg")]:
                    path = Path("dist/vibefer-opencl-v1.2.3-" + platform + "-x64.zip")
                    with zipfile.ZipFile(path) as archive:
                        self.assertEqual(set(archive.namelist()), {name, "app_info.xml"})
                        self.assertEqual(stat.S_IMODE(archive.getinfo(name).external_attr >> 16), 0o755)
                        template = "boinc-app_info-windows.xml" if platform == "windows" else "boinc-app_info.xml"
                        xml = archive.read("app_info.xml")
                        self.assertEqual(xml, templates[template])
                        self.check_app_info(xml, platform, name)
                self.assertEqual(len(Path("dist/SHA256SUMS").read_text().splitlines()), 2)
                self.assertIn("/blob/opencl/doc/opencl.md)", Path("release-notes.md").read_text(encoding="utf-8"))
                self.assertEqual(
                    Path("release-notes.md").read_text(encoding="utf-8").split("\n\n")[0],
                    "Experimental build of Vibefer for NVIDIA GPUs. All changes were written by AI "
                    "and haven’t been independently reviewed. It is unofficial and not endorsed by Yves Gallot or PrimeGrid. "
                    "**Install at your own risk.**",
                )
            finally:
                os.chdir(original)

    def check_app_info(self, xml, platform, executable):
        root = ElementTree.fromstring(xml)
        self.assertEqual(root.tag, "app_info")
        declaration, = root.findall("file_info")
        self.assertEqual(declaration.findtext("name"), executable)
        self.assertIsNotNone(declaration.find("executable"))
        self.assertCountEqual([app.findtext("name") for app in root.findall("app")], APP_PLANS)
        versions = root.findall("app_version")
        self.assertCountEqual([version.findtext("app_name") for version in versions], APP_PLANS)
        for version in versions:
            app = version.findtext("app_name")
            with self.subTest(platform=platform, app=app):
                self.assertEqual(version.findtext("plan_class"), APP_PLANS[app])
                expected_platform = "windows_x86_64" if platform == "windows" else "x86_64-pc-linux-gnu"
                self.assertEqual(version.findtext("platform"), expected_platform)
                self.assertEqual(version.findtext("cmdline", "").split(), ["-boinc", "--proof-storage=ram"])
                self.assertEqual(version.findtext("coproc/type"), "NVIDIA")
                self.assertEqual(float(version.findtext("coproc/count")), 1)
                reference, = version.findall("file_ref")
                self.assertEqual(reference.findtext("file_name"), executable)
                self.assertIsNotNone(reference.find("main_program"))


if __name__ == "__main__":
    unittest.main()
