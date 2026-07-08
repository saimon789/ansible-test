# `block` / `rescue` / `always` в Ansible

## Зачем это нужно

`block` группирует несколько тасков в один логический шаг. Поверх группы можно
один раз указать `when`, `become`, `tags`, `vars`, `ignore_errors` — не повторяя
их на каждом таске. К группе можно пристегнуть `rescue` (обработка ошибки) и
`always` (гарантированное выполнение) — получается аналог `try / except /
finally` из обычных языков программирования:

| Ansible    | Python       | Когда выполняется                                   |
|------------|--------------|------------------------------------------------------|
| `block`    | `try`        | основные таски                                        |
| `rescue`   | `except`     | только если таск в `block` упал                       |
| `always`   | `finally`    | всегда — успех, ошибка, ошибка + rescue, что угодно    |

## Базовый пример: группировка условия

Вместо повторения одного и того же `when`/`become` на каждом таске:

```yaml
- name: "Install and configure nginx"
  become: true
  when: ansible_facts['os_family'] == 'Debian'
  block:
    - name: Install nginx
      apt:
        name: nginx
        state: present

    - name: Start nginx
      service:
        name: nginx
        state: started
```

`when: ansible_facts['os_family'] == 'Debian'` здесь применяется к **каждому**
таску внутри `block` по отдельности (Ansible разворачивает условие block в
условие на каждый вложенный таск) — это не одна проверка "на весь блок", а
именно копирование условия на каждый таск. Из этого следует нюанс:
если внутри `block` есть `include_tasks`/другой `block`, условие
"размножается" рекурсивно на все таски внутри.

## `rescue`: обработка ошибки и восстановление

Если любой таск в `block` завершается неудачей — Ansible немедленно прерывает
выполнение `block` и переходит в `rescue`. Если `rescue` не упал сам — хост
считается успешным, и play продолжается дальше как ни в чём не бывало.

```yaml
- name: "Try primary mirror, fall back to secondary"
  block:
    - name: Download from primary mirror
      get_url:
        url: "https://primary.example.com/pkg.tar.gz"
        dest: /tmp/pkg.tar.gz
  rescue:
    - name: Primary mirror failed — log it
      debug:
        msg: "Primary mirror unreachable: {{ ansible_failed_result.msg }}"

    - name: Download from secondary mirror instead
      get_url:
        url: "https://mirror.example.com/pkg.tar.gz"
        dest: /tmp/pkg.tar.gz
```

Внутри `rescue` доступны специальные переменные:
- `ansible_failed_task` — полное определение упавшего таска;
- `ansible_failed_result` — его результат (`msg`, `rc`, `stdout` и т.д.).

Если нужно, чтобы ошибка всё-таки "пробилась" наружу после какой-то реакции
(например, только залогировать и остановить play) — внутри `rescue` можно
явно вызвать `fail:`.

## `always`: гарантированная очистка

`always` выполняется **в любом случае**: block прошёл успешно, block упал (с
`rescue` или без), `rescue` сам упал — `always` всё равно запустится. Это то,
что нужно для симметричных операций "включили — обязательно выключим обратно"
(lock-файлы, временные отключения сервисов, снятие maintenance-режима и т.п.).

Важное поведение без `rescue`: если таск в `block` падает, а `rescue` не
задан — `always` всё равно выполняется, а уже **после** него ошибка
"пробрасывается" дальше, и play для этого хоста помечается как failed. То
есть `always` не "проглатывает" ошибку сама по себе — для этого нужен
`rescue`.

### Мини-репродукция (проверено в этой сессии)

```yaml
- hosts: localhost
  gather_facts: false
  tasks:
    - name: simulate provisioning
      block:
        - name: pretend module failed to load
          set_fact:
            module_failed: true

        - name: fail like nvidia module check
          fail:
            msg: "module did not load"
          when: module_failed
      always:
        - name: re-enable timers (should always run)
          debug:
            msg: "timers re-enabled"
```

Результат прогона:

```
TASK [fail like nvidia module check] ***
fatal: [localhost]: FAILED! => {"changed": false, "msg": "module did not load"}

TASK [re-enable timers (should always run)] ***
ok: [localhost] => { "msg": "timers re-enabled" }

PLAY RECAP
localhost : ok=2  changed=0  unreachable=0  failed=1  skipped=0  rescued=0  ignored=0
```

`always`-таск выполнился, **несмотря** на fatal-ошибку в `block` — а сам play
всё равно закончился с `failed=1` (ошибка пробросилась дальше, `rescue` не
было). Именно так и должно работать: очистка гарантирована, но провал факта
установки/загрузки модуля всё равно должен быть виден.

## Реальный пример из этого репозитория

