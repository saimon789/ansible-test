# Ansible role: nvidia-docker

Роль устанавливает пакеты nvidia-driver и cuda (если включен параметр cuda_install) из официального репозитория nVidia.

# Параметры

Роль оперирует следующими параметрами:
1. nvidia_driver_version (по-умолчанию: 470) - версия пакета nvidia-driver
1. cuda_install (по-умолчанию: false) - устанавливать ли пакет cuda
1. cuda_version - версия пакета cuda
1. nvidia_repo_keyring_path (по-умолчанию: /etc/apt/keyrings/nvidia-cuda-repo.gpg) - путь до бинарного (dearmored) keyring-файла для репозитория `nvidia_repo`; используется только на Ubuntu < 22.04 (18.04/20.04), где репозиторий добавляется классическим способом (get_url + gpg --dearmor + apt_repository) вместо deb822_repository
1. nvidia_container_toolkit_keyring_path (по-умолчанию: /etc/apt/keyrings/nvidia-container-toolkit.gpg) - аналогично nvidia_repo_keyring_path, но для репозитория nvidia-container-toolkit

# Формат apt-репозиториев

На Ubuntu 22.04/24.04 репозитории `nvidia_repo` и `nvidia-container-toolkit`
добавляются через `ansible.builtin.deb822_repository` (deb822 `.sources`-формат,
ключ управляется самим модулем). На Ubuntu 18.04/20.04, где deb822-формат не
гарантированно поддерживается, роль скачивает armored GPG-ключ через `get_url`,
переводит его в бинарный keyring через `gpg --dearmor` и добавляет репозиторий
классическим способом через `ansible.builtin.apt_repository` (`sources.list.d`).
Ветвление определяется автоматически по факту `ansible_facts['distribution_version']`
(>= 22.04 или нет), отдельная переменная не нужна.
