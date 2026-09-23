SHELL := /bin/bash

CXX ?= g++
PKG_CONFIG ?= pkg-config

PROJECT_DIR := 577262-FPI-Relatorio2
SIMD ?= off
ARCH ?=
DEBUG ?= 0
BUILD_DIR := build/$(SIMD)
BENCHMARK_TARGET := $(BUILD_DIR)/image_benchmark
LAYOUT_TARGET := $(BUILD_DIR)/layout_benchmark
DIAGNOSTIC_TARGET := $(BUILD_DIR)/diagnostic_runner
FLIP_PROFILE_TARGET := $(BUILD_DIR)/flip_profile_runner
GAUSSIAN_SIZES_TARGET := $(BUILD_DIR)/gaussian_sizes_benchmark
GUI_TARGET := $(BUILD_DIR)/image_editor
CONTROL_GENERATOR := $(BUILD_DIR)/generate_controls

CORE_OBJECT := $(BUILD_DIR)/image_manipulation.o
BENCHMARK_OBJECT := $(BUILD_DIR)/benchmark_runner.o
LAYOUT_OBJECT := $(BUILD_DIR)/layout_benchmark.o
DIAGNOSTIC_OBJECT := $(BUILD_DIR)/diagnostic_runner.o
FLIP_PROFILE_OBJECT := $(BUILD_DIR)/flip_profile_runner.o
GAUSSIAN_SIZES_OBJECT := $(BUILD_DIR)/gaussian_sizes_benchmark.o
GUI_OBJECT := $(BUILD_DIR)/main.o
GENERATOR_OBJECT := $(BUILD_DIR)/generate_images.o
OBJECTS := $(CORE_OBJECT) $(BENCHMARK_OBJECT) $(LAYOUT_OBJECT) $(DIAGNOSTIC_OBJECT) $(GUI_OBJECT) $(GENERATOR_OBJECT)
DEPS := $(OBJECTS:.o=.d)

GTK_CFLAGS = $(shell $(PKG_CONFIG) --cflags gtk4 2>/dev/null)
GTK_LIBS = $(shell $(PKG_CONFIG) --libs gtk4 2>/dev/null)

CPPFLAGS += -I$(PROJECT_DIR)
CXXFLAGS ?= -O3 -Wall -Wextra
CXXFLAGS += -std=c++17
OPENMP_FLAGS ?= -fopenmp
CXXFLAGS += $(OPENMP_FLAGS)
# Mantém a aritmética em ponto flutuante bit a bit comparável entre o alvo
# genérico e Haswell. Sem isto, -march=haswell pode introduzir FMA e alterar
# o arredondamento de expressões como a luminância, invalidando hashes mesmo
# quando o algoritmo e os dados são os mesmos. AVX2 continua habilitado.
CXXFLAGS += -ffp-contract=off
ifeq ($(DEBUG),1)
# Símbolos para atribuição de linhas pelo VTune; não altera as otimizações.
CXXFLAGS += -g
endif
LDFLAGS += $(OPENMP_FLAGS)
DEPFLAGS := -MMD -MP
COMPILER_DIAGNOSTICS ?= 0
COMPILER_DIAGNOSTIC_CORE_FLAGS :=
COMPILER_DIAGNOSTIC_LAYOUT_FLAGS :=
ifeq ($(COMPILER_DIAGNOSTICS),1)
# Relatório amplo: registra tanto laços aceitos quanto recusados pelo
# vetorizador. É usado somente no job de evidência, não nos benchmarks.
COMPILER_DIAGNOSTIC_CORE_FLAGS := -fopt-info-vec-all=$(BUILD_DIR)/vectorization-core-all.log
COMPILER_DIAGNOSTIC_LAYOUT_FLAGS := -fopt-info-vec-all=$(BUILD_DIR)/vectorization-layout-all.log
endif

ifeq ($(SIMD),off)
SIMD_FLAGS := -DOMP_EXPLICIT_SIMD=0 -fno-tree-vectorize
VECTOR_REPORT_FLAG :=
else ifeq ($(SIMD),off-avx2)
SIMD_FLAGS := -DOMP_EXPLICIT_SIMD=0 -fno-tree-vectorize -march=haswell
VECTOR_REPORT_FLAG :=
else ifeq ($(SIMD),omp)
SIMD_FLAGS := -DOMP_EXPLICIT_SIMD=1
VECTOR_REPORT_FLAG := -fopt-info-vec-optimized=$(BUILD_DIR)/vectorization-core.log
else ifeq ($(SIMD),omp-avx2)
SIMD_FLAGS := -DOMP_EXPLICIT_SIMD=1 -march=haswell
VECTOR_REPORT_FLAG := -fopt-info-vec-optimized=$(BUILD_DIR)/vectorization-core.log
else
$(error SIMD must be "off", "off-avx2", "omp" or "omp-avx2"; got "$(SIMD)")
endif

# O GCC aceita apenas um arquivo de saída para -fopt-info em uma compilação.
# Na coleta de evidência, o relatório amplo substitui o relatório resumido;
# sem isso, o segundo arquivo pode ficar vazio ou nem ser criado.
ifeq ($(COMPILER_DIAGNOSTICS),1)
VECTOR_REPORT_FLAG :=
endif

ifneq ($(strip $(ARCH)),)
CXXFLAGS += -march=$(ARCH)
endif

