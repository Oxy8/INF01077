#include "image_manipulation.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <string>
#include <vector>

#include <omp.h>

#if defined(__linux__)
#include <sys/mman.h>
#include <unistd.h>
#endif

#ifndef BENCHMARK_SIMD_BUILD
#define BENCHMARK_SIMD_BUILD "unknown"
#endif

namespace fs = std::filesystem;

struct Options {
    std::string mode;
    fs::path image;
    fs::path output;
    fs::path thread_output;
    std::string experiment;
    std::string touch_mode = "fresh";
    int repeats = 1;
    int seed = 577262;
};

struct OutputBuffer {
    explicit OutputBuffer(size_t requested_bytes) {
#if defined(__linux__)
        const long page_size = sysconf(_SC_PAGESIZE);
        const size_t page = page_size > 0 ? static_cast<size_t>(page_size) : 4096u;
        bytes = ((requested_bytes + page - 1u) / page) * page;
        if (posix_memalign(reinterpret_cast<void**>(&data), page, bytes) != 0) data = nullptr;
#else
        bytes = requested_bytes;
        data = static_cast<unsigned char*>(std::malloc(bytes));
#endif
    }

    ~OutputBuffer() { std::free(data); }
    OutputBuffer(const OutputBuffer&) = delete;
    OutputBuffer& operator=(const OutputBuffer&) = delete;

    bool discard_pages() {
#if defined(__linux__)
        return data && madvise(data, bytes, MADV_DONTNEED) == 0;
#else
        return false;
#endif
    }

    unsigned char* data = nullptr;
    size_t bytes = 0;
};

std::string csv_escape(const std::string& text) {
    if (text.find_first_of(",\"") == std::string::npos) return text;
    std::string escaped = "\"";
    for (const char character : text) {
        if (character == '\"') escaped += "\"\"";
        else escaped += character;
    }
    return escaped + "\"";
}

std::pair<std::string, std::string> schedule_fields(const std::string& schedule) {
    const size_t comma = schedule.find(',');
    return comma == std::string::npos ? std::make_pair(schedule, "") :
        std::make_pair(schedule.substr(0, comma), schedule.substr(comma + 1));
}

bool parse_options(int argc, char** argv, Options& options) {
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        const auto value = [&]() -> const char* {
            return ++index < argc ? argv[index] : nullptr;
        };
        if (argument == "--mode") {
            const char* text = value(); if (!text) return false; options.mode = text;
        } else if (argument == "--image") {
            const char* text = value(); if (!text) return false; options.image = text;
        } else if (argument == "--output") {
            const char* text = value(); if (!text) return false; options.output = text;
        } else if (argument == "--thread-output") {
            const char* text = value(); if (!text) return false; options.thread_output = text;
        } else if (argument == "--experiment") {
            const char* text = value(); if (!text) return false; options.experiment = text;
        } else if (argument == "--touch") {
            const char* text = value(); if (!text) return false; options.touch_mode = text;
        } else if (argument == "--repeats") {
            const char* text = value(); if (!text) return false; options.repeats = std::atoi(text);
        } else if (argument == "--seed") {
            const char* text = value(); if (!text) return false; options.seed = std::atoi(text);
        } else {
            return false;
        }
    }
    return !options.mode.empty() && !options.image.empty() && !options.output.empty() &&
        options.repeats > 0 && (options.mode == "zoom" || options.mode == "flip") &&
        (options.touch_mode == "fresh" || options.touch_mode == "pretouch-static");
}

bool load_original(const fs::path& path, ImageState& loaded, std::vector<unsigned char>& original) {
    if (!load_image(path.string().c_str(), loaded)) return false;
    const size_t bytes = static_cast<size_t>(loaded.width) * loaded.height * 3u;
    original.assign(loaded.data, loaded.data + bytes);
    std::free(loaded.data);
    loaded.data = original.data();
    return true;
}

void pre_touch_static(unsigned char* data, size_t bytes) {
    constexpr size_t page = 4096;
    #pragma omp parallel for schedule(static)
    for (long long offset = 0; offset < static_cast<long long>(bytes); offset += static_cast<long long>(page)) {
        data[static_cast<size_t>(offset)] = 0;
    }
}

void write_zoom_header(std::ofstream& output) {
    output << "Experiment,Build,Image,Width,Height,Threads,Schedule,Chunk,Touch_Mode,Repeat,Copy_ms,Horizontal_ms,Vertical_ms,Total_ms\n";
}

