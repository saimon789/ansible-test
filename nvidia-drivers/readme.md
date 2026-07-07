# Ansible role: nvidia-docker

Роль устанавливает пакеты nvidia-driver и cuda (если включен параметр cuda_install) из официального репозитория nVidia.

# Параметры

Роль оперирует следующими параметрами:
1. nvidia_driver_version (по-умолчанию: 470) - версия пакета nvidia-driver
1. cuda_install (по-умолчанию: false) - устанавливать ли пакет cuda
1. cuda_version - версия пакета cuda
