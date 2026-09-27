// Diagnóstico separado: não altera as funções de produção.
// Os remapeamentos abaixo repetem a aritmética dos laços originais e são
// validados byte a byte contra quantize_gray/equalize_histogram.
#include "image_manipulation.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

#include <omp.h>

#ifndef BENCHMARK_SIMD_BUILD
#define BENCHMARK_SIMD_BUILD "unknown"
#endif
#ifndef BENCHMARK_BUILD_FLAGS
#define BENCHMARK_BUILD_FLAGS "unknown"
#endif
#ifndef OMP_EXPLICIT_SIMD
#define OMP_EXPLICIT_SIMD 0
#endif
#if OMP_EXPLICIT_SIMD
#define PHASE_SIMD _Pragma("omp simd")
#else
#define PHASE_SIMD
#endif

namespace {
using Byte = unsigned char;
using Clock = std::chrono::steady_clock;

struct Options {
    std::string image;
    std::string operation;
    std::string csv;
    int repeat = 0;
    bool warmup = false;
};

struct Measurement {
    std::string phase;
    double milliseconds = 0.0;
    std::string scope;
};

template <class Work>
double measure(Work&& work) {
    const auto start = Clock::now();
    work();
    const auto end = Clock::now();
    return std::chrono::duration<double, std::milli>(end - start).count();
}

bool parse(int argc, char** argv, Options& options) {
    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        if (argument == "--warmup") options.warmup = true;
        else if (argument == "--image" && i + 1 < argc) options.image = argv[++i];
        else if (argument == "--operation" && i + 1 < argc) options.operation = argv[++i];
        else if (argument == "--repeat" && i + 1 < argc) options.repeat = std::stoi(argv[++i]);
        else if (argument == "--csv" && i + 1 < argc) options.csv = argv[++i];
        else return false;
    }
    return !options.image.empty() && !options.csv.empty() && options.repeat >= 0 &&
           (options.operation == "Quantize" || options.operation == "Equalize_Histogram");
}

std::string hash_bytes(const std::vector<Byte>& bytes, bool grayscale) {
    uint64_t hash = 14695981039346656037ULL;
    for (const Byte value : bytes) {
        hash ^= value;
        hash *= 1099511628211ULL;
    }
    hash ^= grayscale ? 1U : 0U;
    hash *= 1099511628211ULL;
    std::ostringstream result;
    result << std::hex << std::setw(16) << std::setfill('0') << hash;
    return result.str();
}

std::string csv_escape(const std::string& value) {
    std::string result = "\"";
    for (const char character : value) {
        if (character == '"') result += "\"\"";
        else result += character;
    }
    return result + '"';
}

// Cópia exata do remapeamento em quantize_gray; mantém a fórmula e a ordem.
void quantize_remap(ImageState& image, Byte minimum, Byte maximum, int levels) {
    const int num_levels = static_cast<int>(maximum) - minimum + 1;
    if (num_levels <= levels) return;
    const float tb = static_cast<float>(num_levels) / levels;
    #pragma omp parallel for schedule(runtime)
    for (int j = 0; j < image.height; ++j) {
        PHASE_SIMD
        for (int i = 0; i < image.width; ++i) {
            const int index = (j * image.width + i) * 3;
            const Byte luminance = image.data[index];
            const int bin = static_cast<int>((luminance - minimum + 0.5) / tb);
            const Byte mapped = static_cast<Byte>(std::round(minimum - 0.5 + (bin + 0.5) * tb));
            image.data[index] = mapped;
            image.data[index + 1] = mapped;
            image.data[index + 2] = mapped;
        }
    }
}

// Cópia dos dois laços de 256 posições em compute_normalized_cummulative_histogram.
void normalize_histogram(unsigned int hist[256], int width, int height) {
    const float factor = 255.0f / (width * height);
    for (int i = 1; i < 256; ++i) hist[i] = hist[i - 1] + hist[i];
    for (int i = 0; i < 256; ++i) hist[i] = std::round(hist[i] * factor);
}

// Cópia do remapeamento em equalize_histogram; não converte a imagem para cinza.
void equalize_remap(ImageState& image, const unsigned int hist[256]) {
    #pragma omp parallel for schedule(runtime)
    for (int i = 0; i < image.height; ++i) {
        PHASE_SIMD
        for (int j = 0; j < image.width; ++j) {
            const int index = (i * image.width + j) * 3;
            for (int channel = 0; channel < 3; ++channel)
                image.data[index + channel] = static_cast<Byte>(hist[image.data[index + channel]]);
        }
    }
}