CXXFLAGS += $(SIMD_FLAGS)
# BENCHMARK_BUILD_FLAGS contém espaços. As aspas simples fazem o shell entregar
# toda a definição ao compilador como um único argumento; sem isso, a última
# flag (por exemplo -fno-tree-vectorize) receberia uma aspas literal.
CPPFLAGS += -DBENCHMARK_SIMD_BUILD=\"$(SIMD)\" '-DBENCHMARK_BUILD_FLAGS="$(CXXFLAGS)"'

.PHONY: all layout diagnostics flip-profile gaussian-sizes compiler-evidence gui generator generate-controls check-compiler check-gtk run run-benchmark-image run-benchmark-folder clean

all: $(BENCHMARK_TARGET)

layout: $(LAYOUT_TARGET)

diagnostics: $(DIAGNOSTIC_TARGET)

flip-profile: $(FLIP_PROFILE_TARGET)

gaussian-sizes: $(GAUSSIAN_SIZES_TARGET)

compiler-evidence:
	$(MAKE) -B DEBUG=1 SIMD=off-avx2 COMPILER_DIAGNOSTICS=1 layout all
	objdump -d -C --no-show-raw-insn build/off-avx2/layout_benchmark > build/off-avx2/layout_benchmark.asm
	objdump -d -C --no-show-raw-insn build/off-avx2/image_benchmark > build/off-avx2/image_benchmark.asm
	$(MAKE) -B DEBUG=1 SIMD=omp-avx2 COMPILER_DIAGNOSTICS=1 layout all
	objdump -d -C --no-show-raw-insn build/omp-avx2/layout_benchmark > build/omp-avx2/layout_benchmark.asm
	objdump -d -C --no-show-raw-insn build/omp-avx2/image_benchmark > build/omp-avx2/image_benchmark.asm

gui: $(GUI_TARGET)

generator: $(CONTROL_GENERATOR)

generate-controls: $(CONTROL_GENERATOR)
	@$(CONTROL_GENERATOR) --output images/controls --width 6000 --height 6000 --seed 577262

check-compiler:
	@command -v "$(firstword $(CXX))" >/dev/null 2>&1 || { \
		echo "Erro: compilador C++ '$(firstword $(CXX))' não encontrado." >&2; \
		exit 1; \
	}

check-gtk: check-compiler
	@command -v "$(firstword $(PKG_CONFIG))" >/dev/null 2>&1 || { \
		echo "Erro: pkg-config não encontrado." >&2; \
		exit 1; \
	}
	@$(PKG_CONFIG) --exists gtk4 || { \
		echo "Erro: arquivos de desenvolvimento do GTK 4 não encontrados." >&2; \
		echo "No Debian/Ubuntu, instale com: sudo apt install libgtk-4-dev" >&2; \
		exit 1; \
	}

$(BENCHMARK_TARGET): $(CORE_OBJECT) $(BENCHMARK_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(LAYOUT_TARGET): $(CORE_OBJECT) $(LAYOUT_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(DIAGNOSTIC_TARGET): $(CORE_OBJECT) $(DIAGNOSTIC_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(FLIP_PROFILE_TARGET): $(CORE_OBJECT) $(FLIP_PROFILE_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(GAUSSIAN_SIZES_TARGET): $(CORE_OBJECT) $(GAUSSIAN_SIZES_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(GUI_TARGET): $(CORE_OBJECT) $(GUI_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(GTK_LIBS) $(LDLIBS) -o $@

$(CONTROL_GENERATOR): $(GENERATOR_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(CORE_OBJECT): $(PROJECT_DIR)/image_manipulation.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(VECTOR_REPORT_FLAG) $(COMPILER_DIAGNOSTIC_CORE_FLAGS) $(DEPFLAGS) -c $< -o $@

$(BENCHMARK_OBJECT): $(PROJECT_DIR)/benchmark_runner.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(LAYOUT_OBJECT): $(PROJECT_DIR)/layout_benchmark.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(VECTOR_REPORT_FLAG) $(COMPILER_DIAGNOSTIC_LAYOUT_FLAGS) $(DEPFLAGS) -c $< -o $@

$(DIAGNOSTIC_OBJECT): $(PROJECT_DIR)/diagnostic_runner.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(FLIP_PROFILE_OBJECT): $(PROJECT_DIR)/flip_profile_runner.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(GAUSSIAN_SIZES_OBJECT): $(PROJECT_DIR)/gaussian_sizes_benchmark.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(GUI_OBJECT): $(PROJECT_DIR)/main.cpp | check-gtk $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(GTK_CFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(GENERATOR_OBJECT): $(PROJECT_DIR)/generate_images.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(BUILD_DIR):
	mkdir -p $@

run: $(GUI_TARGET)
	@$(GUI_TARGET)

CSV ?= resultados_benchmark.csv

run-benchmark-image: $(BENCHMARK_TARGET)
	@if [[ -z "$(strip $(IMAGE))" ]]; then \
		echo 'Erro: informe uma imagem com IMAGE="caminho/para/imagem".' >&2; \
		exit 2; \
	fi
	@$(BENCHMARK_TARGET) --image "$(IMAGE)" "$(CSV)" $(BENCHMARK_ARGS)

run-benchmark-folder: $(BENCHMARK_TARGET)
	@if [[ -z "$(strip $(FOLDER))" ]]; then \
		echo 'Erro: informe uma pasta com FOLDER="caminho/para/imagens".' >&2; \
		exit 2; \
	fi
	@$(BENCHMARK_TARGET) --folder "$(FOLDER)" "$(CSV)" $(BENCHMARK_ARGS)

clean:
	rm -rf -- build

-include $(DEPS)
