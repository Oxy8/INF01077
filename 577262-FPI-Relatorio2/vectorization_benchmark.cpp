// Campanha isolada de reescritas: as funções de produção permanecem intactas.
#include "image_manipulation.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <string>
#include <utility>
#include <vector>
#include <omp.h>

#if !defined(_WIN32)
#include <unistd.h>
#endif

#ifndef OMP_EXPLICIT_SIMD
#define OMP_EXPLICIT_SIMD 0
#endif
#if OMP_EXPLICIT_SIMD
#define EXP_SIMD _Pragma("omp simd")
#else
#define EXP_SIMD
#endif
#ifndef BENCHMARK_SIMD_BUILD
#define BENCHMARK_SIMD_BUILD "unknown"
#endif
#ifndef BENCHMARK_BUILD_FLAGS
#define BENCHMARK_BUILD_FLAGS "unknown"
#endif

namespace fs = std::filesystem;
using Byte = unsigned char;
using Clock = std::chrono::steady_clock;

struct Options {
    fs::path image;
    fs::path csv;
    std::string operation;
    int repeat = 1;
    bool warmup = false;
    bool check_production = false;
    int profile_quantize_lookup = 0;
};

struct Picture {
    int width = 0;
    int height = 0;
    std::vector<Byte> bytes;
};

struct Planes {
    explicit Planes(size_t size) : r(size), g(size), b(size) {}
    std::vector<Byte> r, g, b;
};

struct Difference {
    uint64_t count = 0;
    int maximum = 0;
};

struct Row {
    std::string variant;
    std::string phase;
    double elapsed_ms;
    std::string hash;
    std::string reference_hash;
    bool exact;
    Difference difference;
};

std::string csv_text(const std::string& input) {
    if (input.find_first_of(",\"\n") == std::string::npos) return input;
    std::string result = "\"";
    for (char c : input) result += c == '"' ? "\"\"" : std::string(1, c);
    return result + "\"";
}

std::string host_name() {
#if defined(_WIN32)
    const char* name = std::getenv("COMPUTERNAME");
    return name ? name : "unknown";
#else
    char buffer[256]{};
    return gethostname(buffer, sizeof(buffer)) == 0 ? buffer : "unknown";
#endif
}

std::string schedule_name() {
    const char* value = std::getenv("OMP_SCHEDULE");
    return value ? value : "runtime-default";
}

template <class Function> double milliseconds(Function&& function) {
    const auto start = Clock::now();
    function();
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}

std::string hash_picture(const Picture& picture) {
    uint64_t hash = 1469598103934665603ULL;
    const auto add = [&hash](Byte value) { hash ^= value; hash *= 1099511628211ULL; };
    for (uint64_t number : {static_cast<uint64_t>(picture.width), static_cast<uint64_t>(picture.height)})
        for (int byte = 0; byte < 8; ++byte) add(static_cast<Byte>(number >> (byte * 8)));
    for (Byte value : picture.bytes) add(value);
    std::ostringstream text;
    text << std::hex << hash;
    return text.str();
}

Difference difference(const Picture& a, const Picture& b) {
    Difference result;
    if (a.width != b.width || a.height != b.height || a.bytes.size() != b.bytes.size()) {
        result.count = std::numeric_limits<uint64_t>::max();
        result.maximum = 255;
        return result;
    }
    for (size_t index = 0; index < a.bytes.size(); ++index) {
        const int distance = std::abs(static_cast<int>(a.bytes[index]) - static_cast<int>(b.bytes[index]));
        result.count += distance != 0;
        result.maximum = std::max(result.maximum, distance);
    }
    return result;
}

void add_row(std::vector<Row>& rows, const std::string& variant, const std::string& phase,
             double elapsed, const Picture& actual, const Picture& reference) {
    const Difference diff = difference(actual, reference);
    rows.push_back({variant, phase, elapsed, hash_picture(actual), hash_picture(reference), diff.count == 0, diff});
}

void add_phases(std::vector<Row>& rows, const std::string& variant,
                const std::vector<std::pair<std::string, double>>& phases,
                const Picture& actual, const Picture& reference) {
    const Difference diff = difference(actual, reference);
    const std::string actual_hash = hash_picture(actual), reference_hash = hash_picture(reference);
    for (const auto& phase : phases)
        rows.push_back({variant, phase.first, phase.second, actual_hash, reference_hash, diff.count == 0, diff});
}