int run_zoom(const Options& options, const ImageState& source) {
    const int output_width = source.width * 2 - 1;
    const int output_height = source.height * 2 - 1;
    const size_t output_bytes = static_cast<size_t>(output_width) * output_height * 3u;
    OutputBuffer destination(output_bytes);
    if (!destination.data) {
        std::cerr << "Falha ao alocar buffer de saída do Zoom In.\n";
        return 1;
    }

    const std::string schedule = std::getenv("OMP_SCHEDULE") ? std::getenv("OMP_SCHEDULE") : "runtime-default";
    const auto [schedule_name, chunk] = schedule_fields(schedule);
    const bool new_file = !fs::exists(options.output) || fs::file_size(options.output) == 0;
    std::ofstream output(options.output, std::ios::app);
    if (!output) return 1;
    if (new_file) write_zoom_header(output);
    output << std::fixed << std::setprecision(6);

    for (int repeat = 0; repeat < options.repeats; ++repeat) {
        const bool discarded = destination.discard_pages();
        if (options.touch_mode == "pretouch-static") pre_touch_static(destination.data, destination.bytes);
        ZoomInPhaseTimes times{};
        if (!zoom_in_image_to_buffer_profiled(source, destination.data, output_width, output_height, times)) return 1;
        output << csv_escape(options.experiment) << ',' << BENCHMARK_SIMD_BUILD << ','
               << csv_escape(options.image.filename().string()) << ',' << source.width << ',' << source.height << ','
               << omp_get_max_threads() << ',' << csv_escape(schedule_name) << ',' << csv_escape(chunk) << ','
               << options.touch_mode << ',' << repeat << ',' << times.copy_ms << ',' << times.horizontal_ms << ','
               << times.vertical_ms << ',' << times.total_ms << '\n';
        if (!discarded && repeat == 0) {
            std::cerr << "Aviso: MADV_DONTNEED indisponível; a condição fresh reutiliza páginas do alocador.\n";
        }
    }
    return output.good() ? 0 : 1;
}

struct FlipSchedule {
    const char* label;
    omp_sched_t kind;
    int chunk;
};

void write_flip_header(std::ofstream& output) {
    output << "Experiment,Build,Image,Width,Height,Threads,Round,Order,Schedule,Chunk,Elapsed_ms\n";
}

void write_flip_thread_header(std::ofstream& output) {
    output << "Experiment,Build,Image,Threads,Round,Order,Schedule,Chunk,Thread,Rows,Work_ms\n";
}

int run_flip(const Options& options, const ImageState& source, const std::vector<unsigned char>& original) {
    if (options.thread_output.empty()) {
        std::cerr << "--thread-output é obrigatório no modo flip.\n";
        return 2;
    }
    const bool new_raw = !fs::exists(options.output) || fs::file_size(options.output) == 0;
    const bool new_threads = !fs::exists(options.thread_output) || fs::file_size(options.thread_output) == 0;
    std::ofstream raw(options.output, std::ios::app);
    std::ofstream thread_output(options.thread_output, std::ios::app);
    if (!raw || !thread_output) return 1;
    if (new_raw) write_flip_header(raw);
    if (new_threads) write_flip_thread_header(thread_output);
    raw << std::fixed << std::setprecision(6);
    thread_output << std::fixed << std::setprecision(6);

    const std::vector<FlipSchedule> schedules = {
        {"static", omp_sched_static, 0},
        {"static,1", omp_sched_static, 1},
        {"static,16", omp_sched_static, 16},
        {"dynamic,1", omp_sched_dynamic, 1},
        {"dynamic,16", omp_sched_dynamic, 16},
    };
    std::mt19937 random(static_cast<unsigned int>(options.seed));
    std::vector<int> order(schedules.size());
    for (size_t index = 0; index < order.size(); ++index) order[index] = static_cast<int>(index);
    std::vector<unsigned char> working(original.size());

    for (int round = 0; round < options.repeats; ++round) {
        std::shuffle(order.begin(), order.end(), random);
        for (size_t position = 0; position < order.size(); ++position) {
            const FlipSchedule& schedule = schedules[static_cast<size_t>(order[position])];
            std::memcpy(working.data(), original.data(), original.size());
            ImageState image{working.data(), source.width, source.height, false};
            omp_set_schedule(schedule.kind, schedule.chunk);
            std::vector<ThreadWorkInfo> thread_info;
            const double elapsed = flip_horizontal_profiled(image, thread_info);
            const auto [name, chunk] = schedule_fields(schedule.label);
            raw << csv_escape(options.experiment) << ',' << BENCHMARK_SIMD_BUILD << ','
                << csv_escape(options.image.filename().string()) << ',' << source.width << ',' << source.height << ','
                << omp_get_max_threads() << ',' << round << ',' << position << ',' << name << ',' << chunk << ',' << elapsed << '\n';
            for (const ThreadWorkInfo& info : thread_info) {
                if (info.thread < 0) continue;
                thread_output << csv_escape(options.experiment) << ',' << BENCHMARK_SIMD_BUILD << ','
                              << csv_escape(options.image.filename().string()) << ',' << omp_get_max_threads() << ','
                              << round << ',' << position << ',' << name << ',' << chunk << ','
                              << info.thread << ',' << info.rows << ',' << info.work_ms << '\n';
            }
        }
    }
    return raw.good() && thread_output.good() ? 0 : 1;
}

int main(int argc, char** argv) {
    Options options;
    if (!parse_options(argc, argv, options)) {
        std::cerr << "Uso: diagnostic_runner --mode zoom|flip --image ARQUIVO --output CSV [--thread-output CSV] [--experiment NOME] [--touch fresh|pretouch-static] [--repeats N] [--seed N]\n";
        return 2;
    }
    ImageState source{};
    std::vector<unsigned char> original;
    if (!load_original(options.image, source, original)) {
        std::cerr << "Não foi possível carregar a imagem: " << options.image << '\n';
        return 1;
    }
    return options.mode == "zoom" ? run_zoom(options, source) : run_flip(options, source, original);
}
