#include "image_manipulation.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <system_error>
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

namespace fs = std::filesystem;

#define BENCHMARK_BRIGHTNESS_ADJUSTMENT 127
#define BENCHMARK_CONTRAST_FACTOR 1.5f
#define BENCHMARK_QUANTIZATION_LEVELS 16
#define BENCHMARK_ZOOM_OUT_WIDTH 2
#define BENCHMARK_ZOOM_OUT_HEIGHT 2
#define BENCHMARK_CONVOLUTION_CLAMP_OFFSET false
#define BENCHMARK_CONVOLUTION_SINGLE_CHANNEL false

using Transformation = bool (*)(ImageState&);

bool transform_grayscale(ImageState& image) { apply_gray_scale_inplace(image); return true; }
bool transform_flip_horizontal(ImageState& image) { flip_horizontal(image); return true; }
bool transform_adjust_brightness(ImageState& image) { adjust_brightness(image, BENCHMARK_BRIGHTNESS_ADJUSTMENT); return true; }
bool transform_flip_vertical(ImageState& image) { flip_vertical(image); return true; }
bool transform_quantize(ImageState& image) { quantize_gray(image, BENCHMARK_QUANTIZATION_LEVELS); return true; }
bool transform_adjust_contrast(ImageState& image) { adjust_contrast(image, BENCHMARK_CONTRAST_FACTOR); return true; }
bool transform_negative(ImageState& image) { apply_negative(image); return true; }
bool transform_equalize_histogram(ImageState& image) { unsigned int histogram[256]; equalize_histogram(image, histogram); return true; }
bool transform_zoom_in(ImageState& image) { zoom_in_image(image); return true; }

bool transform_zoom_out(ImageState& image) {
    Rectangle rectangle{0, 0, BENCHMARK_ZOOM_OUT_WIDTH, BENCHMARK_ZOOM_OUT_HEIGHT};
    zoom_out_image(image, rectangle);
    return true;
}

bool transform_rotate_clockwise(ImageState& image) { rotate_90_degrees_clockwise(image); return true; }
bool transform_rotate_counterclockwise(ImageState& image) { rotate_90_degrees_counterclockwise(image); return true; }

bool transform_gaussian_convolution_3x3(ImageState& image) {
    return apply_3_by_3_convolution(image, GAUSSIAN_KERNEL_3X3, BENCHMARK_CONVOLUTION_CLAMP_OFFSET, BENCHMARK_CONVOLUTION_SINGLE_CHANNEL);
}
bool transform_gaussian_convolution_5x5(ImageState& image) {
    return apply_5_by_5_convolution(image, GAUSSIAN_KERNEL_5X5, BENCHMARK_CONVOLUTION_CLAMP_OFFSET, BENCHMARK_CONVOLUTION_SINGLE_CHANNEL);
}
bool transform_gaussian_convolution_7x7(ImageState& image) {
    return apply_7_by_7_convolution(image, GAUSSIAN_KERNEL_7X7, BENCHMARK_CONVOLUTION_CLAMP_OFFSET, BENCHMARK_CONVOLUTION_SINGLE_CHANNEL);
}
bool transform_gaussian_convolution_9x9(ImageState& image) {
    return apply_9_by_9_convolution(image, GAUSSIAN_KERNEL_9X9, BENCHMARK_CONVOLUTION_CLAMP_OFFSET, BENCHMARK_CONVOLUTION_SINGLE_CHANNEL);
}
bool transform_gaussian_convolution_11x11(ImageState& image) {
    return apply_11_by_11_convolution(image, GAUSSIAN_KERNEL_11X11, BENCHMARK_CONVOLUTION_CLAMP_OFFSET, BENCHMARK_CONVOLUTION_SINGLE_CHANNEL);
}
bool transform_varying_window_gaussian_denoising(ImageState& image) { return apply_varying_window_gaussian_denoising(image); }

struct TransformationInfo {
    const char* name;
    Transformation apply;
    bool simd_eligible;
    bool adaptive;
};