bool parse(int argc, char** argv, Options& options) {
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if ((argument == "--image" || argument == "--operation" || argument == "--repeat" ||
             argument == "--profile-quantize-lookup") && index + 1 < argc) {
            const char* value = argv[++index];
            if (argument == "--image") options.image = value;
            else if (argument == "--operation") options.operation = value;
            else if (argument == "--repeat") options.repeat = std::atoi(value);
            else {
                char* end = nullptr;
                errno = 0;
                const long count = std::strtol(value, &end, 10);
                if (errno == ERANGE || end == value || *end != '\0' ||
                    count < 1 || count > std::numeric_limits<int>::max())
                    return false;
                options.profile_quantize_lookup = static_cast<int>(count);
            }
        } else if (argument == "--warmup") options.warmup = true;
        else if (argument == "--check-production") options.check_production = true;
        else if (!argument.empty() && argument[0] != '-' && options.csv.empty()) options.csv = argument;
        else return false;
    }
    return !options.image.empty() && !options.csv.empty() && !options.operation.empty() && options.repeat >= 0 &&
           (options.profile_quantize_lookup == 0 || options.operation == "Quantize");
}

// Uma thread recebe uma linha inteira; o laço SIMD percorre bytes RGB
// adjacentes. É o contraste direto com o for(channel) original.
void negative_linear(Byte* data, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        Byte* row = data + static_cast<size_t>(y) * width * 3;
        EXP_SIMD
        for (int byte = 0; byte < width * 3; ++byte) row[byte] = static_cast<Byte>(255 - row[byte]);
    }
}

void brightness_linear(Byte* data, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        Byte* row = data + static_cast<size_t>(y) * width * 3;
        EXP_SIMD
        for (int byte = 0; byte < width * 3; ++byte)
            row[byte] = static_cast<Byte>(std::clamp(static_cast<int>(row[byte]) + 127, 0, 255));
    }
}

void contrast_linear(Byte* data, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        Byte* row = data + static_cast<size_t>(y) * width * 3;
        EXP_SIMD
        for (int byte = 0; byte < width * 3; ++byte) {
            const float value = row[byte] * 1.5f;
            row[byte] = static_cast<Byte>(std::clamp(static_cast<int>(value), 0, 255));
        }
    }
}

void quantize_lut(Byte* data, int width, int height, Byte minimum, Byte maximum) {
    const int count = static_cast<int>(maximum) - minimum + 1;
    if (count <= 16) return;
    const float step = static_cast<float>(count) / 16;
    std::array<Byte, 256> table{};
    for (int value = 0; value < 256; ++value) {
        const int bin = static_cast<int>((value - minimum + 0.5) / step);
        table[static_cast<size_t>(value)] = static_cast<Byte>(std::round(minimum - 0.5 + (bin + 0.5) * step));
    }
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        EXP_SIMD
        for (int x = 0; x < width; ++x) {
            const size_t index = (static_cast<size_t>(y) * width + x) * 3;
            const Byte result = table[data[index]];
            data[index] = result;
            data[index + 1] = result;
            data[index + 2] = result;
        }
    }
}

void histogram_private(const Picture& input, std::array<unsigned int, 256>& output) {
    const int threads = omp_get_max_threads();
    std::vector<std::array<unsigned int, 256>> private_bins(static_cast<size_t>(threads));
    #pragma omp parallel
    {
        auto& bins = private_bins[static_cast<size_t>(omp_get_thread_num())];
        #pragma omp for schedule(runtime)
        for (int y = 0; y < input.height; ++y) {
            for (int x = 0; x < input.width; ++x) {
                const size_t index = (static_cast<size_t>(y) * input.width + x) * 3;
                const Byte r = input.bytes[index], g = input.bytes[index + 1], b = input.bytes[index + 2];
                const Byte gray = static_cast<Byte>(0.299 * r + 0.587 * g + 0.114 * b);
                ++bins[gray];
            }
        }
    }
    output.fill(0);
    for (const auto& bins : private_bins)
        for (size_t bin = 0; bin < output.size(); ++bin) output[bin] += bins[bin];
}

void histogram_normalize(std::array<unsigned int, 256>& bins, int width, int height) {
    const float factor = 255.0f / (width * height);
    for (size_t bin = 1; bin < bins.size(); ++bin) bins[bin] += bins[bin - 1];
    for (auto& value : bins) value = std::round(value * factor);
}