В роли `nvidia-drivers` (`tasks/main.yml`) есть пара тасков, которые
отключают `apt-daily.timer`/`apt-daily-upgrade.timer` и
`unattended-upgrades` перед установкой драйвера — чтобы не ловить конфликт
по dpkg-локу с фоновыми апдейтами. Раньше таски "включить всё обратно"
стояли в конце файла как обычные таски **после** финального `fail`, которым
роль намеренно прерывает play, если модуль `nvidia` не загрузился
(`modprobe`). Проблема: если `fail` срабатывал (а в любом окружении без
реального GPU — например, в Docker при тестах через molecule — он
срабатывает практически всегда), плейбук падал раньше, чем доходил до
re-enable-тасков, и timers/unattended-upgrades оставались выключенными
навсегда на хосте.

Исправлено оборачиванием всей цепочки "установить драйвер → toolkit → cuda →
загрузить модуль → проверить" в `block`, а re-enable-таски — в `always`:

```yaml
- name: "Nvidia | Stop unattended-upgrades to avoid dpkg lock conflicts"
  ansible.builtin.systemd:
    name: unattended-upgrades
    state: stopped
  ignore_errors: true

- name: "Nvidia | Disable apt daily timers during provisioning"
  ansible.builtin.systemd:
    name: "{{ item }}"
    state: stopped
  loop:
    - apt-daily.timer
    - apt-daily-upgrade.timer
  ignore_errors: true

- name: "Nvidia | Install driver, container toolkit, cuda and load kernel module"
  block:
    - name: "Nvidia | Update apt cache"
      ansible.builtin.apt:
        update_cache: true
        cache_valid_time: 3600

    - name: "Nvidia | Install nvidia drivers"
      apt:
        name: "{{ item }}"
        state: "present"
      loop:
        - "nvidia-driver-{{ nvidia_driver_version }}"

    # ... установка linux-modules/dkms, container toolkit, cuda ...

    - name: "Nvidia | Load kernel module"
      modprobe:
        name: "nvidia"
        state: "present"
        persistent: "present"
      ignore_errors: true
      register: nvidia_module_state

    - name: "Nvidia | Fail when module not started"
      fail:
        msg: "Node {{ inventory_hostname }} can`t load nvidia kernel module. Try to restart server"
      when: nvidia_module_state.failed
  always:
    - name: "Nvidia | Re-enable apt daily timers after provisioning"
      ansible.builtin.systemd:
        name: "{{ item }}"
        state: started
      loop:
        - apt-daily.timer
        - apt-daily-upgrade.timer
      ignore_errors: true

    - name: "Nvidia | Re-enable unattended-upgrades"
      ansible.builtin.systemd:
        name: unattended-upgrades
        state: started
      ignore_errors: true
```

Проверено прогоном `molecule test` на `ubuntu-2204` и `ubuntu-2404`: даже
когда `block` падал (в одном случае — на `Install linux-modules` из-за
read-only `/lib/modules` в Docker, в другом — из-за недоступного в noble
пакета `linux-modules-nvidia-530-generic`), таск `Nvidia | Re-enable apt
daily timers after provisioning` в `always` всё равно отработал (`changed`)
— именно то поведение, которое и требовалось.

## Частые грабли

1. **`when` на block копируется на каждый вложенный таск**, а не проверяется
   один раз "на входе в блок". Обычно это не имеет значения, но если внутри
   block есть таск с side-effect до срабатывания условия — таск всё равно
   не выполнится (условие честно проверяется на нём тоже), путаницы не будет.
   Проблемы возникают, если полагаться на "block пропущен → ничего внутри не
   выполнилось и не зарегистрировалось" — это верно, но `register`-переменные
   от пропущенных тасков всё равно создаются (см. следующий пункт).

2. **Пропущенный (`when: false`) таск с `register` всё равно создаёт
   переменную** — со значением `{"changed": false, "skipped": true, ...}`.
   Значит `existing_var.changed` в последующем `when` не упадёт с ошибкой
   "undefined variable", а просто будет `false`. Проверено в этой сессии
   отдельным тестом:

   ```yaml
   - name: maybe-download
     debug:
       msg: "skipped on purpose"
     register: dl_result
     when: false

   - name: use-changed
     debug:
       msg: "would run"
     when: dl_result.changed   # false, но НЕ ошибка — таск просто skipped
   ```

3. **`ignore_errors: true` внутри block "гасит" ошибку до того, как она
   дойдёт до механизма block/rescue/always** — такой таск не считается
   провалившим block. В примере выше `Nvidia | Load kernel module` нарочно
   с `ignore_errors: true` + `register`, а реальное решение "падать или нет"
   вынесено в отдельный явный `fail:`-таск ниже (без `ignore_errors`) — это
   стандартный паттерн, когда нужно самому решить, что считать ошибкой,
   а не полагаться на код возврата модуля.

4. **`rescue` перехватывает только ошибки из `block`**, не из другого
   `rescue` или `always`. Если нужно упасть после какой-то реакции —
   вызывайте `fail:` явно внутри `rescue`.

5. **`block` нельзя зациклить через `loop`** — `loop` можно вешать только на
   обычный таск, не на `block:` целиком (ограничение самого Ansible).
