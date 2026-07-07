import os

import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ["MOLECULE_INVENTORY_FILE"]
).get_hosts("all")


def test_nvidia_driver_package_installed(host):
    variables = host.ansible.get_variables()
    driver_version = variables["nvidia_driver_version"]
    specific_version = variables.get("nvidia_driver_specific_version", "")

    package_name = f"nvidia-driver-{driver_version}"
    package = host.package(package_name)

    assert package.is_installed
    if specific_version:
        assert package.version == specific_version


def test_unattended_upgrades_blacklist_present(host):
    blacklist = host.file("/etc/apt/apt.conf.d/10nvidia-unattented")

    assert blacklist.exists
    assert blacklist.contains("nvidia-")
    assert blacklist.contains("libnvidia-")


def test_apt_daily_timers_reenabled_after_provisioning(host):
    for timer in ("apt-daily.timer", "apt-daily-upgrade.timer"):
        service = host.service(timer)
        assert service.is_running


def test_nvidia_container_toolkit_when_enabled(host):
    variables = host.ansible.get_variables()
    if not variables.get("nvidia_container_toolkit_install", False):
        return

    assert host.exists("nvidia-ctk")

    config_path = variables.get(
        "nvidia_ctk_containerd_config_path",
        "/etc/containerd/conf.d/99-nvidia.toml",
    )
    assert host.file(config_path).exists


def test_nouveau_module_not_loaded(host):
    lsmod = host.run("lsmod")
    assert "nouveau" not in lsmod.stdout
