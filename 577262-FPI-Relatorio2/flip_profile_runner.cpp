// Executável pequeno para perfilar somente Flip Horizontal. Ele evita que a
// cópia de restauração entre no trecho repetido pelo VTune: dois flips
// consecutivos restauram a imagem original. A inicialização é deliberadamente
// configurável para testar first-touch/NUMA sem misturar esse custo ao kernel.

#include "image_manipulation.h"

#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include <omp.h>

namespace fs = std::filesystem;

struct Options {
    fs::path image;
    fs::path thread_csv;
    std::string init_mode = "serial";
    int iterations = 1;
};

bool parse(int argc, char** argv, Options& options) {
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if ((argument == "--image" || argument == "--thread-csv" || argument == "--init") && index + 1 < argc) {
            const char* value = argv[++index];
            if (argument == "--image") options.image = value;
            else if (argument == "--thread-csv") options.thread_csv = value;
            else options.init_mode = value;
        } else if (argument == "--iterations" && index + 1 < argc) {
            options.iterations = std::atoi(argv[++index]);
        } else {
            return false;
        }
    }
    return !options.image.empty() && options.iterations > 0 &&
        (options.init_mode == "serial" || options.init_mode == "parallel-static" || options.init_mode == "parallel-runtime");
}

void usage() {
    std::cerr << "Uso: flip_profile_runner --image ARQUIVO --iterations N [--init serial|parallel-static|parallel-runtime] [--thread-csv CSV]\n";
}

bool load_original(const fs::path& path, ImageState& image, std::vector<unsigned char>& original) {
    if (!load_image(path.string().c_str(), image)) return false;
    const size_t bytes = static_cast<size_t>(image.width) * image.height * 3u;
    original.assign(image.data, image.data + bytes);
    std::free(image.data);
    image.data = nullptr;
    return true;
}

void initialize(unsigned char* target, const std::vector<unsigned char>& original, int width, int height, const std::string& mode) {
    if (mode == "serial") {
        std::memcpy(target, original.data(), original.size());
        return;
    }
    if (mode == "parallel-static") {
        #pragma omp parallel for schedule(static)
        for (int row = 0; row < height; ++row) {
            const size_t offset = static_cast<size_t>(row) * width * 3u;
            std::memcpy(target + offset, original.data() + offset, static_cast<size_t>(width) * 3u);
        }
        return;
    }
    #pragma omp parallel for schedule(runtime)
    for (int row = 0; row < height; ++row) {
        const size_t offset = static_cast<size_t>(row) * width * 3u;
        std::memcpy(target + offset, original.data() + offset, static_cast<size_t>(width) * 3u);
    }
}

int main(int argc, char** argv) {
    Options options;
    if (!parse(argc, argv, options)) { usage(); return 2; }

    ImageState loaded{};
    std::vector<unsigned char> original;
    if (!load_original(options.image, loaded, original)) {
        std::cerr << "Não foi possível carregar " << options.image << '\n';
        return 1;
    }
    unsigned char* working = static_cast<unsigned char*>(std::malloc(original.size()));
    if (!working) return 1;
    initialize(working, original, loaded.width, loaded.height, options.init_mode);
    ImageState image{working, loaded.width, loaded.height, false};

    // Amostra por thread, fora do trecho longo que o VTune coleta.
    std::vector<ThreadWorkInfo> work;
    const double control_ms = flip_horizontal_profiled(image, work);
    flip_horizontal(image); // desfaz a amostra, deixando a entrada original.
    if (std::memcmp(working, original.data(), original.size()) != 0) {
        std::cerr << "Falha de validação: dois flips não restauraram a imagem.\n";
        std::free(working);
        return 1;
    }
    if (!options.thread_csv.empty()) {
        std::ofstream output(options.thread_csv);
        output << "Thread,Rows,Work_ms,Init_Mode,Control_ms\n";
        for (const ThreadWorkInfo& info : work) {
            output << info.thread << ',' << info.rows << ',' << info.work_ms << ',' << options.init_mode << ',' << control_ms << '\n';
        }
    }

    // Cada par retorna ao mesmo conteúdo e remove a cópia do caminho perfilado.
    for (int iteration = 0; iteration < options.iterations; ++iteration) {
        flip_horizontal(image);
        flip_horizontal(image);
    }
    if (std::memcmp(working, original.data(), original.size()) != 0) {
        std::cerr << "Falha de validação após profiling.\n";
        std::free(working);
        return 1;
    }
    std::cout << "Flip validado; init=" << options.init_mode << ", iterations=" << options.iterations
              << ", control_ms=" << control_ms << '\n';
    std::free(working);
    return 0;
}