void histogram_remap(Byte* data, int width, int height, const std::array<unsigned int, 256>& bins) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        Byte* row = data + static_cast<size_t>(y) * width * 3;
        EXP_SIMD
        for (int byte = 0; byte < width * 3; ++byte) row[byte] = static_cast<Byte>(bins[row[byte]]);
    }
}

std::vector<uint32_t> weights_for(int taps) {
    std::vector<uint32_t> weights(static_cast<size_t>(taps), 1);
    for (int index = 1; index < taps - 1; ++index)
        weights[static_cast<size_t>(index)] = weights[static_cast<size_t>(index - 1)] * (taps - index) / index;
    return weights;
}

void unpack(const Picture& input, Planes& output) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < input.height; ++y) {
        EXP_SIMD
        for (int x = 0; x < input.width; ++x) {
            const size_t pixel = static_cast<size_t>(y) * input.width + x;
            output.r[pixel] = input.bytes[pixel * 3];
            output.g[pixel] = input.bytes[pixel * 3 + 1];
            output.b[pixel] = input.bytes[pixel * 3 + 2];
        }
    }
}

void pack(const Planes& input, Picture& output) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < output.height; ++y) {
        EXP_SIMD
        for (int x = 0; x < output.width; ++x) {
            const size_t pixel = static_cast<size_t>(y) * output.width + x;
            output.bytes[pixel * 3] = input.r[pixel];
            output.bytes[pixel * 3 + 1] = input.g[pixel];
            output.bytes[pixel * 3 + 2] = input.b[pixel];
        }
    }
}

// Acumuladores de 64 bits mantêm todas as quatro variantes gaussianas exatas
// para os coeficientes binomiais de 3 a 11 taps.
void gaussian_direct_aos(const Picture& input, Picture& output, const std::vector<uint32_t>& weights) {
    const int taps = static_cast<int>(weights.size());
    const uint64_t sum_weights = std::accumulate(weights.begin(), weights.end(), 0ULL);
    const uint64_t divisor = sum_weights * sum_weights;
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < output.height; ++y) {
        EXP_SIMD
        for (int x = 0; x < output.width; ++x) {
            uint64_t sums[3]{};
            for (int dy = 0; dy < taps; ++dy)
                for (int dx = 0; dx < taps; ++dx) {
                    const uint64_t weight = static_cast<uint64_t>(weights[dy]) * weights[dx];
                    const size_t source = (static_cast<size_t>(y + dy) * input.width + x + dx) * 3;
                    for (int channel = 0; channel < 3; ++channel)
                        sums[channel] += weight * input.bytes[source + channel];
                }
            const size_t target = (static_cast<size_t>(y) * output.width + x) * 3;
            for (int channel = 0; channel < 3; ++channel)
                output.bytes[target + channel] = static_cast<Byte>((sums[channel] + divisor / 2) / divisor);
        }
    }
}

void gaussian_direct_soa(const Planes& input, Planes& output, int width, int out_width, int out_height,
                         const std::vector<uint32_t>& weights) {
    const int taps = static_cast<int>(weights.size());
    const uint64_t sum_weights = std::accumulate(weights.begin(), weights.end(), 0ULL);
    const uint64_t divisor = sum_weights * sum_weights;
    const std::array<const std::vector<Byte>*, 3> sources = {&input.r, &input.g, &input.b};
    const std::array<std::vector<Byte>*, 3> targets = {&output.r, &output.g, &output.b};
    for (int channel = 0; channel < 3; ++channel) {
        const Byte* source = sources[channel]->data();
        Byte* target = targets[channel]->data();
        #pragma omp parallel for schedule(runtime)
        for (int y = 0; y < out_height; ++y) {
            EXP_SIMD
            for (int x = 0; x < out_width; ++x) {
                uint64_t sum = 0;
                for (int dy = 0; dy < taps; ++dy)
                    for (int dx = 0; dx < taps; ++dx)
                        sum += static_cast<uint64_t>(weights[dy]) * weights[dx] *
                               source[static_cast<size_t>(y + dy) * width + x + dx];
                target[static_cast<size_t>(y) * out_width + x] = static_cast<Byte>((sum + divisor / 2) / divisor);
            }
        }
    }
}