bool run(const Options& options, const std::vector<Byte>& source, int width, int height,
         std::vector<Measurement>& measurements, std::string& output_hash) {
    std::vector<Byte> full = source;
    ImageState full_image{full.data(), width, height, false};
    if (options.operation == "Quantize") {
        const double total = measure([&] { quantize_gray(full_image, 16); });
        measurements.push_back({"production_total", total, "production"});

        std::vector<Byte> staged = source;
        ImageState stage{staged.data(), width, height, false};
        const double gray = measure([&] { apply_gray_scale_inplace(stage); });
        measurements.push_back({"grayscale", gray, "phase_replica"});

        std::vector<Byte> prepared = staged;
        ImageState post_gray{prepared.data(), width, height, true};
        const double post_gray_ms = measure([&] { quantize_gray(post_gray, 16); });
        measurements.push_back({"production_after_gray", post_gray_ms, "production_prepared_input"});

        std::array<Byte, 2> extrema{};
        const double minmax = measure([&] {
            extrema = find_min_and_max_luminance_on_gray_scale_image(width, height, stage.data);
        });
        measurements.push_back({"minmax", minmax, "phase_replica"});
        const double remap = measure([&] { quantize_remap(stage, extrema[0], extrema[1], 16); });
        measurements.push_back({"remap", remap, "phase_replica"});
        if (staged != full || prepared != full || !stage.isGrayScale || !post_gray.isGrayScale) return false;
    } else {
        unsigned int full_hist[256]{};
        const double total = measure([&] { equalize_histogram(full_image, full_hist); });
        measurements.push_back({"production_total", total, "production"});

        std::vector<Byte> staged = source;
        ImageState stage{staged.data(), width, height, false};
        unsigned int hist[256]{};
        const double count = measure([&] { compute_histogram(stage, hist, false); });
        measurements.push_back({"histogram_count", count, "phase_replica"});
        const double normalize = measure([&] { normalize_histogram(hist, width, height); });
        measurements.push_back({"cdf_normalize", normalize, "phase_replica"});
        const double remap = measure([&] { equalize_remap(stage, hist); });
        measurements.push_back({"remap", remap, "phase_replica"});
        if (staged != full || !std::equal(std::begin(hist), std::end(hist), std::begin(full_hist)))
            return false;
    }
    output_hash = hash_bytes(full, full_image.isGrayScale);
    return true;
}
} // namespace

int main(int argc, char** argv) {
    Options options;
    if (!parse(argc, argv, options)) {
        std::cerr << "Uso: simd_phase_benchmark --image ARQUIVO --operation "
                     "Quantize|Equalize_Histogram --csv ARQUIVO [--repeat N] [--warmup]\n";
        return 2;
    }
    ImageState loaded{};
    if (!load_image(options.image.c_str(), loaded)) return 2;
    const int width = loaded.width, height = loaded.height;
    const size_t bytes = static_cast<size_t>(width) * height * 3;
    const std::vector<Byte> source(loaded.data, loaded.data + bytes);
    std::free(loaded.data);

    std::vector<Measurement> measurements;
    std::string output_hash;
    if (!run(options, source, width, height, measurements, output_hash)) {
        std::cerr << "Divergência entre fases e operação de produção: " << options.operation << '\n';
        return 1;
    }
    if (options.warmup) return 0;
    const bool header = !std::filesystem::exists(options.csv) || std::filesystem::file_size(options.csv) == 0;
    std::ofstream csv(options.csv, std::ios::app);
    if (!csv) return 2;
    if (header) csv << "Image,Operation,Phase,Threads,Build,Repeat,Elapsed_ms,Output_Hash,Exact,Scope,Compiler,Flags\n";
    for (const auto& item : measurements) {
        csv << csv_escape(std::filesystem::path(options.image).filename().string()) << ','
            << csv_escape(options.operation) << ',' << csv_escape(item.phase) << ','
            << omp_get_max_threads() << ',' << csv_escape(BENCHMARK_SIMD_BUILD) << ','
            << options.repeat << ',' << std::setprecision(9) << item.milliseconds << ','
            << output_hash << ",yes," << csv_escape(item.scope) << ','
            << csv_escape(__VERSION__) << ',' << csv_escape(BENCHMARK_BUILD_FLAGS) << '\n';
    }
    return 0;
}
