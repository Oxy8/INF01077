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
GUI_TARGET := $(BUILD_DIR)/image_editor
CONTROL_GENERATOR := $(BUILD_DIR)/generate_controls

CORE_OBJECT := $(BUILD_DIR)/image_manipulation.o
BENCHMARK_OBJECT := $(BUILD_DIR)/benchmark_runner.o
LAYOUT_OBJECT := $(BUILD_DIR)/layout_benchmark.o
GUI_OBJECT := $(BUILD_DIR)/main.o
GENERATOR_OBJECT := $(BUILD_DIR)/generate_images.o
OBJECTS := $(CORE_OBJECT) $(BENCHMARK_OBJECT) $(LAYOUT_OBJECT) $(GUI_OBJECT) $(GENERATOR_OBJECT)
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

ifneq ($(strip $(ARCH)),)
CXXFLAGS += -march=$(ARCH)
endif

CXXFLAGS += $(SIMD_FLAGS)
# BENCHMARK_BUILD_FLAGS contém espaços. As aspas simples fazem o shell entregar
# toda a definição ao compilador como um único argumento; sem isso, a última
# flag (por exemplo -fno-tree-vectorize) receberia uma aspas literal.
CPPFLAGS += -DBENCHMARK_SIMD_BUILD=\"$(SIMD)\" '-DBENCHMARK_BUILD_FLAGS="$(CXXFLAGS)"'

.PHONY: all layout gui generator generate-controls check-compiler check-gtk run run-benchmark-image run-benchmark-folder clean

all: $(BENCHMARK_TARGET)

layout: $(LAYOUT_TARGET)

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

$(GUI_TARGET): $(CORE_OBJECT) $(GUI_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(GTK_LIBS) $(LDLIBS) -o $@

$(CONTROL_GENERATOR): $(GENERATOR_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(CORE_OBJECT): $(PROJECT_DIR)/image_manipulation.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(VECTOR_REPORT_FLAG) $(DEPFLAGS) -c $< -o $@

$(BENCHMARK_OBJECT): $(PROJECT_DIR)/benchmark_runner.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(LAYOUT_OBJECT): $(PROJECT_DIR)/layout_benchmark.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(VECTOR_REPORT_FLAG) $(DEPFLAGS) -c $< -o $@

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
