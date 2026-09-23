#include "image_manipulation.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <omp.h>

#if !defined(_WIN32)
#include <unistd.h>
#endif

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
#define OMP_SIMD _Pragma("omp simd")
#else
#define OMP_SIMD
#endif

namespace fs = std::filesystem;

struct Options {
    fs::path image;
    fs::path csv_path = "layout_raw.csv";
    std::string run_id = "manual";
    std::string operation = "Grayscale";
    int repeat = 1;
    int profile_iterations = 1;
    // Em coletas VTune, repete somente uma variante; as demais executam uma
    // vez para manter a validação, sem dominar a amostra do profiler.
    std::string profile_layout = "all";
    bool warmup = false;
};

// As três matrizes são alocadas uma vez e reutilizadas. Assim, a medição do
// kernel planar não inclui alocação, conversão nem reconstrução da imagem.
struct PlanarRgb {
    explicit PlanarRgb(size_t pixels) : red(pixels), green(pixels), blue(pixels) {}

    std::vector<unsigned char> red;
    std::vector<unsigned char> green;
    std::vector<unsigned char> blue;
};

// A linha geradora dos kernels gaussianos binomiais do projeto. O produto
// externo desta sequência consigo mesma produz exatamente o kernel 11x11.
constexpr std::array<uint32_t, 11> BINOMIAL_11 = {1, 10, 45, 120, 210, 252, 210, 120, 45, 10, 1};
constexpr uint64_t BINOMIAL_11_NORMALIZER = 1024ULL * 1024ULL;

std::string environment(const char* name, const char* fallback = "") {
    const char* value = std::getenv(name);
    return value ? value : fallback;
}

std::string csv_escape(const std::string& value) {
    if (value.find_first_of(",\"\n") == std::string::npos) return value;
    std::string escaped = "\"";
    for (char character : value) escaped += character == '\"' ? "\"\"" : std::string(1, character);
    return escaped + "\"";
}

std::string hostname() {
#if defined(_WIN32)
    const char* name = std::getenv("COMPUTERNAME");
    return name ? name : "unknown";
#else
    char buffer[256]{};
    return gethostname(buffer, sizeof(buffer)) == 0 ? std::string(buffer) : "unknown";
#endif
}

std::string timestamp_utc() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t current_time = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#if defined(_WIN32)
    gmtime_s(&utc, &current_time);
#else
    gmtime_r(&current_time, &utc);
#endif
    std::ostringstream output;
    output << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return output.str();
}

std::string hash_image(const ImageState& image) {
    uint64_t value = 1469598103934665603ULL;
    const auto update = [&value](unsigned char byte) {
        value ^= byte;
        value *= 1099511628211ULL;
    };
    const auto update_number = [&update](uint64_t number) {
        for (int index = 0; index < 8; ++index) update(static_cast<unsigned char>(number >> (index * 8)));
    };

    update_number(static_cast<uint64_t>(image.width));
    update_number(static_cast<uint64_t>(image.height));
    update(image.isGrayScale ? 1 : 0);
    const size_t size = static_cast<size_t>(image.width) * image.height * 3;
    for (size_t index = 0; index < size; ++index) update(image.data[index]);

    std::ostringstream output;
    output << std::hex << std::setw(16) << std::setfill('0') << value;
    return output.str();
}

struct DifferenceStats {
    unsigned int max_abs_error = 0;
    size_t differing_bytes = 0;
};

DifferenceStats compare_images(const ImageState& candidate, const ImageState& reference) {
    DifferenceStats stats;
    if (candidate.width != reference.width || candidate.height != reference.height || candidate.isGrayScale != reference.isGrayScale) {
        stats.max_abs_error = 255;
        stats.differing_bytes = 1;
        return stats;
    }
    const size_t bytes = static_cast<size_t>(candidate.width) * candidate.height * 3;
    for (size_t index = 0; index < bytes; ++index) {
        const unsigned int error = candidate.data[index] > reference.data[index]
            ? candidate.data[index] - reference.data[index]
            : reference.data[index] - candidate.data[index];
        if (error) ++stats.differing_bytes;
        stats.max_abs_error = std::max(stats.max_abs_error, error);
    }
    return stats;
}

