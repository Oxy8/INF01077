#include "image_manipulation.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <system_error>
#include <vector>

namespace fs = std::filesystem;

// Parâmetros usados pelas transformações configuráveis.
#define BENCHMARK_BRIGHTNESS_ADJUSTMENT 127
#define BENCHMARK_CONTRAST_FACTOR 1.5f
#define BENCHMARK_QUANTIZATION_LEVELS 16
#define BENCHMARK_ZOOM_OUT_WIDTH 2
#define BENCHMARK_ZOOM_OUT_HEIGHT 2
#define BENCHMARK_CONVOLUTION_KERNEL \
    {{0.0625f, 0.125f, 0.0625f}, \
     {0.125f,  0.25f,  0.125f},  \
     {0.0625f, 0.125f, 0.0625f}}
#define BENCHMARK_CONVOLUTION_CLAMP_OFFSET false
#define BENCHMARK_CONVOLUTION_SINGLE_CHANNEL false

using Transformation = void (*)(ImageState&);

void transform_grayscale(ImageState& image) {
    apply_gray_scale_inplace(image);
}

void transform_flip_horizontal(ImageState& image) {
    flip_horizontal(image);
}

void transform_adjust_brightness(ImageState& image) {
    adjust_brightness(image, BENCHMARK_BRIGHTNESS_ADJUSTMENT);
}

void transform_flip_vertical(ImageState& image) {
    flip_vertical(image);
}

void transform_quantize(ImageState& image) {
    quantize_gray(image, BENCHMARK_QUANTIZATION_LEVELS);
}

void transform_adjust_contrast(ImageState& image) {
    adjust_contrast(image, BENCHMARK_CONTRAST_FACTOR);
}

void transform_negative(ImageState& image) {
    apply_negative(image);
}

void transform_equalize_histogram(ImageState& image) {
    unsigned int cumulative_histogram[256];
    equalize_histogram(image, cumulative_histogram);
}

void transform_zoom_in(ImageState& image) {
    zoom_in_image(image);
}

void transform_zoom_out(ImageState& image) {
    Rectangle rectangle{
        0,
        0,
        BENCHMARK_ZOOM_OUT_WIDTH,
        BENCHMARK_ZOOM_OUT_HEIGHT
    };
    zoom_out_image(image, rectangle);
}

void transform_rotate_clockwise(ImageState& image) {
    rotate_90_degrees_clockwise(image);
}

void transform_rotate_counterclockwise(ImageState& image) {
    rotate_90_degrees_counterclockwise(image);
}

void transform_convolution(ImageState& image) {
    float kernel[3][3] = BENCHMARK_CONVOLUTION_KERNEL;
    apply_3_by_3_convolution(
        image,
        kernel,
        BENCHMARK_CONVOLUTION_CLAMP_OFFSET,
        BENCHMARK_CONVOLUTION_SINGLE_CHANNEL
    );
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
#define TRANSFORM_CONVOLUTION transform_convolution

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
    TRANSFORM_CONVOLUTION,
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

bool process_image(const fs::path& path) {
    ImageState image{};
    const std::string filename = path.string();

    if (!load_image(filename.c_str(), image)) {
        fprintf(stderr, "Erro ao carregar a imagem: %s\n", filename.c_str());
        return false;
    }

    for (Transformation transformation : TRANSFORMATIONS) {
        transformation(image);
    }

    free(image.data);
    return true;
}

int process_folder(const fs::path& folder) {
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
        if (!process_image(image)) {
            all_succeeded = false;
        }
    }

    return all_succeeded ? 0 : 1;
}

void print_usage(const char* executable) {
    fprintf(stderr, "Uso: %s --image CAMINHO | --folder CAMINHO\n", executable);
}

int main(int argc, char** argv) {
    if (argc != 3) {
        print_usage(argv[0]);
        return 2;
    }

    const std::string mode = argv[1];
    const fs::path path = argv[2];

    if (mode == "--image") {
        return process_image(path) ? 0 : 1;
    }

    if (mode == "--folder") {
        return process_folder(path);
    }

    print_usage(argv[0]);
    return 2;
}