void gaussian_horizontal(const std::vector<Byte>& source, std::vector<uint32_t>& intermediate,
                         int width, int height, int channels,
                         const std::vector<uint32_t>& weights) {
    const int out_width = width - static_cast<int>(weights.size()) + 1;
    const int row_size = out_width * channels;
    const Byte* input = source.data();
    uint32_t* output = intermediate.data();
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        uint32_t* row = output + static_cast<size_t>(y) * row_size;
        EXP_SIMD
        for (int byte = 0; byte < row_size; ++byte) row[byte] = 0;
        for (size_t tap = 0; tap < weights.size(); ++tap) {
            const Byte* source_row = input + static_cast<size_t>(y) * width * channels + tap * channels;
            const uint32_t weight = weights[tap];
            EXP_SIMD
            for (int byte = 0; byte < row_size; ++byte)
                row[byte] += weight * source_row[byte];
        }
    }
}

void gaussian_vertical(const std::vector<uint32_t>& intermediate, std::vector<Byte>& target,
                       int out_width, int out_height, int channels,
                       const std::vector<uint32_t>& weights) {
    const uint64_t sum_weights = std::accumulate(weights.begin(), weights.end(), 0ULL);
    const uint64_t divisor = sum_weights * sum_weights;
    const int row_size = out_width * channels;
    const uint32_t* input = intermediate.data();
    Byte* output = target.data();
    #pragma omp parallel
    {
        std::vector<uint64_t> sums(static_cast<size_t>(row_size));
        #pragma omp for schedule(runtime)
        for (int y = 0; y < out_height; ++y) {
            uint64_t* sum = sums.data();
            EXP_SIMD
            for (int byte = 0; byte < row_size; ++byte) sum[byte] = 0;
            for (size_t tap = 0; tap < weights.size(); ++tap) {
                const uint32_t* source_row = input + (static_cast<size_t>(y) + tap) * row_size;
                const uint64_t weight = weights[tap];
                EXP_SIMD
                for (int byte = 0; byte < row_size; ++byte)
                    sum[byte] += weight * source_row[byte];
            }
            Byte* destination = output + static_cast<size_t>(y) * row_size;
            EXP_SIMD
            for (int byte = 0; byte < row_size; ++byte)
                destination[byte] = static_cast<Byte>((sum[byte] + divisor / 2) / divisor);
        }
    }
}

void flip_out_of_place(const Picture& input, Picture& output) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < input.height; ++y) {
        EXP_SIMD
        for (int x = 0; x < input.width; ++x) {
            const size_t source = (static_cast<size_t>(y) * input.width + (input.width - 1 - x)) * 3;
            const size_t target = (static_cast<size_t>(y) * input.width + x) * 3;
            output.bytes[target] = input.bytes[source];
            output.bytes[target + 1] = input.bytes[source + 1];
            output.bytes[target + 2] = input.bytes[source + 2];
        }
    }
}

void rotate_blocked(const Picture& input, Picture& output, bool clockwise) {
    constexpr int tile = 32;
    const int x_tiles = (input.width + tile - 1) / tile;
    const int y_tiles = (input.height + tile - 1) / tile;
    #pragma omp parallel for collapse(2) schedule(runtime)
    for (int bx = 0; bx < x_tiles; ++bx)
        for (int by = 0; by < y_tiles; ++by)
            for (int x = bx * tile; x < std::min(input.width, (bx + 1) * tile); ++x) {
                EXP_SIMD
                for (int y = by * tile; y < std::min(input.height, (by + 1) * tile); ++y) {
                    const size_t source = (static_cast<size_t>(y) * input.width + x) * 3;
                    const size_t target_pixel = clockwise
                        ? static_cast<size_t>(input.width - 1 - x) * input.height + y
                        : static_cast<size_t>(x) * input.height + (input.height - 1 - y);
                    const size_t target = target_pixel * 3;
                    output.bytes[target] = input.bytes[source];
                    output.bytes[target + 1] = input.bytes[source + 1];
                    output.bytes[target + 2] = input.bytes[source + 2];
                }
            }
}

