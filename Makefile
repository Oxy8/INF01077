SHELL := /bin/bash

CXX ?= g++
PKG_CONFIG ?= pkg-config

PROJECT_DIR := 577262-FPI-Relatorio2
BUILD_DIR := build
BENCHMARK_TARGET := $(BUILD_DIR)/image_benchmark
SCHEDULE_TARGET := $(BUILD_DIR)/image_schedule_benchmark
GUI_TARGET := $(BUILD_DIR)/image_editor

CORE_OBJECT := $(BUILD_DIR)/image_manipulation.o
BENCHMARK_OBJECT := $(BUILD_DIR)/benchmark_runner.o
SCHEDULE_CORE_OBJECT := $(BUILD_DIR)/image_manipulation_schedule.o
SCHEDULE_RUNNER_OBJECT := $(BUILD_DIR)/benchmark_runner_schedule.o
GUI_OBJECT := $(BUILD_DIR)/main.o
OBJECTS := $(CORE_OBJECT) $(BENCHMARK_OBJECT) $(SCHEDULE_CORE_OBJECT) $(SCHEDULE_RUNNER_OBJECT) $(GUI_OBJECT)
DEPS := $(OBJECTS:.o=.d)

GTK_CFLAGS = $(shell $(PKG_CONFIG) --cflags gtk4 2>/dev/null)
GTK_LIBS = $(shell $(PKG_CONFIG) --libs gtk4 2>/dev/null)

CPPFLAGS += -I$(PROJECT_DIR)
CXXFLAGS ?= -O2 -Wall -Wextra
CXXFLAGS += -std=c++17
OPENMP_FLAGS ?= -fopenmp
CXXFLAGS += $(OPENMP_FLAGS)
LDFLAGS += $(OPENMP_FLAGS)
DEPFLAGS := -MMD -MP

.PHONY: all gui schedule-benchmark check-compiler check-gtk run run-benchmark-image run-benchmark-folder clean

all: $(BENCHMARK_TARGET)

gui: $(GUI_TARGET)

schedule-benchmark: $(SCHEDULE_TARGET)

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

$(SCHEDULE_TARGET): $(SCHEDULE_CORE_OBJECT) $(SCHEDULE_RUNNER_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(GUI_TARGET): $(CORE_OBJECT) $(GUI_OBJECT)
	$(CXX) $(LDFLAGS) $^ $(GTK_LIBS) $(LDLIBS) -o $@

$(CORE_OBJECT): $(PROJECT_DIR)/image_manipulation.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(BENCHMARK_OBJECT): $(PROJECT_DIR)/benchmark_runner.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(SCHEDULE_CORE_OBJECT): $(PROJECT_DIR)/image_manipulation.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) -DBENCHMARK_ALL_SCHEDULES $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(SCHEDULE_RUNNER_OBJECT): $(PROJECT_DIR)/benchmark_runner.cpp | check-compiler $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) -DBENCHMARK_ALL_SCHEDULES $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(GUI_OBJECT): $(PROJECT_DIR)/main.cpp | check-gtk $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(GTK_CFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

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
	@$(BENCHMARK_TARGET) --image "$(IMAGE)" "$(CSV)"

run-benchmark-folder: $(BENCHMARK_TARGET)
	@if [[ -z "$(strip $(FOLDER))" ]]; then \
		echo 'Erro: informe uma pasta com FOLDER="caminho/para/imagens".' >&2; \
		exit 2; \
	fi
	@$(BENCHMARK_TARGET) --folder "$(FOLDER)" "$(CSV)"

clean:
	rm -rf -- "$(BUILD_DIR)"

-include $(DEPS)
