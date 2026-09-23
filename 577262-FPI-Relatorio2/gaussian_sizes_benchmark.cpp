// Confirma a generalização do algoritmo gaussiano separável para 3, 5, 7, 9 e
// 11 taps. A referência direta e a versão separável usam os mesmos pesos
// binomiais inteiros, logo a validação é exata e não depende da ordem float.

#include "image_manipulation.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

#include <omp.h>

#ifndef BENCHMARK_SIMD_BUILD
#define BENCHMARK_SIMD_BUILD "unknown"
#endif
#ifndef OMP_EXPLICIT_SIMD
#define OMP_EXPLICIT_SIMD 0
#endif
#if OMP_EXPLICIT_SIMD
#define OMP_SIMD _Pragma("omp simd")
#else
#define OMP_SIMD
#endif

namespace fs = std::filesystem;

struct Options { fs::path image; fs::path csv; int taps = 11; int repeat = 1; bool warmup = false; };
struct Planes { explicit Planes(size_t count) : r(count), g(count), b(count) {} std::vector<unsigned char> r, g, b; };

bool parse(int argc, char** argv, Options& options) {
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if ((argument == "--image" || argument == "--taps") && index + 1 < argc) {
            const char* value = argv[++index];
            if (argument == "--image") options.image = value; else options.taps = std::atoi(value);
        } else if (argument == "--repeat" && index + 1 < argc) options.repeat = std::atoi(argv[++index]);
        else if (argument == "--warmup") options.warmup = true;
        else if (!argument.empty() && argument[0] != '-' && options.csv.empty()) options.csv = argument;
        else return false;
    }
    return !options.image.empty() && !options.csv.empty() && options.repeat >= 0 &&
        (options.taps == 3 || options.taps == 5 || options.taps == 7 || options.taps == 9 || options.taps == 11);
}

std::vector<uint32_t> binomial(int taps) {
    std::vector<uint32_t> values(static_cast<size_t>(taps), 1);
    for (int index = 1; index < taps - 1; ++index)
        values[static_cast<size_t>(index)] = values[static_cast<size_t>(index - 1)] * static_cast<uint32_t>(taps - index) / static_cast<uint32_t>(index);
    return values;
}

template <typename Function> double measure(Function&& function) {
    const auto begin = std::chrono::steady_clock::now(); function();
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
}

uint64_t hash_bytes(const unsigned char* data, size_t bytes) {
    uint64_t value = 1469598103934665603ULL;
    for (size_t index = 0; index < bytes; ++index) { value ^= data[index]; value *= 1099511628211ULL; }
    return value;
}

void unpack(const unsigned char* source, Planes& planes, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        OMP_SIMD
        for (int x = 0; x < width; ++x) {
            const size_t pixel = static_cast<size_t>(y) * width + x;
            planes.r[pixel] = source[pixel * 3]; planes.g[pixel] = source[pixel * 3 + 1]; planes.b[pixel] = source[pixel * 3 + 2];
        }
    }
}

void direct(const unsigned char* source, unsigned char* destination, int width, int height, const std::vector<uint32_t>& weights) {
    const int radius = static_cast<int>(weights.size()) / 2, output_width = width - radius * 2;
    const uint64_t normalizer = static_cast<uint64_t>(std::accumulate(weights.begin(), weights.end(), 0u)) * std::accumulate(weights.begin(), weights.end(), 0u);
    #pragma omp parallel for schedule(runtime)
    for (int y = radius; y < height - radius; ++y) {
        OMP_SIMD
        for (int x = radius; x < width - radius; ++x) {
            uint64_t sums[3]{};
            for (int dy = -radius; dy <= radius; ++dy) for (int dx = -radius; dx <= radius; ++dx) {
                const uint64_t weight = static_cast<uint64_t>(weights[static_cast<size_t>(dy + radius)]) * weights[static_cast<size_t>(dx + radius)];
                const size_t input = (static_cast<size_t>(y + dy) * width + x + dx) * 3;
                sums[0] += weight * source[input]; sums[1] += weight * source[input + 1]; sums[2] += weight * source[input + 2];
            }
            const size_t output = (static_cast<size_t>(y - radius) * output_width + x - radius) * 3;
            destination[output] = static_cast<unsigned char>((sums[0] + normalizer / 2) / normalizer);
            destination[output + 1] = static_cast<unsigned char>((sums[1] + normalizer / 2) / normalizer);
            destination[output + 2] = static_cast<unsigned char>((sums[2] + normalizer / 2) / normalizer);
        }
    }
}

