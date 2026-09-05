SHELL := /bin/bash

CXX ?= g++
PKG_CONFIG ?= pkg-config

PROJECT_DIR := 577262-FPI-Relatorio2
BUILD_DIR := build
TARGET := $(BUILD_DIR)/image_editor

SOURCES := \
	$(PROJECT_DIR)/main.cpp \
	$(PROJECT_DIR)/image_manipulation.cpp
OBJECTS := $(patsubst $(PROJECT_DIR)/%.cpp,$(BUILD_DIR)/%.o,$(SOURCES))
DEPS := $(OBJECTS:.o=.d)

GTK_CFLAGS := $(shell $(PKG_CONFIG) --cflags gtk4 2>/dev/null)
GTK_LIBS := $(shell $(PKG_CONFIG) --libs gtk4 2>/dev/null)

CPPFLAGS += -I$(PROJECT_DIR) $(GTK_CFLAGS)
CXXFLAGS ?= -O2 -Wall -Wextra
CXXFLAGS += -std=c++17
DEPFLAGS := -MMD -MP
LDLIBS += $(GTK_LIBS)

.PHONY: all check-deps run run-image run-folder clean

all: $(TARGET)

check-deps:
	@command -v "$(firstword $(CXX))" >/dev/null 2>&1 || { \
		echo "Erro: compilador C++ '$(firstword $(CXX))' não encontrado." >&2; \
		exit 1; \
	}
	@command -v "$(firstword $(PKG_CONFIG))" >/dev/null 2>&1 || { \
		echo "Erro: pkg-config não encontrado." >&2; \
		exit 1; \
	}
	@$(PKG_CONFIG) --exists gtk4 || { \
		echo "Erro: arquivos de desenvolvimento do GTK 4 não encontrados." >&2; \
		echo "No Debian/Ubuntu, instale com: sudo apt install libgtk-4-dev" >&2; \
		exit 1; \
	}

$(TARGET): $(OBJECTS)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(BUILD_DIR)/%.o: $(PROJECT_DIR)/%.cpp | check-deps $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(BUILD_DIR):
	mkdir -p $@

run: $(TARGET)
	@$(TARGET)

run-image: $(TARGET)
	@if [[ -z "$(strip $(IMAGE))" ]]; then \
		echo 'Erro: informe uma imagem com IMAGE="caminho/para/imagem".' >&2; \
		exit 2; \
	fi
	@$(TARGET) "$(IMAGE)"

run-folder: $(TARGET)
	@if [[ -z "$(strip $(FOLDER))" ]]; then \
		echo 'Erro: informe uma pasta com FOLDER="caminho/para/imagens".' >&2; \
		exit 2; \
	fi
	@if [[ ! -d "$(FOLDER)" ]]; then \
		echo "Erro: pasta não encontrada: $(FOLDER)" >&2; \
		exit 2; \
	fi
	@status=0; count=0; \
	while IFS= read -r -d '' image; do \
		count=$$((count + 1)); \
		printf 'Abrindo: %s\n' "$$image"; \
		$(TARGET) "$$image"; \
		result=$$?; \
		if (( result != 0 )); then \
			printf 'Falha ao abrir: %s\n' "$$image" >&2; \
			status=1; \
		fi; \
	done < <(find "$(FOLDER)" -maxdepth 1 -type f \( \
		-iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o \
		-iname '*.bmp' -o -iname '*.tga' -o -iname '*.gif' -o \
		-iname '*.psd' -o -iname '*.hdr' -o -iname '*.pic' -o \
		-iname '*.pnm' -o -iname '*.ppm' -o -iname '*.pgm' \
	\) -print0 | sort -z); \
	if (( count == 0 )); then \
		echo "Erro: nenhuma imagem suportada encontrada em: $(FOLDER)" >&2; \
		exit 2; \
	fi; \
	if (( status != 0 )); then \
		echo "Erro: uma ou mais imagens não puderam ser abertas." >&2; \
	fi; \
	exit $$status

clean:
	rm -rf -- "$(BUILD_DIR)"

-include $(DEPS)
