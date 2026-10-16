from dataclasses import dataclass


@dataclass(frozen=True)
class Slicer:
    key: str
    name: str
    windows_executable: str
    windows_folder: str
    windows_install_keys: tuple
    windows_uninstall_key: str
    url_scheme: str
    config_folder: str
    mac_bundles: tuple
    linux_binaries: tuple
    flatpak_id: str
    linux_forwarding: bool

    @property
    def config_file(self):
        return self.config_folder + ".conf"


BAMBU_STUDIO = Slicer(
    key="BAMBU_STUDIO",
    name="Bambu Studio",
    windows_executable="bambu-studio.exe",
    windows_folder="Bambu Studio",
    windows_install_keys=((r"SOFTWARE\BambuLab\Bambu Studio", "InstallPath"),),
    windows_uninstall_key="Bambu Studio",
    url_scheme="bambustudio",
    config_folder="BambuStudio",
    mac_bundles=("BambuStudio.app", "Bambu Studio.app"),
    linux_binaries=("bambu-studio", "BambuStudio", "bambustudio"),
    flatpak_id="com.bambulab.BambuStudio",
    linux_forwarding=False,
)

ORCA_SLICER = Slicer(
    key="ORCA_SLICER",
    name="OrcaSlicer",
    windows_executable="orca-slicer.exe",
    windows_folder="OrcaSlicer",
    windows_install_keys=(),
    windows_uninstall_key="OrcaSlicer",
    url_scheme="orcaslicer",
    config_folder="OrcaSlicer",
    mac_bundles=("OrcaSlicer.app",),
    linux_binaries=("orca-slicer", "OrcaSlicer", "orcaslicer"),
    flatpak_id="com.orcaslicer.OrcaSlicer",
    linux_forwarding=True,
)

SLICERS = (BAMBU_STUDIO, ORCA_SLICER)


def get(key):
    return next((slicer for slicer in SLICERS if slicer.key == key), BAMBU_STUDIO)