void schedule_fields(std::string& schedule, std::string& chunk) {
    const std::string schedule_environment = environment("OMP_SCHEDULE", "default");
    const size_t comma = schedule_environment.find(',');
    schedule = schedule_environment.substr(0, comma);
    chunk = comma == std::string::npos ? "" : schedule_environment.substr(comma + 1);
}

template <typename Function>
double measure_ms(Function&& function) {
    const auto start = std::chrono::steady_clock::now();
    function();
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::milli>(end - start).count();
}

void aos_to_soa(const unsigned char* source, PlanarRgb& planes, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        const size_t row = static_cast<size_t>(y) * width;
        OMP_SIMD
        for (int x = 0; x < width; ++x) {
            const size_t pixel = row + static_cast<size_t>(x);
            const size_t interleaved = pixel * 3;
            planes.red[pixel] = source[interleaved];
            planes.green[pixel] = source[interleaved + 1];
            planes.blue[pixel] = source[interleaved + 2];
        }
    }
}

void grayscale_planar(PlanarRgb& planes, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        const size_t row = static_cast<size_t>(y) * width;
        OMP_SIMD
        for (int x = 0; x < width; ++x) {
            const size_t pixel = row + static_cast<size_t>(x);
            const unsigned char gray = static_cast<unsigned char>(
                0.299 * planes.red[pixel] + 0.587 * planes.green[pixel] + 0.114 * planes.blue[pixel]);
            planes.red[pixel] = gray;
            planes.green[pixel] = gray;
            planes.blue[pixel] = gray;
        }
    }
}

unsigned char clamp_to_byte(float value) {
    return static_cast<unsigned char>(std::max(0, std::min(255, static_cast<int>(std::round(value)))));
}

// O filtro da aplicação reduz a imagem em cinco pixels de cada borda. Os
// buffers de destino são pré-alocados para que esta medição seja apenas do
// kernel, tanto para AoS quanto para SoA.
void gaussian_11_aos(const unsigned char* source, unsigned char* destination, int width, int height) {
    const int output_width = width - 10;
    #pragma omp parallel for schedule(runtime)
    for (int y = 5; y < height - 5; ++y) {
        OMP_SIMD
        for (int x = 5; x < width - 5; ++x) {
            float sum_red = 0.0f;
            float sum_green = 0.0f;
            float sum_blue = 0.0f;
            for (int k = -5; k <= 5; ++k) {
                for (int l = -5; l <= 5; ++l) {
                    const size_t source_pixel = static_cast<size_t>(y - k) * width + (x - l);
                    const size_t source_index = source_pixel * 3;
                    const float weight = GAUSSIAN_KERNEL_11X11[5 + k][5 + l];
                    sum_red += weight * source[source_index];
                    sum_green += weight * source[source_index + 1];
                    sum_blue += weight * source[source_index + 2];
                }
            }
            const size_t output_index = (static_cast<size_t>(y - 5) * output_width + (x - 5)) * 3;
            destination[output_index] = clamp_to_byte(sum_red);
            destination[output_index + 1] = clamp_to_byte(sum_green);
            destination[output_index + 2] = clamp_to_byte(sum_blue);
        }
    }
}

void gaussian_11_planar(const PlanarRgb& source, PlanarRgb& destination, int width, int height) {
    const int output_width = width - 10;
    #pragma omp parallel for schedule(runtime)
    for (int y = 5; y < height - 5; ++y) {
        OMP_SIMD
        for (int x = 5; x < width - 5; ++x) {
            float sum_red = 0.0f;
            float sum_green = 0.0f;
            float sum_blue = 0.0f;
            for (int k = -5; k <= 5; ++k) {
                for (int l = -5; l <= 5; ++l) {
                    const size_t source_pixel = static_cast<size_t>(y - k) * width + (x - l);
                    const float weight = GAUSSIAN_KERNEL_11X11[5 + k][5 + l];
                    sum_red += weight * source.red[source_pixel];
                    sum_green += weight * source.green[source_pixel];
                    sum_blue += weight * source.blue[source_pixel];
                }
            }
            const size_t output_pixel = static_cast<size_t>(y - 5) * output_width + (x - 5);
            destination.red[output_pixel] = clamp_to_byte(sum_red);
            destination.green[output_pixel] = clamp_to_byte(sum_green);
            destination.blue[output_pixel] = clamp_to_byte(sum_blue);
        }
    }
}