static const TransformationInfo TRANSFORMATIONS[] = {
    {"Grayscale", transform_grayscale, true, false},
    {"Flip_Horizontal", transform_flip_horizontal, false, false},
    {"Adjust_Brightness", transform_adjust_brightness, true, false},
    {"Flip_Vertical", transform_flip_vertical, false, false},
    {"Quantize", transform_quantize, true, false},
    {"Adjust_Contrast", transform_adjust_contrast, true, false},
    {"Negative", transform_negative, true, false},
    {"Equalize_Histogram", transform_equalize_histogram, true, false},
    {"Zoom_In", transform_zoom_in, true, false},
    {"Zoom_Out", transform_zoom_out, false, false},
    {"Rotate_CW", transform_rotate_clockwise, false, false},
    {"Rotate_CCW", transform_rotate_counterclockwise, false, false},
    {"Gaussian_3x3", transform_gaussian_convolution_3x3, true, false},
    {"Gaussian_5x5", transform_gaussian_convolution_5x5, true, false},
    {"Gaussian_7x7", transform_gaussian_convolution_7x7, true, false},
    {"Gaussian_9x9", transform_gaussian_convolution_9x9, true, false},
    {"Gaussian_11x11", transform_gaussian_convolution_11x11, true, false},
    {"Adaptive_Median", transform_varying_window_gaussian_denoising, true, true},
};

struct Options {
    std::string mode;
    fs::path path;
    fs::path csv_path = "resultados_benchmark.csv";
    std::string operations = "all";
    std::string run_id = "manual";
    int repeat = 1;
    int profile_iterations = 1;
    bool warmup = false;
    bool hash_only = false;
    fs::path reference_hashes;
    fs::path write_hashes;
};

using HashMap = std::map<std::string, std::string>;

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
    const std::time_t time = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#if defined(_WIN32)
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif
    std::ostringstream output;
    output << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return output.str();
}