bool run_pointwise(const Picture& input, const std::string& operation, std::vector<Row>& rows) {
    Picture reference = input;
    const double reference_ms = milliseconds([&] {
        ImageState state{reference.bytes.data(), reference.width, reference.height, false};
        if (operation == "Negative") apply_negative(state);
        else if (operation == "Adjust_Brightness") adjust_brightness(state, 127);
        else adjust_contrast(state, 1.5f);
    });
    add_row(rows, "original", "total", reference_ms, reference, reference);

    Picture linear = input;
    const double kernel_ms = milliseconds([&] {
        if (operation == "Negative") negative_linear(linear.bytes.data(), linear.width, linear.height);
        else if (operation == "Adjust_Brightness") brightness_linear(linear.bytes.data(), linear.width, linear.height);
        else contrast_linear(linear.bytes.data(), linear.width, linear.height);
    });
    add_phases(rows, "linear_bytes", {{"kernel", kernel_ms}, {"total", kernel_ms}}, linear, reference);
    return difference(linear, reference).count == 0;
}

bool run_quantize(const Picture& input, std::vector<Row>& rows) {
    Picture reference = input;
    const double reference_ms = milliseconds([&] {
        ImageState state{reference.bytes.data(), reference.width, reference.height, false};
        quantize_gray(state, 16);
    });
    add_row(rows, "original", "total", reference_ms, reference, reference);

    Picture candidate = input;
    ImageState state{candidate.bytes.data(), candidate.width, candidate.height, false};
    const double gray_ms = milliseconds([&] { apply_gray_scale_inplace(state); });
    std::array<Byte, 2> extrema{};
    const double reduction_ms = milliseconds([&] {
        extrema = find_min_and_max_luminance_on_gray_scale_image(state.width, state.height, state.data);
    });
    const double lookup_ms = milliseconds([&] {
        quantize_lut(state.data, state.width, state.height, extrema[0], extrema[1]);
    });
    add_phases(rows, "quantize_lut", {{"grayscale", gray_ms}, {"minmax", reduction_ms},
               {"lookup", lookup_ms}, {"total", gray_ms + reduction_ms + lookup_ms}}, candidate, reference);
    return difference(candidate, reference).count == 0;
}

// Repete o MESMO lookup da campanha principal. Restaurar os bytes antes de
// cada chamada evita que as repetições perfílem pixels já quantizados. O
// wrapper não-inline mantém uma região reconhecível na visão de funções do
// VTune sem alterar o caminho normal de run_quantize().
#if defined(__GNUC__)
__attribute__((noinline))
#endif
void profile_quantize_lookup_kernel(Byte* data, int width, int height, Byte minimum, Byte maximum) {
    quantize_lut(data, width, height, minimum, maximum);
}

bool run_quantize_lookup_profile(const Picture& input, int iterations, std::vector<Row>& rows) {
    Picture reference = input;
    ImageState reference_state{reference.bytes.data(), reference.width, reference.height, false};
    quantize_gray(reference_state, 16);

    Picture prepared = input;
    ImageState prepared_state{prepared.bytes.data(), prepared.width, prepared.height, false};
    apply_gray_scale_inplace(prepared_state);
    const auto extrema = find_min_and_max_luminance_on_gray_scale_image(
        prepared_state.width, prepared_state.height, prepared_state.data);
    if (static_cast<int>(extrema[1]) - extrema[0] + 1 <= 16) {
        std::cerr << "A imagem não ativa o lookup de Quantize (intervalo de luminância <= 16).\n";
        return false;
    }

    Picture working = prepared;
    double reset_total_ms = 0.0;
    double lookup_total_ms = 0.0;
    for (int iteration = 0; iteration < iterations; ++iteration) {
        reset_total_ms += milliseconds([&] {
            std::copy(prepared.bytes.begin(), prepared.bytes.end(), working.bytes.begin());
        });
        lookup_total_ms += milliseconds([&] {
            profile_quantize_lookup_kernel(working.bytes.data(), working.width, working.height,
                                           extrema[0], extrema[1]);
        });
    }
    const Difference diff = difference(working, reference);
    if (diff.count != 0) return false;
    add_phases(rows, "quantize_lut_profile",
               {{"reset_average", reset_total_ms / iterations},
                {"lookup_average", lookup_total_ms / iterations}}, working, reference);
    std::cout << "Quantize lookup: " << iterations << " iteracoes; min="
              << static_cast<int>(extrema[0]) << "; max=" << static_cast<int>(extrema[1])
              << "; restauracao="
              << reset_total_ms << " ms; lookup=" << lookup_total_ms
              << " ms; lookup medio=" << lookup_total_ms / iterations << " ms\n";
    return true;
}