// As duas passadas mantêm o loop vetorizável em x. A primeira grava uma soma
// horizontal sem normalização; a segunda aplica a soma vertical e normaliza.
// O mesmo padrão funciona para kernels gaussianos binomiais 3, 5, 7 e 9 ao
// trocar coeficientes, normalizador e tamanho da janela.
void gaussian_11_horizontal_pass(
    const std::vector<unsigned char>& source,
    std::vector<uint32_t>& intermediate,
    int width,
    int height) {
    const int output_width = width - 10;
    const unsigned char* input = source.data();
    uint32_t* output = intermediate.data();
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        const size_t input_row = static_cast<size_t>(y) * width;
        const size_t output_row = static_cast<size_t>(y) * output_width;
        OMP_SIMD
        for (int output_x = 0; output_x < output_width; ++output_x) {
            uint32_t sum = 0;
            for (int tap = 0; tap < 11; ++tap) {
                sum += BINOMIAL_11[tap] * input[input_row + output_x + tap];
            }
            output[output_row + output_x] = sum;
        }
    }
}

void gaussian_11_vertical_pass(
    const std::vector<uint32_t>& intermediate,
    std::vector<unsigned char>& destination,
    int output_width,
    int output_height) {
    const uint32_t* input = intermediate.data();
    unsigned char* output = destination.data();
    #pragma omp parallel for schedule(runtime)
    for (int output_y = 0; output_y < output_height; ++output_y) {
        const size_t output_row = static_cast<size_t>(output_y) * output_width;
        OMP_SIMD
        for (int x = 0; x < output_width; ++x) {
            uint64_t sum = 0;
            for (int tap = 0; tap < 11; ++tap) {
                sum += BINOMIAL_11[tap] * input[static_cast<size_t>(output_y + tap) * output_width + x];
            }
            output[output_row + x] = static_cast<unsigned char>((sum + BINOMIAL_11_NORMALIZER / 2) / BINOMIAL_11_NORMALIZER);
        }
    }
}

struct SeparableTimes {
    double horizontal_ms = 0.0;
    double vertical_ms = 0.0;
};

SeparableTimes gaussian_11_separable_planar(
    const PlanarRgb& source,
    PlanarRgb& destination,
    std::vector<uint32_t>& intermediate,
    int width,
    int height) {
    const int output_width = width - 10;
    const int output_height = height - 10;
    SeparableTimes times;
    const std::array<const std::vector<unsigned char>*, 3> inputs = {&source.red, &source.green, &source.blue};
    const std::array<std::vector<unsigned char>*, 3> outputs = {&destination.red, &destination.green, &destination.blue};
    for (size_t channel = 0; channel < inputs.size(); ++channel) {
        times.horizontal_ms += measure_ms([&] { gaussian_11_horizontal_pass(*inputs[channel], intermediate, width, height); });
        times.vertical_ms += measure_ms([&] { gaussian_11_vertical_pass(intermediate, *outputs[channel], output_width, output_height); });
    }
    return times;
}

void soa_to_aos(const PlanarRgb& planes, unsigned char* destination, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        const size_t row = static_cast<size_t>(y) * width;
        OMP_SIMD
        for (int x = 0; x < width; ++x) {
            const size_t pixel = row + static_cast<size_t>(x);
            const size_t interleaved = pixel * 3;
            destination[interleaved] = planes.red[pixel];
            destination[interleaved + 1] = planes.green[pixel];
            destination[interleaved + 2] = planes.blue[pixel];
        }
    }
}

void write_header(std::ofstream& csv) {
    csv << "Run_ID,Timestamp_UTC,Image,Operation,Width,Height,Layout,Phase,Repeat,Threads,Schedule,Chunk,Simd_Build,"
           "OMP_Places,OMP_Proc_Bind,Hostname,Compiler,Build_Flags,Elapsed_ms,Result_Hash,Validation,Reference_Max_Abs_Error,Reference_Differing_Bytes\n";
}

