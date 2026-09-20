#include "image_manipulation.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <system_error>
#include <vector>
#include <cstring>

#include <chrono>
#include <cerrno>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <omp.h> // Para ler o número de threads


namespace fs = std::filesystem;

// Parâmetros usados pelas transformações configuráveis.
#define BENCHMARK_BRIGHTNESS_ADJUSTMENT 127
#define BENCHMARK_CONTRAST_FACTOR 1.5f
#define BENCHMARK_QUANTIZATION_LEVELS 16
#define BENCHMARK_ZOOM_OUT_WIDTH 2
#define BENCHMARK_ZOOM_OUT_HEIGHT 2
#define BENCHMARK_CONVOLUTION_CLAMP_OFFSET false
#define BENCHMARK_CONVOLUTION_SINGLE_CHANNEL false

using Transformation = bool (*)(ImageState&);

bool transform_grayscale(ImageState& image) {
    apply_gray_scale_inplace(image);
    return true;
}

bool transform_flip_horizontal(ImageState& image) {
    flip_horizontal(image);
    return true;
}

bool transform_adjust_brightness(ImageState& image) {
    adjust_brightness(image, BENCHMARK_BRIGHTNESS_ADJUSTMENT);
    return true;
}

bool transform_flip_vertical(ImageState& image) {
    flip_vertical(image);
    return true;
}

bool transform_quantize(ImageState& image) {
    quantize_gray(image, BENCHMARK_QUANTIZATION_LEVELS);
    return true;
}

bool transform_adjust_contrast(ImageState& image) {
    adjust_contrast(image, BENCHMARK_CONTRAST_FACTOR);
    return true;
}

bool transform_negative(ImageState& image) {
    apply_negative(image);
    return true;
}

bool transform_equalize_histogram(ImageState& image) {
    unsigned int cumulative_histogram[256];
    equalize_histogram(image, cumulative_histogram);
    return true;
}

bool transform_zoom_in(ImageState& image) {
    return zoom_in_image(image);
}

bool transform_zoom_out(ImageState& image) {
    Rectangle rectangle{
        0,
        0,
        BENCHMARK_ZOOM_OUT_WIDTH,
        BENCHMARK_ZOOM_OUT_HEIGHT
    };
    zoom_out_image(image, rectangle);
    return true;
}

bool transform_rotate_clockwise(ImageState& image) {
    rotate_90_degrees_clockwise(image);
    return true;
}

bool transform_rotate_counterclockwise(ImageState& image) {
    rotate_90_degrees_counterclockwise(image);
    return true;
}