std::string hash_key(const std::string& image, const std::string& operation) {
    return image + "\x1f" + operation;
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

bool has_supported_extension(const fs::path& path) {
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    static const std::vector<std::string> supported_extensions = {
        ".jpg", ".jpeg", ".png", ".bmp", ".tga", ".gif", ".psd", ".hdr", ".pic", ".pnm", ".ppm", ".pgm"
    };
    return std::find(supported_extensions.begin(), supported_extensions.end(), extension) != supported_extensions.end();
}

std::vector<std::string> split(const std::string& value, char separator) {
    std::vector<std::string> items;
    std::stringstream input(value);
    std::string item;
    while (std::getline(input, item, separator)) {
        if (!item.empty()) items.push_back(item);
    }
    return items;
}

bool selected(const TransformationInfo& transformation, const std::string& requested) {
    if (requested == "all") return true;
    if (requested == "regular") return !transformation.adaptive;
    if (requested == "adaptive") return transformation.adaptive;
    const std::vector<std::string> names = split(requested, ',');
    return std::find(names.begin(), names.end(), transformation.name) != names.end();
}

void schedule_fields(std::string& schedule, std::string& chunk) {
    const std::string schedule_environment = environment("OMP_SCHEDULE", "default");
    const size_t comma = schedule_environment.find(',');
    schedule = schedule_environment.substr(0, comma);
    chunk = comma == std::string::npos ? "" : schedule_environment.substr(comma + 1);
}

bool load_reference_hashes(const fs::path& path, HashMap& hashes) {
    if (path.empty()) return true;
    std::ifstream input(path);
    if (!input.is_open()) {
        std::cerr << "Erro ao abrir hashes de referência: " << path << "\n";
        return false;
    }
    std::string line;
    std::getline(input, line);
    while (std::getline(input, line)) {
        const std::vector<std::string> fields = split(line, ',');
        if (fields.size() != 3) continue;
        hashes[hash_key(fields[0], fields[1])] = fields[2];
    }
    return true;
}

bool append_hash(std::ofstream* output, const std::string& image, const std::string& operation, const std::string& hash) {
    if (!output) return true;
    *output << image << ',' << operation << ',' << hash << "\n";
    return output->good();
}

// Zoom_In aloca e substitui a imagem de entrada na implementação normal. Para
// o VTune, repetimos apenas o kernel com a mesma entrada e um buffer de saída
// já alocado; assim a coleta não é dominada por malloc/free ou por cópias.
bool profile_zoom_in_kernel(const ImageState& source, int iterations) {
    const long long output_width = 2LL * source.width - 1;
    const long long output_height = 2LL * source.height - 1;
    if (iterations < 1 || output_width <= 0 || output_height <= 0 ||
        output_width > INT32_MAX || output_height > INT32_MAX ||
        output_width * output_height * 3LL > INT32_MAX) {
        return false;
    }
    const size_t output_size = static_cast<size_t>(output_width) * output_height * 3;
    std::vector<unsigned char> output(output_size);
    for (int iteration = 0; iteration < iterations; ++iteration) {
        if (!zoom_in_image_to_buffer(source, output.data(), static_cast<int>(output_width), static_cast<int>(output_height))) return false;
    }
    return true;
}

bool process_image(const fs::path& path, std::ofstream* csv, std::ofstream* hash_output, const HashMap& references, const Options& options) {
    ImageState image{};
    const std::string filename = path.string();
    if (!load_image(filename.c_str(), image)) {
        std::cerr << "Erro ao carregar a imagem: " << filename << "\n";
        return false;
    }

    const int original_width = image.width;
    const int original_height = image.height;
    const size_t original_size = static_cast<size_t>(original_width) * original_height * 3;
    unsigned char* original_data = static_cast<unsigned char*>(std::malloc(original_size));
    if (!original_data) {
        std::cerr << "Erro ao alocar backup da imagem: " << filename << "\n";
        std::free(image.data);
        return false;
    }
    std::memcpy(original_data, image.data, original_size);

    std::string schedule;
    std::string chunk;
    schedule_fields(schedule, chunk);
    const std::string image_name = path.filename().string();
    const std::string host = hostname();
    const int threads = omp_get_max_threads();
    bool success = true;

    for (const TransformationInfo& transformation : TRANSFORMATIONS) {
        if (!selected(transformation, options.operations)) continue;
        reset(image, original_data, original_width, original_height);
        if (options.profile_iterations > 1) {
            if (std::string(transformation.name) != "Zoom_In") {
                std::cerr << "--profile-iterations só é suportado para Zoom_In neste executável.\n";
                success = false;
                break;
            }
            if (!profile_zoom_in_kernel(image, options.profile_iterations)) {
                std::cerr << "Erro ao repetir o kernel Zoom_In para profiling.\n";
                success = false;
                break;
            }
            // A execução normal abaixo preserva a validação por hash.
            reset(image, original_data, original_width, original_height);
        }
        const auto start = std::chrono::steady_clock::now();
        if (!transformation.apply(image)) {
            std::cerr << "Erro na operação " << transformation.name << " para " << filename << "\n";
            success = false;
            break;
        }
        const auto end = std::chrono::steady_clock::now();
        const std::string result_hash = hash_image(image);
        const auto reference = references.find(hash_key(image_name, transformation.name));
        const std::string validation = references.empty() ? "not-requested" :
            (reference != references.end() && reference->second == result_hash ? "passed" : "failed");

        if (!append_hash(hash_output, image_name, transformation.name, result_hash)) {
            std::cerr << "Erro ao gravar hash de referência\n";
            success = false;
            break;
        }
        if (validation == "failed") {
            std::cerr << "Hash divergente: " << image_name << " / " << transformation.name << "\n";
            success = false;
            break;
        }
        if (options.warmup || options.hash_only) continue;

        const double elapsed_ms = std::chrono::duration<double, std::milli>(end - start).count();
        *csv << csv_escape(options.run_id) << ','
             << csv_escape(timestamp_utc()) << ','
             << csv_escape(image_name) << ','
             << original_width << ',' << original_height << ','
             << transformation.name << ',' << options.repeat << ',' << threads << ','
             << schedule << ',' << chunk << ','
             << BENCHMARK_SIMD_BUILD << ',' << (transformation.simd_eligible ? "yes" : "no") << ','
             << csv_escape(environment("OMP_PLACES", "unset")) << ','
             << csv_escape(environment("OMP_PROC_BIND", "unset")) << ','
             << csv_escape(host) << ','
             << csv_escape(__VERSION__) << ','
             << csv_escape(BENCHMARK_BUILD_FLAGS) << ','
             << std::fixed << std::setprecision(6) << elapsed_ms << ','
             << result_hash << ',' << validation << "\n";
        if (!csv->good()) {
            std::cerr << "Erro ao gravar CSV\n";
            success = false;
            break;
        }
    }

    std::free(image.data);
    std::free(original_data);
    return success;
}

int process_path(const Options& options, std::ofstream* csv, std::ofstream* hash_output, const HashMap& references) {
    if (options.mode == "--image") return process_image(options.path, csv, hash_output, references, options) ? 0 : 1;
    if (options.mode != "--folder") return 2;

    std::error_code error;
    if (!fs::is_directory(options.path, error)) {
        std::cerr << "Erro: pasta não encontrada: " << options.path << "\n";
        return 1;
    }
    std::vector<fs::path> images;
    for (fs::directory_iterator iterator(options.path, error), end; !error && iterator != end; iterator.increment(error)) {
        const fs::directory_entry& entry = *iterator;
        std::error_code entry_error;
        if (entry.is_regular_file(entry_error) && !entry_error && has_supported_extension(entry.path())) images.push_back(entry.path());
    }
    if (error) {
        std::cerr << "Erro ao percorrer pasta: " << error.message() << "\n";
        return 1;
    }
    std::sort(images.begin(), images.end());
    if (images.empty()) {
        std::cerr << "Erro: nenhuma imagem suportada em " << options.path << "\n";
        return 1;
    }
    for (const fs::path& image : images) {
        if (!process_image(image, csv, hash_output, references, options)) return 1;
    }
    return 0;
}

void print_usage(const char* executable) {
    std::cerr << "Uso: " << executable << " --image CAMINHO [CSV] [opções]\n"
              << "     " << executable << " --folder CAMINHO [CSV] [opções]\n\n"
              << "Opções:\n"
              << "  --operations all|regular|adaptive|NOME[,NOME...]\n"
              << "  --run-id ID --repeat N --profile-iterations N --warmup --hash-only\n"
              << "  --reference-hashes ARQUIVO --write-hashes ARQUIVO\n";
}

bool parse_options(int argc, char** argv, Options& options) {
    if (argc < 3) return false;
    options.mode = argv[1];
    options.path = argv[2];
    int index = 3;
    if (index < argc && std::string(argv[index]).rfind("--", 0) != 0) options.csv_path = argv[index++];
    while (index < argc) {
        const std::string argument = argv[index++];
        const auto value = [&]() -> const char* { return index < argc ? argv[index++] : nullptr; };
        if (argument == "--operations") {
            const char* text = value(); if (!text) return false; options.operations = text;
        } else if (argument == "--run-id") {
            const char* text = value(); if (!text) return false; options.run_id = text;
        } else if (argument == "--repeat") {
            const char* text = value(); if (!text) return false;
            try { options.repeat = std::stoi(text); } catch (...) { return false; }
            if (options.repeat < 0) return false;
        } else if (argument == "--profile-iterations") {
            const char* text = value(); if (!text) return false;
            try { options.profile_iterations = std::stoi(text); } catch (...) { return false; }
            if (options.profile_iterations < 1) return false;
        } else if (argument == "--reference-hashes") {
            const char* text = value(); if (!text) return false; options.reference_hashes = text;
        } else if (argument == "--write-hashes") {
            const char* text = value(); if (!text) return false; options.write_hashes = text;
        } else if (argument == "--warmup") {
            options.warmup = true;
        } else if (argument == "--hash-only") {
            options.hash_only = true;
        } else {
            return false;
        }
    }
    return options.mode == "--image" || options.mode == "--folder";
}

int main(int argc, char** argv) {
    Options options;
    if (!parse_options(argc, argv, options)) {
        print_usage(argv[0]);
        return 2;
    }

    HashMap references;
    if (!load_reference_hashes(options.reference_hashes, references)) return 1;

    std::ofstream hash_output;
    if (!options.write_hashes.empty()) {
        const bool exists = fs::exists(options.write_hashes);
        hash_output.open(options.write_hashes, std::ios::app);
        if (!hash_output.is_open()) {
            std::cerr << "Erro ao abrir arquivo de hashes: " << options.write_hashes << "\n";
            return 1;
        }
        if (!exists) hash_output << "Image,Operation,Result_Hash\n";
    }

    std::ofstream csv;
    if (!options.warmup && !options.hash_only) {
        const bool exists = fs::exists(options.csv_path);
        csv.open(options.csv_path, std::ios::app);
        if (!csv.is_open()) {
            std::cerr << "Erro ao abrir CSV: " << options.csv_path << "\n";
            return 1;
        }
        if (!exists) {
            csv << "Run_ID,Timestamp_UTC,Image,Width,Height,Operation,Repeat,Threads,Schedule,Chunk,Simd_Build,Simd_Eligible,OMP_Places,OMP_Proc_Bind,Hostname,Compiler,Build_Flags,Elapsed_ms,Result_Hash,Validation\n";
        }
    }

    return process_path(options, csv.is_open() ? &csv : nullptr, hash_output.is_open() ? &hash_output : nullptr, references);
}