void horizontal(const std::vector<unsigned char>& source, std::vector<uint32_t>& intermediate, int width, int height, const std::vector<uint32_t>& weights) {
    const int output_width = width - static_cast<int>(weights.size()) + 1;
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        OMP_SIMD
        for (int x = 0; x < output_width; ++x) {
            uint32_t sum = 0;
            for (size_t tap = 0; tap < weights.size(); ++tap) sum += weights[tap] * source[static_cast<size_t>(y) * width + x + tap];
            intermediate[static_cast<size_t>(y) * output_width + x] = sum;
        }
    }
}

void vertical(const std::vector<uint32_t>& intermediate, std::vector<unsigned char>& destination, int output_width, int output_height, const std::vector<uint32_t>& weights) {
    const uint64_t sum_weights = std::accumulate(weights.begin(), weights.end(), 0u);
    const uint64_t normalizer = sum_weights * sum_weights;
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < output_height; ++y) {
        OMP_SIMD
        for (int x = 0; x < output_width; ++x) {
            uint64_t sum = 0;
            for (size_t tap = 0; tap < weights.size(); ++tap) sum += static_cast<uint64_t>(weights[tap]) * intermediate[(static_cast<size_t>(y) + tap) * output_width + x];
            destination[static_cast<size_t>(y) * output_width + x] = static_cast<unsigned char>((sum + normalizer / 2) / normalizer);
        }
    }
}

int main(int argc, char** argv) {
    Options options; if (!parse(argc, argv, options)) { std::cerr << "Uso: gaussian_sizes_benchmark --image ARQUIVO CSV --taps 3|5|7|9|11 [--repeat N] [--warmup]\n"; return 2; }
    ImageState image{}; if (!load_image(options.image.string().c_str(), image)) return 1;
    const size_t input_bytes = static_cast<size_t>(image.width) * image.height * 3u;
    std::vector<unsigned char> source(image.data, image.data + input_bytes); std::free(image.data);
    const int output_width = image.width - options.taps + 1, output_height = image.height - options.taps + 1;
    const size_t output_pixels = static_cast<size_t>(output_width) * output_height;
    std::vector<unsigned char> direct_output(output_pixels * 3), planar_output(output_pixels * 3);
    Planes input(static_cast<size_t>(image.width) * image.height), output(output_pixels);
    std::vector<uint32_t> intermediate(static_cast<size_t>(image.height) * output_width);
    const std::vector<uint32_t> weights = binomial(options.taps);
    const double conversion_ms = measure([&] { unpack(source.data(), input, image.width, image.height); });
    double direct_ms = 0, horizontal_ms = 0, vertical_ms = 0;
    direct_ms = measure([&] { direct(source.data(), direct_output.data(), image.width, image.height, weights); });
    for (const auto* channel : {&input.r, &input.g, &input.b}) {
        horizontal_ms += measure([&] { horizontal(*channel, intermediate, image.width, image.height, weights); });
        std::vector<unsigned char>* target = channel == &input.r ? &output.r : channel == &input.g ? &output.g : &output.b;
        vertical_ms += measure([&] { vertical(intermediate, *target, output_width, output_height, weights); });
    }
    for (size_t pixel = 0; pixel < output_pixels; ++pixel) { planar_output[pixel * 3] = output.r[pixel]; planar_output[pixel * 3 + 1] = output.g[pixel]; planar_output[pixel * 3 + 2] = output.b[pixel]; }
    const bool valid = direct_output == planar_output;
    if (!valid) { std::cerr << "Validação falhou.\n"; return 1; }
    if (!options.warmup) {
        const bool new_file = !fs::exists(options.csv) || fs::file_size(options.csv) == 0;
        std::ofstream csv(options.csv, std::ios::app);
        if (new_file) csv << "Image,Taps,Threads,Build,Component,Elapsed_ms,Direct_Hash,Separable_Hash,Validation\n";
        const auto write = [&](const char* component, double elapsed) { csv << options.image.filename().string() << ',' << options.taps << ',' << omp_get_max_threads() << ',' << BENCHMARK_SIMD_BUILD << ',' << component << ',' << std::fixed << std::setprecision(6) << elapsed << ',' << std::hex << hash_bytes(direct_output.data(), direct_output.size()) << ',' << hash_bytes(planar_output.data(), planar_output.size()) << std::dec << ",passed\n"; };
        write("AoS_Direct", direct_ms); write("AoS_to_SoA", conversion_ms); write("SoA_Separable_Horizontal", horizontal_ms); write("SoA_Separable_Vertical", vertical_ms); write("SoA_Separable_Kernel", horizontal_ms + vertical_ms);
    }
    return 0;
}
