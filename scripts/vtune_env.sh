#!/usr/bin/env bash
# Deve ser "source"dentro de um nó de cálculo. O PCAD pode disponibilizar o
# VTune via módulo apenas nos nós; o frontend não é uma indicação confiável.

if command -v vtune >/dev/null 2>&1; then
    export VTUNE_MODULE_LOADED="PATH"
    return 0
fi

# Alguns ambientes Slurm não inicializam modules em shells não interativos.
for module_init in /etc/profile.d/modules.sh /usr/share/Modules/init/bash; do
    [[ -r "$module_init" ]] && source "$module_init"
done

if ! type module >/dev/null 2>&1; then
    return 0
fi

if [[ -n "${VTUNE_MODULE:-}" ]]; then
    if module load "$VTUNE_MODULE" >/dev/null 2>&1 && command -v vtune >/dev/null 2>&1; then
        export VTUNE_MODULE_LOADED="$VTUNE_MODULE"
    fi
    return 0
fi

# Tentativas conservadoras para nomes frequentes; se nenhuma funcionar, o
# preflight registra a ausência e o usuário informa VTUNE_MODULE=nome-exato.
for candidate in intel-oneapi-vtune oneapi-vtune intel/vtune vtune; do
    if module load "$candidate" >/dev/null 2>&1 && command -v vtune >/dev/null 2>&1; then
        export VTUNE_MODULE_LOADED="$candidate"
        return 0
    fi
done

return 0