bool run_equalize(const Picture& input, std::vector<Row>& rows) {
    Picture reference = input;
    const double reference_ms = milliseconds([&] {
        ImageState state{reference.bytes.data(), reference.width, reference.height, false};
        unsigned int bins[256]{};
        equalize_histogram(state, bins);
    });
    add_row(rows, "original", "total", reference_ms, reference, reference);

    Picture candidate = input;
    std::array<unsigned int, 256> bins{};
    const double count_ms = milliseconds([&] { histogram_private(input, bins); });
    const double cumulative_ms = milliseconds([&] { histogram_normalize(bins, input.width, input.height); });
    const double remap_ms = milliseconds([&] {
        histogram_remap(candidate.bytes.data(), candidate.width, candidate.height, bins);
    });
    add_phases(rows, "private_histogram", {{"count", count_ms}, {"cumulative", cumulative_ms},
               {"remap", remap_ms}, {"total", count_ms + cumulative_ms + remap_ms}}, candidate, reference);
    return difference(candidate, reference).count == 0;
}

bool run_gaussian(const Picture& input, int taps, bool check_production, std::vector<Row>& rows) {
    if (input.width < taps || input.height < taps) return false;
    const int output_width = input.width - taps + 1;
    const int output_height = input.height - taps + 1;
    const size_t pixels = static_cast<size_t>(output_width) * output_height;
    const auto weights = weights_for(taps);

    Picture reference{output_width, output_height, std::vector<Byte>(pixels * 3)};
    const double reference_ms = milliseconds([&] { gaussian_direct_aos(input, reference, weights); });
    add_phases(rows, "aos_direct", {{"kernel", reference_ms}, {"total", reference_ms}}, reference, reference);

    Planes source(static_cast<size_t>(input.width) * input.height);
    const double unpack_ms = milliseconds([&] { unpack(input, source); });
    Planes planar_result(pixels);
    Picture planar_output{output_width, output_height, std::vector<Byte>(pixels * 3)};
    const double direct_planar_ms = milliseconds([&] {
        gaussian_direct_soa(source, planar_result, input.width, output_width, output_height, weights);
    });
    const double direct_pack_ms = milliseconds([&] { pack(planar_result, planar_output); });
    add_phases(rows, "soa_direct", {{"aos_to_soa", unpack_ms}, {"kernel", direct_planar_ms},
               {"soa_to_aos", direct_pack_ms}, {"total", unpack_ms + direct_planar_ms + direct_pack_ms}},
               planar_output, reference);
    bool valid = difference(planar_output, reference).count == 0;

    // AoS separável: mesmo algoritmo e pesos da versão SoA, sem conversão.
    std::vector<uint32_t> aos_intermediate(static_cast<size_t>(input.height) * output_width * 3);
    Picture aos_separable{output_width, output_height, std::vector<Byte>(pixels * 3)};
    const double aos_horizontal_ms = milliseconds([&] {
        gaussian_horizontal(input.bytes, aos_intermediate, input.width, input.height, 3, weights);
    });
    const double aos_vertical_ms = milliseconds([&] {
        gaussian_vertical(aos_intermediate, aos_separable.bytes, output_width, output_height, 3, weights);
    });
    add_phases(rows, "aos_separable", {{"horizontal", aos_horizontal_ms}, {"vertical", aos_vertical_ms},
               {"kernel", aos_horizontal_ms + aos_vertical_ms}, {"total", aos_horizontal_ms + aos_vertical_ms}},
               aos_separable, reference);
    valid &= difference(aos_separable, reference).count == 0;

    Planes separated(pixels);
    std::vector<uint32_t> planar_intermediate(static_cast<size_t>(input.height) * output_width);
    const std::array<const std::vector<Byte>*, 3> source_channels = {&source.r, &source.g, &source.b};
    const std::array<std::vector<Byte>*, 3> target_channels = {&separated.r, &separated.g, &separated.b};
    double planar_horizontal_ms = 0.0, planar_vertical_ms = 0.0;
    for (int channel = 0; channel < 3; ++channel) {
        planar_horizontal_ms += milliseconds([&] {
            gaussian_horizontal(*source_channels[channel], planar_intermediate, input.width, input.height, 1, weights);
        });
        planar_vertical_ms += milliseconds([&] {
            gaussian_vertical(planar_intermediate, *target_channels[channel], output_width, output_height, 1, weights);
        });
    }
    Picture separable_output{output_width, output_height, std::vector<Byte>(pixels * 3)};
    const double separable_pack_ms = milliseconds([&] { pack(separated, separable_output); });
    add_phases(rows, "soa_separable", {{"aos_to_soa", unpack_ms}, {"horizontal", planar_horizontal_ms},
               {"vertical", planar_vertical_ms}, {"kernel", planar_horizontal_ms + planar_vertical_ms},
               {"soa_to_aos", separable_pack_ms},
               {"total", unpack_ms + planar_horizontal_ms + planar_vertical_ms + separable_pack_ms}},
               separable_output, reference);
    valid &= difference(separable_output, reference).count == 0;

    {
        ImageState state{static_cast<Byte*>(std::malloc(input.bytes.size())), input.width, input.height, false};
        if (!state.data) return false;
        std::memcpy(state.data, input.bytes.data(), input.bytes.size());
        bool success = false;
        const double production_ms = milliseconds([&] {
            if (taps == 3) success = apply_3_by_3_convolution(state, GAUSSIAN_KERNEL_3X3, false, false);
            if (taps == 5) success = apply_5_by_5_convolution(state, GAUSSIAN_KERNEL_5X5, false, false);
            if (taps == 7) success = apply_7_by_7_convolution(state, GAUSSIAN_KERNEL_7X7, false, false);
            if (taps == 9) success = apply_9_by_9_convolution(state, GAUSSIAN_KERNEL_9X9, false, false);
            if (taps == 11) success = apply_11_by_11_convolution(state, GAUSSIAN_KERNEL_11X11, false, false);
        });
        if (!success) { std::free(state.data); return false; }
        Picture production{state.width, state.height,
                           std::vector<Byte>(state.data, state.data + static_cast<size_t>(state.width) * state.height * 3)};
        std::free(state.data);
        add_row(rows, "production_float", "total_including_allocation", production_ms, production, reference);
        // A referência float pode diferir por arredondamento. Seu tempo inclui
        // alocação/liberação internas e não é comparável ao kernel pré-alocado.
        // --check-production torna a tolerância um requisito na validação curta.
        if (check_production) valid &= difference(production, reference).maximum <= 1;
    }
    return valid;
}

