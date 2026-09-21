#!/usr/bin/env bash
# Deve ser usado dentro de um nó de cálculo. O frontend não é uma indicação
# confiável da disponibilidade do VTune no PCAD.

if command -v vtune >/dev/null 2>&1; then
    export VTUNE_MODULE_LOADED="PATH"
    return 0
fi

# Instalação documentada para os nós hype do PCAD.
PCAD_VTUNE_ENV=/home/intel/oneapi/vtune/2021.1.1/vtune-vars.sh
if [[ -r "$PCAD_VTUNE_ENV" ]]; then
    # O vtune-vars.sh de 2021 consulta ZSH_VERSION sem testar se ela existe.
    # Os jobs usam `set -u`; suspendemos nounset apenas durante esse source.
    had_nounset=0
    case $- in *u*) had_nounset=1; set +u ;; esac
    source_status=0
    source "$PCAD_VTUNE_ENV" || source_status=$?
    if [[ "$had_nounset" -eq 1 ]]; then set -u; fi
    if [[ "$source_status" -eq 0 ]] && command -v vtune >/dev/null 2>&1; then
        export VTUNE_MODULE_LOADED="$PCAD_VTUNE_ENV"
        return 0
    fi
fi
return 0