bool transform_gaussian_convolution_3x3(ImageState& image) {
    return apply_3_by_3_convolution(
        image,
        GAUSSIAN_KERNEL_3X3,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_5x5(ImageState& image) {
    return apply_5_by_5_convolution(
        image,
        GAUSSIAN_KERNEL_5X5,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_7x7(ImageState& image) {
    return apply_7_by_7_convolution(
        image,
        GAUSSIAN_KERNEL_7X7,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_9x9(ImageState& image) {
    return apply_9_by_9_convolution(
        image,
        GAUSSIAN_KERNEL_9X9,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_gaussian_convolution_11x11(ImageState& image) {
    return apply_11_by_11_convolution(
        image,
        GAUSSIAN_KERNEL_11X11,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
}

bool transform_varying_window_gaussian_denoising(ImageState& image) {
    return apply_varying_window_gaussian_denoising(image);
}

// Nomes que podem ser usados para montar a lista abaixo.
#define TRANSFORM_GRAYSCALE transform_grayscale
#define TRANSFORM_FLIP_HORIZONTAL transform_flip_horizontal
#define TRANSFORM_ADJUST_BRIGHTNESS transform_adjust_brightness
#define TRANSFORM_FLIP_VERTICAL transform_flip_vertical
#define TRANSFORM_QUANTIZE transform_quantize
#define TRANSFORM_ADJUST_CONTRAST transform_adjust_contrast
#define TRANSFORM_NEGATIVE transform_negative
#define TRANSFORM_EQUALIZE_HISTOGRAM transform_equalize_histogram
#define TRANSFORM_ZOOM_IN transform_zoom_in
#define TRANSFORM_ZOOM_OUT transform_zoom_out
#define TRANSFORM_ROTATE_CLOCKWISE transform_rotate_clockwise
#define TRANSFORM_ROTATE_COUNTERCLOCKWISE transform_rotate_counterclockwise
#define TRANSFORM_GAUSSIAN_CONVOLUTION_3X3 transform_gaussian_convolution_3x3
#define TRANSFORM_GAUSSIAN_CONVOLUTION_5X5 transform_gaussian_convolution_5x5
#define TRANSFORM_GAUSSIAN_CONVOLUTION_7X7 transform_gaussian_convolution_7x7
#define TRANSFORM_GAUSSIAN_CONVOLUTION_9X9 transform_gaussian_convolution_9x9
#define TRANSFORM_GAUSSIAN_CONVOLUTION_11X11 transform_gaussian_convolution_11x11
#define TRANSFORM_VARYING_WINDOW_GAUSSIAN_DENOISING transform_varying_window_gaussian_denoising

// Edite esta lista para mudar quais transformações são executadas e a ordem.
static constexpr Transformation TRANSFORMATIONS[] = {
    TRANSFORM_GRAYSCALE,
    TRANSFORM_FLIP_HORIZONTAL,
    TRANSFORM_ADJUST_BRIGHTNESS,
    TRANSFORM_FLIP_VERTICAL,
    TRANSFORM_QUANTIZE,
    TRANSFORM_ADJUST_CONTRAST,
    TRANSFORM_NEGATIVE,
    TRANSFORM_EQUALIZE_HISTOGRAM,
    TRANSFORM_ZOOM_IN,
    TRANSFORM_ZOOM_OUT,
    TRANSFORM_ROTATE_CLOCKWISE,
    TRANSFORM_ROTATE_COUNTERCLOCKWISE,
    TRANSFORM_GAUSSIAN_CONVOLUTION_3X3,
    TRANSFORM_GAUSSIAN_CONVOLUTION_5X5,
    TRANSFORM_GAUSSIAN_CONVOLUTION_7X7,
    TRANSFORM_GAUSSIAN_CONVOLUTION_9X9,
    TRANSFORM_GAUSSIAN_CONVOLUTION_11X11,
    TRANSFORM_VARYING_WINDOW_GAUSSIAN_DENOISING,
};

// Array paralelo com os nomes para salvar no CSV
static const char* TRANSFORMATION_NAMES[] = {
    "Grayscale", "Flip_Horizontal", "Adjust_Brightness", "Flip_Vertical",
    "Quantize", "Adjust_Contrast", "Negative", "Equalize_Histogram",
    "Zoom_In", "Zoom_Out", "Rotate_CW", "Rotate_CCW",
    "Gaussian_3x3", "Gaussian_5x5", "Gaussian_7x7", "Gaussian_9x9", "Gaussian_11x11",
#ifdef BENCHMARK_ALL_SCHEDULES
    "Adaptive_Gaussian"
#else
    "Adaptive_Median"
#endif
};

bool has_supported_extension(const fs::path& path) {
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(),
        [](unsigned char character) {
            return static_cast<char>(std::tolower(character));
        });

    static const std::vector<std::string> supported_extensions = {
        ".jpg", ".jpeg", ".png", ".bmp", ".tga", ".gif",
        ".psd", ".hdr", ".pic", ".pnm", ".ppm", ".pgm"
    };

    return std::find(
        supported_extensions.begin(),
        supported_extensions.end(),
        extension
    ) != supported_extensions.end();
}

#ifdef BENCHMARK_ALL_SCHEDULES

static std::string csv_field(const std::string& value) {
    if (value.find_first_of(",\"\r\n") == std::string::npos) return value;
    std::string escaped = "\"";
    for (char character : value) {
        if (character == '"') escaped += '"';
        escaped += character;
    }
    return escaped + '"';
}

static std::string schedule_name_from_environment() {
    const char* value = std::getenv("OMP_SCHEDULE");
    if (!value) return {};
    std::string schedule(value);
    if (schedule == "static") return schedule;
    if (schedule.rfind("dynamic,", 0) != 0) return {};
    const std::string chunk = schedule.substr(std::strlen("dynamic,"));
    if (chunk.empty() || chunk[0] == '0' ||
        !std::all_of(chunk.begin(), chunk.end(), [](unsigned char digit) { return std::isdigit(digit); })) {
        return {};
    }
    return "dynamic_" + chunk;
}

static bool reset_for_schedule_benchmark(ImageState& image, const unsigned char* original_data,
                                         int width, int height, size_t data_size) {
    free(image.data);
    image.data = static_cast<unsigned char*>(malloc(data_size));
    if (!image.data) return false;
    memcpy(image.data, original_data, data_size);
    image.width = width;
    image.height = height;
    image.isGrayScale = false;
    return true;
}

static bool process_schedule_image(const fs::path& path, std::ofstream& csv_file,
                                   int repetition, const std::string& schedule_name) {
    ImageState image{};
    const std::string filename = path.string();
    if (!load_image(filename.c_str(), image)) {
        fprintf(stderr, "Erro ao carregar a imagem: %s\n", filename.c_str());
        return false;
    }

    const int original_width = image.width;
    const int original_height = image.height;
    const size_t data_size = static_cast<size_t>(original_width) * original_height * 3;
    unsigned char* original_data = static_cast<unsigned char*>(malloc(data_size));
    if (!original_data) {
        fprintf(stderr, "Erro ao alocar backup da imagem: %s\n", filename.c_str());
        free(image.data);
        return false;
    }
    memcpy(original_data, image.data, data_size);

    bool succeeded = true;
    for (size_t i = 0; i < std::size(TRANSFORMATIONS); ++i) {
        if (!reset_for_schedule_benchmark(image, original_data, original_width, original_height, data_size)) {
            fprintf(stderr, "Erro ao restaurar a imagem: %s\n", filename.c_str());
            succeeded = false;
            break;
        }

        const auto start = std::chrono::steady_clock::now();
        const bool transformed = TRANSFORMATIONS[i](image);
        const auto end = std::chrono::steady_clock::now();
        if (!transformed) {
            fprintf(stderr, "Erro na transformacao %s: %s\n", TRANSFORMATION_NAMES[i], filename.c_str());
            succeeded = false;
            break;
        }

        const double elapsed_ms = std::chrono::duration<double, std::milli>(end - start).count();
        csv_file << repetition << ',' << csv_field(path.filename().string()) << ','
                 << omp_get_max_threads() << ',' << schedule_name << ','
                 << TRANSFORMATION_NAMES[i] << ',' << std::setprecision(12) << elapsed_ms << '\n';
        if (!csv_file) {
            fprintf(stderr, "Erro ao escrever CSV: %s\n", filename.c_str());
            succeeded = false;
            break;
        }
    }

    free(image.data);
    free(original_data);
    return succeeded;
}

static int process_schedule_folder(const fs::path& folder, std::ofstream& csv_file,
                                   int repetition, const std::string& schedule_name) {
    std::error_code error;
    if (!fs::is_directory(folder, error)) {
        fprintf(stderr, "Erro: pasta nao encontrada: %s\n", folder.string().c_str());
        return 1;
    }

    std::vector<fs::path> images;
    fs::directory_iterator iterator(folder, error);
    const fs::directory_iterator end;
    while (!error && iterator != end) {
        const fs::directory_entry& entry = *iterator;
        std::error_code entry_error;
        if (entry.is_regular_file(entry_error) && !entry_error && has_supported_extension(entry.path())) {
            images.push_back(entry.path());
        }
        iterator.increment(error);
    }
    if (error || images.empty()) {
        fprintf(stderr, "Erro ao listar imagens em: %s\n", folder.string().c_str());
        return 1;
    }

    std::sort(images.begin(), images.end());
    for (const fs::path& image : images) {
        if (!process_schedule_image(image, csv_file, repetition, schedule_name)) return 1;
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc != 5 || std::string(argv[1]) != "--folder") {
        fprintf(stderr, "Uso: %s --folder PASTA ARQUIVO_CSV REPETICAO\n", argv[0]);
        return 2;
    }

    const std::string schedule_name = schedule_name_from_environment();
    if (schedule_name.empty()) {
        fprintf(stderr, "Erro: OMP_SCHEDULE deve ser static ou dynamic,N (N > 0).\n");
        return 2;
    }

    errno = 0;
    char* end = nullptr;
    const long parsed_repetition = std::strtol(argv[4], &end, 10);
    if (errno != 0 || end == argv[4] || *end != '\0' ||
        parsed_repetition <= 0 || parsed_repetition > std::numeric_limits<int>::max()) {
        fprintf(stderr, "Erro: repeticao invalida: %s\n", argv[4]);
        return 2;
    }

    const fs::path csv_path = argv[3];
    std::error_code error;
    const bool needs_header = !fs::exists(csv_path, error) || fs::file_size(csv_path, error) == 0;
    if (error) {
        fprintf(stderr, "Erro ao verificar CSV: %s\n", csv_path.string().c_str());
        return 1;
    }
    std::ofstream csv_file(csv_path, std::ios::app);
    if (!csv_file) {
        fprintf(stderr, "Erro ao abrir CSV: %s\n", csv_path.string().c_str());
        return 1;
    }
    if (needs_header) {
        csv_file << "Repetition,Image,Num_Threads,OMP_Schedule,Transformation,Time_ms\n";
    }
    const int status = process_schedule_folder(argv[2], csv_file,
                                               static_cast<int>(parsed_repetition), schedule_name);
    csv_file.close();
    return !csv_file && status == 0 ? 1 : status;
}

#else

bool process_image(const fs::path& path, std::ofstream& csv_file) {
    ImageState image{};
    const std::string filename = path.string();

    if (!load_image(filename.c_str(), image)) {
        fprintf(stderr, "Erro ao carregar a imagem: %s\n", filename.c_str());
        return false;
    }

    // BACKUP DA IMAGEM ORIGINAL
    // =================================================================
    int original_width = image.width;
    int original_height = image.height;
    size_t data_size = static_cast<size_t>(original_width) * original_height * 3;
    
    unsigned char* original_data = (unsigned char*)malloc(data_size);
    if (!original_data) {
        fprintf(stderr, "Erro ao alocar memória para o backup da imagem!\n");
        free(image.data);
        free(original_data);
        return false;
    }
    memcpy(original_data, image.data, data_size);
    // =================================================================

    // Pega o número máximo de threads que o OpenMP está autorizado a usar
    int num_threads = omp_get_max_threads();
    
    // Tenta ler a variável de ambiente OMP_SCHEDULE injetada pelo Bash
    const char* env_schedule = std::getenv("OMP_SCHEDULE");
    std::string schedule_info = env_schedule ? env_schedule : "Padrao";
    
    // Escreve a identificação no CSV (agora com a terceira coluna)
    csv_file << path.filename().string() << "," << num_threads << "," << schedule_info;
    
    // Atualiza o print do terminal para você acompanhar visualmente
    printf("Imagem: %-25s | Threads: %2d | Schedule: %s\n", 
           path.filename().string().c_str(), num_threads, schedule_info.c_str());

    // Lê a chave para saber se devemos pular os estáticos
    const char* env_only_adaptive = std::getenv("ONLY_ADAPTIVE");
    bool only_adaptive = env_only_adaptive && std::string(env_only_adaptive) == "1";

    double total_time_ms = 0.0;

    for (size_t i = 0; i < std::size(TRANSFORMATIONS); ++i) {
        double ms_count = 0.0;

        if (only_adaptive && TRANSFORMATIONS[i] != transform_varying_window_gaussian_denoising) {
            // Pula a operação, mantendo o tempo em 0.0 para não quebrar o CSV
        } else {

            reset(image, original_data, original_width, original_height);

            auto start = std::chrono::high_resolution_clock::now();
            
            if (!TRANSFORMATIONS[i](image)) {
                fprintf(stderr, "Erro ao processar a imagem: %s\n", filename.c_str());
                free(image.data);
                return false;
            }

            auto end = std::chrono::high_resolution_clock::now();
            ms_count = std::chrono::duration<double, std::milli>(end - start).count();
        }
        
        // Salva o tempo (real ou 0.0) no CSV
        csv_file << "," << ms_count;
        total_time_ms += ms_count;
    }

    // Salva o tempo total na última coluna e pula linha
    csv_file << "," << total_time_ms << "\n";
    printf(" -> Tempo total: %.2f ms\n", total_time_ms);

    free(image.data);
    return true;
}


int process_folder(const fs::path& folder, std::ofstream& csv_file) {
    std::error_code error;
    if (!fs::is_directory(folder, error)) {
        fprintf(stderr, "Erro: pasta não encontrada: %s\n", folder.string().c_str());
        return 1;
    }

    std::vector<fs::path> images;
    fs::directory_iterator iterator(folder, error);
    fs::directory_iterator end;

    while (!error && iterator != end) {
        const fs::directory_entry& entry = *iterator;
        std::error_code entry_error;
        if (entry.is_regular_file(entry_error) && !entry_error && has_supported_extension(entry.path())) {
            images.push_back(entry.path());
        }
        iterator.increment(error);
    }

    if (error) {
        fprintf(stderr, "Erro ao percorrer a pasta: %s\n", folder.string().c_str());
        return 1;
    }

    std::sort(images.begin(), images.end());

    if (images.empty()) {
        fprintf(stderr, "Erro: nenhuma imagem suportada encontrada em: %s\n", folder.string().c_str());
        return 1;
    }

    bool all_succeeded = true;
    for (const fs::path& image : images) {
        // Agora passamos o csv_file corretamente para a process_image!
        if (!process_image(image, csv_file)) {
            all_succeeded = false;
        }
    }

    return all_succeeded ? 0 : 1;
}

void print_usage(const char* executable) {
    fprintf(stderr, "Uso: %s --image CAMINHO [ARQUIVO_CSV] | --folder CAMINHO [ARQUIVO_CSV]\n", executable);
}

int main(int argc, char** argv) {
    // Agora aceita 3 ou 4 argumentos (nome_programa, mode, path, [csv_filename])
    if (argc < 3 || argc > 4) {
        print_usage(argv[0]);
        return 2;
    }

    const std::string mode = argv[1];
    const fs::path path = argv[2];
    
    // Se o usuário passou o nome do CSV, usa ele. Senão, usa o padrão.
    const char* csv_filename = (argc == 4) ? argv[3] : "resultados_benchmark.csv";

    // Prepara o arquivo CSV
    bool file_exists = fs::exists(csv_filename);
    
    // Abre em modo append para não apagar execuções anteriores
    std::ofstream csv_file(csv_filename, std::ios::app);
    
    if (!csv_file.is_open()) {
        fprintf(stderr, "Erro ao criar o arquivo CSV: %s\n", csv_filename);
        return 1;
    }

    // Se o arquivo acabou de ser criado, escrevemos o cabeçalho
    if (!file_exists) {
        // ADICIONE A COLUNA AQUI:
        csv_file << "Image,Num_Threads,OMP_Schedule";
        
        for (const char* name : TRANSFORMATION_NAMES) {
            csv_file << "," << name;
        }
        csv_file << ",Total_Time_ms\n";
    }

    int status = 2;
    if (mode == "--image") {
        status = process_image(path, csv_file) ? 0 : 1;
    } else if (mode == "--folder") {
        status = process_folder(path, csv_file);
    } else {
        print_usage(argv[0]);
    }

    csv_file.close();
    return status;
}
#endif