bool run_geometry(const Picture& input, const std::string& operation, std::vector<Row>& rows) {
    const bool flip = operation == "Flip_Horizontal";
    const bool clockwise = operation == "Rotate_CW";
    const int output_width = flip ? input.width : input.height;
    const int output_height = flip ? input.height : input.width;

    Byte* baseline_data = static_cast<Byte*>(std::malloc(input.bytes.size()));
    if (!baseline_data) return false;
    std::memcpy(baseline_data, input.bytes.data(), input.bytes.size());
    ImageState baseline{baseline_data, input.width, input.height, false};
    const double reference_ms = milliseconds([&] {
        if (flip) flip_horizontal(baseline);
        else if (clockwise) rotate_90_degrees_clockwise(baseline);
        else rotate_90_degrees_counterclockwise(baseline);
    });
    Picture reference{baseline.width, baseline.height,
                      std::vector<Byte>(baseline.data, baseline.data + input.bytes.size())};
    std::free(baseline.data);
    add_row(rows, "original", "total", reference_ms, reference, reference);

    Picture candidate{output_width, output_height, {}};
    const double allocation_ms = milliseconds([&] { candidate.bytes.resize(input.bytes.size()); });
    const double kernel_ms = milliseconds([&] {
        if (flip) flip_out_of_place(input, candidate);
        else rotate_blocked(input, candidate, clockwise);
    });
    const std::string variant = flip ? "out_of_place" : "blocked_32";
    add_phases(rows, variant, {{"allocation", allocation_ms}, {"kernel", kernel_ms},
               {"total", allocation_ms + kernel_ms}}, candidate, reference);
    return difference(candidate, reference).count == 0;
}