void write_measurement(
    std::ofstream& csv,
    const Options& options,
    const std::string& image,
    int width,
    int height,
    const char* layout,
    const char* phase,
    const std::string& schedule,
    const std::string& chunk,
    const std::string& host,
    double elapsed_ms,
    const std::string& result_hash,
    const char* validation,
    const DifferenceStats& difference) {
    const std::vector<std::string> fields = {
        options.run_id, timestamp_utc(), image, options.operation, std::to_string(width), std::to_string(height), layout, phase,
        std::to_string(options.repeat), std::to_string(omp_get_max_threads()), schedule, chunk,
        BENCHMARK_SIMD_BUILD, environment("OMP_PLACES"), environment("OMP_PROC_BIND"), host,
        environment("CXX", "g++"), BENCHMARK_BUILD_FLAGS, std::to_string(elapsed_ms), result_hash, validation,
        std::to_string(difference.max_abs_error), std::to_string(difference.differing_bytes),
    };
    for (size_t index = 0; index < fields.size(); ++index) {
        if (index) csv << ',';
        csv << csv_escape(fields[index]);
    }
    csv << '\n';
}

bool parse_arguments(int argc, char* argv[], Options& options) {
    if (argc < 2) return false;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--image" && index + 1 < argc) {
            options.image = argv[++index];
        } else if (argument == "--run-id" && index + 1 < argc) {
            options.run_id = argv[++index];
        } else if (argument == "--operation" && index + 1 < argc) {
            options.operation = argv[++index];
        } else if (argument == "--repeat" && index + 1 < argc) {
            options.repeat = std::stoi(argv[++index]);
        } else if (argument == "--profile-iterations" && index + 1 < argc) {
            options.profile_iterations = std::stoi(argv[++index]);
        } else if (argument == "--profile-layout" && index + 1 < argc) {
            options.profile_layout = argv[++index];
        } else if (argument == "--warmup") {
            options.warmup = true;
        } else if (!argument.empty() && argument[0] != '-' && options.csv_path == "layout_raw.csv") {
            options.csv_path = argument;
        } else {
            return false;
        }
    }
    return !options.image.empty() && options.repeat >= 0 && options.profile_iterations >= 1 &&
           (options.operation == "Grayscale" || options.operation == "Gaussian_11x11") &&
           (options.profile_layout == "all" || options.profile_layout == "aos" ||
            options.profile_layout == "soa-naive" || options.profile_layout == "soa-separable");
}

void usage() {
    std::cerr << "Uso: layout_benchmark --image ARQUIVO CSV [--operation Grayscale|Gaussian_11x11] [--run-id ID] [--repeat N] [--profile-iterations N] [--profile-layout all|aos|soa-naive|soa-separable] [--warmup]\n";
}