bool run_control(const Picture& input, const std::string& operation, std::vector<Row>& rows) {
    if (operation == "Grayscale") {
        Picture result = input;
        const double elapsed = milliseconds([&] {
            ImageState image{result.bytes.data(), result.width, result.height, false};
            apply_gray_scale_inplace(image);
        });
        add_row(rows, "original", "total", elapsed, result, result);
        return true;
    }
    const int width = input.width * 2 - 1, height = input.height * 2 - 1;
    if (width <= 0 || height <= 0 || static_cast<int64_t>(width) * height * 3 > INT32_MAX) return false;
    Picture result{width, height, std::vector<Byte>(static_cast<size_t>(width) * height * 3)};
    ImageState image{const_cast<Byte*>(input.bytes.data()), input.width, input.height, false};
    bool success = false;
    const double elapsed = milliseconds([&] {
        success = zoom_in_image_to_buffer(image, result.bytes.data(), width, height);
    });
    if (success) add_row(rows, "original", "total", elapsed, result, result);
    return success;
}

bool write_csv(const Options& options, const Picture& input, const std::vector<Row>& rows) {
    if (options.warmup) return true;
    const bool fresh = !fs::exists(options.csv) || fs::file_size(options.csv) == 0;
    std::ofstream csv(options.csv, std::ios::app);
    if (!csv) return false;
    if (fresh) csv << "Image,Operation,Variant,Phase,Width,Height,Threads,Schedule,Build,Repeat,Elapsed_ms,Hash,Reference_Hash,Exact,Differing_Bytes,Max_Abs_Error,Compiler,Flags,Hostname\n";
    csv << std::fixed << std::setprecision(6);
    const std::string host = host_name(), schedule = schedule_name();
    for (const Row& row : rows) {
        csv << csv_text(options.image.filename().string()) << ',' << options.operation << ',' << row.variant << ',' << row.phase
            << ',' << input.width << ',' << input.height << ',' << omp_get_max_threads() << ',' << csv_text(schedule)
            << ',' << BENCHMARK_SIMD_BUILD << ',' << options.repeat << ',' << row.elapsed_ms << ',' << row.hash
            << ',' << row.reference_hash << ',' << (row.exact ? "yes" : "no") << ',' << row.difference.count
            << ',' << row.difference.maximum << ',' << csv_text(__VERSION__) << ',' << csv_text(BENCHMARK_BUILD_FLAGS)
            << ',' << csv_text(host) << '\n';
    }
    return true;
}

int main(int argc, char** argv) {
    Options options;
    if (!parse(argc, argv, options)) {
        std::cerr << "Uso: vectorization_benchmark --image ARQUIVO --operation NOME CSV [--repeat N] [--warmup] [--check-production] [--profile-quantize-lookup N]\n";
        return 2;
    }
    ImageState loaded{};
    if (!load_image(options.image.string().c_str(), loaded)) return 1;
    Picture input{loaded.width, loaded.height,
                  std::vector<Byte>(loaded.data, loaded.data + static_cast<size_t>(loaded.width) * loaded.height * 3)};
    std::free(loaded.data);

    std::vector<Row> rows;
    bool valid = false;
    if (options.operation == "Negative" || options.operation == "Adjust_Brightness" || options.operation == "Adjust_Contrast")
        valid = run_pointwise(input, options.operation, rows);
    else if (options.operation == "Quantize") {
        valid = options.profile_quantize_lookup > 0
            ? run_quantize_lookup_profile(input, options.profile_quantize_lookup, rows)
            : run_quantize(input, rows);
    }
    else if (options.operation == "Equalize_Histogram") valid = run_equalize(input, rows);
    else if (options.operation == "Flip_Horizontal" || options.operation == "Rotate_CW" || options.operation == "Rotate_CCW")
        valid = run_geometry(input, options.operation, rows);
    else if (options.operation == "Grayscale" || options.operation == "Zoom_In")
        valid = run_control(input, options.operation, rows);
    else if (options.operation.rfind("Gaussian_", 0) == 0) {
        const auto suffix = options.operation.substr(9);
        if (suffix == "3x3" || suffix == "5x5" || suffix == "7x7" || suffix == "9x9" || suffix == "11x11")
            valid = run_gaussian(input, std::stoi(suffix.substr(0, suffix.find('x'))), options.check_production, rows);
    }
    if (!valid) {
        std::cerr << "Validação falhou ou operação desconhecida: " << options.operation << " / " << options.image << '\n';
        return 1;
    }
    if (!write_csv(options, input, rows)) {
        std::cerr << "Não foi possível gravar " << options.csv << '\n';
        return 1;
    }
    return 0;
}