int main(int argc, char* argv[]) {
    Options options;
    if (!parse_arguments(argc, argv, options)) {
        usage();
        return 2;
    }

    ImageState loaded{};
    const std::string filename = options.image.string();
    if (!load_image(filename.c_str(), loaded)) {
        std::cerr << "Erro ao carregar a imagem: " << filename << "\n";
        return 1;
    }

    const size_t input_bytes = static_cast<size_t>(loaded.width) * loaded.height * 3;
    const size_t input_pixels = static_cast<size_t>(loaded.width) * loaded.height;
    std::vector<unsigned char> original(loaded.data, loaded.data + input_bytes);
    std::free(loaded.data);

    std::string schedule;
    std::string chunk;
    schedule_fields(schedule, chunk);

    int output_width = loaded.width;
    int output_height = loaded.height;
    double direct_ms = 0.0;
    double unpack_ms = 0.0;
    double planar_kernel_ms = 0.0;
    double repack_ms = 0.0;
    SeparableTimes separable_times{};
    double separable_repack_ms = 0.0;
    std::string direct_hash;
    std::string planar_hash;
    std::string separable_hash;
    std::string reference_hash;
    DifferenceStats naive_difference{};
    DifferenceStats separable_difference{};
    bool valid = false;

    if (options.operation == "Grayscale") {
        ImageState direct{static_cast<unsigned char*>(std::malloc(input_bytes)), loaded.width, loaded.height, false};
        ImageState planar_output{static_cast<unsigned char*>(std::malloc(input_bytes)), loaded.width, loaded.height, false};
        if (!direct.data || !planar_output.data) {
            std::cerr << "Erro ao alocar buffers de trabalho.\n";
            std::free(direct.data);
            std::free(planar_output.data);
            return 1;
        }
        PlanarRgb planes(input_pixels);

        // A cópia restaura a entrada antes do kernel AoS, mas não é cronometrada;
        // é a mesma convenção usada pelo benchmark principal para resetar imagens.
        std::memcpy(direct.data, original.data(), input_bytes);
        const int direct_iterations = (options.profile_layout == "all" || options.profile_layout == "aos") ? options.profile_iterations : 1;
        direct_ms = measure_ms([&] {
            for (int iteration = 0; iteration < direct_iterations; ++iteration) {
                // Depois da primeira passagem a imagem já é cinza, mas o
                // kernel continua idêntico se a guarda for restaurada.
                direct.isGrayScale = false;
                apply_gray_scale_inplace(direct);
            }
        });
        direct_hash = hash_image(direct);

        unpack_ms = measure_ms([&] { aos_to_soa(original.data(), planes, loaded.width, loaded.height); });
        const int planar_iterations = (options.profile_layout == "all" || options.profile_layout == "soa-naive") ? options.profile_iterations : 1;
        planar_kernel_ms = measure_ms([&] {
            for (int iteration = 0; iteration < planar_iterations; ++iteration) {
                grayscale_planar(planes, loaded.width, loaded.height);
            }
        });
        repack_ms = measure_ms([&] { soa_to_aos(planes, planar_output.data, loaded.width, loaded.height); });
        planar_output.isGrayScale = true;
        planar_hash = hash_image(planar_output);
        reference_hash = direct_hash;
        valid = direct_hash == planar_hash;
        std::free(direct.data);
        std::free(planar_output.data);
    } else {
        if (loaded.width < 11 || loaded.height < 11) {
            std::cerr << "Imagem muito pequena para Gaussian_11x11.\n";
            return 1;
        }
        output_width = loaded.width - 10;
        output_height = loaded.height - 10;
        const size_t output_pixels = static_cast<size_t>(output_width) * output_height;
        const size_t output_bytes = output_pixels * 3;
        ImageState direct{static_cast<unsigned char*>(std::malloc(output_bytes)), output_width, output_height, false};
        ImageState planar_output{static_cast<unsigned char*>(std::malloc(output_bytes)), output_width, output_height, false};
        ImageState reference{static_cast<unsigned char*>(std::malloc(input_bytes)), loaded.width, loaded.height, false};
        if (!direct.data || !planar_output.data || !reference.data) {
            std::cerr << "Erro ao alocar buffers de trabalho.\n";
            std::free(direct.data);
            std::free(planar_output.data);
            std::free(reference.data);
            return 1;
        }
        PlanarRgb source_planes(input_pixels);
        PlanarRgb filtered_planes(output_pixels);
        std::vector<uint32_t> intermediate(static_cast<size_t>(output_width) * loaded.height);

        // Referência de produção fora da janela de tempo.
        std::memcpy(reference.data, original.data(), input_bytes);
        if (!apply_11_by_11_convolution(reference, GAUSSIAN_KERNEL_11X11, false, false)) {
            std::cerr << "Erro ao calcular a referência Gaussian_11x11.\n";
            std::free(direct.data);
            std::free(planar_output.data);
            std::free(reference.data);
            return 1;
        }
        reference_hash = hash_image(reference);

        const int direct_iterations = (options.profile_layout == "all" || options.profile_layout == "aos") ? options.profile_iterations : 1;
        direct_ms = measure_ms([&] {
            for (int iteration = 0; iteration < direct_iterations; ++iteration) {
                gaussian_11_aos(original.data(), direct.data, loaded.width, loaded.height);
            }
        });
        direct_hash = hash_image(direct);

        unpack_ms = measure_ms([&] { aos_to_soa(original.data(), source_planes, loaded.width, loaded.height); });
        const int planar_iterations = (options.profile_layout == "all" || options.profile_layout == "soa-naive") ? options.profile_iterations : 1;
        planar_kernel_ms = measure_ms([&] {
            for (int iteration = 0; iteration < planar_iterations; ++iteration) {
                gaussian_11_planar(source_planes, filtered_planes, loaded.width, loaded.height);
            }
        });
        repack_ms = measure_ms([&] { soa_to_aos(filtered_planes, planar_output.data, output_width, output_height); });
        planar_hash = hash_image(planar_output);
        naive_difference = compare_images(planar_output, reference);

        // Reutiliza a mesma conversão de entrada e os mesmos buffers já
        // alocados. O método separável sobrescreve filtered_planes depois que
        // o hash do método ingênuo foi guardado.
        const int separable_iterations = (options.profile_layout == "all" || options.profile_layout == "soa-separable") ? options.profile_iterations : 1;
        for (int iteration = 0; iteration < separable_iterations; ++iteration) {
            const SeparableTimes times = gaussian_11_separable_planar(source_planes, filtered_planes, intermediate, loaded.width, loaded.height);
            separable_times.horizontal_ms += times.horizontal_ms;
            separable_times.vertical_ms += times.vertical_ms;
        }
        separable_repack_ms = measure_ms([&] { soa_to_aos(filtered_planes, planar_output.data, output_width, output_height); });
        separable_hash = hash_image(planar_output);
        separable_difference = compare_images(planar_output, reference);
        // O resultado inteiro separável pode diferir em 1 nível da soma float
        // em ordem 2D, mas não pode ter erro maior. A métrica fica no CSV.
        valid = direct_hash == reference_hash && planar_hash == reference_hash && separable_difference.max_abs_error <= 1;
        std::free(direct.data);
        std::free(planar_output.data);
        std::free(reference.data);
    }

    const char* validation = valid ? "passed" : "failed";

    if (!options.warmup) {
        const bool new_file = !fs::exists(options.csv_path) || fs::file_size(options.csv_path) == 0;
        std::ofstream csv(options.csv_path, std::ios::app);
        if (!csv.is_open()) {
            std::cerr << "Erro ao abrir CSV: " << options.csv_path << "\n";
            return 1;
        }
        if (new_file) write_header(csv);
        const std::string image_name = options.image.filename().string();
        const std::string host = hostname();
        if (options.operation == "Grayscale") {
            write_measurement(csv, options, image_name, output_width, output_height, "AoS", "Kernel", schedule, chunk, host, direct_ms, direct_hash, validation, {});
            write_measurement(csv, options, image_name, output_width, output_height, "SoA", "AoS_to_SoA", schedule, chunk, host, unpack_ms, planar_hash, validation, {});
            write_measurement(csv, options, image_name, output_width, output_height, "SoA", "Kernel", schedule, chunk, host, planar_kernel_ms, planar_hash, validation, {});
            write_measurement(csv, options, image_name, output_width, output_height, "SoA", "SoA_to_AoS", schedule, chunk, host, repack_ms, planar_hash, validation, {});
            write_measurement(csv, options, image_name, output_width, output_height, "SoA", "End_to_End", schedule, chunk, host, unpack_ms + planar_kernel_ms + repack_ms, planar_hash, validation, {});
        } else {
            write_measurement(csv, options, image_name, output_width, output_height, "AoS_Naive", "Kernel", schedule, chunk, host, direct_ms, direct_hash, validation, {});
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Naive", "AoS_to_SoA", schedule, chunk, host, unpack_ms, planar_hash, validation, naive_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Naive", "Kernel", schedule, chunk, host, planar_kernel_ms, planar_hash, validation, naive_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Naive", "SoA_to_AoS", schedule, chunk, host, repack_ms, planar_hash, validation, naive_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Naive", "End_to_End", schedule, chunk, host, unpack_ms + planar_kernel_ms + repack_ms, planar_hash, validation, naive_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Separable", "AoS_to_SoA", schedule, chunk, host, unpack_ms, separable_hash, validation, separable_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Separable", "Horizontal_Passes", schedule, chunk, host, separable_times.horizontal_ms, separable_hash, validation, separable_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Separable", "Vertical_Passes", schedule, chunk, host, separable_times.vertical_ms, separable_hash, validation, separable_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Separable", "Kernel", schedule, chunk, host, separable_times.horizontal_ms + separable_times.vertical_ms, separable_hash, validation, separable_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Separable", "SoA_to_AoS", schedule, chunk, host, separable_repack_ms, separable_hash, validation, separable_difference);
            write_measurement(csv, options, image_name, output_width, output_height, "SoA_Separable", "End_to_End", schedule, chunk, host, unpack_ms + separable_times.horizontal_ms + separable_times.vertical_ms + separable_repack_ms, separable_hash, validation, separable_difference);
        }
    }

    if (!valid) {
        std::cerr << "Validação falhou: AoS=" << direct_hash << ", SoA ingênuo=" << planar_hash
                  << ", SoA separável=" << separable_hash << ", referência=" << reference_hash << "\n";
        return 1;
    }
    return 0;
}
